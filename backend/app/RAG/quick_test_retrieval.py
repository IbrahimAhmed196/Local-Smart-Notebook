import json
from pathlib import Path
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings"

MODELS_CONFIG = {
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "query_prefix": "",
        "trust_remote_code": False,
    },
    "nomic": {
        "model_name": "nomic-ai/nomic-embed-text-v1.5",
        "query_prefix": "search_query: ",
        "trust_remote_code": True,
    },
}


def load_saved_embeddings(document_id: str, model_key: str) -> tuple[np.ndarray, list[dict]]:
    base_dir = EMBEDDINGS_DIR / document_id / model_key
    npz_path = base_dir / "embeddings.npz"
    meta_path = base_dir / "chunks_meta.jsonl"

    if not npz_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Saved embeddings not found in: {base_dir}")

    embeddings = np.load(npz_path)["embeddings"]

    metadata = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                metadata.append(json.loads(line))

    return embeddings, metadata


def search_model(
    query: str,
    model: SentenceTransformer,
    query_prefix: str,
    embeddings: np.ndarray,
    metadata: list[dict],
    top_k: int = 3,
) -> list[dict]:
    formatted_query = f"{query_prefix}{query.strip()}"
    q_vec = model.encode(
        [formatted_query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)[0]

    scores = embeddings @ q_vec
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for rank, idx in enumerate(top_indices, start=1):
        item = metadata[int(idx)]
        results.append({
            "rank": rank,
            "score": float(scores[int(idx)]),
            "chunk_id": item.get("chunk_id"),
            "pages": item.get("page_numbers"),
            "headings": item.get("headings"),
            "preview": " ".join(item.get("text", "").split())[:150],
        })
    return results


def compare_models(document_id: str, queries: list[str], top_k: int = 3):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    loaded_models = {}

    for key, cfg in MODELS_CONFIG.items():
        print(f"Loading cached {key} ({cfg['model_name']}) on {device}...")
        embeddings, metadata = load_saved_embeddings(document_id, key)
        model = SentenceTransformer(
            cfg["model_name"],
            device=device,
            trust_remote_code=cfg["trust_remote_code"],
            local_files_only=True,
        )
        loaded_models[key] = {
            "model": model,
            "query_prefix": cfg["query_prefix"],
            "embeddings": embeddings,
            "metadata": metadata,
        }

    for q in queries:
        print("\n" + "=" * 75)
        print(f"QUERY: {q}")
        print("=" * 75)

        for key, bundle in loaded_models.items():
            results = search_model(
                query=q,
                model=bundle["model"],
                query_prefix=bundle["query_prefix"],
                embeddings=bundle["embeddings"],
                metadata=bundle["metadata"],
                top_k=top_k,
            )
            print(f"\n--- [{key.upper()}] ---")
            for r in results:
                print(
                    f"  #{r['rank']} | score={r['score']:.4f} | {r['chunk_id']} | pages={r['pages']}\n"
                    f"     headings: {r['headings']}\n"
                    f"     text: {r['preview']}..."
                )


if __name__ == "__main__":
    document_id = "Local Smart Notebook project proposal (1)"

    test_queries = [
        "What is the main goal of Local Smart Notebook?",
        "What models or tools are used in this project?",
        "How does the system handle document summarization or analytics?",
        "What are the main challenges or risks in this project?",
    ]

    compare_models(document_id=document_id, queries=test_queries, top_k=3)