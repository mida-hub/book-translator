import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from src.capture import SCREENSHOTS_BASE_DIR, _safe_dirname, capture_screen, save_screenshot
from src.hotkey_listener import HotkeyListener
from src.settings import Settings
from src.translator import TranslationCache, compute_image_hash, stream_translate_image
from src.ui.overlay_window import OverlayWindow

# ロギング設定: コンソールへの出力を確実に
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("book-translator")


class _TranslateWorker(QObject):
    """バックグラウンドスレッドでキャッシュ確認 → Gemini ストリーミング翻訳 → 保存を実行する。"""

    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str, str, bool)  # (txt_path, text, from_cache)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, image: Image.Image, png_path: Path) -> None:
        super().__init__()
        self.image = image
        self.png_path = png_path

    @pyqtSlot()
    def run(self) -> None:
        try:
            image_hash = compute_image_hash(self.image)
            cache = TranslationCache(self.png_path.parent)
            cached = cache.get(image_hash)
            if cached is not None:
                cached_path, cached_text = cached
                self.status.emit(f"Cache hit: {cached_path.name}")
                self.finished.emit(str(cached_path), cached_text, True)
                return

            self.status.emit(f"Starting Gemini translation for {self.png_path.name}")
            chunks: list[str] = []
            for chunk in stream_translate_image(self.image):
                chunks.append(chunk)
                self.chunk_received.emit(chunk)

            full_text = "".join(chunks).strip()
            if not full_text:
                self.error.emit("翻訳結果が空でした。")
                return

            ja_path = self.png_path.with_suffix(".ja.txt")
            ja_path.write_text(full_text, encoding="utf-8")
            cache.put(image_hash, ja_path)
            self.finished.emit(str(ja_path), full_text, False)
        except Exception as exc:
            log.exception("TranslateWorker error")
            self.error.emit(str(exc))


class _AppController(QObject):
    """ホットキー・ワーカー・UI を統合するコントローラー。"""

    _sig_capture = pyqtSignal()
    _sig_toggle_click_through = pyqtSignal()

    def __init__(self, settings: Settings, window: OverlayWindow) -> None:
        super().__init__()
        self.settings = settings
        self.window = window
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._current_ja_path: Path | None = None

        self._sig_capture.connect(self._start_capture)
        self._sig_toggle_click_through.connect(window.toggle_click_through)
        window.capture_requested.connect(self._start_capture)
        window.history_prev_requested.connect(lambda: self._navigate_history(-1))
        window.history_next_requested.connect(lambda: self._navigate_history(1))

    def on_hotkey_capture(self) -> None:
        self._sig_capture.emit()

    def on_hotkey_click_through(self) -> None:
        self._sig_toggle_click_through.emit()

    @pyqtSlot()
    def _start_capture(self) -> None:
        """キャプチャ処理。ウィンドウを隠して非ブロッキングタイマー経由で実行する。"""
        if self._thread is not None and self._thread.isRunning():
            log.debug("Capture/Translation already in progress; ignoring request.")
            return

        book_title = self.window.current_book_title()
        if not book_title:
            self.window.show_status("Warning: Book title is empty.")
            self.window.focus_title_input()
            return

        self.window.set_busy(True)
        self.window.show_status("Hiding window for capture...")

        # ウィンドウを隠し、macOS のウィンドウサーバーが反映するのをイベントループを止めずに待つ
        self.window.hide()
        QApplication.processEvents()
        QTimer.singleShot(150, lambda: self._perform_capture(book_title))

    def _perform_capture(self, book_title: str) -> None:
        try:
            capture_mode = self.settings.get("capture_mode", "full")
            image = capture_screen(capture_mode)

            # キャプチャ直後にウィンドウを戻す
            self.window.show()
            QApplication.processEvents()

            saved_path = save_screenshot(image, book_title)
            log.info("Captured: %s", saved_path.name)
            self.window.show_captured(str(saved_path))
            self.window.start_translation_stream()

            # メモリ上の画像をそのまま渡してバックグラウンドで翻訳実行
            self._start_translation(image, saved_path)
        except Exception as exc:
            log.exception("Capture process failed")
            self.window.show()
            self.window.show_error(str(exc))

    def _start_translation(self, image: Image.Image, png_path: Path) -> None:
        """バックグラウンドスレッドで翻訳を開始する。"""
        self.window.set_busy(True)
        worker = _TranslateWorker(image, png_path)
        self._run_worker(
            worker,
            on_chunk=self.window.append_translation_chunk,
            on_finished=self._on_translation_finished,
            on_error=self._on_translation_error,
            on_status=self.window.show_status,
        )

    def _on_translation_finished(self, txt_path: str, text: str, from_cache: bool) -> None:
        self._current_ja_path = Path(txt_path)
        log.info("Translation Success (cache=%s): %s", from_cache, self._current_ja_path.name)
        self.window.show_translation_done(txt_path, text, from_cache=from_cache)

    def _on_translation_error(self, message: str) -> None:
        log.error("Translation Failed: %s", message)
        self.window.show_error(message)

    def _navigate_history(self, delta: int) -> None:
        """翻訳済み .ja.txt ファイルの履歴を前後に移動して表示する。"""
        book_title = self.window.current_book_title()
        if not book_title:
            return
        book_dir = SCREENSHOTS_BASE_DIR / _safe_dirname(book_title)
        if not book_dir.exists():
            return

        files = sorted(book_dir.glob("*.ja.txt"))
        if not files:
            return

        if self._current_ja_path in files:
            idx = files.index(self._current_ja_path) + delta
        else:
            idx = len(files) - 1 if delta < 0 else 0

        idx = max(0, min(idx, len(files) - 1))
        target = files[idx]
        self._current_ja_path = target
        text = target.read_text(encoding="utf-8")
        self.window.show_translation_done(str(target), text, from_cache=True)

    def _run_worker(
        self,
        worker: _TranslateWorker,
        *,
        on_chunk,
        on_finished,
        on_error,
        on_status,
    ) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_received.connect(on_chunk)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.status.connect(on_status)

        # Cleanup connections
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker_refs)

        self._worker = worker
        self._thread = thread
        thread.start()

    def _clear_worker_refs(self) -> None:
        self._worker = None
        self._thread = None


def main() -> int:
    load_dotenv()

    app = QApplication(sys.argv)
    app.setApplicationName("Book Translator")

    settings = Settings()
    window = OverlayWindow(settings)
    controller = _AppController(settings, window)

    try:
        hotkey_listener = HotkeyListener(
            on_translate=controller.on_hotkey_capture,
            on_toggle_click_through=controller.on_hotkey_click_through,
        )
        hotkey_listener.start()
    except Exception as exc:
        log.error("Hotkey listener failed to start: %s", exc)
        hotkey_listener = None

    def _on_about_to_quit() -> None:
        log.info("Closing application...")
        if hotkey_listener is not None:
            hotkey_listener.stop()
        # 1.5秒待っても終了しない場合は強制終了
        QTimer.singleShot(1500, lambda: sys.exit(0))

    app.aboutToQuit.connect(_on_about_to_quit)

    window.show()
    exit_code = app.exec()

    log.info("Process finished.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
