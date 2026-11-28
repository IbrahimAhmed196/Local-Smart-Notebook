"""CTX-06: a fact is kept only if its evidence quote is really in the document."""
 
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.readers import Block
from app.presentations.context.schemas import ContextFact
from app.presentations.context.verify import verify_facts
from tests.fake_llm import ScriptedLLMClient
from tests.presentations.context_samples import extraction, fact, txt_document
 
 
def cf(evidence, page=None, fact_id="doc1-f1"):
    return ContextFact(fact_id=fact_id, text="x", document_id=1, filename="a.txt", page=page, evidence=evidence)
 
 
def check(evidence, text, page=None):
    result = verify_facts([cf(evidence, page)], [Block(text, page=page)])
    return bool(result.kept)
 
 
def test_a_real_quote_is_kept_and_an_invented_one_is_dropped():
    blocks = [Block("Revenue grew by 12 percent in March.", page=1)]
    result = verify_facts([cf("Revenue grew by 12 percent", 1), cf("Profit doubled in April", 1, "doc1-f2")], blocks)
    assert [f.fact_id for f in result.kept] == ["doc1-f1"]
    assert [f.fact_id for f in result.dropped] == ["doc1-f2"]
 
 
def test_case_and_spacing_do_not_matter():
    assert check("revenue   GREW by\n12 percent", "Revenue grew by 12 percent.")
    assert check("Revenuegrew by 12 percent", "Revenue grew by 12 percent.")  # PDF extraction lost a space
 
 
def test_ligatures_quotes_and_dashes_are_folded():
    assert check("the financial results were strong", "the ﬁnancial results were strong")
    assert check("it's a well-known result", "it’s a well—known result")
 
 
def test_arabic_marks_and_digit_forms_are_folded():
    assert check("ارتفعت المبيعات بنسبة 12 في المئة", "ارتفعَتِ المبيعاتُ بنسبة ١٢ في المئة")
    assert check("المبيعـــات ارتفعت هذا العام", "المبيعات ارتفعت هذا العام")  # tatweel
 
 
def test_an_arabic_presentation_form_ligature_matches_its_plain_letters():
    assert check("لا توجد بيانات كافية", "ﻻ توجد بيانات كافية")
 
 
def test_a_very_short_quote_proves_nothing():
    assert not check("Yes.", "Yes. The answer is yes.")
 
 
def test_a_wrong_page_is_corrected_when_the_quote_is_on_another_page():
    blocks = [Block("Costs fell in March.", page=1), Block("Revenue grew by 12 percent.", page=2)]
    result = verify_facts([cf("Revenue grew by 12 percent", page=1)], blocks)
    assert result.kept[0].page == 2 and result.pages_fixed == 1
 
 
def test_a_missing_page_is_filled_in_for_a_pdf():
    blocks = [Block("Costs fell in March.", page=1), Block("Revenue grew by 12 percent.", page=2)]
    assert verify_facts([cf("Revenue grew by 12 percent", page=None)], blocks).kept[0].page == 2
 
 
def test_a_quote_across_a_page_break_is_kept_on_its_cited_page():
    blocks = [Block("In the second quarter revenue grew by", page=1), Block("twelve percent in March.", page=2)]
    result = verify_facts([cf("revenue grew by twelve percent", page=1)], blocks)
    assert result.kept[0].page == 1 and result.pages_fixed == 0
 
 
def test_a_document_without_pages_is_checked_against_the_whole_text():
    blocks = [Block("Intro text.", heading="A"), Block("Costs fell sharply in March.", heading="B")]
    assert verify_facts([cf("Costs fell sharply in March")], blocks).kept
 
 
# ------------------------------------------------------------ through the provider
 
 
def test_a_planted_invented_fact_is_dropped_and_the_ratio_is_reported(tmp_path, use_files):
    text = "Revenue grew by 12 percent. Costs fell in March. North was the strongest region."
    client = ScriptedLLMClient(
        extraction(
            fact("Revenue grew 12%.", evidence="Revenue grew by 12 percent."),
            fact("Profit doubled.", evidence="Profit doubled in the second quarter."),  # invented
            fact("Costs fell.", evidence="Costs fell in March."),
            fact("North led.", evidence="North was the strongest region."),
        )
    )
    context = LlmContextProvider(client).build([txt_document(tmp_path, 1, "a.txt", text)], "Sales")
    document = context.documents[0]
    assert [f.fact_id for f in context.facts] == ["doc1-f1", "doc1-f3", "doc1-f4"]  # ids never shift
    assert (document.facts_checked, document.facts_dropped) == (4, 1)
    assert context.warnings == ["'a.txt': 3 of 4 extracted facts matched the document text (75%); the other 1 were dropped."]
 
 
def test_all_facts_invented_leaves_the_document_without_facts_and_says_so(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("Made up.", evidence="This sentence is not in the file.")))
    context = LlmContextProvider(client).build([txt_document(tmp_path, 1, "a.txt", "Real text only.")], "Sales")
    assert context.facts == []
    assert len(context.warnings) == 2 and "0 of 1" in context.warnings[0] and "no usable facts" in context.warnings[1]
 
 
def test_the_cap_is_applied_after_the_check(tmp_path, use_files):
    text = "First real fact here. Second real fact here. Third real fact here."
    from app.presentations.context.schemas import ContextOptions
 
    client = ScriptedLLMClient(
        extraction(
            fact("Invented.", evidence="This quote does not exist anywhere."),
            fact("one", evidence="First real fact here."),
            fact("two", evidence="Second real fact here."),
            fact("three", evidence="Third real fact here."),
        )
    )
    context = LlmContextProvider(client).build(
        [txt_document(tmp_path, 1, "a.txt", text)], "t", ContextOptions(max_facts_per_document=2)
    )
    assert [f.fact_id for f in context.facts] == ["doc1-f2", "doc1-f3"]  # the invented one did not use a slot
