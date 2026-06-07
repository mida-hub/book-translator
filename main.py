import logging
import sys
import time
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QTimer
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
    stream=sys.stdout
)
log = logging.getLogger("book-translator")


class _OcrWorker(QObject):
    """バックグラウンドスレッドで OCR → テキストファイル保存を実行する。"""
    finished = pyqtSignal(str, str)  # (txt_path, text)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, png_path: str) -> None:
        super().__init__()
        self.png_path = Path(png_path)

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.status.emit(f"Starting OCR for {self.png_path.name}")
            image = Image.open(self.png_path)
            text = recognize_text_from_image(image)

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

        self._sig_capture.connect(self._start_capture)
        self._sig_toggle_click_through.connect(window.toggle_click_through)
        window.capture_requested.connect(self._start_capture)

    def on_hotkey_capture(self) -> None:
        self._sig_capture.emit()

    def on_hotkey_click_through(self) -> None:
        self._sig_toggle_click_through.emit()

    @pyqtSlot()
    def _start_capture(self) -> None:
        """キャプチャ処理。ウィンドウを確実に隠してから実行する。"""
        book_title = self.window.current_book_title()
        if not book_title:
            self.window.show_status("Warning: Book title is empty.")
            self.window.focus_title_input()
            return

        self.window.set_busy(True)
        self.window.show_status("Hiding window for capture...")

        # 1. ウィンドウを隠す
        self.window.hide()
        # 2. イベントループを回して確実に画面から消す
        QApplication.processEvents()
        # 3. macOSのウィンドウサーバーが反映するのを少し待つ (重要)
        time.sleep(0.15)

        try:
            capture_mode = self.settings.get("capture_mode", "full")
            image = capture_screen(capture_mode)

            # 4. キャプチャ直後にウィンドウを戻す
            self.window.show()
            QApplication.processEvents()

            saved_path = save_screenshot(image, book_title)
            log.info("Captured: %s", saved_path.name)
            self.window.show_captured(str(saved_path))
            
            # Automatically start OCR
            self._start_ocr(str(saved_path))
        except Exception as exc:
            log.exception("Capture process failed")
            self.window.show()
            self.window.show_error(str(exc))

    @pyqtSlot(str)
    def _start_ocr(self, png_path: str) -> None:
        """OCRを一時的にメインスレッドで実行して、ハングの原因を調査する。"""
        self.window.set_busy(True)
        log.info("Starting OCR (Direct) for: %s", Path(png_path).name)
        
        try:
            from PIL import Image
            image = Image.open(png_path)
            text = recognize_text_from_image(image)
            
            if not text.strip():
                self._on_ocr_error("No text detected.")
                return
                
            txt_path = save_text(text, Path(png_path))
            self._on_ocr_finished(str(txt_path), text)
        except Exception as exc:
            log.exception("Direct OCR failed")
            self._on_ocr_error(str(exc))

    def _on_ocr_finished(self, txt_path: str, text: str) -> None:
        log.info("OCR Success: %s", Path(txt_path).name)
        self.window.show_ocr_done(txt_path, text)

    def _on_ocr_error(self, message: str) -> None:
        log.error("OCR Failed: %s", message)
        self.window.show_error(message)

    def _run_worker(self, worker: QObject, *, on_finished, on_error, on_status) -> None:
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.status.connect(on_status)

        # Cleanup connections
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, '_thread', None))

        self._thread = thread
        thread.start()


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

    # 終了シグナルに反応して、数秒後に強制終了するウォッチドッグを設定
    # これにより QApplication.quit() が呼ばれた後、クリーンアップでハングしても確実に終了する
    def _on_about_to_quit():
        log.info("Closing application...")
        # 1.5秒待っても終了しない場合は強制終了
        QTimer.singleShot(1500, lambda: sys.exit(0))

    app.aboutToQuit.connect(_on_about_to_quit)

    window.show()
    exit_code = app.exec()

    log.info("Process finished. Force exiting.")
    sys.exit(exit_code)


if __name__ == "__main__":
    sys.exit(main())
