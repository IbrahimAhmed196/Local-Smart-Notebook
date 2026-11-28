"""
vector_db_check.py

Inspect what is stored in ChromaDB (read-only).
Put this file next to vector_store.py and run:

    python vector_db_check.py
"""

import pandas as pd

from embed_nomic import PROJECT_ROOT
from vector_store import collection

OUTPUT_DIR = PROJECT_ROOT / "data" / "chromadb"

# Where to save the CSV dump (open it in Excel). Set to None to skip.
CSV_PATH = "chroma_dump.csv"


def main():
    total = collection.count()
    print(f"Chroma path : {OUTPUT_DIR}")
    print(f"Collection  : {collection.name}")
    print(f"Total chunks: {total}")

    if total == 0:
        print("The collection is empty.")
        return

    data = collection.get(include=["documents", "metadatas"])

    df = pd.DataFrame(data["metadatas"])
    df.insert(0, "id", data["ids"])
    df["text_preview"] = [doc[:100].replace("\n", " ") for doc in data["documents"]]

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)

    columns = [
        "id", "user_id", "conversation_id", "file_id", "file_name",
        "chunk_index", "page_number", "text_preview",
    ]
    columns = [c for c in columns if c in df.columns]

    print("\n=== Chunks ===")
    print(df[columns].to_string(index=False))

    print("\n=== Chunks per file ===")
    print(
        df.groupby(["user_id", "conversation_id", "file_name"])
        .size()
        .rename("chunks")
        .to_string()
    )

    if CSV_PATH:
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        print(f"\nSaved full dump to: {CSV_PATH}")


if __name__ == "__main__":
    main()

from vector_store import collection

r = collection.get(include=["embeddings"])
print("chunks      :", len(r["ids"]))
print("vector dim  :", len(r["embeddings"][0]))   # المفروض 768 لـ nomic
print("first values:", r["embeddings"][0][:5])