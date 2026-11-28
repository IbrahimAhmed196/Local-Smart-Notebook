"""Which facts may one slide cite (CTX-08). Stateless: it reads the context it is given and nothing else.
 
Order: facts that the outline named in source_hints first, then facts that share meaningful words with the slide.
A slide that matches nothing gets no sources. It is never given "the first facts" as a fallback.
"""
 
from __future__ import annotations
 
import math
import re
from collections.abc import Sequence
 
from app.presentations.context.schemas import ContextFact, PresentationContext
from app.presentations.context.textnorm import fold
from app.presentations.schemas.outline import SlideOutlineItem
from app.presentations.schemas.slide_content import SourceChunk
 
TOP_K = 5  # facts given to the slide writer for one slide
WORD = re.compile(r"\w{3,}", re.UNICODE)
_HINT_DOCUMENT = re.compile(r"^doc(\d+)(?::p(\d+))?$")
 
STOPWORDS = frozenset(
    """the and for are was were with this that these those from into over under about their there then than which what
    when where who how why will would can could should has have had not but its our your you they them his her she him
    all any each more most some such only also very per via slide slides presentation overview introduction summary
    في من على إلى عن مع هذا هذه ذلك تلك التي الذي الذين كان كانت يكون هو هي هم ثم أو أن إن كل بعد قبل بين حول عند""".split()
)
 
 
def words(text: str) -> set[str]:
    """Meaningful, lightly stemmed words: no stop words, no Arabic 'ال', no plural 's'."""
    found = set()
    for word in WORD.findall(fold(text)):
        if word in STOPWORDS:
            continue
        if word.startswith("ال") and len(word) > 4:
            word = word[2:]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 4:
            word = word[:-1]
        found.add(word)
    return found
 
 
def overview_chunks(context: PresentationContext) -> list[SourceChunk]:
    """What the outline step reads until OUT-05: every document's summary first, then the facts."""
    summaries = [
        SourceChunk(chunk_id=f"doc{d.document_id}-summary", document_id=d.document_id, filename=d.filename, text=d.summary)
        for d in context.documents
        if d.summary
    ]
    return summaries + [fact.as_chunk() for fact in context.facts]
 
 
def select_facts(context: PresentationContext, item: SlideOutlineItem, top_k: int = TOP_K) -> list[ContextFact]:
    facts = context.facts
    if not facts or (item.layout_type or "").strip().lower() == "title":
        return []
    chosen = _from_hints(facts, item.source_hints)[:top_k]
    if len(chosen) < top_k:
        taken = {fact.fact_id for fact in chosen}
        chosen += _rank(facts, item, taken)[: top_k - len(chosen)]
    return chosen
 
 
def _from_hints(facts: Sequence[ContextFact], hints: Sequence[str]) -> list[ContextFact]:
    """Hints are 'doc2-f3' (a fact), 'doc2' (a document) or 'doc2:p5' (a page). Unknown hints are ignored."""
    chosen: dict[str, ContextFact] = {}
    for hint in hints:
        hint = hint.strip().lower()
        document = _HINT_DOCUMENT.match(hint)
        for fact in facts:
            if fact.fact_id.lower() == hint:
                matched = True
            elif document:
                matched = fact.document_id == int(document.group(1)) and (
                    document.group(2) is None or fact.page == int(document.group(2))
                )
            else:
                matched = False
            if matched:
                chosen.setdefault(fact.fact_id, fact)
    return list(chosen.values())
 
 
def _rank(facts: Sequence[ContextFact], item: SlideOutlineItem, taken: set[str]) -> list[ContextFact]:
    query = words(" ".join([item.title, item.purpose, item.section or "", *item.key_points]))
    if not query:
        return []
    fact_words = [words(f"{fact.text} {fact.section or ''} {fact.evidence}") for fact in facts]
    count = len(facts)
    weight = {w: math.log(1 + count / sum(w in fw for fw in fact_words)) for w in query if any(w in fw for fw in fact_words)}
    scored = []
    for index, fact in enumerate(facts):
        if fact.fact_id in taken:
            continue
        score = sum(weight[w] for w in query & fact_words[index])
        if score > 0:
            scored.append((-score, index, fact))
    return [fact for _, _, fact in sorted(scored, key=lambda row: (row[0], row[1]))]
