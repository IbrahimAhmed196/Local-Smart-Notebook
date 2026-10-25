# Presentation generation

[Back to the README](../README.md)

Local Smart Notebook can turn documents and spreadsheet data from a notebook into an editable PowerPoint presentation. Users choose a topic, slide count, audience, writing style, and visual theme. The backend prepares the presentation in the background and makes the finished `.pptx` available for download.

## What is available now

- Generate a presentation from selected documents, or use all documents in a notebook.
- Choose a title, topic, audience, style, and requested slide count.
- Choose from the `classic`, `modern`, and `warm` themes, with automatic, left-to-right, or right-to-left direction.
- Create title, bullet, two-column, chart, and table slides, with a concluding slide and optional Sources slide.
- Include speaker notes and source references.
- Create native editable PowerPoint charts and tables. Charts currently include bar, line, and pie charts.
- Track generation status, list previous presentations, download files, and delete presentations.
- Edit the deck JSON and render the PowerPoint again without another AI call.

The most recent slide-count adjustment reserves a place for Sources when it is enabled. Long tables can still be split across multiple slides, so the final count may exceed the requested count.

## How generation works

1. **Choose the material.** Upload documents to a notebook and select the documents to use.
2. **Describe the presentation.** Set the topic and preferences, including any requested charts or tables.
3. **Plan the slides.** A local model running through Ollama proposes the order, purpose, and layout of each slide.
4. **Write the content.** The model produces slide text, speaker notes, and references. For charts and tables, it selects the spreadsheet, sheet, and columns to use.
5. **Read the real data and render.** Python calculates chart values and reads table cells from the spreadsheet, then produces an editable PowerPoint file.
6. **Review and download.** Check warnings and review both visible content and speaker notes before using the presentation.

The current model is Qwen2.5-7B-Instruct through Ollama. Generation time depends on the machine, slide count, and model workload.

## Documents and spreadsheet data

The presentation context adapter currently reads text from TXT, text-based PDF, and DOCX files. It selects relevant passages using word overlap with each slide's title and purpose. This is a temporary approach, not the planned full RAG integration. Scanned PDFs need text extraction through OCR before this adapter can use their contents.

CSV and XLSX files supply chart and table data. XLSX reading requires `openpyxl` in the backend environment. Files should have clear column headers and consistent data types.

Spreadsheet identifiers must match the actual file. Units belong in display titles or captions rather than being appended to source column names. Chart values and table cells come from the file, but the model's written interpretation still needs review.

## Using the API

The [README](../README.md#presentation-endpoints) lists all presentation endpoints. All require authentication and enforce notebook or presentation ownership. Paths below assume the default empty API prefix.

1. Upload your source files to a notebook.
2. Call `GET /presentations/options` to obtain available themes, layouts, directions, and slide limits.
3. Submit `POST /notebooks/{notebook_id}/presentations` with a request such as:

```json
{
  "topic": "Summarize the uploaded report and illustrate its main findings using the spreadsheet data.",
  "title": "Report Overview",
  "num_slides": 6,
  "audience": "Project team",
  "style": "Clear and concise",
  "theme": "classic",
  "direction": "auto",
  "include_sources_slide": true,
  "document_ids": [2, 3]
}
```

Replace the document IDs with IDs belonging to your notebook. Omit `document_ids`, or set it to `null`, to use all notebook documents.

4. The create request returns HTTP `202` and a presentation record. Use its `id` to poll `GET /presentations/{presentation_id}`. There is no separate public job ID.
5. Status progresses through `PENDING` and `RUNNING`, then `COMPLETED` or `FAILED`. The response also includes `stage`, `warnings`, `error`, and a `download_url` when complete.
6. If completed, review warnings and download from `GET /presentations/{presentation_id}/download`. If failed, inspect `error` and the backend logs.

`COMPLETED` means a file was produced; it does not guarantee every requested chart or table was included or every sentence is factually supported. Warnings can report omitted data, a fallback layout, or a placeholder slide.

### Editing a generated deck

Fetch `GET /presentations/{presentation_id}/deck`, edit the returned deck JSON, and send the complete updated object to `PUT /presentations/{presentation_id}/deck`. This replaces the stored deck and renders it again without calling the model. This endpoint is a full replacement, not a partial patch.

You can also edit the downloaded PowerPoint directly. Those local PowerPoint changes do not automatically update the backend's stored JSON.

## Current limitations

- Content retrieval uses extracted text and simple word matching rather than semantic or hybrid retrieval.
- Citation checks confirm that referenced source IDs exist. They do not prove that every claim is supported by the cited passage.
- Written explanations and speaker notes can contain unsupported interpretations even when chart and table values are correct.
- Rendering uses a fixed set of layouts and themes. Automatic picture selection and placement are not implemented.
- Background jobs run within the backend process. Keep the server running while generating; interrupted jobs are not automatically resumed. Avoid development reloads during generation.
- Long content, Arabic text, and larger tables need visual review for readability and layout quality.

## Potential future improvements

These are possible extensions, not currently available features.

| Improvement | Benefit |
|---|---|
| Full RAG integration | Reuse the notebook's retrieval pipeline to find more relevant evidence across larger document collections. |
| Pictures and document figures | Extract figures from uploaded documents or accept user-provided images, with captions, source attribution, and suitable placement. |
| Optional image generation | Create illustrations when appropriate, keeping generated visuals distinct from factual evidence. |
| Visual slide editor and previews | Let users review, reorder, and edit slides without editing JSON. |
| Notebook chat integration | Turn a conversation or selected answer into a presentation while preserving its sources. |
| Spreadsheet analysis integration | Reuse verified analyses and computed results from other notebook features for charts and explanations. |
| Stronger content checks | Check numerical claims and evaluate whether evidence supports statements in both slides and speaker notes. |
| Model choice | Compare local models for quality, speed, and hardware requirements. A stronger model can still make factual errors. |
| More layouts and templates | Add diagrams, comparisons, branded templates, and more chart types. |
| More resilient jobs | Add a persistent queue, cancellation, and controlled retries for interrupted work. |
| Broader evaluation | Measure schema-valid rate, slide-count accuracy, citation faithfulness, generation time, and visual quality across different topics and languages. |
