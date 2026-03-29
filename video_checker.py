import cv2
import requests
import os
import tempfile

# ─────────────────────────────────────────────
# SightEngine API — same keys you use for images
# ─────────────────────────────────────────────
SIGHTENGINE_USER   = os.environ.get('SIGHTENGINE_USER',   '1386884004')
SIGHTENGINE_SECRET = os.environ.get('SIGHTENGINE_SECRET', '7TidexJ3WdN9v7pDrrA5WcLp34CAT9Ye')

def load_model():
    """No local model needed — we use SightEngine API"""
    return "sightengine"

def extract_frames(video_path, max_frames=5):
    """Extract up to max_frames evenly spaced frames from video"""
    frames = []
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return frames

    # Pick evenly spaced frame indices
    indices = [int(total * i / max_frames) for i in range(max_frames)]

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)

    cap.release()
    return frames

def analyse_frame(frame):
    """Send a single frame to SightEngine API and get AI score"""
    try:
        # Save frame to a temp file
        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        cv2.imwrite(tmp.name, frame)
        tmp.close()

        with open(tmp.name, 'rb') as f:
            response = requests.post(
                'https://api.sightengine.com/1.0/check.json',
                files={'media': f},
                data={
                    'models': 'genai',
                    'api_user': SIGHTENGINE_USER,
                    'api_secret': SIGHTENGINE_SECRET
                },
                timeout=15
            )
        os.unlink(tmp.name)

        result = response.json()
        if result.get('status') == 'success':
            return result.get('type', {}).get('ai_generated', 0)
        return None

    except Exception as e:
        print(f"Frame analysis error: {e}")
        return None

def analyse_video(video_path: str, model=None) -> dict:
    """
    Analyse video by extracting frames and checking each with SightEngine.
    Returns verdict, confidence, and frame details.
    """
    result = {
        "verdict": "Unknown",
        "is_fake": False,
        "confidence": 0,
        "frames_analysed": 0,
        "total_frames": 0,
        "duration_seconds": 0,
        "error": None
    }

    # Get video info
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    result["total_frames"] = total_frames
    result["duration_seconds"] = round(total_frames / fps, 1) if fps else 0

    # Extract frames
    frames = extract_frames(video_path, max_frames=5)

    if not frames:
        result["error"] = "Could not extract frames from video"
        result["verdict"] = "Error"
        return result

    # Analyse each frame
    scores = []
    for frame in frames:
        score = analyse_frame(frame)
        if score is not None:
            scores.append(score)

    if not scores:
        result["error"] = "API analysis failed for all frames"
        result["verdict"] = "Error"
        return result

    # Calculate average AI score across all frames
    avg_score = sum(scores) / len(scores)
    ai_percent = round(avg_score * 100, 1)
    real_percent = round(100 - ai_percent, 1)

    result["frames_analysed"] = len(scores)

    if avg_score >= 0.7:
        result["verdict"] = "FAKE / AI-Generated"
        result["is_fake"] = True
        result["confidence"] = ai_percent
    elif avg_score >= 0.4:
        result["verdict"] = "Possibly Fake"
        result["is_fake"] = True
        result["confidence"] = ai_percent
    else:
        result["verdict"] = "REAL"
        result["is_fake"] = False
        result["confidence"] = real_percent

    return result
