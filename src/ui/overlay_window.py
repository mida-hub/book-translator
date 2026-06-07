import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.capture import SCREENSHOTS_BASE_DIR, _safe_dirname
from src.settings import Settings

_CAPTURE_MODES: dict[str, str] = {
    "画面左半分": "left",
    "画面右半分": "right",
    "画面全体": "full",
}

_DARK_STYLE = """
QMainWindow, QWidget#central_widget {
    background: transparent;
}
#top_container {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border: 1px solid #3c3c3c;
    border-bottom: none;
}
#bottom_container {
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    border: none;
}
QLabel {
    color: #e0e0e0;
}
QLineEdit {
    background-color: #252526;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
}
QTextEdit {
    background-color: transparent;
    color: #e0e0e0;
    border: none;
    border-radius: 4px;
    padding: 6px;
}
QComboBox {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #e0e0e0;
    selection-background-color: #0e639c;
}
QPushButton {
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:disabled {
    background-color: #3c3c3c;
    color: #555;
}
"""

_LIGHT_STYLE = """
QMainWindow, QWidget#central_widget {
    background: transparent;
}
#top_container {
    background-color: #f5f5f5;
    color: #1a1a1a;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border: 1px solid #ccc;
    border-bottom: none;
}
#bottom_container {
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    border: none;
}
QLabel {
    color: #1a1a1a;
}
QLineEdit {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 4px 8px;
}
QTextEdit {
    background-color: transparent;
    color: #1a1a1a;
    border: none;
    border-radius: 4px;
    padding: 6px;
}
QComboBox {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 4px 8px;
}
QPushButton {
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #106ebe;
}
QPushButton:disabled {
    background-color: #ccc;
    color: #888;
}
"""


class OverlayWindow(QMainWindow):
    """
    常に最前面に表示されるキャプチャ・OCR ウィンドウ。
    ユーザーの要望に従い、進捗ログを画面に流さず、コンソール出力に限定します。
    """

    capture_requested = pyqtSignal()
    ocr_requested = pyqtSignal(str)  # png_path

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._click_through = False
        self._last_png_path: str | None = None
        self._drag_pos = None

        self._setup_window()
        self._build_ui()
        self._apply_settings()
        self._restore_geometry()

    def _setup_window(self) -> None:
        self.setWindowTitle("Book Translator")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central_widget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Top Container (Opaque, Draggable) ----
        self._top_container = QWidget()
        self._top_container.setObjectName("top_container")
        top_layout = QVBoxLayout(self._top_container)
        top_layout.setSpacing(10)
        top_layout.setContentsMargins(12, 12, 12, 10)

        # Row 1: Title and Folder
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("📚"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("書籍タイトルを入力してください")
        self._title_edit.textChanged.connect(self._on_title_changed)
        header_layout.addWidget(self._title_edit, stretch=1)

        self._open_folder_btn = QPushButton("📂")
        self._open_folder_btn.setFixedWidth(36)
        self._open_folder_btn.setToolTip("保存フォルダを Finder で開く")
        self._open_folder_btn.clicked.connect(self._open_screenshots_folder)
        header_layout.addWidget(self._open_folder_btn)
        top_layout.addLayout(header_layout)

        # Row 2: Controls
        ctrl_layout = QHBoxLayout()

        self._capture_combo = QComboBox()
        for label in _CAPTURE_MODES:
            self._capture_combo.addItem(label)
        self._capture_combo.currentTextChanged.connect(self._on_capture_mode_changed)
        ctrl_layout.addWidget(self._capture_combo, stretch=1)

        self._capture_btn = QPushButton("📸 キャプチャ")
        self._capture_btn.setToolTip("スクリーンショットを保存 (Cmd+Option+T)")
        self._capture_btn.clicked.connect(self.capture_requested.emit)
        ctrl_layout.addWidget(self._capture_btn, stretch=1)

        self._ocr_btn = QPushButton("🔤 変換")
        self._ocr_btn.setToolTip("最後に保存した PNG をテキストに変換します")
        self._ocr_btn.clicked.connect(self._on_ocr_btn_clicked)
        self._ocr_btn.setEnabled(False)
        ctrl_layout.addWidget(self._ocr_btn, stretch=1)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setFixedWidth(36)
        self._settings_btn.setToolTip("設定")
        self._settings_btn.clicked.connect(self._open_settings)
        ctrl_layout.addWidget(self._settings_btn)

        self._quit_btn = QPushButton("❌")
        self._quit_btn.setFixedWidth(36)
        self._quit_btn.setToolTip("アプリを終了")
        self._quit_btn.clicked.connect(self._on_quit_clicked)
        ctrl_layout.addWidget(self._quit_btn)

        top_layout.addLayout(ctrl_layout)
        main_layout.addWidget(self._top_container)

        # ---- Bottom Container (Translucent) ----
        self._bottom_container = QWidget()
        self._bottom_container.setObjectName("bottom_container")
        bottom_layout = QVBoxLayout(self._bottom_container)
        bottom_layout.setContentsMargins(12, 0, 12, 12)

        self._text_edit = QTextEdit()
        self._text_edit.setObjectName("text_edit")
        self._text_edit.setReadOnly(True)
        self._text_edit.setMinimumHeight(250)
        bottom_layout.addWidget(self._text_edit, stretch=1)

        # Resize Grip
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        self._size_grip = QSizeGrip(self._bottom_container)
        grip_layout.addWidget(self._size_grip)
        bottom_layout.addLayout(grip_layout)

        main_layout.addWidget(self._bottom_container, stretch=1)

    # ---------------------------------------------------------------- settings

    def _apply_settings(self) -> None:
        # ウィンドウ自体の不透明度は常に1.0に固定し、背景色(RGBA)で透過を表現する
        self.setWindowOpacity(1.0)

        opacity = self.settings.get("opacity", 0.92)
        theme = self.settings.get("theme", "dark")

        # テーマに応じたベースカラー(16 hex)からRGBAを生成
        base_color = "#1e1e1e" if theme == "dark" else "#f5f5f5"
        r, g, b = int(base_color[1:3], 16), int(base_color[3:5], 16), int(base_color[5:7], 16)
        rgba = f"rgba({r}, {g}, {b}, {opacity})"

        self.setStyleSheet(_DARK_STYLE if theme == "dark" else _LIGHT_STYLE)

        # 下部コンテナにのみ透過背景を適用
        self._bottom_container.setStyleSheet(
            f"#bottom_container {{ background-color: {rgba}; }}"
        )

        current_mode = self.settings.get("capture_mode", "full")

        for label, value in _CAPTURE_MODES.items():
            if value == current_mode:
                self._capture_combo.setCurrentText(label)
                break

        self._title_edit.setText(self.settings.get("book_title", ""))

        click_through = self.settings.get("click_through", False)
        if click_through != self._click_through:
            self._set_click_through(click_through)

    def _restore_geometry(self) -> None:
        self.move(
            self.settings.get("window_x", 100),
            self.settings.get("window_y", 100),
        )
        self.resize(
            self.settings.get("window_width", 600),
            self.settings.get("window_height", 400),
        )

    def _save_geometry(self) -> None:
        geo = self.geometry()
        self.settings.update({
            "window_x": geo.x(),
            "window_y": geo.y(),
            "window_width": geo.width(),
            "window_height": geo.height(),
        })

    def _open_settings(self) -> None:
        from src.ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self._apply_settings()

    # ----------------------------------------------------------------- actions

    def _on_title_changed(self, text: str) -> None:
        self.settings.set("book_title", text.strip())

    def _on_capture_mode_changed(self, label: str) -> None:
        self.settings.set("capture_mode", _CAPTURE_MODES.get(label, "full"))

    def _on_quit_clicked(self) -> None:
        """保存して安全に終了をリクエストする。"""
        self._save_geometry()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def _on_ocr_btn_clicked(self) -> None:
        if self._last_png_path:
            self._ocr_btn.setEnabled(False)
            self.ocr_requested.emit(self._last_png_path)

    def _set_click_through(self, enabled: bool) -> None:
        self._click_through = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)

    def _open_screenshots_folder(self) -> None:
        book_title = self.settings.get("book_title", "").strip()
        target = SCREENSHOTS_BASE_DIR / _safe_dirname(book_title) if book_title else SCREENSHOTS_BASE_DIR
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(target)], check=False)

    def toggle_click_through(self) -> None:
        enabled = not self._click_through
        self._set_click_through(enabled)
        self.settings.set("click_through", enabled)

    # --------------------------------------------------------------- public API

    def show_status(self, message: str) -> None:
        """UIには表示せず、コンソールログのみ出力します。"""
        import logging
        logging.getLogger("book-translator").info("Status: %s", message)

    def show_captured(self, png_path: str) -> None:
        """キャプチャ完了通知。ボタンの有効化と内部状態の更新のみ。"""
        self._last_png_path = png_path
        self._ocr_btn.setEnabled(True)
        self._capture_btn.setEnabled(True)
        self.show_status(f"Captured: {Path(png_path).name}")

    def show_ocr_done(self, txt_path: str, text: str) -> None:
        """OCR完了。テキスト表示エリアの更新。"""
        self._text_edit.setPlainText(text)
        self._ocr_btn.setEnabled(True)
        self.show_status(f"OCR Done: {Path(txt_path).name}")

    def show_error(self, message: str) -> None:
        """エラー通知もコンソールログのみ。"""
        import logging
        logging.getLogger("book-translator").error("Error: %s", message)
        self._capture_btn.setEnabled(True)
        self._ocr_btn.setEnabled(self._last_png_path is not None)

    def set_busy(self, busy: bool) -> None:
        self._capture_btn.setEnabled(not busy)
        if busy:
            self._ocr_btn.setEnabled(False)

    def focus_title_input(self) -> None:
        self._title_edit.setFocus()
        self._title_edit.selectAll()

    def current_book_title(self) -> str:
        return self._title_edit.text().strip()

    # ------------------------------------------------------------------ events

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # top_container の範囲内でのクリックのみドラッグを許可する
            if self._top_container.geometry().contains(event.pos()):
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._save_geometry()

    def closeEvent(self, event) -> None:
        self._save_geometry()
        super().closeEvent(event)
