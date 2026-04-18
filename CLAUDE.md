# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 起動方法

```bash
cd customer-manager
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開く。初期ログイン: `admin` / `admin123`

依存ライブラリのインストール（初回のみ）:
```bash
pip install flask
```

## アーキテクチャ

単一ファイル Flask アプリ（`app.py`）+ SQLite（`customers.db`）+ Jinja2 テンプレート。

**データベーススキーマ（4テーブル）:**
- `users` — ログインアカウント。`role` は `'admin'` または `'user'`
- `customers` — 顧客マスタ（name, company, phone, email, address, memo）
- `deals` — 案件。`customer_id` で顧客に紐づく。`status` は `提案中/商談中/受注/失注/完了`
- `contacts` — 連絡履歴。`customer_id` と `created_by`（users.id）で紐づく

**アクセス制御:**
- `@login_required` — 未ログインを `/login` にリダイレクト
- `@admin_required` — `role != 'admin'` を顧客一覧にリダイレクト（アカウント管理ページに使用）

**ルーティング構造:**
- `/` — 顧客一覧（検索・CSV操作）
- `/customers/<id>` — 顧客詳細（案件一覧・連絡履歴フォームを含む）
- `/customers/<id>/edit` — 顧客編集（削除ボタンもここ）
- `/customers/<customer_id>/deals/new`, `/deals/<id>/edit` — 案件フォーム
- `/customers/<customer_id>/contacts/new`, `/contacts/<id>/delete` — 連絡履歴
- `/customers/export`, `/customers/import` — CSV
- `/accounts` — アカウント管理（管理者専用）

**テンプレート:**
全テンプレートは `templates/base.html` を継承。Bootstrap 5 と Bootstrap Icons を CDN で使用。
`base.html` はサイドバーナビとフラッシュメッセージ表示を担当。

## CSVインポート仕様

ヘッダー行: `顧客名,会社名,電話,メール,住所,メモ`（`顧客名` のみ必須）。
文字コード: UTF-8（BOM付き推奨）。エクスポートしたCSVをそのまま再インポート可能（`ID`・`登録日`列は無視）。

## 注意事項

- `app.secret_key` は本番環境では必ず変更すること
- `customers.db` はアプリを起動したカレントディレクトリに作成される
- `init_db()` は起動時に毎回呼ばれるが、`CREATE TABLE IF NOT EXISTS` のため既存データは消えない
