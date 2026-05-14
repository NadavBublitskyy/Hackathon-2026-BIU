from fastapi import APIRouter

from Graph.graph_builder import build_graph


router = APIRouter(prefix="/graph", tags=["Graph"])


@router.post("")
def generate_graph(structure: dict) -> dict:
    return build_graph(structure)
