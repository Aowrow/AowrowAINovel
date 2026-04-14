from __future__ import annotations

from typing import Any


def build_relationship_graph(character_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [{"id": p.get("id", ""), "name": p.get("name", "")} for p in character_profiles]
    return {"nodes": nodes, "edges": []}

