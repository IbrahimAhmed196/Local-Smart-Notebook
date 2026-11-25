import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# ==========================================
# 1. CONFIGURATION
# ==========================================

# Project root: matches Extract_Chunking.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings"

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
MODEL_KEY = "nomic"

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

DEFAULT_MAX_SEQ_LENGTH = 2048   # tokens; text beyond this is silently cut by the model
DEFAULT_BATCH_SIZE = 8


# ==========================================
# 2. LOAD & FILTER CHUNKS
# ==========================================

def load_chunks(document_id: str) -> list[dict]:
    """
    Load processed chunks from chunks.jsonl for a given document_id.
    """
    chunks_path = PROCESSED_DIR / document_id / "chunks.jsonl"

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks file not found at: {chunks_path}\n"
            f"Run Extract_Chunking.py first to generate chunks.jsonl."
        )

    chunks = []
    with open(chunks_path, "r", encoding="utf-8") as file:
        for line in file:
            cleaned = line.strip()
            if cleaned:
                chunks.append(json.loads(cleaned))

    if not chunks:
        raise ValueError(f"No chunks found in: {chunks_path}")

    print(f"Loaded {len(chunks)} chunks for document '{document_id}'.")
    return chunks


def filter_embeddable(chunks: list[dict]) -> list[dict]:
    """
    Keep only chunks that can be embedded.

    Processing:
    1. Drop chunks with no text (an empty text still produces a vector,
       and that meaningless vector could show up in search results).
    2. Make sure chunk_id values are unique (the vector DB would
       silently overwrite duplicates).
    """
    usable = [
        chunk for chunk in chunks
        if (chunk.get("text") or chunk.get("raw_text") or "").strip()
    ]

    skipped = len(chunks) - len(usable)
    if skipped:
        print(f"Skipped {skipped} empty chunks.")

    if not usable:
        raise ValueError("No chunks with text to embed (scanned PDF without OCR?).")

    ids = [chunk.get("chunk_id") for chunk in usable]
    if any(chunk_id is None for chunk_id in ids):
        raise ValueError("One or more chunks are missing 'chunk_id'.")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk_id values found in chunks.jsonl.")

    return usable


# ==========================================
# 3. LOAD MODEL & GENERATE EMBEDDINGS
# ==========================================

def load_nomic_model(
    device: str | None = None,
    max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH,
) -> SentenceTransformer:
    """
    Load nomic-ai/nomic-embed-text-v1.5 using SentenceTransformer on GPU if available, else CPU.
    """
    selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading '{MODEL_NAME}' on device: {selected_device}...")

    model = SentenceTransformer(
        MODEL_NAME,
        device=selected_device,
        trust_remote_code=True,
    )
    model.max_seq_length = max_seq_length

    print(f"Model loaded successfully (max_seq_length={max_seq_length}).")
    return model


# Holds the single loaded model (loading nomic takes time and memory)
_model_cache = {"model": None}


def get_model(max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH) -> SentenceTransformer:
    """
    Load the model ONCE and reuse it for every document and every query.

    Calling this again with a different max_seq_length does NOT reload the
    model: the limit is just an attribute, so we only update it.
    """
    if _model_cache["model"] is None:
        _model_cache["model"] = load_nomic_model(max_seq_length=max_seq_length)
    else:
        _model_cache["model"].max_seq_length = max_seq_length

    return _model_cache["model"]


def build_embedding_texts(chunks: list[dict]) -> list[str]:
    """
    Use contextualized `text` (which includes headings/section context)
    and fall back to `raw_text` if needed, prefixed for Nomic documents.
    """
    texts = []
    for chunk in chunks:
        content = (chunk.get("text") or chunk.get("raw_text") or "").strip()
        texts.append(f"{DOC_PREFIX}{content}")
    return texts


def text_fingerprints(chunks: list[dict]) -> np.ndarray:
    """
    One short hash per chunk, computed from the exact prefixed text that gets embedded.
    Saved next to the vectors so we can tell later if the text or prefix changed.
    """
    return np.array(
        [
            hashlib.md5(text.encode("utf-8")).hexdigest()
            for text in build_embedding_texts(chunks)
        ]
    )


def check_truncation(model: SentenceTransformer, texts: list[str]) -> int:
    """
    Warn about chunks longer than the model limit.
    Text beyond max_seq_length is NOT embedded, so the end of such a chunk
    can never be found by search.
    """
    encoded = model.tokenizer(texts, add_special_tokens=True, truncation=False)
    lengths = [len(ids) for ids in encoded["input_ids"]]

    too_long = sum(length > model.max_seq_length for length in lengths)

    print(
        f"Tokens per chunk: min={min(lengths)}, "
        f"avg={sum(lengths) / len(lengths):.0f}, max={max(lengths)}"
    )

    if too_long:
        print(
            f"WARNING: {too_long} chunks exceed {model.max_seq_length} tokens "
            f"and will be truncated."
        )

    return too_long


def encode_chunks(
    model: SentenceTransformer,
    chunks: list[dict],
    batch_size: int = DEFAULT_BATCH_SIZE,
    normalize: bool = True,
) -> np.ndarray:
    """
    Generate dense embeddings for all chunks and validate vector integrity.
    """
    texts = build_embedding_texts(chunks)

    check_truncation(model, texts)

    print(f"Encoding {len(texts)} chunks with batch_size={batch_size}...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=normalize,
        convert_to_numpy=True,
    ).astype(np.float32)

    if embeddings.shape[0] != len(chunks):
        raise ValueError(
            f"Embedding count mismatch: got {embeddings.shape[0]}, expected {len(chunks)}."
        )

    if np.isnan(embeddings).any() or np.isinf(embeddings).any():
        raise ValueError("Generated embeddings contain NaN or Inf values.")

    norms = np.linalg.norm(embeddings, axis=1)

    # Normalized vectors must have length ~1 (a zero vector would break cosine search)
    if normalize and not np.allclose(norms, 1.0, atol=1e-3):
        raise ValueError(
            f"Embeddings are not unit-length: norm range [{norms.min():.4f}, {norms.max():.4f}]"
        )

    print(
        f"Embeddings generated: shape={embeddings.shape}, dtype={embeddings.dtype}, "
        f"norm_range=[{norms.min():.4f}, {norms.max():.4f}]"
    )

    return embeddings


# ==========================================
# 4. SAVE EMBEDDINGS & METADATA
# ==========================================

def save_embeddings(
    document_id: str,
    chunks: list[dict],
    embeddings: np.ndarray,
) -> Path:
    """
    Save dense vectors in compressed NPZ format and metadata in JSONL format.
    """
    output_dir = EMBEDDINGS_DIR / document_id / MODEL_KEY
    output_dir.mkdir(parents=True, exist_ok=True)

    npz_path = output_dir / "embeddings.npz"
    meta_path = output_dir / "chunks_meta.jsonl"

    chunk_ids = np.array(
        [chunk.get("chunk_id", f"{document_id}_{i}") for i, chunk in enumerate(chunks)]
    )

    np.savez_compressed(
        npz_path,
        embeddings=embeddings,
        chunk_ids=chunk_ids,
        text_hashes=text_fingerprints(chunks),
    )

    with open(meta_path, "w", encoding="utf-8") as meta_file:
        for idx, chunk in enumerate(chunks):
            record = {
                "vector_index": idx,
                "chunk_id": chunk.get("chunk_id", f"{document_id}_{idx}"),
                "document_id": chunk.get("document_id", document_id),
                "chunk_index": chunk.get("chunk_index", idx),
                "page_numbers": chunk.get("page_numbers", []),
                "headings": chunk.get("headings", []),
                "section": chunk.get("section"),
                "slide_number": chunk.get("slide_number"),
                "captions": chunk.get("captions", []),
                "model_key": MODEL_KEY,
                "model_name": MODEL_NAME,
                "text": chunk.get("text", ""),
                # Original text without the heading prefix: best for showing
                # the user the source passage in citations.
                "raw_text": chunk.get("raw_text", ""),
            }
            meta_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Saved embeddings to: {npz_path}")
    print(f"Saved metadata to:   {meta_path}")
    return output_dir


def embeddings_are_current(
    npz_path: Path,
    meta_path: Path,
    chunks: list[dict],
) -> bool:
    """
    True only if saved embeddings exist AND were built from exactly the
    current chunks: same chunk_ids, same order, AND same text.
    If the chunking or the document changed since the last run, the old
    vectors are stale and must be rebuilt.
    """
    if not (npz_path.exists() and meta_path.exists()):
        return False

    data = np.load(npz_path)

    # Files saved by an older version have no text hashes -> treat as stale
    if "text_hashes" not in data.files:
        return False

    same_ids = data["chunk_ids"].tolist() == [chunk.get("chunk_id") for chunk in chunks]
    same_text = data["text_hashes"].tolist() == text_fingerprints(chunks).tolist()

    return same_ids and same_text


# ==========================================
# 5. QUERY EMBEDDING HELPER (FOR RETRIEVAL)
# ==========================================

def embed_query(
    query: str,
    model: SentenceTransformer | None = None,
    normalize: bool = True,
) -> np.ndarray:
    """
    Embed a single search query using Nomic's required query prefix.
    Uses the shared cached model when none is passed.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query text cannot be empty.")

    model = model or get_model()

    query_vec = model.encode(
        [f"{QUERY_PREFIX}{cleaned_query}"],
        normalize_embeddings=normalize,
        convert_to_numpy=True,
    ).astype(np.float32)[0]

    return query_vec


# ==========================================
# 6. PIPELINE RUNNER
# ==========================================

def run_embedding_pipeline(
    document_id: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH,
    overwrite: bool = True,
    model: SentenceTransformer | None = None,
) -> dict:
    """
    Run the complete Nomic embedding stage for one document.

    Processing:
    1. Load chunks and drop the ones that cannot be embedded.
    2. If overwrite=False and up-to-date embeddings exist, reuse them.
    3. Otherwise embed (model is loaded once and cached) and save.
    """
    output_dir = EMBEDDINGS_DIR / document_id / MODEL_KEY
    npz_path = output_dir / "embeddings.npz"
    meta_path = output_dir / "chunks_meta.jsonl"

    # Step 1: Load and filter chunks
    chunks = filter_embeddable(load_chunks(document_id))

    # Step 2: Reuse existing embeddings only if they match the current chunks
    if not overwrite:
        if embeddings_are_current(npz_path, meta_path, chunks):
            print(f"Skipping '{document_id}': embeddings already up to date at {output_dir}")
            data = np.load(npz_path)
            return {
                "document_id": document_id,
                "embeddings": data["embeddings"],
                "output_dir": output_dir,
                "skipped": True,
            }

        if npz_path.exists():
            print("Existing embeddings are stale (chunks changed). Re-embedding...")

    # Step 3: Embed and save
    if model is None:
        model = get_model(max_seq_length)

    embeddings = encode_chunks(
        model=model,
        chunks=chunks,
        batch_size=batch_size,
        normalize=True,
    )

    save_embeddings(
        document_id=document_id,
        chunks=chunks,
        embeddings=embeddings,
    )

    return {
        "document_id": document_id,
        "embeddings": embeddings,
        "output_dir": output_dir,
        "skipped": False,
    }


# ==========================================
# 7. EXECUTION
# ==========================================

if __name__ == "__main__":
    # Matches the PDF stem used in Extract_Chunking.py
    document_id = "Local Smart Notebook project proposal (1)"

    run_embedding_pipeline(
        document_id=document_id,
        batch_size=DEFAULT_BATCH_SIZE,
        max_seq_length=DEFAULT_MAX_SEQ_LENGTH,
        overwrite=True,
    )