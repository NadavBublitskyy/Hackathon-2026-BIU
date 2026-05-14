"""This file owns JSON upload parsing for multipart API endpoints."""

# Import json so uploaded context files can be decoded.
import json
# Import Any so parsed JSON values can be typed flexibly.
from typing import Any

# Import FastAPI tools for uploaded files and controlled HTTP errors.
from fastapi import HTTPException, UploadFile


# Read and parse a JSON upload from Swagger or the frontend.
async def read_json_upload(upload: UploadFile) -> Any:
    # Read the uploaded file bytes.
    content = await upload.read()
    # Try to parse the uploaded bytes as JSON.
    try:
        # Decode the JSON payload into Python objects.
        return json.loads(content)
    # Convert invalid JSON into a clear HTTP 400 response.
    except json.JSONDecodeError as exc:
        # Tell the caller which uploaded file was invalid.
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'uploaded file'} is not valid JSON.") from exc
