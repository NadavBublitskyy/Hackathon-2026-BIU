import json
from pathlib import Path

from Memory.chunk_adapter import normalize_chunk


REQUIRED_STRING_FIELDS = [
    "chunk_id",
    "file_path",
    "type",
    "name",
    "scope",
    "content"
]

REQUIRED_INT_FIELDS = [
    "start_line",
    "end_line"
]


def load_code_chunks(json_file_path: str) -> list[dict]:
    """
    Loads code chunks from a JSON file produced by Milestone 1,
    validates the expected structure, and returns the chunks
    in a format that can later be indexed into ChromaDB.

    Args:
        json_file_path: Path to the code chunks JSON file.

    Returns:
        A list of validated code chunks.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
        ValueError: If the JSON content is invalid or does not match
                    the expected structure.
    """

    file_path = Path(json_file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        try:
            chunks = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON format: {error}")

    return validate_code_chunks(chunks)


def validate_code_chunks(chunks: list[dict]) -> list[dict]:
    """
    Validates the structure of the code chunks list.

    Expected structure:
    [
        {
            "chunk_id": "...",
            "file_path": "...",
            "type": "...",
            "name": "...",
            "scope": "...",
            "content": "...",
            "start_line": 1,
            "end_line": 10
        }
    ]

    Args:
        chunks: Parsed JSON content.

    Raises:
        ValueError: If the structure is invalid.
    """

    if not isinstance(chunks, list):
        raise ValueError("Invalid structure: root object must be a list.")

    normalized_chunks = []

    for index, chunk in enumerate(chunks):
        normalized_chunks.append(validate_single_chunk(chunk, index))

    return normalized_chunks


def validate_single_chunk(chunk: dict, index: int) -> dict:
    """
    Validates a single code chunk.
    """

    if not isinstance(chunk, dict):
        raise ValueError(f"Invalid chunk at index {index}: each chunk must be an object.")

    normalized_chunk = normalize_chunk(chunk, index + 1)

    if normalized_chunk is None:
        raise ValueError(f"Invalid chunk at index {index}: chunk cannot be normalized.")

    for field in REQUIRED_STRING_FIELDS:
        if field not in normalized_chunk:
            raise ValueError(f"Invalid chunk at index {index}: missing '{field}' field.")

        if not isinstance(normalized_chunk[field], str):
            raise ValueError(f"Invalid chunk at index {index}: '{field}' must be a string.")

        if normalized_chunk[field].strip() == "":
            raise ValueError(f"Invalid chunk at index {index}: '{field}' cannot be empty.")

    for field in REQUIRED_INT_FIELDS:
        if field not in normalized_chunk:
            raise ValueError(f"Invalid chunk at index {index}: missing '{field}' field.")

        if not isinstance(normalized_chunk[field], int):
            raise ValueError(f"Invalid chunk at index {index}: '{field}' must be an integer.")

    if normalized_chunk["start_line"] <= 0:
        raise ValueError(f"Invalid chunk at index {index}: 'start_line' must be positive.")

    if normalized_chunk["end_line"] < normalized_chunk["start_line"]:
        raise ValueError(
            f"Invalid chunk at index {index}: 'end_line' must be greater than or equal to 'start_line'."
        )

    return normalized_chunk
