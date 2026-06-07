from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.settings import Settings


class SettingsDialog(QDialog):
    """アプリケーション設定ダイアログ。"""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("設定")
        self.setMinimumWidth(300)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # 透過度
        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(30, 100)
        self._opacity_slider.setTickInterval(10)
        self._opacity_val_label = QLabel("92%")
        self._opacity_val_label.setFixedWidth(36)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_val_label.setText(f"{v}%")
        )
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_val_label)
        form.addRow("透過度:", opacity_row)

        # テーマ
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["ダーク", "ライト"])
        form.addRow("テーマ:", self._theme_combo)

        # クリック透過
        self._click_through_check = QCheckBox("マウスクリックを透過させる")
        self._click_through_check.setToolTip(
            "ON にすると Kindle のページめくりを妨げません。\n"
            "Cmd+Option+C でいつでも切り替えられます。"
        )
        form.addRow("クリック透過:", self._click_through_check)

        layout.addLayout(form)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._save_and_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _load_values(self) -> None:
        opacity_pct = int(self.settings.get("opacity", 0.92) * 100)
        self._opacity_slider.setValue(opacity_pct)
        self._opacity_val_label.setText(f"{opacity_pct}%")

        theme = self.settings.get("theme", "dark")
        self._theme_combo.setCurrentText("ダーク" if theme == "dark" else "ライト")

        self._click_through_check.setChecked(self.settings.get("click_through", False))

    def _save_and_accept(self) -> None:
        self.settings.update(
            {
                "opacity": self._opacity_slider.value() / 100.0,
                "theme": (
                    "dark" if self._theme_combo.currentText() == "ダーク" else "light"
                ),
                "click_through": self._click_through_check.isChecked(),
            }
        )
        self.accept()
