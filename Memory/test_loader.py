from Memory.loader import load_code_chunks


def main():
    chunks = load_code_chunks("Memory/mock_code_chunks.json")

    print("Loader works!")
    print(f"Loaded {len(chunks)} chunks")

    for chunk in chunks:
        print("--------------------------------")
        print("Chunk ID:", chunk["chunk_id"])
        print("File path:", chunk["file_path"])
        print("Type:", chunk["type"])
        print("Name:", chunk["name"])
        print("Scope:", chunk["scope"])
        print("Lines:", chunk["start_line"], "-", chunk["end_line"])
        print("Content preview:", chunk["content"][:80])


if __name__ == "__main__":
    main()