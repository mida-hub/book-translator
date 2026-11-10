import logging
import sys
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from src.capture import capture_screen, save_screenshot, save_text
from src.hotkey_listener import HotkeyListener
from src.ocr import recognize_text_from_image
from src.settings import Settings
from src.ui.overlay_window import OverlayWindow

# ロギング設定: コンソールへの出力を確実に
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("book-translator")


class _OcrWorker(QObject):
    """バックグラウンドスレッドで OCR → テキストファイル保存を実行する。"""
    finished = pyqtSignal(str, str)  # (txt_path, text)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, image: Image.Image, png_path: Path) -> None:
        super().__init__()
        self.image = image
        self.png_path = png_path

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.status.emit(f"Starting OCR for {self.png_path.name}")
            text = recognize_text_from_image(self.image)

            if not text.strip():
                self.error.emit("No text detected in image.")
                return

            txt_path = save_text(text, self.png_path)
            self.finished.emit(str(txt_path), text)
        except Exception as exc:
            log.exception("OcrWorker error")
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

        self._sig_capture.connect(self._start_capture)
        self._sig_toggle_click_through.connect(window.toggle_click_through)
        window.capture_requested.connect(self._start_capture)

    def on_hotkey_capture(self) -> None:
        self._sig_capture.emit()

    def on_hotkey_click_through(self) -> None:
        self._sig_toggle_click_through.emit()

    @pyqtSlot()
    def _start_capture(self) -> None:
        """キャプチャ処理。ウィンドウを隠して非ブロッキングタイマー経由で実行する。"""
        if self._thread is not None and self._thread.isRunning():
            log.debug("Capture/OCR already in progress; ignoring request.")
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

            # メモリ上の画像をそのまま渡してバックグラウンドで OCR 実行
            self._start_ocr(image, saved_path)
        except Exception as exc:
            log.exception("Capture process failed")
            self.window.show()
            self.window.show_error(str(exc))

    def _start_ocr(self, image: Image.Image, png_path: Path) -> None:
        """バックグラウンドスレッドで OCR を開始する。"""
        self.window.set_busy(True)
        worker = _OcrWorker(image, png_path)
        self._run_worker(
            worker,
            on_finished=self._on_ocr_finished,
            on_error=self._on_ocr_error,
            on_status=self.window.show_status,
        )

    def _on_ocr_finished(self, txt_path: str, text: str) -> None:
        log.info("OCR Success: %s", Path(txt_path).name)
        self.window.show_ocr_done(txt_path, text)

    def _on_ocr_error(self, message: str) -> None:
        log.error("OCR Failed: %s", message)
        self.window.show_error(message)

    def _run_worker(self, worker: _OcrWorker, *, on_finished, on_error, on_status) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
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
