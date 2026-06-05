# book-translator

Kindle 英語読書補助用 Mac スクリーンショット収集アプリ。
ウィンドウに書籍タイトルを設定し、`Cmd+Option+T` でキャプチャするたびに `~/book-translator/screenshots/<タイトル>/` にタイムスタンプ付き PNG として保存します。

## セットアップ

### 1. uv のインストール（未インストールの場合）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 依存パッケージのインストール

```bash
uv sync
```

### 3. macOS 権限の付与

| 権限 | 用途 |
|------|------|
| **画面収録** | スクリーンキャプチャ |
| **アクセシビリティ** | グローバルホットキー監視 |

システム環境設定 → プライバシーとセキュリティ から、Terminal（または Python）に上記 2 つの権限を付与してください。

### 4. 起動

```bash
uv run python main.py
```

## 使い方

1. ウィンドウ上部の 📚 フィールドに**書籍タイトル**を入力（Enter で確定）
2. キャプチャ領域をドロップダウンで選択
3. Kindle でページを表示し `Cmd+Option+T` またはウィンドウの「キャプチャ」ボタンを押す
4. `~/book-translator/screenshots/<タイトル>/YYYY-MM-DD_HH-MM-SS.png` に保存される
5. 📂 ボタンで保存フォルダを Finder で開ける

| 操作 | 機能 |
|------|------|
| `Cmd+Option+T` | キャプチャ保存（Kindle 画面がアクティブなまま押せる） |
| `Cmd+Option+C` | クリック透過 ON/OFF 切り替え |
| ウィンドウ内「キャプチャ」ボタン | 同上 |
| ウィンドウ内「⚙」ボタン | 設定（透過度・テーマ） |

## ファイル構成

```
book-translator/
├── main.py                  # エントリーポイント
├── pyproject.toml
├── uv.lock
└── src/
    ├── capture.py           # スクリーンキャプチャ・ファイル保存 (mss / Pillow)
    ├── settings.py          # 設定の永続化 (~/.book-translator/settings.json)
    ├── hotkey_listener.py   # グローバルホットキー (pynput)
    └── ui/
        ├── overlay_window.py   # メインオーバーレイウィンドウ
        └── settings_dialog.py  # 設定ダイアログ
```

## 保存先

```
~/book-translator/screenshots/
└── <書籍タイトル>/
    ├── 2026-05-31_10-00-00.png
    ├── 2026-05-31_10-01-23.png
    └── ...
```

## 動作環境

- macOS 12 Monterey 以降
- Python 3.11 以上（3.12 推奨）
- Apple Silicon / Intel 両対応
