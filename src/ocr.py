import logging
import re
from dataclasses import dataclass

from PIL import Image

try:
    import objc
    import Quartz
    import Vision
    from Foundation import NSArray, NSData, NSDictionary

    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

log = logging.getLogger("book-translator")


@dataclass(frozen=True)
class _TextLine:
    top: float
    bottom: float
    left: float
    height: float
    text: str


def recognize_text_from_image(pil_image: Image.Image) -> str:
    """
    macOS Vision フレームワークで画像から英語テキストを抽出する。
    """
    if not VISION_AVAILABLE:
        raise RuntimeError(
            "macOS Vision フレームワークが利用できません。\n"
            "uv sync を実行してください。"
        )

    with objc.autorelease_pool():
        log.debug("Converting PIL image to CGImage...")
        cg_image = _pil_to_cgimage(pil_image)

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLanguages_(NSArray.arrayWithObject_("en-US"))
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        log.debug("Performing Vision request...")
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, NSDictionary.dictionary()
        )
        success, error = handler.performRequests_error_(
            NSArray.arrayWithObject_(request), None
        )

        if not success:
            raise RuntimeError(f"Vision OCR 失敗: {error}")

        results = request.results()
        if not results:
            log.debug("No results from Vision request.")
            return ""

        log.debug("Found %d text observations.", len(results))
        lines: list[_TextLine] = []
        for observation in results:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            text_str = str(candidates[0].string())

            # 座標系は左下が (0,0)、右上が (1,1)
            box = observation.boundingBox()
            top = float(box.origin.y + box.size.height)
            bottom = float(box.origin.y)
            left = float(box.origin.x)
            height = float(box.size.height)

            # 上端 5% (メニューバー等) と下端 5% (ページ番号・進捗等) を除外
            if top > 0.95:
                log.debug("Filtered out top margin text: %s", text_str)
                continue
            if bottom < 0.05:
                log.debug("Filtered out bottom margin text: %s", text_str)
                continue

            lines.append(
                _TextLine(
                    top=top,
                    bottom=bottom,
                    left=left,
                    height=height,
                    text=text_str,
                )
            )

    if not lines:
        return ""

    full_text = _join_observations(lines)
    log.debug("Raw OCR text length: %d", len(full_text))

    cleaned = _clean_text(full_text)
    log.debug("Cleaned OCR text length: %d", len(cleaned))

    return cleaned


def _join_observations(lines: list[_TextLine]) -> str:
    """
    座標情報をもとに上から下・左から右へ並べ替え、段落の切れ目を判定して結合する。
    """
    # まず上端座標の降順（上から下）でソート
    sorted_by_top = sorted(lines, key=lambda item: -item.top)

    # 同一行（垂直方向の重なりが大きい要素）をグループ化して左から右へ並べる
    grouped_rows: list[list[_TextLine]] = []
    for line in sorted_by_top:
        if not grouped_rows:
            grouped_rows.append([line])
            continue
        prev_row_rep = grouped_rows[-1][0]
        if abs(prev_row_rep.top - line.top) < min(prev_row_rep.height, line.height) * 0.5:
            grouped_rows[-1].append(line)
        else:
            grouped_rows.append([line])

    ordered_rows: list[_TextLine] = []
    for row in grouped_rows:
        row.sort(key=lambda item: item.left)
        merged_text = " ".join(item.text for item in row)
        ordered_rows.append(
            _TextLine(
                top=max(item.top for item in row),
                bottom=min(item.bottom for item in row),
                left=row[0].left,
                height=max(item.height for item in row),
                text=merged_text,
            )
        )

    if len(ordered_rows) == 1:
        return ordered_rows[0].text

    avg_height = sum(r.height for r in ordered_rows) / len(ordered_rows)
    # 典型的な左端マージン（下位20%点付近）を取得
    sorted_lefts = sorted(r.left for r in ordered_rows)
    base_left = sorted_lefts[max(0, len(sorted_lefts) // 5)]

    chunks: list[str] = [ordered_rows[0].text]
    for prev, curr in zip(ordered_rows, ordered_rows[1:]):
        vertical_gap = prev.bottom - curr.top
        is_large_gap = vertical_gap > avg_height * 0.55
        is_indented = (curr.left - base_left) > 0.025

        if is_large_gap or is_indented:
            chunks.append("\n\n" + curr.text)
        else:
            chunks.append("\n" + curr.text)

    return "".join(chunks)


def _pil_to_cgimage(pil_image: Image.Image):
    """PIL Image を PNG 再エンコードなしで直接 CGImageRef に変換する。"""
    rgba_image = pil_image.convert("RGBA") if pil_image.mode != "RGBA" else pil_image
    raw_bytes = rgba_image.tobytes()

    ns_data = NSData.dataWithBytes_length_(raw_bytes, len(raw_bytes))
    provider = Quartz.CGDataProviderCreateWithCFData(ns_data)
    color_space = Quartz.CGColorSpaceCreateDeviceRGB()

    return Quartz.CGImageCreate(
        rgba_image.width,
        rgba_image.height,
        8,
        32,
        rgba_image.width * 4,
        color_space,
        Quartz.kCGImageAlphaNoneSkipLast | Quartz.kCGBitmapByteOrderDefault,
        provider,
        None,
        False,
        Quartz.kCGRenderingIntentDefault,
    )


def _clean_text(text: str) -> str:
    """OCR テキストを整形する: 行末ハイフン結合・段落内改行の正規化。"""
    # 同一段落内の行末ハイフンで分割された単語を結合（例: "exam-\nple" → "example"）
    text = re.sub(r"-\n(?!\n)\s*(\w)", r"\1", text)
    # 段落内の単一改行をスペースに置換（段落区切りの連続改行 \n\n は保持）
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # 連続スペースを正規化
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()
