import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
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
QMainWindow, QWidget {
    background-color: #1e1e1e;
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
    background-color: #252526;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
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
QFrame#step_frame {
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    background-color: #252526;
}
QLabel#step_header {
    color: #4ec9b0;
    font-weight: bold;
    font-size: 12px;
}
QLabel#status {
    color: #888;
    font-size: 11px;
}
QLabel#file_label {
    color: #9cdcfe;
    font-size: 11px;
}
"""

_LIGHT_STYLE = """
QMainWindow, QWidget {
    background-color: #f5f5f5;
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
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #ccc;
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
QFrame#step_frame {
    border: 1px solid #ddd;
    border-radius: 6px;
    background-color: #ffffff;
}
QLabel#step_header {
    color: #107c10;
    font-weight: bold;
    font-size: 12px;
}
QLabel#status {
    color: #666;
    font-size: 11px;
}
QLabel#file_label {
    color: #0078d4;
    font-size: 11px;
}
"""


class OverlayWindow(QMainWindow):
    """常に最前面に表示されるキャプチャ・OCR ステップバイステップウィンドウ。"""

    capture_requested = pyqtSignal()
    ocr_requested = pyqtSignal(str)  # png_path

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._click_through = False
        self._capture_count = 0
        self._last_png_path: str | None = None

        self._setup_window()
        self._build_ui()
        self._apply_settings()
        self._restore_geometry()

    # ------------------------------------------------------------------ setup

    def _setup_window(self) -> None:
        self.setWindowTitle("Book Translator")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # ---- 書籍タイトル行 ----
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("📚"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("書籍タイトルを入力してください")
        self._title_edit.textChanged.connect(self._on_title_changed)
        title_row.addWidget(self._title_edit, stretch=1)
        self._open_folder_btn = QPushButton("📂")
        self._open_folder_btn.setFixedWidth(32)
        self._open_folder_btn.setToolTip("保存フォルダを Finder で開く")
        self._open_folder_btn.clicked.connect(self._open_screenshots_folder)
        title_row.addWidget(self._open_folder_btn)
        root.addLayout(title_row)

        # ---- コントロール行 ----
        ctrl_row = QHBoxLayout()
        self._capture_combo = QComboBox()
        for label in _CAPTURE_MODES:
            self._capture_combo.addItem(label)
        self._capture_combo.currentTextChanged.connect(self._on_capture_mode_changed)
        ctrl_row.addWidget(self._capture_combo)
        self._capture_btn = QPushButton("📸 キャプチャ")
        self._capture_btn.setToolTip("スクリーンショットを保存 (Cmd+Option+T)")
        self._capture_btn.clicked.connect(self.capture_requested)
        ctrl_row.addWidget(self._capture_btn)
        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setFixedWidth(32)
        self._settings_btn.setToolTip("設定")
        self._settings_btn.clicked.connect(self._open_settings)
        ctrl_row.addWidget(self._settings_btn)
        root.addLayout(ctrl_row)

        # ---- ステップ 1: キャプチャ完了フレーム（初期非表示）----
        self._step1_frame = QFrame()
        self._step1_frame.setObjectName("step_frame")
        s1 = QVBoxLayout(self._step1_frame)
        s1.setSpacing(4)
        s1.setContentsMargins(8, 8, 8, 8)

        s1_header = QLabel("✅  ステップ 1: キャプチャ保存完了")
        s1_header.setObjectName("step_header")
        s1.addWidget(s1_header)

        self._png_name_label = QLabel("")
        self._png_name_label.setObjectName("file_label")
        s1.addWidget(self._png_name_label)

        self._ocr_btn = QPushButton("🔤  テキスト変換を実行")
        self._ocr_btn.setToolTip(
            "保存した PNG を Vision OCR でテキストに変換し .txt として保存します"
        )
        self._ocr_btn.clicked.connect(self._on_ocr_btn_clicked)
        s1.addWidget(self._ocr_btn)

        self._step1_frame.hide()
        root.addWidget(self._step1_frame)

        # ---- ステップ 2: OCR 完了フレーム（初期非表示）----
        self._step2_frame = QFrame()
        self._step2_frame.setObjectName("step_frame")
        s2 = QVBoxLayout(self._step2_frame)
        s2.setSpacing(4)
        s2.setContentsMargins(8, 8, 8, 8)

        s2_header = QLabel("✅  ステップ 2: テキスト変換完了")
        s2_header.setObjectName("step_header")
        s2.addWidget(s2_header)

        self._txt_name_label = QLabel("")
        self._txt_name_label.setObjectName("file_label")
        s2.addWidget(self._txt_name_label)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setMinimumHeight(250)
        self._text_edit.setPlaceholderText("変換されたテキストがここに表示されます")
        s2.addWidget(self._text_edit, stretch=1)

        self._step2_frame.hide()
        root.addWidget(self._step2_frame)

        root.addStretch()

    # ---------------------------------------------------------------- settings

    def _apply_settings(self) -> None:
        self.setWindowOpacity(self.settings.get("opacity", 0.92))

        theme = self.settings.get("theme", "dark")
        self.setStyleSheet(_DARK_STYLE if theme == "dark" else _LIGHT_STYLE)

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

    def _on_ocr_btn_clicked(self) -> None:
        if self._last_png_path:
            self._ocr_btn.setEnabled(False)
            self.ocr_requested.emit(self._last_png_path)

    def _set_click_through(self, enabled: bool) -> None:
        self._click_through = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)

    def _open_screenshots_folder(self) -> None:
        book_title = self.settings.get("book_title", "").strip()
        target = (
            SCREENSHOTS_BASE_DIR / _safe_dirname(book_title)
            if book_title
            else SCREENSHOTS_BASE_DIR
        )
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(target)], check=False)

    def toggle_click_through(self) -> None:
        enabled = not self._click_through
        self._set_click_through(enabled)
        self.settings.set("click_through", enabled)

    # --------------------------------------------------------------- public API

    def show_status(self, message: str) -> None:
        import logging
        logging.getLogger("book-translator").debug("status: %s", message)

    def show_captured(self, png_path: str) -> None:
        """ステップ1完了: キャプチャ保存完了を表示し、OCRボタンを有効化する。"""
        self.show_status("保存完了")
        self._last_png_path = png_path
        self._capture_count += 1

        self._png_name_label.setText(f"📸  {Path(png_path).name}")
        self._ocr_btn.setEnabled(True)

        # 新しいキャプチャ時はステップ2を非表示に戻す
        self._step2_frame.hide()
        self._step1_frame.show()

        self._capture_btn.setEnabled(True)

    def show_ocr_done(self, txt_path: str, text: str) -> None:
        """ステップ2完了: OCR結果とテキストファイルパスを表示する。"""
        self._txt_name_label.setText(f"📝  {Path(txt_path).name}")
        self._text_edit.setPlainText(text)
        self._step2_frame.show()
        self._ocr_btn.setEnabled(True)

    def show_error(self, message: str) -> None:
        import logging
        logging.getLogger("book-translator").error("error: %s", message)
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._save_geometry()

    def _save_geometry(self) -> None:
        geo = self.geometry()
        self.settings.update(
            {
                "window_x": geo.x(),
                "window_y": geo.y(),
                "window_width": geo.width(),
                "window_height": geo.height(),
            }
        )

    def closeEvent(self, event) -> None:
        self._save_geometry()
        super().closeEvent(event)
