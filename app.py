from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os, hashlib, secrets, base64, json, re
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import numpy as np

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ✅ FIX 1: Fixed secret key - set a permanent one, not random each restart
app.secret_key = os.environ.get('SECRET_KEY', 'deepfake_detector_secret_key_2025_fixed')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deepfake.db')

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                result TEXT NOT NULL,
                confidence TEXT,
                detail TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        ''')

init_db()

def hash_password(pw):
    return hashlib.sha256(('df_salt_2025' + pw).encode()).hexdigest()

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ✅ FIX 2: Completely rewritten analyze_image with a much more reliable approach
def analyze_image(image_path):
    try:
        import requests
        api_user = os.environ.get('SIGHTENGINE_USER', '1386884004')
        api_secret = os.environ.get('SIGHTENGINE_SECRET', '7TidexJ3WdN9v7pDrrA5WcLp34CAT9Ye')
        with open(image_path, 'rb') as f:
            response = requests.post(
                'https://api.sightengine.com/1.0/check.json',
                files={'media': f},
                data={
                    'models': 'ai-generated',
                    'api_user': api_user,
                    'api_secret': api_secret
                }
            )
        result = response.json()
        if result.get('status') == 'success':
            ai_score = result.get('type', {}).get('ai_generated', 0)
            ai_percent = round(ai_score * 100)
            real_percent = 100 - ai_percent
            if ai_score >= 0.7:
                verdict = "AI-Generated / Deepfake"
                confidence = ai_percent
                details = f"Sightengine AI score: {ai_percent}% AI-generated"
            elif ai_score >= 0.4:
                verdict = "Possibly AI-Generated"
                confidence = ai_percent
                details = f"Sightengine AI score: {ai_percent}% AI-generated"
            else:
                verdict = "Real Image"
                confidence = real_percent
                details = f"Sightengine AI score: {ai_percent}% AI-generated, likely real"
        else:
            verdict = "Error"
            confidence = 0
            details = f"API error: {result.get('error', {}).get('message', 'Unknown error')}"
        return {"verdict": verdict, "confidence": confidence, "details": details}
    except Exception as e:
        return {"verdict": "Error", "confidence": 0, "details": f"Analysis failed: {str(e)}"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        c = request.form.get('confirm','').strip()
        if not u or not p: flash('All fields required.','error')
        elif len(p) < 6: flash('Password must be at least 6 characters.','error')
        elif p != c: flash('Passwords do not match.','error')
        else:
            try:
                with get_db() as db:
                    db.execute('INSERT INTO users (username,password,created) VALUES (?,?,?)',
                               (u, hash_password(p), datetime.now().isoformat()))
                flash('Account created! Please log in.','success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already taken.','error')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        with get_db() as db:
            user = db.execute('SELECT * FROM users WHERE username=? AND password=?',
                              (u, hash_password(p))).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {u}!','success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.','error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.','success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as db:
        analyses = db.execute('SELECT * FROM analyses WHERE user_id=? ORDER BY uploaded_at DESC LIMIT 20',
                              (session['user_id'],)).fetchall()
    return render_template('dashboard.html', analyses=analyses)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'image' not in request.files:
        flash('No file selected.','error'); return redirect(url_for('dashboard'))
    file = request.files['image']
    if not file.filename or not allowed_file(file.filename):
        flash('Invalid or missing file.','error'); return redirect(url_for('dashboard'))
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(file.filename)}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    analysis = analyze_image(path)
    with get_db() as db:
        row_id = db.execute(
            'INSERT INTO analyses (user_id,image_path,result,confidence,detail,uploaded_at) VALUES (?,?,?,?,?,?)',
            (session['user_id'], filename, analysis['verdict'], analysis['confidence'],
             analysis['details'], datetime.now().isoformat())).lastrowid
    return redirect(url_for('result', analysis_id=row_id))

@app.route('/result/<int:analysis_id>')
@login_required
def result(analysis_id):
    with get_db() as db:
        row = db.execute('SELECT * FROM analyses WHERE id=? AND user_id=?',
                         (analysis_id, session['user_id'])).fetchone()
    if not row: flash('Result not found.','error'); return redirect(url_for('dashboard'))
    return render_template('result.html', analysis=row)

@app.route('/delete/<int:analysis_id>', methods=['POST'])
@login_required
def delete_analysis(analysis_id):
    with get_db() as db:
        row = db.execute('SELECT * FROM analyses WHERE id=? AND user_id=?',
                         (analysis_id, session['user_id'])).fetchone()
        if row:
            p = os.path.join(app.config['UPLOAD_FOLDER'], row['image_path'])
            if os.path.exists(p): os.remove(p)
            db.execute('DELETE FROM analyses WHERE id=?', (analysis_id,))
    flash('Record deleted.','success')
    return redirect(url_for('dashboard'))


# ✅ FIX 3: host='0.0.0.0' so it works when deployed online
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, port=port, host='0.0.0.0')
