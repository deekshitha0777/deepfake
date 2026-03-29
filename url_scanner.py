import re
import requests
import tldextract
import validators
from urllib.parse import urlparse
import os

# ─────────────────────────────────────────────
# API KEY — Google Safe Browsing
# Get your free key here: https://developers.google.com/safe-browsing/v4/get-started
# Then replace the string below or set env variable GOOGLE_SAFE_BROWSING_KEY
# ─────────────────────────────────────────────
GOOGLE_SAFE_BROWSING_KEY = os.environ.get('GOOGLE_SAFE_BROWSING_KEY', 'YOUR_GOOGLE_API_KEY_HERE')

SUSPICIOUS_KEYWORDS = [
    "login", "verify", "update", "secure", "account", "bank",
    "paypal", "amazon", "apple", "google", "microsoft", "support",
    "confirm", "signin", "password", "free", "win", "lucky"
]

SHORTENERS = [
    "bit.ly", "tinyurl.com", "t.co", "ow.ly", "goo.gl",
    "buff.ly", "rebrand.ly", "short.io", "is.gd"
]

def check_google_safe_browsing(url):
    """Check URL against Google Safe Browsing API"""
    if GOOGLE_SAFE_BROWSING_KEY == 'YOUR_GOOGLE_API_KEY_HERE':
        return None, "Google Safe Browsing API key not set"
    try:
        api_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={GOOGLE_SAFE_BROWSING_KEY}"
        payload = {
            "client": {"clientId": "deepscan", "clientVersion": "1.0"},
            "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}]
            }
        }
        response = requests.post(api_url, json=payload, timeout=5)
        data = response.json()
        if data.get("matches"):
            threat = data["matches"][0].get("threatType", "THREAT")
            return True, f"Google Safe Browsing: {threat} detected"
        return False, "Google Safe Browsing: No threats found"
    except Exception as e:
        return None, f"Google Safe Browsing check failed: {str(e)}"

def check_url_safety(url: str) -> dict:
    result = {
        "url": url,
        "is_valid": False,
        "is_suspicious": False,
        "risk_score": 0,
        "flags": [],
        "final_url": url,
        "status_code": None,
        "api_result": None
    }

    # 1. Basic validation
    if not validators.url(url):
        result["flags"].append("Invalid URL format")
        return result
    result["is_valid"] = True

    parsed = urlparse(url)
    ext = tldextract.extract(url)
    domain = f"{ext.domain}.{ext.suffix}"

    # 2. Google Safe Browsing API check
    is_threat, api_msg = check_google_safe_browsing(url)
    result["api_result"] = api_msg
    if is_threat is True:
        result["flags"].append(f"🚨 {api_msg}")
        result["risk_score"] += 80

    # 3. HTTPS check
    if parsed.scheme != "https":
        result["flags"].append("No HTTPS — connection is not secure")
        result["risk_score"] += 20

    # 4. URL shortener check
    if domain in SHORTENERS:
        result["flags"].append("URL shortener detected — real destination is hidden")
        result["risk_score"] += 25

    # 5. Suspicious keywords in URL
    url_lower = url.lower()
    found_keywords = [kw for kw in SUSPICIOUS_KEYWORDS if kw in url_lower]
    if found_keywords:
        result["flags"].append(f"Suspicious keywords found: {', '.join(found_keywords)}")
        result["risk_score"] += min(len(found_keywords) * 10, 30)

    # 6. Excessive subdomains (possible spoofing)
    subdomain_count = len(ext.subdomain.split(".")) if ext.subdomain else 0
    if subdomain_count > 2:
        result["flags"].append("Too many subdomains — possible domain spoofing")
        result["risk_score"] += 15

    # 7. IP address used instead of domain
    ip_pattern = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
    if ip_pattern.match(parsed.hostname or ""):
        result["flags"].append("IP address used instead of domain name")
        result["risk_score"] += 20

    # 8. Unusually long URL
    if len(url) > 100:
        result["flags"].append("Unusually long URL — common in phishing links")
        result["risk_score"] += 10

    # 9. Follow redirects and check final destination
    try:
        resp = requests.get(url, timeout=6, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0"})
        result["status_code"] = resp.status_code
        result["final_url"] = resp.url

        if resp.url != url:
            result["flags"].append(f"Redirects to: {resp.url}")
            result["risk_score"] += 10

        if resp.status_code in [403, 404, 500, 503]:
            result["flags"].append(f"Server returned error code: {resp.status_code}")
            result["risk_score"] += 10

    except requests.exceptions.SSLError:
        result["flags"].append("SSL certificate error — site may be unsafe")
        result["risk_score"] += 25
    except requests.exceptions.ConnectionError:
        result["flags"].append("Could not connect to URL")
        result["risk_score"] += 15
    except Exception as e:
        result["flags"].append(f"Request failed: {str(e)}")

    result["risk_score"] = min(result["risk_score"], 100)
    result["is_suspicious"] = result["risk_score"] >= 40

    return result
