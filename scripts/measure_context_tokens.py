"""Measure how many tokens your model needs per character, to set PRESENTATION_CONTEXT_MAX_CHARS_PER_DOCUMENT (CTX-03).
 
The context step sends one whole document to the model, so prompt + document + answer must fit PRESENTATION_NUM_CTX.
Ollama reports the real prompt size (prompt_eval_count), so this script asks it with the real prompt and num_predict=1.
Run it once per language you care about (English and Arabic differ a lot) and per model.
 
From the repo root:
    python scripts/measure_context_tokens.py samples/english.txt samples/arabic.txt
    python scripts/measure_context_tokens.py --fake notes.txt      # checks the script itself, no Ollama
"""
 
import argparse
import sys
from pathlib import Path
 
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
 
import requests  # noqa: E402
 
from app.core.config import settings  # noqa: E402
from app.presentations.context.readers import normalise_text, read_file  # noqa: E402
from app.presentations.context.schemas import DocumentExtraction  # noqa: E402
from app.presentations.prompts.context import build_context_prompt  # noqa: E402
 
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+", type=Path, help="txt, pdf or docx samples (a few thousand characters is enough)")
ap.add_argument("--answer-tokens", type=int, default=1800, help="room kept for the model's answer (12 facts is about 1,500)")
ap.add_argument("--fake", action="store_true")
args = ap.parse_args()
 
SYSTEM = (
    "You are an AI assistant that outputs strictly valid JSON matching this Pydantic schema: "
    f"{DocumentExtraction.model_json_schema()}"
)
 
 
def prompt_tokens(user_prompt: str) -> int:
    """Tokens of system + user message, exactly as the client sends them."""
    if args.fake:
        return (len(SYSTEM) + len(user_prompt)) // 3
    reply = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.presentation_model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt}],
            "stream": False,
            "options": {"num_predict": 1, "num_ctx": 32768},  # large, so that nothing is cut while measuring
        },
        timeout=600,
    )
    reply.raise_for_status()
    return reply.json()["prompt_eval_count"]
 
 
def make_prompt(blocks) -> str:
    return build_context_prompt(
        topic="sample topic", audience="general audience", filename="sample", blocks=blocks, max_facts=12
    )
 
 
overhead = prompt_tokens(make_prompt([]))
room = settings.presentation_num_ctx - overhead - args.answer_tokens
print(f"model {settings.presentation_model}, PRESENTATION_NUM_CTX {settings.presentation_num_ctx}")
print(f"fixed prompt + schema: {overhead} tokens; answer reserve: {args.answer_tokens}; room for the document: {room} tokens\n")
 
for path in args.files:
    blocks, _ = read_file(path, path.suffix.lstrip(".").lower())
    chars = sum(len(normalise_text(b.text)) for b in blocks)
    tokens = prompt_tokens(make_prompt(blocks)) - overhead
    per_char = tokens / max(chars, 1)
    safe = int(room / per_char * 0.9) if per_char else 0  # 10% safety margin
    print(f"{path.name}: {chars:,} characters = {tokens:,} tokens ({1 / per_char:.2f} characters per token)")
    print(f"   -> PRESENTATION_CONTEXT_MAX_CHARS_PER_DOCUMENT up to about {safe:,} for this kind of text")
print("\nIf a \"characters per token\" value is lower than the one in context/budget.py (chars_per_token), lower it there.")
