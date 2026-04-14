from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "defaults": {
        "chapter_start": 1,
        "chapter_end": 5,
        "chapter_count": 5,
        "token_budget": 1800,
        "run_t7_batch": False,
    },
    "length_control": {
        "enabled": True,
        "default_target_chars": 3000,
        "tolerance_ratio": 0.15,
        "auto_revise_on_out_of_range": True,
        "max_revise_rounds": 1,
        "token_per_char_init": 0.9,
        "token_per_char_min": 0.4,
        "token_per_char_max": 1.8,
        "token_safety_multiplier": 1.1,
    },
    "runtime_prompt_view": {
        "enabled": True,
        "shadow_mode": True,
        "chapter_summaries_recent": 3,
        "threads_max": 8,
        "foreshadow_due_horizon": 3,
        "foreshadows_max": 8,
        "enable_digests": False,
        "digest_max_chars": 220,
    },
    "storage": {
        "layout_version": "v2",
        "write_debug_package": False,
        "write_alignment_file": False,
        "export_plain_text": False,
        "export_full_book": False,
    },
    "analysis": {
        "enabled": True,
        "mode": "builtin",
    },
    "anti_ai_style": {
        "enabled": True,
        "strict_level": "high",
        "banned_phrases": [
            "总之",
            "综上所述",
            "需要注意的是",
            "首先",
            "其次",
            "最后",
            "接上回",
            "书接上文",
            "作为一个",
        ],
        "max_connector_density": 0.018,
        "max_repeated_opening_ratio": 0.25,
    },
    "writer": {
        "backend": "builtin",
        "model": "",
        "api_key": "",
        "base_url": "",
        "temperature": 0.7,
        "max_tokens": 2200,
        "timeout_sec": 120,
        "retries": 3,
        "retry_backoff_sec": 2.0,
        "stream": True,
        "system_prompt_file": "",
    },
}


def load_runtime_config(project_root: Path) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_RUNTIME_CONFIG)
    # JSON config file support
    json_paths = [project_root / "template_novel_engine.config.json"]
    cwd_json = Path.cwd() / "template_novel_engine.config.json"
    if cwd_json != json_paths[0]:
        json_paths.append(cwd_json)
    for conf_path in json_paths:
        if conf_path.exists():
            data = _read_json_object(conf_path)
            cfg = _deep_merge(cfg, data)
            break
    return cfg


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Config JSON must be an object: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
