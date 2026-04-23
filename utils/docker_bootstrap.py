"""Container bootstrap helpers for first-run runtime state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import tomlkit


ROOT = Path(__file__).resolve().parent.parent


def _default_from_template(node: Dict[str, Any]) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, dict) and "optional" in value:
            if "default" in value:
                defaults[key] = value["default"]
            else:
                value_type = value.get("type")
                if value_type == "bool":
                    defaults[key] = False
                elif value_type in {"int", "float"}:
                    defaults[key] = 0
                else:
                    defaults[key] = ""
        elif isinstance(value, dict):
            defaults[key] = _default_from_template(value)
    return defaults


def _ensure_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _ensure_config(path: Path) -> None:
    if path.exists():
        return

    template_path = ROOT / "utils/.config.template.toml"
    template = tomlkit.loads(template_path.read_text(encoding="utf-8"))
    defaults = _default_from_template(template)
    path.write_text(tomlkit.dumps(defaults), encoding="utf-8")


def ensure_runtime_state() -> None:
    """Create runtime files and directories expected by the app."""
    for relative in (
        "assets/temp",
        "assets/backgrounds/audio",
        "assets/backgrounds/video",
        "results",
        "video_creation/data",
    ):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)

    _ensure_config(ROOT / "config.toml")
    _ensure_json(ROOT / "video_creation/data/videos.json", "[]\n")
    _ensure_json(ROOT / "utils/backgrounds.json", "{}\n")


def main() -> None:
    ensure_runtime_state()


if __name__ == "__main__":
    main()
