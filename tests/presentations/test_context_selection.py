"""CTX-08: each slide gets only the facts that belong to it, never 'the first facts' as a fallback."""
 
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.schemas import ContextFact, DocumentContext, PresentationContext
from app.presentations.context.selection import TOP_K, overview_chunks, select_facts, words
from app.presentations.schemas.outline import SlideOutlineItem
from tests.fake_llm import ScriptedLLMClient
 
 
def make_fact(document_id, number, text, page=None, section=None):
    return ContextFact(
        fact_id=f"doc{document_id}-f{number}", text=text, document_id=document_id,
        filename=f"d{document_id}.txt", page=page, section=section, evidence=text,
    )
 
 
def make_context(*facts, summaries=None):
    documents = {}
    for f in facts:
        documents.setdefault(f.document_id, DocumentContext(document_id=f.document_id, filename=f.filename)).facts.append(f)
    for document_id, summary in (summaries or {}).items():
        documents[document_id].summary = summary
    return PresentationContext(topic="t", documents=list(documents.values()))
 
 
def slide(title, purpose="", layout="bullet_points", **extra):
    return SlideOutlineItem(slide_number=2, title=title, purpose=purpose, layout_type=layout, **extra)
 
 
REVENUE = make_fact(1, 1, "Revenue grew by 12 percent in the second quarter.")
COSTS = make_fact(1, 2, "Operating costs fell after the warehouse moved.")
STAFF = make_fact(2, 1, "The team hired nine engineers during the year.", page=4, section="People")
CONTEXT = make_context(REVENUE, COSTS, STAFF)
 
 
def ids(facts):
    return [f.fact_id for f in facts]
 
 
def test_a_slide_gets_the_facts_that_share_its_words():
    assert ids(select_facts(CONTEXT, slide("Revenue growth", "Show how revenue changed"))) == ["doc1-f1"]
    assert ids(select_facts(CONTEXT, slide("Hiring", "How many engineers joined"))) == ["doc2-f1"]
 
 
def test_a_slide_that_matches_nothing_gets_no_sources_and_no_fallback():
    assert select_facts(CONTEXT, slide("Weather forecast", "Rain expected tomorrow")) == []
 
 
def test_the_title_slide_gets_no_sources():
    assert select_facts(CONTEXT, slide("Revenue", "Revenue", layout="title")) == []
 
 
def test_an_empty_context_gives_no_sources():
    assert select_facts(PresentationContext(), slide("Revenue")) == []
 
 
def test_stop_words_alone_never_match():
    # 'the', 'in' and 'during' are in several facts; they must not attach unrelated facts to a slide
    assert select_facts(CONTEXT, slide("The overview", "The summary in the end")) == []
 
 
def test_matching_ignores_plural_case_and_the_arabic_article():
    assert ids(select_facts(CONTEXT, slide("ENGINEER hires"))) == ["doc2-f1"]
    arabic = make_context(make_fact(1, 1, "ارتفعت المبيعات بنسبة ١٢ في المئة."))
    assert ids(select_facts(arabic, slide("المبيعات"))) == ["doc1-f1"]
    assert words("المبيعات") == words("مبيعات")
 
 
def test_rarer_words_rank_higher():
    context = make_context(
        make_fact(1, 1, "Sales rose in the north."),
        make_fact(1, 2, "Sales rose in the south."),
        make_fact(1, 3, "Warehouse sales rose sharply."),
    )
    assert ids(select_facts(context, slide("Warehouse sales")))[0] == "doc1-f3"
 
 
def test_no_more_than_top_k_facts():
    many = make_context(*[make_fact(1, i, f"Revenue note number {i}.") for i in range(1, 12)])
    assert len(select_facts(many, slide("Revenue"))) == TOP_K
 
 
def test_source_hints_come_first_then_ranking_fills_the_rest():
    selected = select_facts(CONTEXT, slide("Revenue growth", source_hints=["doc2-f1"]))
    assert ids(selected) == ["doc2-f1", "doc1-f1"]
 
 
def test_a_document_hint_and_a_page_hint():
    assert ids(select_facts(CONTEXT, slide("Anything", source_hints=["doc1"]))) == ["doc1-f1", "doc1-f2"]
    assert ids(select_facts(CONTEXT, slide("Anything", source_hints=["doc2:p4"]))) == ["doc2-f1"]
    assert select_facts(CONTEXT, slide("Anything", source_hints=["doc2:p9"])) == []
 
 
def test_unknown_hints_are_ignored_not_trusted():
    # until OUT-05 teaches the model real ids, it may invent hints
    assert ids(select_facts(CONTEXT, slide("Revenue growth", source_hints=["doc9-f9", "nonsense"]))) == ["doc1-f1"]
 
 
def test_the_section_and_key_points_widen_the_query():
    selected = select_facts(CONTEXT, slide("Next steps", section="People", key_points=["engineers"]))
    assert ids(selected) == ["doc2-f1"]
 
 
def test_the_outline_sees_every_document_summary_first():
    context = make_context(REVENUE, STAFF, summaries={1: "About sales.", 2: "About people."})
    chunks = overview_chunks(context)
    assert [c.chunk_id for c in chunks] == ["doc1-summary", "doc2-summary", "doc1-f1", "doc2-f1"]
 
 
def test_for_slide_returns_source_chunks_and_never_calls_the_model():
    client = ScriptedLLMClient()
    chunks = LlmContextProvider(client).for_slide(CONTEXT, slide("Hiring", "engineers"))
    assert [(c.chunk_id, c.document_id, c.filename, c.page) for c in chunks] == [("doc2-f1", 2, "d2.txt", 4)]
    assert client.calls == []
