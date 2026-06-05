import logging
import sys
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from src.capture import capture_screen, save_screenshot, save_text
from src.hotkey_listener import HotkeyListener
from src.ocr import recognize_text_from_image
from src.settings import Settings
from src.ui.overlay_window import OverlayWindow

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
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
        log.debug("OcrWorker.run() start: png=%s", self.png_path)
        try:
            self.status.emit("テキスト変換中...")
            image = Image.open(self.png_path)
            log.debug("Image.open() done")
            text = recognize_text_from_image(image)
            log.debug("recognize_text_from_image() done: %d chars", len(text))
            if not text.strip():
                self.error.emit("テキストが検出されませんでした")
                return
            txt_path = save_text(text, self.png_path)
            log.debug("save_text() done: path=%s", txt_path)
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
        window.ocr_requested.connect(self._start_ocr)

    # pynput スレッドから呼ばれるメソッド -------

    def on_hotkey_capture(self) -> None:
        self._sig_capture.emit()

    def on_hotkey_click_through(self) -> None:
        self._sig_toggle_click_through.emit()

    # メインスレッドのスロット ----------------

    @pyqtSlot()
    def _start_capture(self) -> None:
        log.debug("_start_capture called")

        book_title = self.settings.get("book_title", "").strip()
        log.debug("book_title from settings: %r", book_title)
        if not book_title:
            book_title = self.window.current_book_title()
            log.debug("book_title from widget: %r", book_title)
            if book_title:
                self.settings.set("book_title", book_title)
        if not book_title:
            self.window.show_status("書籍タイトルを入力してください")
            self.window.focus_title_input()
            return

        capture_mode = self.settings.get("capture_mode", "full")
        log.debug("starting capture: mode=%s title=%s", capture_mode, book_title)
        self.window.show_status("キャプチャ中...")
        self.window.set_busy(True)

        # キャプチャにウィンドウが写らないように一時的に隠す
        self.window.hide()
        QApplication.processEvents()

        # mss は macOS では必ずメインスレッドで呼ぶ必要がある
        try:
            image = capture_screen(capture_mode)
            log.debug("capture_screen() done: size=%s", image.size)
            
            # キャプチャが終わったらすぐに戻す
            self.window.show()
            QApplication.processEvents()

            saved_path = save_screenshot(image, book_title)
            log.debug("save_screenshot() done: path=%s", saved_path)
            self.window.show_captured(str(saved_path))
        except Exception as exc:
            log.exception("capture error")
            self.window.show() # エラー時も再表示
            self.window.show_error(str(exc))

    @pyqtSlot(str)
    def _start_ocr(self, png_path: str) -> None:
        log.debug("_start_ocr called: png_path=%s", png_path)
        try:
            if self._thread is not None and self._thread.isRunning():
                log.debug("_start_ocr: thread still running, skip")
                return
        except RuntimeError:
            log.debug("_start_ocr: RuntimeError on isRunning, resetting thread")
            self._thread = None

        self.window.show_status("テキスト変換中...")
        self.window.set_busy(True)

        worker = _OcrWorker(png_path)
        self._run_worker(
            worker,
            on_finished=self.window.show_ocr_done,
            on_error=self.window.show_error,
            on_status=self.window.show_status,
        )

    def _clear_thread(self) -> None:
        log.debug("_clear_thread: thread finished")
        self._thread = None

    def _run_worker(self, worker: QObject, *, on_finished, on_error, on_status) -> None:
        log.debug("_run_worker: starting thread for %s", type(worker).__name__)
        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.status.connect(on_status)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_thread)
        thread.finished.connect(thread.deleteLater)

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
        window.show_status(f"ホットキー初期化失敗: {exc}")
        hotkey_listener = None

    window.show()
    exit_code = app.exec()

    if hotkey_listener:
        hotkey_listener.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())


class _CaptureWorker(QObject):
    """バックグラウンドスレッドでキャプチャ → ファイル保存を実行する。"""

    finished = pyqtSignal(str)  # 保存したファイルパス
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, capture_mode: str, book_title: str) -> None:
        super().__init__()
        self.capture_mode = capture_mode
        self.book_title = book_title

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.status.emit("キャプチャ中...")
            image = capture_screen(self.capture_mode)

            self.status.emit("保存中...")
            saved_path = save_screenshot(image, self.book_title)

            self.finished.emit(str(saved_path))
        except Exception as exc:
            self.error.emit(str(exc))
