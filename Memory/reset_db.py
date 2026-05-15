"""Utility script to wipe the ChromaDB directory before re-indexing with a new embedding model."""

import os
import shutil

from Memory.chroma_factory import reset_client


DEFAULT_CHROMA_DB_PATH = "Memory/chroma_db"


def reset_chroma_db(persist_directory: str = DEFAULT_CHROMA_DB_PATH) -> None:
    # Invalidate the in-process singleton so the next call opens a fresh client.
    reset_client()

    if os.path.exists(persist_directory):
        shutil.rmtree(persist_directory)
        print(f"Deleted: {persist_directory}")
    else:
        print(f"Nothing to delete: {persist_directory} does not exist.")


if __name__ == "__main__":
    reset_chroma_db()
