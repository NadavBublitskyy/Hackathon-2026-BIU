from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from Memory.indexer import index_code_chunks
from Memory.loader import load_code_chunks
from Memory.retriever import retrieve_snippets


router = APIRouter(prefix="/memory", tags=["Memory"])


class IndexRequest(BaseModel):
    json_file_path: Optional[str] = None


class IndexResponse(BaseModel):
    status: str
    message: str
    indexed_chunks: int


class RetrieveRequest(BaseModel):
    query: Optional[str] = None


class RetrieveResponse(BaseModel):
    snippets: list[dict]


@router.post("/index", response_model=IndexResponse)
def index_memory(request: IndexRequest) -> IndexResponse:
    if request.json_file_path is None or request.json_file_path.strip() == "":
        raise HTTPException(status_code=400, detail="json_file_path cannot be empty.")

    try:
        chunks = load_code_chunks(request.json_file_path)
        index_code_chunks(chunks)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Internal server error.") from error

    return IndexResponse(
        status="success",
        message="Indexed code chunks successfully",
        indexed_chunks=len(chunks),
    )


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve_memory(request: RetrieveRequest) -> RetrieveResponse:
    if request.query is None or request.query.strip() == "":
        raise HTTPException(status_code=400, detail="query cannot be empty.")

    try:
        snippets = retrieve_snippets(request.query)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Internal server error.") from error

    return RetrieveResponse(snippets=snippets)
