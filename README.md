# DeepScan — AI Deepfake Detection Website

## Setup & Run

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Gemini API Key
**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```
**Windows (CMD):**
```cmd
set GEMINI_API_KEY=your-api-key-here
```
**Linux/Mac:**
```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 3. Run the app
```bash
python app.py
```
Then open: http://127.0.0.1:5000

---

## Project Structure
```
deepfake_detector/
├── app.py               ← Flask backend (routes, DB, Gemini API)
├── deepfake.db          ← SQLite database (auto-created)
├── requirements.txt
├── uploads/             ← Uploaded images (auto-created)
├── templates/
│   ├── base.html        ← Shared layout
│   ├── index.html       ← Landing page
│   ├── login.html       ← Login page
│   ├── register.html    ← Register page
│   ├── dashboard.html   ← User dashboard + upload
│   └── result.html      ← Analysis result page
└── static/
    ├── css/style.css    ← All styles
    └── js/main.js       ← Drag-drop, preview, UI
```

## Database Schema
- **users**: id, username, password (SHA-256 hashed), created
- **analyses**: id, user_id, image_path, result, confidence, detail, uploaded_at

## Get a Gemini API Key
1. Go to https://aistudio.google.com/app/apikey
2. Create a free API key
3. Set it as GEMINI_API_KEY environment variable
