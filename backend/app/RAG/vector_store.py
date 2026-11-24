import chromadb

client = chromadb.PersistentClient(
    path="./data/chroma"
)

collection = client.get_or_create_collection(
    name="notebook_chunks",
    embedding_function=None
)

def store_chunks(
    user_id,
    conversation_id,
    file_id,
    file_name,
    chunks
):
    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for chunk in chunks:
        chunk_id = (
            f"{user_id}_{conversation_id}_"
            f"{file_id}_{chunk['chunk_index']}"
        )

        ids.append(chunk_id)
        documents.append(chunk["text"])
        embeddings.append(chunk["embedding"])

        metadatas.append({
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "file_id": str(file_id),
            "file_name": file_name,
            "chunk_index": int(chunk["chunk_index"]),
            "page_number": int(chunk["page_number"])
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )