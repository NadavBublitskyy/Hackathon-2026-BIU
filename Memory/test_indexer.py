import chromadb

from Memory.loader import load_code_chunks
from Memory.indexer import index_code_chunks, get_indexed_chunks_count, COLLECTION_NAME


def main():
    chunks = load_code_chunks("Memory/mock_code_chunks.json")

    index_code_chunks(chunks)

    count = get_indexed_chunks_count()

    print("Indexer works!")
    print(f"Indexed {len(chunks)} chunks into ChromaDB.")
    print(f"Collection currently contains {count} chunks.")

    client = chromadb.PersistentClient(path="Memory/chroma_db")
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    result = collection.get(limit=1)

    print("\nSample item from ChromaDB:")
    print("ID:", result["ids"][0])
    print("Document:")
    print(result["documents"][0])
    print("Metadata:")
    print(result["metadatas"][0])


if __name__ == "__main__":
    main()