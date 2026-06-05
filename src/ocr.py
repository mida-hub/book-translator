import io
import re

from PIL import Image

try:
    import Vision
    import Quartz
    from Foundation import NSData

    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False


def recognize_text_from_image(pil_image: Image.Image) -> str:
    """
    macOS Vision フレームワークで画像から英語テキストを抽出する。

    Args:
        pil_image: 対象の PIL Image

    Returns:
        抽出・整形済みのテキスト文字列

    Raises:
        RuntimeError: Vision フレームワーク未インストール、または OCR 失敗時
    """
    if not VISION_AVAILABLE:
        raise RuntimeError(
            "macOS Vision フレームワークが利用できません。\n"
            "uv sync を実行してください。"
        )

    cg_image = _pil_to_cgimage(pil_image)
    recognized_strings: list[str] = []

    def completion_handler(request, error):
        if error or request.results() is None:
            return
        for observation in request.results():
            candidates = observation.topCandidates_(1)
            if candidates:
                recognized_strings.append(candidates[0].string())

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(
        completion_handler
    )
    request.setRecognitionLanguages_(["en-US"])
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, {}
    )
    success, error = handler.performRequests_error_([request], None)

    if not success:
        raise RuntimeError(f"Vision OCR 失敗: {error}")

    return _clean_text("\n".join(recognized_strings))


def _pil_to_cgimage(pil_image: Image.Image):
    """PIL Image を CGImageRef に変換する。"""
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    data = buffer.getvalue()

    ns_data = NSData.dataWithBytes_length_(data, len(data))
    source = Quartz.CGImageSourceCreateWithData(ns_data, None)
    return Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)


def _clean_text(text: str) -> str:
    """OCR テキストを整形する: 行末ハイフン結合・改行正規化。"""
    # 行末ハイフンで分割された単語を結合（例: "exam-\nple" → "example"）
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 段落内の改行をスペースに置換（連続改行は段落区切りとして保持）
    text = re.sub(r"(?<![.\n])\n(?!\n)", " ", text)
    # 連続スペースを正規化
    text = re.sub(r" +", " ", text)
    return text.strip()
