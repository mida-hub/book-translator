# サービスアカウントの作成
resource "google_service_account" "book_translator" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "Book Translator Service Account"
  description  = "Service account for book-translator to call Vertex AI Gemini"
}

# サービスアカウントキーの発行
resource "google_service_account_key" "book_translator_key" {
  service_account_id = google_service_account.book_translator.name
}

# Vertex AI ユーザーロールの付与 (Gemini 呼び出し権限)
resource "google_project_iam_member" "book_translator_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.book_translator.email}"
}

# 発行した秘密鍵JSONを credentials/service_account.json として保存
resource "local_file" "service_account_key" {
  content         = base64decode(google_service_account_key.book_translator_key.private_key)
  filename        = "${path.module}/../credentials/service_account.json"
  file_permission = "0600"
}
