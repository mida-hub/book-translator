import json
from pathlib import Path
from typing import Any

_SETTINGS_DIR = Path.home() / ".book-translator"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

_DEFAULTS: dict[str, Any] = {
    "capture_mode": "full",   # 'left' | 'right' | 'full'
    "opacity": 0.92,          # 0.3 – 1.0
    "theme": "dark",          # 'dark' | 'light'
    "click_through": False,
    "book_title": "",
    "window_x": 100,
    "window_y": 100,
    "window_width": 600,
    "window_height": 400,
}


class Settings:
    """JSON ファイルで永続化するアプリケーション設定。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)
        self._save()

    def _load(self) -> None:
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass  # デフォルト値にフォールバック

    def _save(self) -> None:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
