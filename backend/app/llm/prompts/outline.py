"""Prompt used to generate presentation outlines."""

OUTLINE_PROMPT = """Create the outline of a presentation.
 
TOPIC: {topic}
NUMBER OF SLIDES: exactly {count}
AUDIENCE: {audience}
STYLE: {style}
 
RULES:
- slide_number goes from 1 to {count}. Slide 1 has layout_type "title".
- layout_type must be one of: {layouts}.
- Every slide has a short title and a one-sentence purpose that says what the slide must show.
- Follow a logical order: introduction, the main points, then a closing slide.
- Write in the same language as the DOCUMENT EXCERPTS.
- Preserve explicit user requirements in each relevant slide's purpose.
- For a requested chart, the purpose must specify its chart type, categories, measure, and aggregation.
- For a requested table, the purpose must specify the requested columns and record count.
- Use layout_type "chart" for charts; record bar, line, or pie in the purpose.
- Give each slide a distinct purpose. Avoid repeating the same findings across slides.
- Do not add a Q&A slide unless the user requests one.
- The requested outline count already excludes the separately rendered Sources slide. Do not create a Sources slide.
- Include exactly one concluding slide, as the last outline slide.
- Do not add separate Closing Remarks, Summary, Thank You, or Q&A slides that repeat the conclusion.
- Give every slide a distinct purpose.
{data_note}
DOCUMENT EXCERPTS:
{excerpts}
"""