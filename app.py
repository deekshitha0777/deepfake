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
        import cv2
        import numpy as np
        from PIL import Image as PILImage
        import math

        img_pil = PILImage.open(image_path).convert('RGB')
        img_array = np.array(img_pil)
        img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # ── Resize for consistent analysis ──
        img_resized = cv2.resize(img, (512, 512))
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)

        suspicious_signals = []
        real_signals = []

        # ── 1. Error Level Analysis (ELA) ──
        # AI images often have suspiciously uniform error levels
        temp_path = image_path + "_temp_ela.jpg"
        PILImage.fromarray(cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)).save(
            temp_path, 'JPEG', quality=75)
        compressed = cv2.imread(temp_path)
        os.remove(temp_path)
        ela = cv2.absdiff(img_resized, compressed).astype(np.float32)
        ela_mean = np.mean(ela)
        ela_std = np.std(ela)
        ela_uniformity = ela_std / (ela_mean + 1e-6)

        if ela_uniformity < 0.8:
            suspicious_signals.append(f"ELA uniformity too smooth ({ela_uniformity:.2f})")
        else:
            real_signals.append(f"ELA variation normal ({ela_uniformity:.2f})")

        # ── 2. Noise Pattern Analysis ──
        # Real cameras have natural sensor noise; AI images are too clean or have fake noise
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        noise_map = cv2.absdiff(gray, blur).astype(np.float32)
        noise_mean = np.mean(noise_map)
        noise_std = np.std(noise_map)

        if noise_mean < 3.5:
            suspicious_signals.append(f"Too clean - no natural sensor noise ({noise_mean:.2f})")
        elif noise_mean > 25:
            suspicious_signals.append(f"Artificial noise pattern detected ({noise_mean:.2f})")
        else:
            real_signals.append(f"Natural noise level ({noise_mean:.2f})")

        # ── 3. Frequency Domain Analysis (DCT) ──
        # AI generators leave distinct frequency artifacts
        dct = cv2.dct(np.float32(gray))
        high_freq = dct[64:, 64:]
        low_freq = dct[:64, :64]
        freq_ratio = np.mean(np.abs(high_freq)) / (np.mean(np.abs(low_freq)) + 1e-6)

        if freq_ratio < 0.01:
            suspicious_signals.append(f"Missing high-frequency detail (ratio {freq_ratio:.4f})")
        else:
            real_signals.append(f"Healthy frequency distribution ({freq_ratio:.4f})")

        # ── 4. Color Channel Correlation ──
        # AI images often have unnaturally correlated RGB channels
        r, g, b = img_resized[:,:,2], img_resized[:,:,1], img_resized[:,:,0]
        rg_corr = np.corrcoef(r.flatten(), g.flatten())[0,1]
        rb_corr = np.corrcoef(r.flatten(), b.flatten())[0,1]
        avg_corr = (abs(rg_corr) + abs(rb_corr)) / 2

        if avg_corr > 0.97:
            suspicious_signals.append(f"Unnaturally high channel correlation ({avg_corr:.3f})")
        else:
            real_signals.append(f"Normal channel correlation ({avg_corr:.3f})")

        # ── 5. Edge Consistency Analysis ──
        # AI images often have overly smooth or perfectly consistent edges
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.mean(edges) / 255.0
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        if laplacian_var < 50:
            suspicious_signals.append(f"Over-smooth edges (sharpness: {laplacian_var:.1f})")
        elif edge_density < 0.02:
            suspicious_signals.append(f"Too few natural edges ({edge_density:.4f})")
        else:
            real_signals.append(f"Natural edge complexity ({laplacian_var:.1f})")

        # ── 6. JPEG Artifact Consistency ──
        # Real photos have consistent JPEG block artifacts; AI images often don't
        h, w = gray.shape
        block_vars = []
        for i in range(0, min(h, 256), 8):
            for j in range(0, min(w, 256), 8):
                block = gray[i:i+8, j:j+8]
                if block.shape == (8, 8):
                    block_vars.append(np.var(block))
        if block_vars:
            block_consistency = np.std(block_vars) / (np.mean(block_vars) + 1e-6)
            if block_consistency < 0.5:
                suspicious_signals.append(f"Unnaturally uniform block structure ({block_consistency:.3f})")
            else:
                real_signals.append(f"Natural block variation ({block_consistency:.3f})")

        # ── Final Decision ──
        total_signals = len(suspicious_signals) + len(real_signals)
        suspicious_count = len(suspicious_signals)
        real_count = len(real_signals)

        # Weighted scoring
        if total_signals == 0:
            verdict = "Unknown"
            confidence = 50
        elif suspicious_count >= 4:
            verdict = "AI-Generated / Deepfake"
            confidence = min(95, 60 + (suspicious_count * 7))
        elif suspicious_count == 3:
            verdict = "Likely AI-Generated"
            confidence = min(85, 55 + (suspicious_count * 6))
        elif suspicious_count == 2:
            verdict = "Possibly AI-Generated"
            confidence = 55
        elif real_count >= 4:
            verdict = "Likely Real Image"
            confidence = min(92, 60 + (real_count * 6))
        else:
            verdict = "Real Image"
            confidence = min(88, 65 + (real_count * 5))

        details = "🔴 Suspicious signals: " + ("; ".join(suspicious_signals) if suspicious_signals else "None")
        details += " | ✅ Real signals: " + ("; ".join(real_signals) if real_signals else "None")

        return {
            "verdict": verdict,
            "confidence": confidence,
            "details": details
        }

    except Exception as e:
        return {
            "verdict": "Error",
            "confidence": 0,
            "details": f"Analysis failed: {str(e)}"
        }


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
