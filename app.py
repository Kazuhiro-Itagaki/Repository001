# ============================================================
# 顧客管理ツール - メインファイル
# 使い方: python app.py を実行して http://127.0.0.1:5000 を開く
# 初期ログイン: ユーザー名 admin / パスワード admin123
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import csv
import io
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'change-this-secret-key-in-production'  # セッション暗号化キー

DATABASE = 'customers.db'  # データベースファイル名


# ----- データベース接続 -----

def get_db():
    """データベースに接続して返す"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # 結果を辞書形式で扱えるようにする
    return conn


def init_db():
    """テーブルを作成し、管理者アカウントを初期化する"""
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                role       TEXT DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS customers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                company    TEXT,
                phone      TEXT,
                email      TEXT,
                address    TEXT,
                memo       TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS deals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                title       TEXT NOT NULL,
                status      TEXT DEFAULT '提案中',
                amount      INTEGER DEFAULT 0,
                memo        TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                date        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_by  INTEGER,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
        ''')

        # 管理者アカウントがなければ作成
        admin = conn.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
        if not admin:
            conn.execute(
                'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                ('admin', generate_password_hash('admin123'), 'admin')
            )
            conn.commit()


# ----- デコレーター（アクセス制限） -----

def login_required(f):
    """ログインしていないとアクセスできないページに付ける"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """管理者だけアクセスできるページに付ける"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('管理者権限が必要です', 'danger')
            return redirect(url_for('customers'))
        return f(*args, **kwargs)
    return decorated


# ================================================================
# 認証（ログイン・ログアウト）
# ================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['role']     = user['role']
            return redirect(url_for('customers'))
        flash('ユーザー名またはパスワードが違います', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ================================================================
# 顧客管理
# ================================================================

@app.route('/')
@login_required
def customers():
    search = request.args.get('search', '')
    with get_db() as conn:
        if search:
            rows = conn.execute(
                '''SELECT * FROM customers
                   WHERE name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ?
                   ORDER BY updated_at DESC''',
                (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%')
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM customers ORDER BY updated_at DESC').fetchall()
    return render_template('customers.html', customers=rows, search=search)


@app.route('/customers/new', methods=['GET', 'POST'])
@login_required
def new_customer():
    if request.method == 'POST':
        with get_db() as conn:
            conn.execute(
                'INSERT INTO customers (name, company, phone, email, address, memo) VALUES (?, ?, ?, ?, ?, ?)',
                (request.form['name'], request.form.get('company', ''),
                 request.form.get('phone', ''), request.form.get('email', ''),
                 request.form.get('address', ''), request.form.get('memo', ''))
            )
            conn.commit()
        flash('顧客を登録しました', 'success')
        return redirect(url_for('customers'))
    return render_template('customer_form.html', customer=None, title='顧客登録')


@app.route('/customers/<int:id>')
@login_required
def customer_detail(id):
    with get_db() as conn:
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (id,)).fetchone()
        deals    = conn.execute(
            'SELECT * FROM deals WHERE customer_id = ? ORDER BY created_at DESC', (id,)
        ).fetchall()
        contacts = conn.execute(
            '''SELECT contacts.*, users.username
               FROM contacts
               LEFT JOIN users ON contacts.created_by = users.id
               WHERE contacts.customer_id = ?
               ORDER BY contacts.date DESC''',
            (id,)
        ).fetchall()
    if not customer:
        flash('顧客が見つかりません', 'danger')
        return redirect(url_for('customers'))
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('customer_detail.html', customer=customer, deals=deals, contacts=contacts, now=today)


@app.route('/customers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_customer(id):
    with get_db() as conn:
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (id,)).fetchone()
        if request.method == 'POST':
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                '''UPDATE customers
                   SET name=?, company=?, phone=?, email=?, address=?, memo=?, updated_at=?
                   WHERE id=?''',
                (request.form['name'], request.form.get('company', ''),
                 request.form.get('phone', ''), request.form.get('email', ''),
                 request.form.get('address', ''), request.form.get('memo', ''), now, id)
            )
            conn.commit()
            flash('顧客情報を更新しました', 'success')
            return redirect(url_for('customer_detail', id=id))
    return render_template('customer_form.html', customer=customer, title='顧客編集')


@app.route('/customers/<int:id>/delete', methods=['POST'])
@login_required
def delete_customer(id):
    with get_db() as conn:
        conn.execute('DELETE FROM deals    WHERE customer_id = ?', (id,))
        conn.execute('DELETE FROM contacts WHERE customer_id = ?', (id,))
        conn.execute('DELETE FROM customers WHERE id = ?', (id,))
        conn.commit()
    flash('顧客を削除しました', 'warning')
    return redirect(url_for('customers'))


# ================================================================
# 案件管理
# ================================================================

@app.route('/customers/<int:customer_id>/deals/new', methods=['GET', 'POST'])
@login_required
def new_deal(customer_id):
    with get_db() as conn:
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
        if request.method == 'POST':
            conn.execute(
                'INSERT INTO deals (customer_id, title, status, amount, memo) VALUES (?, ?, ?, ?, ?)',
                (customer_id, request.form['title'], request.form.get('status', '提案中'),
                 request.form.get('amount') or 0, request.form.get('memo', ''))
            )
            conn.commit()
            flash('案件を登録しました', 'success')
            return redirect(url_for('customer_detail', id=customer_id))
    return render_template('deal_form.html', customer=customer, deal=None)


@app.route('/deals/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_deal(id):
    with get_db() as conn:
        deal     = conn.execute('SELECT * FROM deals WHERE id = ?', (id,)).fetchone()
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (deal['customer_id'],)).fetchone()
        if request.method == 'POST':
            conn.execute(
                'UPDATE deals SET title=?, status=?, amount=?, memo=? WHERE id=?',
                (request.form['title'], request.form.get('status', '提案中'),
                 request.form.get('amount') or 0, request.form.get('memo', ''), id)
            )
            conn.commit()
            flash('案件を更新しました', 'success')
            return redirect(url_for('customer_detail', id=deal['customer_id']))
    return render_template('deal_form.html', customer=customer, deal=deal)


@app.route('/deals/<int:id>/delete', methods=['POST'])
@login_required
def delete_deal(id):
    with get_db() as conn:
        deal = conn.execute('SELECT * FROM deals WHERE id = ?', (id,)).fetchone()
        customer_id = deal['customer_id']
        conn.execute('DELETE FROM deals WHERE id = ?', (id,))
        conn.commit()
    flash('案件を削除しました', 'warning')
    return redirect(url_for('customer_detail', id=customer_id))


# ================================================================
# 連絡履歴
# ================================================================

@app.route('/customers/<int:customer_id>/contacts/new', methods=['POST'])
@login_required
def new_contact(customer_id):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO contacts (customer_id, date, content, created_by) VALUES (?, ?, ?, ?)',
            (customer_id, request.form['date'], request.form['content'], session['user_id'])
        )
        conn.commit()
    flash('連絡履歴を記録しました', 'success')
    return redirect(url_for('customer_detail', id=customer_id))


@app.route('/contacts/<int:id>/delete', methods=['POST'])
@login_required
def delete_contact(id):
    with get_db() as conn:
        contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (id,)).fetchone()
        customer_id = contact['customer_id']
        conn.execute('DELETE FROM contacts WHERE id = ?', (id,))
        conn.commit()
    flash('連絡履歴を削除しました', 'warning')
    return redirect(url_for('customer_detail', id=customer_id))


# ================================================================
# CSV インポート / エクスポート
# ================================================================

@app.route('/customers/export')
@login_required
def export_csv():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM customers ORDER BY id').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '顧客名', '会社名', '電話', 'メール', '住所', 'メモ', '登録日'])
    for c in rows:
        writer.writerow([c['id'], c['name'], c['company'], c['phone'],
                         c['email'], c['address'], c['memo'], c['created_at']])
    response = make_response(output.getvalue())
    response.headers['Content-Type']        = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = 'attachment; filename=customers.csv'
    return response


def parse_csv_row(row):
    """
    CSV の列名に応じて顧客データを取り出す。
    通常フォーマット（顧客名,会社名,...）と
    Zoho CRM フォーマット（取引先名,電話番号,...）の両方に対応。
    """
    # Zoho CRM フォーマット判定
    if '取引先名' in row:
        # 住所を結合（都道府県 + 市区町村 + 町名・番地）
        address_parts = [
            row.get('都道府県（請求先）', ''),
            row.get('市区町村（請求先）', ''),
            row.get('町名・番地（請求先）', ''),
        ]
        address = ''.join(p for p in address_parts if p.strip())

        # メモは詳細情報と備考を結合
        memo_parts = [row.get('詳細情報', ''), row.get('備考', '')]
        memo = ' / '.join(p for p in memo_parts if p.strip())

        return {
            'name':    row.get('取引先名', ''),
            'company': row.get('取引先名', ''),
            'phone':   row.get('電話番号', ''),
            'email':   row.get('メールアドレス', ''),
            'address': address,
            'memo':    memo,
        }

    # 通常フォーマット
    return {
        'name':    row.get('顧客名', ''),
        'company': row.get('会社名', ''),
        'phone':   row.get('電話', ''),
        'email':   row.get('メール', ''),
        'address': row.get('住所', ''),
        'memo':    row.get('メモ', ''),
    }


@app.route('/customers/import', methods=['POST'])
@login_required
def import_csv():
    file = request.files.get('file')
    if not file:
        flash('ファイルを選択してください', 'danger')
        return redirect(url_for('customers'))

    raw = file.stream.read()

    # UTF-8（BOMあり）→ CP932（Windows日本語）→ Shift-JIS → UTF-8 の順に試す
    text = None
    for encoding in ('utf-8-sig', 'cp932', 'shift_jis', 'utf-8'):
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        flash('文字コードを認識できませんでした（UTF-8 または Shift-JIS のCSVを使用してください）', 'danger')
        return redirect(url_for('customers'))

    reader = csv.DictReader(io.StringIO(text))
    count  = 0
    skip   = 0
    with get_db() as conn:
        for row in reader:
            data = parse_csv_row(row)
            if not data['name'].strip():  # 顧客名が空の行はスキップ
                skip += 1
                continue
            conn.execute(
                'INSERT INTO customers (name, company, phone, email, address, memo) VALUES (?, ?, ?, ?, ?, ?)',
                (data['name'], data['company'], data['phone'],
                 data['email'], data['address'], data['memo'])
            )
            count += 1
        conn.commit()

    msg = f'{count} 件の顧客をインポートしました'
    if skip:
        msg += f'（{skip} 件は顧客名が空のためスキップ）'
    flash(msg, 'success')
    return redirect(url_for('customers'))


# ================================================================
# アカウント管理（管理者専用）
# ================================================================

@app.route('/accounts')
@admin_required
def accounts():
    with get_db() as conn:
        users = conn.execute('SELECT id, username, role, created_at FROM users ORDER BY id').fetchall()
    return render_template('accounts.html', users=users)


@app.route('/accounts/new', methods=['GET', 'POST'])
@admin_required
def new_account():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role     = request.form.get('role', 'user')
        with get_db() as conn:
            try:
                conn.execute(
                    'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                    (username, generate_password_hash(password), role)
                )
                conn.commit()
                flash('アカウントを作成しました', 'success')
            except sqlite3.IntegrityError:
                flash('そのユーザー名は既に使われています', 'danger')
        return redirect(url_for('accounts'))
    return render_template('account_form.html')


@app.route('/accounts/<int:id>/delete', methods=['POST'])
@admin_required
def delete_account(id):
    if id == session['user_id']:
        flash('自分自身は削除できません', 'danger')
        return redirect(url_for('accounts'))
    with get_db() as conn:
        conn.execute('DELETE FROM users WHERE id = ?', (id,))
        conn.commit()
    flash('アカウントを削除しました', 'warning')
    return redirect(url_for('accounts'))


# ================================================================
# 起動
# ================================================================

if __name__ == '__main__':
    init_db()  # テーブルと初期データを準備
    print('======================================')
    print('顧客管理ツール 起動中...')
    print('ブラウザで http://127.0.0.1:5000 を開いてください')
    print('初期ログイン: admin / admin123')
    print('======================================')
    app.run(debug=True)
