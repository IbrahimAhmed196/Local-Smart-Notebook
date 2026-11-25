
import json
import re
from pathlib import Path

from docling.datamodel.accelerator_options import (
    AcceleratorDevice,
    AcceleratorOptions
)
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode
)
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.chunking import HybridChunker

from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider
)
from docling_core.transforms.serializer.markdown import (
    MarkdownTableSerializer
)


# ==========================================
# 1. CONFIGURATION
# ==========================================

# Project root: Local-Smart-Notebook/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Data folders (outside backend)
DATA_DIR = PROJECT_ROOT / "data" / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 2. DOCUMENT EXTRACTION
# ==========================================

def extract_document(pdf_path):
    """
    Extract a PDF into a structured DoclingDocument
    using automatic CPU/GPU selection.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Document not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a PDF.")

    print("\nStarting document extraction...")

    # Configure PDF pipeline
    pipeline_options = PdfPipelineOptions()

    # Enable table structure recognition
    pipeline_options.do_table_structure = True

    # Use accurate table recognition
    pipeline_options.table_structure_options.mode = (
        TableFormerMode.ACCURATE
    )

    # Automatically select GPU if available, otherwise CPU
    pipeline_options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.AUTO
    )

    # Initialize Docling converter
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )

    # Convert PDF into a structured document
    result = converter.convert(str(pdf_path))

    doc = result.document

    print(f"Conversion status: {result.status}")
    print("Document extracted successfully.")

    return doc


# ==========================================
# 3. EXPORT DOCUMENT
# ==========================================

def export_document(doc, document_output_dir):
    """
    Export the complete document to Markdown and JSON.
    """

    document_output_dir = Path(document_output_dir)
    document_output_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = document_output_dir / "document.md"
    json_path = document_output_dir / "document.json"

    # Export complete document to Markdown
    markdown = doc.export_to_markdown()

    # Save Markdown
    markdown_path.write_text(
        markdown,
        encoding="utf-8"
    )

    # Save structured Docling document
    doc.save_as_json(json_path)

    print(f"Markdown saved: {markdown_path}")
    print(f"JSON saved: {json_path}")

    return markdown


# ==========================================
# 4. CUSTOM TABLE SERIALIZER
# ==========================================

class MDTableSerializerProvider(ChunkingSerializerProvider):
    """
    Use Markdown serialization instead of the default
    row-column triplet serialization for tables.
    """

    def get_serializer(self, doc):

        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer()
        )


# ==========================================
# 5. INITIALIZE CHUNKER
# ==========================================

def initialize_chunker():
    """
    Initialize HybridChunker with:
    - Default Docling tokenizer
    - Markdown table serialization
    - Repeated table headers
    - Peer merging
    """

    chunker = HybridChunker(
        serializer_provider=MDTableSerializerProvider(),
        merge_peers=True,
        repeat_table_header=True
    )

    print("HybridChunker initialized successfully.")
    print("Table serialization: Markdown")
    print("Table header repetition: Enabled")

    return chunker


# ==========================================
# 6. TABLE OF CONTENTS FILTER
# ==========================================

def is_toc_chunk(chunk):
    """
    Identify and exclude Table of Contents chunks.
    """

    headings = [
        str(heading).strip().lower()
        for heading in (chunk.meta.headings or [])
    ]

    raw_text = chunk.text.strip().lower()

    # Check exact heading names
    toc_headings = {
        "table of contents",
        "contents"
    }

    if any(heading in toc_headings for heading in headings):
        return True

    # Check the beginning of the chunk text
    if re.match(
        r"^(table of contents|contents)\s*($|\n|:)",
        raw_text
    ):
        return True

    return False


# ==========================================
# 7. MERGE SMALL CHUNKS
# ==========================================

def merge_chunk_data(first, second):
    """
    Combine two neighboring chunks while preserving metadata.
    Avoid duplicating heading context in contextualized text.
    """

    merged = first.copy()

    # Combine original chunk content
    merged["raw_text"] = (
        first["raw_text"] + "\n\n" + second["raw_text"]
    )

    # Rebuild contextualized text using the heading only once
    heading = "\n".join(first["headings"])

    merged["text"] = (
        (heading + "\n" if heading else "")
        + merged["raw_text"]
    )

    # Combine page numbers without duplicates
    merged["page_numbers"] = sorted(
        set(
            first["page_numbers"] +
            second["page_numbers"]
        )
    )

    # Combine captions without duplicates
    merged["captions"] = list(
        dict.fromkeys(
            first["captions"] + second["captions"]
        )
    )

    return merged


def is_slide_deck(chunks, max_words_per_page=120, min_pages=3, min_sparse_page_ratio=0.7):
    """
    Conservatively detect presentation-style PDFs.

    A document is treated as a slide deck only when it has several pages,
    its average extracted words per page is low, and most pages are sparse.
    This reduces the chance of applying slide merging to ordinary PDFs.
    """

    page_word_counts = {}

    for chunk in chunks:
        pages = chunk["page_numbers"]
        if not pages:
            continue

        # If a chunk spans multiple pages, distribute its words evenly.
        words_per_page = len(chunk["raw_text"].split()) / len(pages)
        for page in pages:
            page_word_counts[page] = (
                page_word_counts.get(page, 0) + words_per_page
            )

    if len(page_word_counts) < min_pages:
        return False

    average_words = sum(page_word_counts.values()) / len(page_word_counts)
    sparse_pages = sum(
        count <= max_words_per_page
        for count in page_word_counts.values()
    )
    sparse_page_ratio = sparse_pages / len(page_word_counts)

    return (
        average_words < max_words_per_page
        and sparse_page_ratio >= min_sparse_page_ratio
    )


def merge_slide_chunks(chunks):
    """
    Merge consecutive chunks belonging to the same single PDF page.

    The first chunk's heading path is retained as the slide title. Later
    chunk headings are added as labels in the raw text so slide sections
    such as PROBLEM and CORE IDEA remain attached to their content.
    """

    out = []

    for chunk in chunks:
        if (
            out
            and len(chunk["page_numbers"]) == 1
            and out[-1]["page_numbers"] == chunk["page_numbers"]
        ):
            previous = out[-1]
            label = chunk["headings"][-1] if chunk["headings"] else ""

            # Avoid repeating the same heading as a label.
            if label and label not in previous["headings"]:
                addition = f"{label}:\n{chunk['raw_text']}"
            else:
                addition = chunk["raw_text"]

            previous["raw_text"] = (
                previous["raw_text"].rstrip() + "\n\n" + addition.lstrip()
            )
            previous["captions"] = list(dict.fromkeys(
                previous["captions"] + chunk["captions"]
            ))

            heading = "\n".join(previous["headings"])
            previous["text"] = (
                (heading + "\n" if heading else "")
                + previous["raw_text"]
            )
        else:
            out.append(chunk.copy())

    return out


def merge_small_chunks(chunks, min_words=40):
    """
    Merge chunks containing fewer than min_words
    with an adjacent chunk from the same heading path.

    Chunks from different sections are never merged.
    """

    merged_chunks = []

    index = 0

    while index < len(chunks):

        current = chunks[index]

        current_word_count = len(
            current["raw_text"].split()
        )

        # Check whether the current chunk is too small
        if current_word_count < min_words:

            # Prefer merging with the next chunk
            if index + 1 < len(chunks):

                next_chunk = chunks[index + 1]

                same_heading = current["headings"] == next_chunk["headings"]
                same_slide = current.get("slide_number") == next_chunk.get("slide_number")

                # Also merge a short chapter introduction into its next
                # subsection when both belong to the same numbered chapter.
                chapter_intro_match = (
                    len(current["headings"]) == 1
                    and re.match(r"^(\d+)\.\s+", current["headings"][0])
                )
                next_subsection_match = (
                    next_chunk["headings"]
                    and re.match(r"^(\d+)\.(\d+)\s+", next_chunk["headings"][-1])
                )

                same_chapter = (
                    chapter_intro_match
                    and next_subsection_match
                    and chapter_intro_match.group(1) == next_subsection_match.group(1)
                )

                if same_slide and (same_heading or same_chapter):

                    combined = merge_chunk_data(
                        current,
                        next_chunk
                    )

                    # Use the more specific subsection breadcrumb for the
                    # combined intro + subsection content.
                    if same_chapter:
                        combined["headings"] = next_chunk["headings"]
                        heading = "\n".join(combined["headings"])
                        combined["text"] = (
                            (heading + "\n" if heading else "")
                            + combined["raw_text"]
                        )

                    merged_chunks.append(combined)

                    index += 2
                    continue

            # Otherwise, try merging with the previous chunk
            if (
                merged_chunks
                and merged_chunks[-1]["headings"] == current["headings"]
                and merged_chunks[-1].get("slide_number") == current.get("slide_number")
            ):

                merged_chunks[-1] = merge_chunk_data(
                    merged_chunks[-1],
                    current
                )

                index += 1
                continue

        # Keep the chunk unchanged if no valid merge is possible
        merged_chunks.append(current)

        index += 1

    return merged_chunks


# ==========================================
# 8. TABLE HEADER REPAIR + CAPTION METADATA
# ==========================================

def fix_orphaned_currency_header(text):
    """
    Repair the known Table 12.1 extraction issue when the word
    'Currency' appears as a standalone line after a Markdown table
    whose final header cell is empty.

    This changes the chunk text only. It does not modify Docling's
    original DoclingDocument or document.json export.
    """

    lines = text.splitlines()

    for index, line in enumerate(lines):
        if line.strip().lower() != "currency":
            continue

        # Search backward for the nearest Markdown table ending before
        # this standalone label. Stop if unrelated prose intervenes.
        table_header_index = None
        table_end_index = None

        for candidate in range(index - 1, 0, -1):
            current = lines[candidate].strip()
            previous = lines[candidate - 1].strip()

            if (
                current.startswith("|")
                and current.endswith("|")
                and previous.startswith("|")
                and previous.endswith("|")
            ):
                # Candidate is potentially the first data row; the
                # preceding line is likely the Markdown separator.
                separator_cells = [
                    cell.strip()
                    for cell in previous.strip("|").split("|")
                ]
                if separator_cells and all(
                    re.fullmatch(r":?-{3,}:?", cell)
                    for cell in separator_cells
                ):
                    table_header_index = candidate - 2
                    table_end_index = candidate
                    while (
                        table_end_index + 1 < index
                        and lines[table_end_index + 1].strip().startswith("|")
                        and lines[table_end_index + 1].strip().endswith("|")
                    ):
                        table_end_index += 1
                    break

            # Don't cross another standalone text line while looking
            # backward; this keeps the repair local to the nearest table.
            if current and not (current.startswith("|") and current.endswith("|")):
                if current.lower().startswith(("table ", "figure ")):
                    continue
                break

        if table_header_index is None or table_header_index < 0:
            continue

        header_line = lines[table_header_index].strip()
        if not (header_line.startswith("|") and header_line.endswith("|")):
            continue

        header_cells = [
            cell.strip()
            for cell in header_line.strip("|").split("|")
        ]

        # Only repair a blank final header cell; never overwrite a label.
        if header_cells and not header_cells[-1]:
            header_cells[-1] = "Currency"
            lines[table_header_index] = "| " + " | ".join(header_cells) + " |"
            del lines[index]
            return "\n".join(lines), True

    return text, False


def extract_caption_lines(text):
    """
    Extract explicit table/figure caption lines into metadata.
    The caption remains in raw_text as well, so no document content
    is removed or duplicated in the chunk body.
    """

    caption_pattern = re.compile(
        r"^\s*(?:Table|Figure)\s+\d+(?:\.\d+)*(?:\s*[:.]\s*|\s+).+?\s*$",
        re.IGNORECASE
    )

    captions = []

    for line in text.splitlines():
        cleaned = line.strip()
        if caption_pattern.match(cleaned) and cleaned not in captions:
            captions.append(cleaned)

    return captions


# ==========================================
# 9. HEADING HIERARCHY + TABLE STITCHING
# ==========================================

def build_heading_context(doc):
    """
    Scan all document headings before chunking.
    This remembers chapter titles even when they do not create a chunk.
    """

    current_chapters = {}
    heading_parents = {}

    for item in doc.texts:
        if not item.prov or item.label.value != "section_header":
            continue

        heading = item.text.strip()
        subsection_match = re.match(r"^(\d+)\.(\d+)(?:\.\d+)*\s+(.+)$", heading)
        chapter_match = re.match(r"^(\d+)\.?\s*(?=[A-Za-z])(.+)$", heading)

        if subsection_match:
            chapter_number = subsection_match.group(1)
            if chapter_number in current_chapters:
                heading_parents[heading.casefold()] = current_chapters[chapter_number]

        elif chapter_match:
            chapter_number = chapter_match.group(1)
            current_chapters[chapter_number] = heading

        elif heading and current_chapters:
            heading_parents[heading.casefold()] = list(current_chapters.values())[-1]

    return current_chapters, heading_parents


def update_heading_hierarchy(headings, current_chapters, heading_parents=None):
    """Rebuild heading breadcrumbs using numbered and pre-scanned headings."""

    rebuilt = []

    for heading in headings:
        heading = str(heading).strip()

        chapter_match = re.match(r"^(\d+)\.?\s*(?=[A-Za-z])(.+)$", heading)
        subsection_match = re.match(r"^(\d+)\.(\d+)(?:\.\d+)*\s*(.+)$", heading)

        if subsection_match:
            chapter_number = subsection_match.group(1)
            chapter_heading = current_chapters.get(chapter_number)

            if chapter_heading and chapter_heading not in rebuilt:
                rebuilt.append(chapter_heading)

            if heading not in rebuilt:
                rebuilt.append(heading)

        elif chapter_match:
            chapter_number = chapter_match.group(1)
            current_chapters[chapter_number] = heading

            if heading not in rebuilt:
                rebuilt.append(heading)

        else:
            parent = (heading_parents or {}).get(heading.casefold())
            if parent and parent not in rebuilt:
                rebuilt.append(parent)

            if heading and heading not in rebuilt:
                rebuilt.append(heading)

    return rebuilt


def repair_markdown_table_rows(text):
    """
    Join Markdown table rows that Docling split across physical lines.
    Only joins lines inside an unfinished pipe-delimited row.
    """

    lines = text.splitlines()
    output = []
    current = ""

    for line in lines:
        stripped = line.strip()

        if current:
            current += " " + stripped
            if stripped.endswith("|"):
                output.append(current)
                current = ""
            continue

        if stripped.startswith("|") and not stripped.endswith("|"):
            current = stripped
        else:
            output.append(line)

    if current:
        output.append(current)

    return "\n".join(output)


def markdown_table_column_count(text):
    """
    Return the column count if text contains a Markdown table,
    otherwise return None.
    """

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]

            # Ignore Markdown separator rows such as | --- | --- |
            if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue

            if cells:
                return len(cells)

    return None


def is_markdown_table_chunk(text):
    return markdown_table_column_count(text) is not None


def deduplicate_stitched_table_headers(text):
    """
    Remove repeated Markdown table headers inside a table assembled from
    multiple Docling chunks.

    If a later copy contains a value missing from an earlier header cell,
    the missing value is added to the one header we keep. For example,
    a later "Currency" cell fills the blank final cell in the first header.

    Data rows and non-table text are left unchanged.
    """

    lines = text.splitlines()
    output = []
    seen_headers = []
    index = 0

    def parse_header(line):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return None
        return [cell.strip() for cell in stripped.strip("|").split("|")]

    def is_separator(line):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return False
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        return bool(cells) and all(
            re.fullmatch(r":?-{3,}:?", cell) for cell in cells
        )

    while index < len(lines):
        # Do not compare headers from separate tables or distant sections.
        if not lines[index].strip().startswith("|"):
            seen_headers = []

        # A Markdown header is a pipe-delimited row immediately followed
        # by a Markdown separator row.
        if index + 1 < len(lines) and is_separator(lines[index + 1]):
            cells = parse_header(lines[index])

            if cells is not None:
                duplicate_of = None

                for previous in seen_headers:
                    previous_cells = previous["cells"]

                    if len(cells) != len(previous_cells):
                        continue

                    # Blank cells are treated as unknown. Non-empty labels
                    # must agree, and at least one label must match.
                    shared_labels = 0
                    compatible = True

                    for old_cell, new_cell in zip(previous_cells, cells):
                        if old_cell and new_cell:
                            if old_cell.casefold() != new_cell.casefold():
                                compatible = False
                                break
                            shared_labels += 1

                    if compatible and shared_labels > 0:
                        duplicate_of = previous
                        break

                if duplicate_of is not None:
                    # Fill missing cells in the first header from this copy.
                    for cell_index, cell in enumerate(cells):
                        if not duplicate_of["cells"][cell_index] and cell:
                            duplicate_of["cells"][cell_index] = cell

                    output[duplicate_of["output_index"]] = (
                        "| " + " | ".join(duplicate_of["cells"]) + " |"
                    )

                    # Skip the repeated header and its separator. Keep all
                    # following data rows and any surrounding caption text.
                    index += 2
                    continue

                seen_headers.append({
                    "cells": cells,
                    "output_index": len(output)
                })

                output.append(lines[index])
                output.append(lines[index + 1])
                index += 2
                continue

        output.append(lines[index])
        index += 1

    return "\n".join(output)


def merge_table_chunk_data(first, second):
    """
    Stitch consecutive Markdown table chunks when they have the same
    heading path and column count. This handles tables split into
    separate Docling table items across a page break.
    """

    merged = first.copy()
    merged["raw_text"] = first["raw_text"].rstrip() + "\n" + second["raw_text"].lstrip()
    merged["raw_text"] = deduplicate_stitched_table_headers(merged["raw_text"])

    heading = "\n".join(first["headings"])
    merged["text"] = (heading + "\n" if heading else "") + merged["raw_text"]

    merged["page_numbers"] = sorted(
        set(first["page_numbers"] + second["page_numbers"])
    )
    merged["captions"] = list(
        dict.fromkeys(first["captions"] + second["captions"])
    )

    return merged


def stitch_split_tables(chunks):
    """
    Merge adjacent table chunks with matching heading paths and
    matching Markdown column counts.

    This is deliberately conservative: it does not merge tables
    separated by prose or tables with different column counts.
    """

    stitched = []
    index = 0

    while index < len(chunks):
        current = chunks[index]

        while index + 1 < len(chunks):
            following = chunks[index + 1]

            # Keep a table caption with its table when Docling made
            # the caption a separate neighboring chunk.
            caption_before_table = (
                bool(current["captions"])
                and not is_markdown_table_chunk(current["raw_text"])
                and is_markdown_table_chunk(following["raw_text"])
                and current["headings"] == following["headings"]
                and bool(set(current["page_numbers"]) & set(following["page_numbers"]))
            )

            if caption_before_table:
                current = merge_table_chunk_data(current, following)
                index += 1
                continue

            current_columns = markdown_table_column_count(current["raw_text"])
            following_columns = markdown_table_column_count(following["raw_text"])

            if (
                current_columns is not None
                and current_columns == following_columns
                and current["headings"] == following["headings"]
            ):
                current = merge_table_chunk_data(current, following)
                index += 1
            else:
                break

        stitched.append(current)
        index += 1

    return stitched


def dedupe_table_headers(chunks):
    """Remove repeated Markdown table headers from each chunk."""

    for chunk in chunks:
        chunk["raw_text"] = deduplicate_stitched_table_headers(
            chunk["raw_text"]
        )
        heading = "\n".join(chunk["headings"])
        chunk["text"] = (
            (heading + "\n" if heading else "")
            + chunk["raw_text"]
        )

    return chunks


def merge_orphan_table_fragments(chunks):
    """Merge a table fragment that begins with an orphaned header row."""

    out = []

    for chunk in chunks:
        first = next(
            (line.strip() for line in chunk["raw_text"].splitlines() if line.strip()),
            ""
        )
        orphan = (
            first == "|"
            or bool(re.fullmatch(r"\|?[-| :]+\|?", first))
        )

        if (
            orphan
            and out
            and out[-1]["headings"] == chunk["headings"]
        ):
            out[-1] = merge_table_chunk_data(out[-1], chunk)
        else:
            out.append(chunk)

    return out


def table_is_garbage(text, max_empty=0.85):
    """Detect only severely corrupted table fragments; preserve sparse tables."""

    rows = [
        line for line in text.splitlines()
        if line.strip().startswith("|")
        and not re.fullmatch(r"\|?[-| :]+\|?", line.strip())
    ]
    cells = [
        cell.strip()
        for row in rows
        for cell in row.strip().strip("|").split("|")
    ]

    return (
        len(rows) >= 3
        and len(cells) >= 12
        and sum(not cell for cell in cells) / len(cells) > max_empty
    )


# ==========================================
# 9B. SLIDE DECK FIXES (NEW)
# ==========================================

def get_slide_info(doc):
    """
    Read simple facts about each PDF page from the DoclingDocument:
    - titles:   first heading on the page
    - kickers:  small label such as "MVC / MODEL" -> "MVC"
    - dividers: pages that only hold a section title (no body text)
    - footers:  footer text on each page (to remove it from chunks)
    - numbers:  the slide number printed in the footer
    """

    pages = {}
    for item in doc.texts:
        if item.prov:
            pages.setdefault(item.prov[0].page_no, []).append(item)

    titles, kickers, dividers, footers, numbers = {}, {}, {}, {}, {}

    for page, items in pages.items():
        body = [
            i for i in items
            if i.label.value not in ("page_footer", "page_header")
        ]
        headings = [i for i in body if i.label.value == "section_header"]

        if headings:
            titles[page] = headings[0].text.strip()

        # A page with only one heading and nothing else is a divider slide
        if len(body) == 1 and headings:
            dividers[page] = headings[0].text.strip()

        for i in items:
            if i.label.value == "page_header" and "/" in i.text:
                kickers[page] = i.text.split("/")[0].strip()

        footer_texts = [
            i.text.strip() for i in items
            if i.label.value == "page_footer"
        ]
        footers[page] = [t for t in footer_texts if not t.isdigit()]

        for text in footer_texts:
            match = re.search(r"(\d+)\s*$", text)
            if match:
                numbers[page] = int(match.group(1))

    # If a page has no printed number, continue from the page before it
    last_offset = 0
    for page in sorted(doc.pages.keys()):
        if page in numbers:
            last_offset = numbers[page] - page
        else:
            numbers[page] = page + last_offset

    return titles, kickers, dividers, footers, numbers


def get_diagram_text(doc, min_items=3):
    """
    Docling stores diagram labels inside picture items and HybridChunker
    skips them. Collect those labels for each page so we can add them back.
    """

    diagram_text = {}

    for picture in doc.pictures:
        labels = []
        for child in picture.children:
            item = child.resolve(doc)
            if not hasattr(item, "text") or not item.prov:
                continue
            if item.label.value in ("page_footer", "page_header"):
                continue
            if item.text.strip():
                labels.append((item.prov[0].page_no, item.text.strip()))

        if len(labels) < min_items:
            continue

        for page, text in labels:
            diagram_text.setdefault(page, []).append(text)

    return diagram_text


def add_slide_context(doc, chunks, document_id):
    """
    Slide deck repairs:
    1. Add diagram text back (new chunk if the slide has none).
    2. Remove footer text such as "CSE 336s - Software Design Patterns 28".
    3. Add the section name (for example MVC or Facade) to every chunk.
    4. Save the slide number printed on the slide.
    """

    titles, kickers, dividers, footers, numbers = get_slide_info(doc)
    diagram_text = get_diagram_text(doc)

    # Section of each page = the latest divider slide before it
    section_of_page = {}
    section = None
    for page in range(1, max(doc.pages.keys()) + 1):
        if page in dividers:
            section = dividers[page]
        section_of_page[page] = section

    # Footer texts seen anywhere in the document (e.g. the course name)
    all_footers = {
        text for texts in footers.values() for text in texts
    }

    first_page_chunks = {}
    for chunk in chunks:
        if chunk["page_numbers"]:
            first_page_chunks.setdefault(chunk["page_numbers"][0], chunk)

    for page, labels in sorted(diagram_text.items()):
        # dict.fromkeys removes repeated labels but keeps the order
        diagram = "Diagram text:\n" + "\n".join(dict.fromkeys(labels))

        if page in first_page_chunks:
            chunk = first_page_chunks[page]
            chunk["raw_text"] = chunk["raw_text"].rstrip() + "\n\n" + diagram
        else:
            chunk = {
                "chunk_id": "",
                "document_id": document_id,
                "chunk_index": -1,
                "text": "",
                "raw_text": diagram,
                "headings": [titles.get(page, f"Slide {page}")],
                "captions": [],
                "page_numbers": [page]
            }
            chunks.append(chunk)
            first_page_chunks[page] = chunk

    chunks.sort(key=lambda c: c["page_numbers"][0] if c["page_numbers"] else 0)

    for chunk in chunks:
        page = chunk["page_numbers"][0] if chunk["page_numbers"] else None

        # Remove footer text that got mixed into the chunk
        for footer in all_footers:
            chunk["raw_text"] = re.sub(
                re.escape(footer) + r"\s*\d*", "", chunk["raw_text"]
            ).strip()

        chunk["section"] = section_of_page.get(page)
        chunk["slide_number"] = numbers.get(page)

        prefix = f"[{chunk['section']}] " if chunk["section"] else ""
        heading = "\n".join(chunk["headings"])
        chunk["text"] = (
            prefix + (heading + "\n" if heading else "") + chunk["raw_text"]
        )

    return chunks


def check_chunks(doc, chunks, min_words=15):
    """
    Check coverage, chunk size, table structure and likely OCR damage.
    Warnings do not delete document content.
    """

    print("\n========== CHUNK QUALITY CHECK ==========")

    warnings = 0
    _, _, dividers, _, _ = get_slide_info(doc)

    covered = {page for chunk in chunks for page in chunk["page_numbers"]}
    missing = [
        page for page in doc.pages.keys()
        if page not in covered and page not in dividers
    ]
    if missing:
        warnings += 1
        print(f"WARNING: pages with no chunk: {sorted(missing)}")

    for chunk in chunks:
        words = chunk["raw_text"].split()
        word_count = len(words)

        if word_count < min_words:
            warnings += 1
            print(
                f"WARNING: chunk {chunk['chunk_index']} is very short "
                f"({word_count} words, pages {chunk['page_numbers']})"
            )

        if "```" in chunk["raw_text"] and re.search(
            r"\bCSE \d+", chunk["raw_text"]
        ):
            warnings += 1
            print(
                f"WARNING: chunk {chunk['chunk_index']} has footer text "
                f"inside a code block"
            )

        # Flag likely OCR errors without changing or deleting the text.
        long_words = [word for word in words if len(word) >= 18 and word.isalpha()]
        single_letters = sum(
            len(word) == 1 and word.isalpha() for word in words
        )
        if len(long_words) >= 2 or (
            len(words) >= 12 and single_letters / len(words) > 0.35
        ):
            warnings += 1
            print(
                f"WARNING: chunk {chunk['chunk_index']} may contain OCR errors "
                f"(pages {chunk['page_numbers']})"
            )

        # Report inconsistent table row widths; Docling may have lost cells.
        table_rows = [
            line.strip() for line in chunk["raw_text"].splitlines()
            if line.strip().startswith("|") and line.strip().endswith("|")
        ]
        column_counts = {
            len(line.strip("|").split("|")) for line in table_rows
            if not re.fullmatch(r"\|?[-| :]+\|?", line.strip())
        }
        if len(column_counts) > 1:
            warnings += 1
            print(
                f"WARNING: chunk {chunk['chunk_index']} has inconsistent "
                f"table columns {sorted(column_counts)} "
                f"(pages {chunk['page_numbers']})"
            )

    if warnings == 0:
        print("No warnings.")
    else:
        print(f"Total warnings: {warnings}")


# ==========================================
# 10. CHUNK DOCUMENT
# ==========================================

def chunk_document(doc, chunker, document_id):
    """
    Split a structured DoclingDocument into context-aware chunks.

    Processing:
    1. Generate chunks.
    2. Remove Table of Contents chunks.
    3. Pre-scan headings and rebuild heading breadcrumbs.
    4. Repair split table rows and the known orphaned Currency header.
    5. Extract page, heading and caption metadata.
    6. Stitch consecutive split tables.
    7. Detect slide decks and merge chunks from the same slide.
    8. Merge tiny chapter-intro chunks into the following subsection.
    9. (Slide decks) Add diagram text, section names and slide numbers.
    """

    print("\nStarting document chunking...")

    chunks = []
    current_chapters, heading_parents = build_heading_context(doc)

    # Generate all Docling chunks
    doc_chunks = list(chunker.chunk(doc))

    print(f"Chunks before filtering: {len(doc_chunks)}")

    # Remove Table of Contents and References chunks
    filtered_chunks = [
        chunk
        for chunk in doc_chunks
        if not is_toc_chunk(chunk)
        and not any(
            str(heading).strip().lower() in {"references", "bibliography"}
            for heading in (chunk.meta.headings or [])
        )
    ]

    removed_count = len(doc_chunks) - len(filtered_chunks)
    print(f"TOC/References chunks removed: {removed_count}")

    # Extract chunk information in document order
    for chunk in filtered_chunks:

        doc_items = chunk.meta.doc_items

        # Extract original PDF page numbers
        page_numbers = sorted({
            provenance.page_no
            for item in doc_items
            for provenance in item.prov
        })

        # Rebuild hierarchy from numbered headings
        headings = update_heading_hierarchy(
            list(chunk.meta.headings or []),
            current_chapters,
            heading_parents
        )

        # Repair table rows split by line breaks before table stitching.
        raw_text = repair_markdown_table_rows(chunk.text)

        # Repair the known orphaned Currency header in the chunk text.
        raw_text, currency_header_fixed = fix_orphaned_currency_header(raw_text)
        if currency_header_fixed:
            print("Repaired an orphaned 'Currency' table header.")

        # Combine Docling-detected captions with explicit caption lines
        # found in the chunk text. Caption text stays in raw_text too.
        captions = list(chunk.meta.captions or [])
        for caption in extract_caption_lines(raw_text):
            if caption not in captions:
                captions.append(caption)

        # Build contextualized text using the corrected heading path
        heading_context = "\n".join(headings)
        contextualized_text = (
            heading_context + "\n" if heading_context else ""
        ) + raw_text

        chunk_data = {
            "chunk_id": "",
            "document_id": document_id,
            "chunk_index": -1,
            "text": contextualized_text,
            "raw_text": raw_text,
            "headings": headings,
            "captions": captions,
            "page_numbers": page_numbers
        }

        chunks.append(chunk_data)

    print(f"Chunks after TOC filtering: {len(chunks)}")

    # Stitch table chunks split across page boundaries
    before_stitching = len(chunks)
    chunks = stitch_split_tables(chunks)

    print(f"Split table chunks stitched: {before_stitching - len(chunks)}")

    # Remove any repeated table headers remaining after stitching
    chunks = dedupe_table_headers(chunks)

    # Merge table fragments that begin with an orphaned header/separator
    before_orphan_merge = len(chunks)
    chunks = merge_orphan_table_fragments(chunks)
    print(f"Orphan table fragments merged: {before_orphan_merge - len(chunks)}")

    # Keep table content. Flag only severely damaged tables for review.
    suspect_tables = [
        chunk for chunk in chunks
        if table_is_garbage(chunk["raw_text"])
    ]
    print(
        f"Potentially damaged table chunks flagged (preserved): "
        f"{len(suspect_tables)}"
    )

    # Merge chunks from the same slide only when the document looks like
    # a presentation. This leaves ordinary research papers unchanged.
    if is_slide_deck(chunks):
        before_slide_merging = len(chunks)
        chunks = merge_slide_chunks(chunks)
        print(f"Slide chunks merged: {before_slide_merging - len(chunks)}")

        # Add diagram text, section names and slide numbers
        chunks = add_slide_context(doc, chunks, document_id)
        print("Slide context added: diagrams, sections, slide numbers")
    else:
        print("Slide-deck structure not detected; skipping slide merging.")

    # Merge small chunks
    before_merging = len(chunks)

    chunks = merge_small_chunks(
        chunks,
        min_words=40
    )

    print(f"Small chunks merged: {before_merging - len(chunks)}")

    # Reassign IDs and indexes after filtering and merging
    for index, chunk in enumerate(chunks):
        chunk["chunk_id"] = f"{document_id}_{index}"
        chunk["chunk_index"] = index

    print(f"Total final chunks: {len(chunks)}")

    return chunks


# ==========================================
# 11. SAVE CHUNKS
# ==========================================

def save_chunks(chunks, document_output_dir):
    """
    Save generated chunks in JSONL format.
    """

    chunks_path = Path(document_output_dir) / "chunks.jsonl"

    with open(chunks_path, "w", encoding="utf-8") as file:

        for chunk in chunks:

            file.write(
                json.dumps(chunk, ensure_ascii=False) + "\n"
            )

    print(f"Chunks saved: {chunks_path}")

    return chunks_path


# ==========================================
# 12. DISPLAY STATISTICS
# ==========================================

def display_statistics(doc, markdown, chunks, document_id):

    print("\n========== PIPELINE RESULTS ==========")

    print(f"Document: {document_id}")
    print(f"Pages: {len(doc.pages)}")
    print(f"Markdown characters: {len(markdown)}")
    print(f"Total chunks: {len(chunks)}")

    if chunks:

        word_counts = [
            len(chunk["raw_text"].split())
            for chunk in chunks
        ]

        print(f"Minimum words per chunk: {min(word_counts)}")
        print(f"Maximum words per chunk: {max(word_counts)}")
        print(
            f"Average words per chunk: "
            f"{sum(word_counts) / len(word_counts):.1f}"
        )

        print("\nFirst chunk preview:")
        print(chunks[0]["text"])

        print("\nFirst chunk metadata:")
        print("Headings:", chunks[0]["headings"])
        print("Pages:", chunks[0]["page_numbers"])

        # Display a table chunk for inspection
        table_chunks = [
            chunk for chunk in chunks
            if "|" in chunk["raw_text"]
        ]

        print(
            f"\nChunks containing Markdown tables: "
            f"{len(table_chunks)}"
        )

        if table_chunks:

            print("\nFirst table chunk preview:")
            print(table_chunks[0]["raw_text"][:1000])


# ==========================================
# 13. COMPLETE DOCUMENT PROCESSING PIPELINE
# ==========================================

def process_document(pdf_path):
    """
    Run the complete extraction and chunking pipeline.
    """

    pdf_path = Path(pdf_path)

    document_id = pdf_path.stem

    # Create a separate output directory for each document
    document_output_dir = OUTPUT_DIR / document_id

    document_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Step 1: Extract document
    doc = extract_document(pdf_path)

    # Step 2: Export Markdown and structured JSON
    markdown = export_document(
        doc,
        document_output_dir
    )

    # Step 3: Initialize chunker
    chunker = initialize_chunker()

    # Step 4: Generate and clean chunks
    chunks = chunk_document(
        doc,
        chunker,
        document_id
    )

    # Step 4B: Check chunk quality and print warnings
    check_chunks(doc, chunks)

    # Step 5: Save chunks
    save_chunks(
        chunks,
        document_output_dir
    )

    # Step 6: Display statistics
    display_statistics(
        doc,
        markdown,
        chunks,
        document_id
    )

    return doc, markdown, chunks


# ==========================================
# 14. EXECUTION
# ==========================================

if __name__ == "__main__":

    # Select the PDF to process
    pdf_path = DATA_DIR / "Local Smart Notebook project proposal (1).pdf"

    doc, markdown, chunks = process_document(pdf_path)
