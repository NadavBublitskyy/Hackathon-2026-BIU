"""This file verifies that file paths mentioned by the LLM exist in structure.json."""

# Import json so structure data can also be loaded from a JSON file path.
import json
# Import re so file paths can be extracted from LLM text with a regular expression.
import re
# Import Path so callers may pass a filesystem path to structure.json.
from pathlib import Path
# Import Any so the verifier can accept parsed JSON values with flexible shapes.
from typing import Any


# Define a class namespace for code attribution verification helpers.
class CodeAttributionVerifier:
    # Store a regex that extracts likely source-file paths from markdown/plain text.
    FILE_PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:[A-Za-z0-9_@.-]+/)*[A-Za-z0-9_@.-]+\.(?:py|js|jsx|ts|tsx|json|md|yml|yaml|toml|txt|html|css|scss|java|go|rs|cpp|c|h|hpp|cs|rb|php|sh|sql)(?::\d+)?(?![\w/-])")

    # Return True only when every mentioned file path exists in the provided structure JSON.
    @staticmethod
    # Accept parsed structure JSON or a path to a structure JSON file plus the LLM output text.
    def verify_response_paths(structure_json: Any, llm_output: str) -> bool:
        # Extract all source-file paths mentioned by the LLM output.
        mentioned_paths = CodeAttributionVerifier.extract_file_paths(llm_output)
        # Treat answers with no file citations as valid because there are no hallucinated paths to reject.
        if not mentioned_paths:
            # Return True for the vacuous case.
            return True
        # Extract all real file paths from the project structure JSON.
        valid_paths = CodeAttributionVerifier.extract_structure_paths(structure_json)
        # Check that every mentioned path is present in the real project structure.
        return all(path in valid_paths for path in mentioned_paths)

    # Extract all likely file paths from an LLM response.
    @staticmethod
    # Accept the raw LLM response text.
    def extract_file_paths(llm_output: str) -> set[str]:
        # Return no paths when the LLM response is empty or not text.
        if not isinstance(llm_output, str) or not llm_output.strip():
            # Return an empty set because there is nothing to verify.
            return set()
        # Create the output path set.
        paths: set[str] = set()
        # Iterate over every regex match in the response.
        for match in CodeAttributionVerifier.FILE_PATH_PATTERN.finditer(llm_output):
            # Read the matched raw path.
            raw_path = match.group(0)
            # Skip URL-like matches because they are not repo file citations.
            if "://" in raw_path:
                # Continue to the next match.
                continue
            # Normalize the path before comparing it to structure.json paths.
            normalized_path = CodeAttributionVerifier.normalize_path(raw_path)
            # Keep non-empty normalized paths.
            if normalized_path:
                # Add the normalized path to the result set.
                paths.add(normalized_path)
        # Return unique mentioned paths.
        return paths

    # Extract all real file paths from structure.json.
    @staticmethod
    # Accept parsed JSON or a path to a JSON file.
    def extract_structure_paths(structure_json: Any) -> set[str]:
        # Load the structure if the caller passed a path.
        structure = CodeAttributionVerifier.load_structure(structure_json)
        # Create the output set of valid repo paths.
        paths: set[str] = set()
        # Recursively collect paths from the loaded structure.
        CodeAttributionVerifier._collect_structure_paths(structure, paths)
        # Return the complete valid path set.
        return paths

    # Load structure JSON from a dict/list value or from a file path.
    @staticmethod
    # Accept flexible structure input.
    def load_structure(structure_json: Any) -> Any:
        # Return parsed JSON structures directly.
        if isinstance(structure_json, (dict, list)):
            # Return the original parsed JSON value.
            return structure_json
        # Load JSON when the input is a string or Path.
        if isinstance(structure_json, (str, Path)):
            # Convert the input into a Path object.
            path = Path(structure_json)
            # Open and parse the JSON file.
            with path.open(encoding="utf-8") as file:
                # Return the parsed JSON value.
                return json.load(file)
        # Return unsupported values unchanged so collection safely finds no paths.
        return structure_json

    # Normalize paths before comparison.
    @staticmethod
    # Accept a raw path extracted from text or JSON.
    def normalize_path(path: str) -> str:
        # Strip whitespace and common markdown punctuation.
        normalized = str(path).strip().strip("`'\".,;:)(")
        # Remove a leading relative path marker.
        if normalized.startswith("./"):
            # Drop the leading ./ prefix.
            normalized = normalized[2:]
        # Remove leading slashes so structure paths can match repo-relative citations.
        normalized = normalized.lstrip("/")
        # Remove line-number suffixes like src/app.py:12.
        normalized = re.sub(r":\d+$", "", normalized)
        # Return the normalized path.
        return normalized

    # Recursively collect real file paths from common structure.json shapes.
    @staticmethod
    # Accept one JSON value and the output path set.
    def _collect_structure_paths(value: Any, paths: set[str]) -> None:
        # Handle lists by walking each item.
        if isinstance(value, list):
            # Iterate over every item in the list.
            for item in value:
                # Recursively collect paths from the child item.
                CodeAttributionVerifier._collect_structure_paths(item, paths)
            # Stop after handling the list.
            return
        # Handle dictionaries by reading common path fields and walking nested values.
        if isinstance(value, dict):
            # Iterate over common keys that can contain file paths.
            for key in ("file_path", "path", "filename", "file", "name"):
                # Read a possible path value.
                candidate = value.get(key)
                # Check only text values.
                if isinstance(candidate, str):
                    # Normalize the candidate path.
                    normalized = CodeAttributionVerifier.normalize_path(candidate)
                    # Add values that look like source files.
                    if CodeAttributionVerifier._looks_like_file_path(normalized):
                        # Add the normalized valid path.
                        paths.add(normalized)
            # Walk all nested values so shapes like {"files": [...]} are supported.
            for child in value.values():
                # Recursively collect paths from the nested value.
                CodeAttributionVerifier._collect_structure_paths(child, paths)

    # Return whether a normalized path looks like a file path.
    @staticmethod
    # Accept a normalized path candidate.
    def _looks_like_file_path(path: str) -> bool:
        # Return False for empty values.
        if not path:
            # Empty strings are not file paths.
            return False
        # Return whether the path has a known source/document extension.
        return CodeAttributionVerifier.FILE_PATH_PATTERN.fullmatch(path) is not None
