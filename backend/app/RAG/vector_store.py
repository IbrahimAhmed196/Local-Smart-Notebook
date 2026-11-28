import json
from pathlib import Path

import chromadb

from embed_nomic import (
    PROJECT_ROOT,
    MODEL_KEY,
    MODEL_NAME,
    load_chunks,
    filter_embeddable,
    run_embedding_pipeline,
)

# ==========================================
# 1. CHROMA SETUP
# ==========================================

CHROMA_DIR = PROJECT_ROOT / "data" / "chromadb"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(path=str(CHROMA_DIR))

collection = client.get_or_create_collection(
    name="notebook_chunks",
    embedding_function=None,            # إحنا اللي بنجيب الـ vectors
    metadata={"hnsw:space": "cosine"},  # الـ vectors normalized
)


# ==========================================
# 2. HELPERS
# ==========================================

def _clean_metadata(meta: dict) -> dict:
    """Chroma accepts only str/int/float/bool, no None and no lists."""
    clean = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        clean[key] = value
    return clean


def _first_page(page_numbers) -> int:
    return int(page_numbers[0]) if page_numbers else -1


# ==========================================
# 3. STORE
# ==========================================

def store_chunks(
    user_id,
    conversation_id,
    file_id,
    file_name,
    chunks: list[dict],
    embeddings,
):
    """
    chunks:     the filtered chunks (same order as embeddings)
    embeddings: np.ndarray (N, dim) from run_embedding_pipeline
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) mismatch."
        )

    ids, documents, vectors, metadatas = [], [], [], []

    for i, chunk in enumerate(chunks):
        original_id = chunk.get("chunk_id", f"{file_id}_{i}")

        # prefix with user/conversation/file so ids never collide across users
        ids.append(f"{user_id}_{conversation_id}_{file_id}_{original_id}")

        # raw_text = the source passage to show in citations
        documents.append(chunk.get("raw_text") or chunk.get("text", ""))
        vectors.append(embeddings[i].tolist())

        page_numbers = chunk.get("page_numbers", [])

        metadatas.append(_clean_metadata({
            # --- ownership (used for filtering at retrieval) ---
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "file_id": str(file_id),
            "file_name": file_name,
            # --- chunk info ---
            "chunk_id": original_id,
            "document_id": chunk.get("document_id"),
            "chunk_index": int(chunk.get("chunk_index", i)),
            "page_number": _first_page(page_numbers),
            "page_numbers": page_numbers,
            "headings": chunk.get("headings", []),
            "section": chunk.get("section"),
            "slide_number": chunk.get("slide_number"),
            "captions": chunk.get("captions", []),
            # --- embedding info ---
            "model_key": MODEL_KEY,
            "model_name": MODEL_NAME,
            # contextualized text (with headings), kept for debugging
            "context_text": chunk.get("text", ""),
        }))

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=vectors,
        metadatas=metadatas,
    )
    print(f"Stored {len(ids)} chunks in ChromaDB for file '{file_name}'.")


def index_document(user_id, conversation_id, file_id, file_name, document_id: str,
                   overwrite: bool = False):
    """
    One call: embed (or reuse the saved embeddings) then store in Chroma.
    Doesn't touch Extract_Chunking.py or embed_nomic.py.
    """
    result = run_embedding_pipeline(document_id=document_id, overwrite=overwrite)
    chunks = filter_embeddable(load_chunks(document_id))  # same order as embeddings

    store_chunks(
        user_id=user_id,
        conversation_id=conversation_id,
        file_id=file_id,
        file_name=file_name,
        chunks=chunks,
        embeddings=result["embeddings"],
    )


# ==========================================
# 4. DELETE + SEARCH
# ==========================================

def delete_file(user_id, conversation_id, file_id):
    collection.delete(where={"$and": [
        {"user_id": str(user_id)},
        {"conversation_id": str(conversation_id)},
        {"file_id": str(file_id)},
    ]})


def search(query_embedding, user_id, conversation_id, top_k=5, file_id=None):
    conditions = [
        {"user_id": str(user_id)},
        {"conversation_id": str(conversation_id)},
    ]
    if file_id is not None:
        conditions.append({"file_id": str(file_id)})

    return collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=top_k,
        where={"$and": conditions},
    )


if __name__ == "__main__":
    index_document(
        user_id="u1",
        conversation_id="c1",
        file_id="f1",
        file_name="Local Smart Notebook project proposal (1).pdf",
        document_id="Local Smart Notebook project proposal (1)",
    )