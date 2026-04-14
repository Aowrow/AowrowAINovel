from __future__ import annotations

from typing import Any


def build_initial_character_profiles(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(story_bible.get("characters", []), start=1):
        out.append(
            {
                "id": f"char_{idx:04d}",
                "name": str(item.get("name", "")),
                "role": str(item.get("role", "")),
                "goal": str(item.get("goal", "")),
                "flaw": str(item.get("flaw", "")),
                "arc": str(item.get("arc", "")),
                "survival_status": "active",
                "current_state": "",
                "state_updated_chapter": 0,
                "relationships": {},
            },
        )
    return out

