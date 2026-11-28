"""CTX-03: the size limit depends on the model and on the language of the document."""
 
import pytest
 
from app.presentations.context.budget import char_limit, detect_language, document_tokens
from app.presentations.context.errors import ContextTooLargeError
from app.presentations.context.limits import check_sizes
from app.presentations.context.readers import Block, DocumentText
from app.presentations.context.schemas import ContextOptions
 
ENGLISH = "The quarterly report describes revenue and costs. "
ARABIC = "يصف التقرير ربع السنوي الإيرادات والتكاليف. "
 
 
def document(text, name="doc.txt"):
    return DocumentText(document_id=1, filename=name, blocks=[Block(text)])
 
 
def limit(text, model, num_ctx=8192):
    return char_limit(document(text), ContextOptions(model_name=model, num_ctx=num_ctx, max_chars_per_document=None))[0]
 
 
def test_the_language_is_found_from_the_letters():
    assert detect_language(ENGLISH) == "en"
    assert detect_language(ARABIC) == "ar"
    assert detect_language("123 456 ... !!!") == "en"  # no letters
    assert detect_language(ARABIC * 3 + "Revenue") == "ar"
    assert detect_language(ENGLISH * 3 + "إيرادات") == "en"  # a few Arabic words in English text
 
 
def test_the_qwen_7b_gets_the_whole_free_window_and_the_3b_a_smaller_share():
    assert document_tokens("qwen2.5:7b-instruct", 8192) == 5592
    assert document_tokens("qwen2.5:3b", 8192) == 3500
    assert document_tokens("some-other-model", 8192) == 3000  # unknown models are treated carefully
 
 
def test_the_model_tag_can_be_written_in_different_ways():
    for tag in ("qwen2.5:7b-instruct", "qwen2.5:7b", "Qwen2.5-7B-Instruct"):
        assert document_tokens(tag, 8192) == 5592
    for tag in ("qwen2.5:3b", "qwen2.5:3b-instruct-q4_K_M"):
        assert document_tokens(tag, 8192) == 3500
 
 
def test_the_limit_in_characters_by_model_and_language():
    assert limit(ENGLISH, "qwen2.5:7b-instruct") == 19_572  # 5,592 tokens x 3.5
    assert limit(ARABIC, "qwen2.5:7b-instruct") == 11_184  # 5,592 tokens x 2.0
    assert limit(ENGLISH, "qwen2.5:3b") == 12_250
    assert limit(ARABIC, "qwen2.5:3b") == 7_000
 
 
def test_a_bigger_window_helps_the_7b_but_the_3b_stays_capped():
    assert limit(ENGLISH, "qwen2.5:7b", num_ctx=16384) > limit(ENGLISH, "qwen2.5:7b", num_ctx=8192)
    assert limit(ENGLISH, "qwen2.5:3b", num_ctx=16384) == limit(ENGLISH, "qwen2.5:3b", num_ctx=8192)
 
 
def test_a_tiny_window_still_gives_a_small_positive_limit():
    assert limit(ENGLISH, "qwen2.5:7b", num_ctx=1024) > 0
 
 
def test_a_fixed_number_in_the_options_overrides_everything():
    options = ContextOptions(model_name="qwen2.5:3b", max_chars_per_document=1234)
    assert char_limit(document(ARABIC), options) == (1234, "")
 
 
def test_the_same_arabic_document_fits_the_7b_but_not_the_3b():
    text = document(ARABIC * 190)  # about 8,000 characters
    check_sizes([text], ContextOptions(model_name="qwen2.5:7b-instruct", max_chars_per_document=None))
    with pytest.raises(ContextTooLargeError) as error:
        check_sizes([text], ContextOptions(model_name="qwen2.5:3b", max_chars_per_document=None))
    message = str(error.value)
    assert "'doc.txt'" in message and "limit is 7,000 for qwen2.5:3b with Arabic text" in message
 
 
def test_the_same_size_in_english_fits_the_3b():
    check_sizes([document(ENGLISH * 160)], ContextOptions(model_name="qwen2.5:3b", max_chars_per_document=None))  # ~8,000
