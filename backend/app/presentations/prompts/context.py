"""The prompt that turns ONE document into a summary and a list of cited facts (CTX-04)."""
 
from collections.abc import Sequence
 
from app.presentations.context.readers import Block
 
CONTEXT_PROMPT = """You prepare source material for a presentation. Read the DOCUMENT and extract what a presenter can use.
 
PRESENTATION TOPIC: {topic}
AUDIENCE: {audience}
DOCUMENT NAME: {filename}
 
RULES:
- "summary": 2 to 4 sentences about what the document is about.
- "facts": at most {max_facts} facts, the ones most useful for the topic first.
- A fact is ONE statement that the DOCUMENT itself makes (a number, a finding, a definition, a date, a decision).
  Do not add knowledge from outside the document. Do not guess. Keep each fact under 30 words.
- "evidence": a short quote (one sentence at most) COPIED EXACTLY from the DOCUMENT, character for character.
  Do not translate it, do not shorten it with "...", do not fix spelling.
- "page": the number in the nearest [Page N] marker above the evidence. null if the document has no page markers.
- "section": the nearest [Section: ...] heading above the evidence, or null.
- Write "summary" and each fact's "text" in the same language as the DOCUMENT.
- If the document has little to do with the topic, still return its most important facts.
 
DOCUMENT:
{document}
"""
 
 
def render_blocks(blocks: Sequence[Block]) -> str:
    """The document text with the markers that the prompt talks about."""
    parts = []
    for block in blocks:
        markers = []
        if block.page is not None:
            markers.append(f"[Page {block.page}]")
        if block.heading:
            markers.append(f"[Section: {block.heading}]")
        parts.append((" ".join(markers) + "\n" if markers else "") + block.text)
    return "\n\n".join(parts)
 
 
def build_context_prompt(*, topic: str, audience: str, filename: str, blocks: Sequence[Block], max_facts: int) -> str:
    return CONTEXT_PROMPT.format(
        topic=topic or "(not given)",
        audience=audience,
        filename=filename,
        max_facts=max_facts,
        document=render_blocks(blocks),
    )
