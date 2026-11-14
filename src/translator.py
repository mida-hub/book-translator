import hashlib
import io
import json
import os
from collections.abc import Iterator
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

DEFAULT_MODEL = "gemini-3.5-flash"
MAX_IMAGE_LONG_EDGE = 1024
JPEG_QUALITY = 85
CREDENTIALS_PATH = Path(__file__).resolve().parent.parent / "credentials" / "service_account.json"

SYSTEM_PROMPT = """\
あなたは英語書籍（技術書・ビジネス書・一般書）の専門翻訳者です。
渡された書籍ページの画像から英文を読み取り、自然で読みやすい日本語に翻訳してください。

ルール:
- 前置き（「以下に翻訳します」など）やメタコメントは一切出力せず、翻訳結果のみを出力してください。
- 見出し・箇条書き・段落の構造を保ってください。
- プログラムコード、コマンド、数式、UIラベル、固有名詞などは文脈に応じて適切に英語のまま残すか、自然に補ってください。
- 図や表がある場合は、その中のテキストやキャプションも分かる形で翻訳してください。
"""


def compute_image_hash(image: Image.Image) -> str:
    """画像の構造を比較する 64bit dHash (16進文字列) を計算する。"""
    small = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        offset = row * 9
        for col in range(8):
            if pixels[offset + col] > pixels[offset + col + 1]:
                bits |= 1 << (row * 8 + col)
    return f"{bits:016x}"


def _hamming_distance(hex1: str, hex2: str) -> int:
    """2つの16進ハッシュ文字列間のハミング距離を返す。"""
    if len(hex1) != len(hex2):
        return 64
    return (int(hex1, 16) ^ int(hex2, 16)).bit_count()


class TranslationCache:
    """書籍ディレクトリ単位で画像ハッシュと翻訳テキストファイルを紐づけるキャッシュ。"""

    def __init__(self, book_dir: Path) -> None:
        self.book_dir = book_dir
        self.index_path = book_dir / "cache.json"

    def _load_index(self) -> dict[str, str]:
        if not self.index_path.exists():
            return {}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_index(self, index: dict[str, str]) -> None:
        self.book_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, image_hash: str, max_distance: int = 3) -> tuple[Path, str] | None:
        """キャッシュが存在し、対応する翻訳ファイルが読める場合は (path, text) を返す。"""
        index = self._load_index()
        filename = index.get(image_hash)
        if not filename:
            best_dist = max_distance + 1
            for cached_hash, cached_file in index.items():
                dist = _hamming_distance(image_hash, cached_hash)
                if dist <= max_distance and dist < best_dist:
                    best_dist = dist
                    filename = cached_file
        if not filename:
            return None
        target = self.book_dir / filename
        if not target.exists():
            return None
        return target, target.read_text(encoding="utf-8")

    def put(self, image_hash: str, txt_path: Path) -> None:
        """画像ハッシュと翻訳ファイル名をキャッシュに登録する。"""
        index = self._load_index()
        index[image_hash] = txt_path.name
        self._save_index(index)


def _prepare_image_bytes(
    image: Image.Image,
    max_long_edge: int = MAX_IMAGE_LONG_EDGE,
    quality: int = JPEG_QUALITY,
) -> bytes:
    """API 送信コスト・分割推論を防ぐため、長辺を max_long_edge 以下に縮小し JPEG 圧縮する。"""
    rgb_img = image.convert("RGB")
    rgb_img.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb_img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _create_client() -> genai.Client:
    """GEMINI_API_KEY があれば AI Studio、なければサービスアカウントで Vertex AI クライアントを生成する。"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        return genai.Client(api_key=api_key)

    if not CREDENTIALS_PATH.exists():
        raise RuntimeError(
            "GEMINI_API_KEY が未設定で、credentials/service_account.json も見つかりません。"
        )

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(CREDENTIALS_PATH)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "apps-466614").strip() or "apps-466614"
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-northeast1").strip() or "asia-northeast1"
    return genai.Client(vertexai=True, project=project_id, location=location)


def stream_translate_image(image: Image.Image) -> Iterator[str]:
    """Gemini API に画像を直接送信し、日本語訳をストリーミングで返す。"""
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    client = _create_client()
    jpeg_bytes = _prepare_image_bytes(image)

    response = client.models.generate_content_stream(
        model=model,
        contents=[
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            "この書籍ページの英文を日本語に翻訳してください。",
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL,
            ),
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        ),
    )
    for chunk in response:
        text = getattr(chunk, "text", None)
        if text:
            yield text
