import argparse
import ast
import re
import sys
from pathlib import Path

import pandas as pd

from app.analysis.table import read_table
from app.llm.ollama_client import OllamaChatClient

SYSTEM_PROMPT = """You are a data analysis assistant. You write Python code using pandas.

Rules:
- A pandas DataFrame named `df` is ALREADY loaded. Do not read any files.
- Use only: pandas (as pd), numpy (as np), matplotlib.pyplot (as plt), seaborn (as sns).
- Store the final answer in a variable named `result` (a DataFrame, Series, or scalar).
- If the user asks for a chart, create it with matplotlib/seaborn and save it with
  plt.savefig('plot.png', bbox_inches='tight'). Also set `result` to the data plotted.
- Never call plt.show(). Never use input(), open(), os, subprocess, or network calls.
- Use the exact column names from the schema. Do not invent columns.
- Output ONLY one ```python code block. No explanations."""


# ---------- 1. Load the file ----------
def load_table(path: str, sheet: str | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    ext = p.suffix.lower()
    with p.open("rb") as stream:
        return read_table(stream, ext, sheet)


# ---------- 2. Build a compact schema (the model never sees the full data) ----------
def build_schema(df: pd.DataFrame, n_samples: int = 3) -> str:
    lines = [f"Rows: {len(df)}, Columns: {len(df.columns)}", "Columns:"]
    for col in df.columns:
        s = df[col]
        extra = ""
        if pd.api.types.is_numeric_dtype(s):
            if s.notna().any():
                extra = f", min={s.min()}, max={s.max()}"
        elif s.nunique() <= 8:
            extra = f", values={list(s.dropna().unique())}"
        lines.append(f"- {col!r}: {s.dtype}, nulls={int(s.isna().sum())}{extra}")
    sample = df.head(n_samples).to_string(index=False, max_colwidth=30)
    lines.append(f"\nFirst {n_samples} rows:\n{sample}")
    return "\n".join(lines)


def build_user_prompt(schema: str, question: str) -> str:
    return f"DataFrame `df` schema:\n{schema}\n\nQuestion: {question}"


# ---------- 3. Call local Ollama ----------
def generate_from_prompt(client: OllamaChatClient, prompt: str) -> str:
    response = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        num_ctx=4096,
    )
    return extract_code(response)


def repair_prompt(original_prompt: str, code: str, error: str) -> str:
    return (
        f"{original_prompt}\n\nPrevious code:\n```python\n{code}\n```\n"
        f"Error:\n{error}\n\nReturn the complete corrected code for the original question."
    )


# ---------- 4. Extract + sanity-check the code ----------
def extract_code(response: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", response, re.DOTALL)
    code = m.group(1) if m else response  # fall back to raw text
    return code.strip()


def check_syntax(code: str) -> str | None:
    """Return None if code parses, else the error message (used later for retries)."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"


def generate_code(path: str, question: str, model: str | None = None,
                  sheet: str | None = None) -> tuple[str, pd.DataFrame]:
    df = load_table(path, sheet)
    prompt = build_user_prompt(build_schema(df), question)
    return generate_from_prompt(OllamaChatClient(model_name=model), prompt), df


def main():
    ap = argparse.ArgumentParser(description="Generate pandas code for a question about a CSV/XLSX file.")
    ap.add_argument("file")
    ap.add_argument("question")
    ap.add_argument("--model")
    ap.add_argument("--sheet", default=None, help="Excel sheet name (default: first sheet)")
    ap.add_argument("--show-prompt", action="store_true", help="Print the prompt sent to the model")
    args = ap.parse_args()

    df = load_table(args.file, args.sheet)
    schema = build_schema(df)
    prompt = build_user_prompt(schema, args.question)
    if args.show_prompt:
        print("=== PROMPT ===\n" + prompt + "\n")

    client = OllamaChatClient(model_name=args.model)
    print(f"Asking {client.model_name} ...", file=sys.stderr)
    code = generate_from_prompt(client, prompt)

    print("=== GENERATED CODE ===")
    print(code)
    err = check_syntax(code)
    if err:
        print(f"\n[warning] {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
