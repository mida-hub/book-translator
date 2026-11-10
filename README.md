# book-translator

Kindle 英語読書補助用 Mac スクリーンショット収集・OCR アプリ。
ウィンドウに書籍タイトルを設定し、`Cmd+Option+T` でキャプチャするたびに `~/book-translator/screenshots/<タイトル>/` にタイムスタンプ付き PNG を保存するとともに、macOS Vision Framework で自動的に OCR（文字認識）を実行して抽出テキストを `.txt` 保存および透過ウィンドウ上に表示します。

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

1. ウィンドウ上部の 📚 フィールドに**書籍タイトル**を入力（入力内容は自動保存されます）
2. キャプチャ領域（画面左半分 / 画面右半分 / 画面全体）をドロップダウンで選択
3. Kindle でページを表示し `Cmd+Option+T` またはウィンドウの「📸 キャプチャ」ボタンを押す
4. `~/book-translator/screenshots/<タイトル>/` にスクリーンショット（`.png`）と OCR 抽出テキスト（`.txt`）が保存され、ウィンドウ下部の透過エリアにテキストが表示される
5. 📋 ボタンで抽出テキストをクリップボードにコピー、📂 ボタンで保存フォルダを Finder で開ける

| 操作 | 機能 |
|------|------|
| `Cmd+Option+T` | キャプチャ ＆ 自動 OCR 実行（Kindle 画面がアクティブなまま押せる） |
| `Cmd+Option+C` | クリック透過 ON/OFF 切り替え（Kindle のページめくりを妨げないモード） |
| ウィンドウ内「📸 キャプチャ」ボタン | キャプチャ ＆ 自動 OCR 実行 |
| ウィンドウ内「📋」ボタン | 抽出テキストをクリップボードにコピー |
| ウィンドウ内「🧹」ボタン | 表示テキストをクリア |
| ウィンドウ内「📂」ボタン | 保存フォルダを Finder で開く |
| ウィンドウ内「⚙」ボタン | 設定（透過度・テーマ・クリック透過） |
| ウィンドウ内「❌」ボタン | アプリを終了 |

## ファイル構成

```
book-translator/
├── main.py                  # エントリーポイント・アプリ制御
├── pyproject.toml           # プロジェクト定義・依存関係
├── uv.lock
├── spec.md                  # 技術仕様書
└── src/
    ├── capture.py           # スクリーンキャプチャ・画像/テキスト保存 (mss / Pillow)
    ├── ocr.py               # 文字認識・テキスト整形 (macOS Vision Framework)
    ├── settings.py          # 設定の永続化 (~/.book-translator/settings.json)
    ├── hotkey_listener.py   # グローバルホットキー監視 (pynput)
    └── ui/
        ├── overlay_window.py   # メインオーバーレイウィンドウ (フレームレス・部分透過)
        └── settings_dialog.py  # 設定ダイアログ
```

## 保存先

```
~/book-translator/screenshots/
└── <書籍タイトル>/
    ├── 2026-05-31_10-00-00.png
    ├── 2026-05-31_10-00-00.txt
    ├── 2026-05-31_10-01-23.png
    ├── 2026-05-31_10-01-23.txt
    └── ...
```

## 動作環境

- macOS 12 Monterey 以降
- Python 3.12 以上
- Apple Silicon / Intel 両対応
