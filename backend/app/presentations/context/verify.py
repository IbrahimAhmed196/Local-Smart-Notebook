"""Check every extracted fact against the document text before it can be cited (CTX-06).
 
A fact is kept only if its evidence quote really occurs in the document. Models invent quotes, move them to the
wrong page, or "tidy" them, so the check compares folded text (case, spacing, ligatures, Arabic marks and digits
do not matter) and repairs a wrong page number when the quote is found on another page.
"""
 
from __future__ import annotations
 
from collections.abc import Sequence
from dataclasses import dataclass
 
from app.presentations.context.readers import Block
from app.presentations.context.schemas import ContextFact
from app.presentations.context.textnorm import compact
 
MIN_EVIDENCE_CHARS = 8  # a shorter "quote" proves nothing; it would match almost anywhere
 
 
@dataclass
class VerifyResult:
    kept: list[ContextFact]
    dropped: list[ContextFact]
    pages_fixed: int = 0
 
 
def verify_facts(facts: Sequence[ContextFact], blocks: Sequence[Block]) -> VerifyResult:
    pages: dict[int, str] = {}
    for block in blocks:
        if block.page is not None:
            pages[block.page] = pages.get(block.page, "") + compact(block.text)
    whole = "".join(compact(block.text) for block in blocks)
 
    kept, dropped, fixed = [], [], 0
    for fact in facts:
        needle = compact(fact.evidence)
        if len(needle) < MIN_EVIDENCE_CHARS:
            dropped.append(fact)
        elif fact.page in pages and needle in pages[fact.page]:
            kept.append(fact)
        else:
            page = next((number for number, text in pages.items() if needle in text), None)
            if page is not None:  # right quote, wrong or missing page
                kept.append(fact.model_copy(update={"page": page}))
                fixed += 1
            elif needle in whole:  # the quote runs across a page break, or the document has no pages
                kept.append(fact)
            else:
                dropped.append(fact)
    return VerifyResult(kept=kept, dropped=dropped, pages_fixed=fixed)
