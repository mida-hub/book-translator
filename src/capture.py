import re
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image

SCREENSHOTS_BASE_DIR = Path.home() / "book-translator" / "screenshots"


def capture_screen(mode: str) -> Image.Image:
    """
    プライマリモニターの指定領域をキャプチャする。

    Args:
        mode: 'left'（画面左半分）、'right'（画面右半分）、'full'（画面全体）

    Returns:
        キャプチャした PIL RGB Image
    """
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # monitors[0] は全モニター合成、[1] がプライマリ
        width = monitor["width"]
        height = monitor["height"]
        left = monitor["left"]
        top = monitor["top"]

        if mode == "left":
            region = {
                "top": top,
                "left": left,
                "width": width // 2,
                "height": height,
                "mon": 1,
            }
        elif mode == "right":
            region = {
                "top": top,
                "left": left + width // 2,
                "width": width // 2,
                "height": height,
                "mon": 1,
            }
        else:  # full
            region = monitor

        screenshot = sct.grab(region)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")


def save_screenshot(image: Image.Image, book_title: str) -> Path:
    """
    スクリーンショットを ~/book-translator/screenshots/<book_title>/<timestamp>.png に保存する。

    Args:
        image: 保存する PIL Image
        book_title: 書籍タイトル（ディレクトリ名に使用）

    Returns:
        保存したファイルの Path
    """
    safe_title = _safe_dirname(book_title or "untitled")
    dest_dir = SCREENSHOTS_BASE_DIR / safe_title
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_path = dest_dir / f"{timestamp}.png"
    image.save(dest_path, format="PNG")
    return dest_path


def _safe_dirname(name: str) -> str:
    """ファイルシステムに安全なディレクトリ名に変換する。"""
    safe = re.sub(r'[/\\:*?"<>|]', "_", name).strip()
    return safe or "untitled"


def save_text(text: str, png_path: Path) -> Path:
    """
    OCR テキストを PNG と同じディレクトリ・同じベース名の .txt ファイルに保存する。

    Args:
        text: 保存するテキスト
        png_path: 対応する PNG ファイルの Path

    Returns:
        保存した .txt ファイルの Path
    """
    txt_path = png_path.with_suffix(".txt")
    txt_path.write_text(text, encoding="utf-8")
    return txt_path
