# book-translator

Kindle 英語読書補助用 Mac スクリーンショット収集・Gemini 翻訳オーバーレイアプリ。
ウィンドウに書籍タイトルを設定し、`Cmd+Option+T` でキャプチャするたびに Kindle ウィンドウの本文領域を自動切り出しして `~/book-translator/screenshots/<タイトル>/` に PNG 保存するとともに、Gemini (`gemini-3.5-flash`) で日本語訳をストリーミング生成して透過ウィンドウ上に表示します。

同じページを再キャプチャした場合は、dHash（知覚ハッシュ）キャッシュにより API を呼ばず即座に翻訳結果（`.ja.txt`）を再利用します。

## セットアップ

### 1. uv のインストール（未インストールの場合）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 依存パッケージのインストール

```bash
uv sync
```

### 3. Gemini 認証の設定

`.env.example` をコピーして `.env` を作成し、以下のいずれかの方法で認証を設定してください。

- **Vertex AI（サービスアカウント）を使う場合（推奨）**:
  `terraform/` を適用して `credentials/service_account.json` を発行します。
  ```bash
  cd terraform
  terraform init
  terraform apply
  ```
- **Google AI Studio（API キー）を使う場合**:
  `.env` に `GEMINI_API_KEY` を設定します。

### 4. macOS 権限の付与

| 権限 | 用途 |
|------|------|
| **画面収録** | スクリーンキャプチャ |
| **アクセシビリティ** | グローバルホットキー監視 |

システム環境設定 → プライバシーとセキュリティ から、Terminal（または Python）に上記 2 つの権限を付与してください。

### 5. 起動

```bash
uv run python main.py
```

## 使い方

1. ウィンドウ上部の 📚 フィールドに**書籍タイトル**を入力（入力内容は自動保存されます）
2. Kindle でページを表示し `Cmd+Option+T` またはウィンドウの「📸 翻訳」ボタンを押す（Kindle ウィンドウが検出できない場合のみ、ドロップダウンの領域設定にフォールバックします）
3. `~/book-translator/screenshots/<タイトル>/` にスクリーンショット（`.png`）と日本語訳（`.ja.txt`）が保存され、ウィンドウ下部のオーバーレイにストリーミング表示されます
4. `Cmd+Option+C` でクリック透過を ON にすると、オーバーレイを Kindle に重ねたままページめくりができます

| 操作 | 機能 |
|------|------|
| `Cmd+Option+T` | キャプチャ ＆ Gemini 翻訳実行（Kindle 画面がアクティブなまま押せる） |
| `Cmd+Option+C` | クリック透過 ON/OFF 切り替え（Kindle のページめくりを妨げないモード） |
| ウィンドウ内「📸 翻訳」ボタン | キャプチャ ＆ Gemini 翻訳実行 |
| ウィンドウ内「◀ / ▶」ボタン | 翻訳済みの過去ページ履歴を前後移動 |
| ウィンドウ内「A- / A+」ボタン | 翻訳テキストのフォントサイズ調整（自動保存） |
| ウィンドウ内「👁」ボタン | 背景の不透明 / 透過をワンクリック切り替え |
| ウィンドウ内「📋」ボタン | 表示テキストをクリップボードにコピー |
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
├── .env.example             # 環境変数テンプレート
├── credentials/             # Vertex AI サービスアカウントキー格納先
├── terraform/               # Vertex AI API 有効化・サービスアカウント作成用 Terraform
└── src/
    ├── capture.py           # Kindle ウィンドウ検出・キャプチャ・上下クロップ (mss / Quartz / Pillow)
    ├── translator.py        # Gemini ストリーミング翻訳・dHash キャッシュ (google-genai)
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
    ├── cache.json
    ├── 2026-11-14_22-01-48.png
    ├── 2026-11-14_22-01-48.ja.txt
    └── ...
```

## 動作環境

- macOS 12 Monterey 以降
- Python 3.12 以上
- Apple Silicon / Intel 両対応
