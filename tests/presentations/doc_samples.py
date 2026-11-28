"""Small real files for the reader tests: built in memory, nothing is stored in the repo."""
 
from pathlib import Path
from types import SimpleNamespace
 
from docx import Document as WordDocument
from pypdf import PdfWriter
 
 
def make_pdf(path: Path, pages: list[str]) -> Path:
    """A valid PDF with one line of real text per page ('' makes a page with no text, like a scan)."""
    objects: list[bytes] = []
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode() if text else b""
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path
 
 
def make_blank_pdf(path: Path, pages: int = 2) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)
    return path
 
 
def make_docx(path: Path) -> Path:
    """Two headings, paragraphs and one table (with a header row)."""
    word = WordDocument()
    word.add_heading("Sales review", level=1)
    word.add_paragraph("Revenue grew in the second quarter.")
    word.add_heading("Regions", level=2)
    word.add_paragraph("North was the strongest region.")
    table = word.add_table(rows=3, cols=2)
    for row, (region, revenue) in enumerate([("Region", "Revenue"), ("North", "200000"), ("South", "155000")]):
        table.cell(row, 0).text = region
        table.cell(row, 1).text = revenue
    word.save(str(path))
    return path
 
 
def fake_document(doc_id: int, path: Path | str, file_type: str, filename: str | None = None, sha256: str | None = None):
    """What the readers need from a Document row, without a database. Pair it with the use_files fixture."""
    return SimpleNamespace(
        id=doc_id, filename=filename or Path(path).name, file_type=file_type, sha256=sha256, file_path=str(path)
    )
