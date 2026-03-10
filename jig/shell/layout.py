"""Layout save/load — JSON serialization of the full GUI state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".config" / "jig" / "layouts"
_DEFAULT_LAYOUT = _CONFIG_DIR / "default.json"


def _ensure_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_layout(state: dict[str, Any], path: Path | None = None) -> Path:
    """Serialize layout state to a JSON file. Returns the path written."""
    path = path or _DEFAULT_LAYOUT
    _ensure_dir()
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def load_layout(path: Path | None = None) -> dict[str, Any] | None:
    """Load layout state from a JSON file. Returns None if not found."""
    path = path or _DEFAULT_LAYOUT
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_layout_state(
    *,
    panels: list[dict[str, Any]],
    timeline_time: float,
    timeline_range: tuple[float, float],
    sessions: list[dict[str, Any]],
    dock_state: str | None = None,
) -> dict[str, Any]:
    """Build a layout dict from the current app state.

    Args:
        panels: Per-panel state dicts (type, title, state).
        timeline_time: Current timeline position.
        timeline_range: (t_min, t_max) data extent.
        sessions: Session descriptors.
        dock_state: Base64-encoded PyQtAds dock geometry (optional).
    """
    result: dict[str, Any] = {
        "version": 2,
        "timeline": {
            "current_time": timeline_time,
            "range": list(timeline_range),
        },
        "sessions": sessions,
        "panels": panels,
    }
    if dock_state is not None:
        result["dock_state"] = dock_state
    return result
