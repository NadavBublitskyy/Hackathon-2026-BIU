from Memory.retriever import retrieve_snippets


def main() -> None:
    snippets = retrieve_snippets("How are logs created?", top_k=3)

    print("Retriever works!")
    print(f"Found {len(snippets)} relevant snippets")

    for snippet in snippets:
        print()
        print(f"Path: {snippet['path']}")
        print(f"Score: {snippet['score']}")

        if snippet.get("name"):
            print(f"Name: {snippet['name']}")

        if snippet.get("type"):
            print(f"Type: {snippet['type']}")

        if snippet.get("start_line") is not None and snippet.get("end_line") is not None:
            print(f"Lines: {snippet['start_line']}-{snippet['end_line']}")

        print("Code:")
        print(snippet["code"])


if __name__ == "__main__":
    main()
