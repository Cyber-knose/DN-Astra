from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from urllib.parse import urlparse
import hashlib, re, time, os
import httpx
from bs4 import BeautifulSoup

app = FastAPI(title="DN ASTRA", version="0.1.0")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(BASE, "frontend")
app.mount("/static", StaticFiles(directory=FRONT), name="static")

ONION_RE = re.compile(r"(?:https?://)?([a-z2-7]{56}\.onion)(?::\d+)?(?:/[^\s<>\"']*)?", re.I)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

class ScanRequest(BaseModel):
    url: HttpUrl


def score_findings(url, html, headers, redirects):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    scripts = soup.find_all("script")
    forms = soup.find_all("form")
    password_inputs = soup.select('input[type="password"]')
    findings = []
    phishing = 0
    honeypot = 0
    behavior = 0

    if urlparse(str(url)).hostname and urlparse(str(url)).hostname.endswith('.onion'):
        findings.append(("Onion service", "Target is a Tor .onion address", "info"))
    if password_inputs:
        phishing += 12; honeypot += 8
        findings.append(("Credential form", f"{len(password_inputs)} password input(s) detected", "warn"))
    if forms:
        behavior += min(15, len(forms) * 4)
        findings.append(("Forms", f"{len(forms)} form(s) detected", "info"))
    suspicious_terms = ["login", "verify your account", "wallet", "seed phrase", "private key", "password", "recovery phrase", "admin panel"]
    hits = [t for t in suspicious_terms if t in text]
    if hits:
        phishing += min(24, len(hits) * 5)
        findings.append(("Sensitive language", ", ".join(hits[:6]), "warn"))
    external = []
    host = urlparse(str(url)).hostname
    for tag in soup.find_all(["script", "img", "iframe", "link", "form"]):
        ref = tag.get("src") or tag.get("href") or tag.get("action")
        if ref and ref.startswith(("http://", "https://")) and host and urlparse(ref).hostname != host:
            external.append(ref)
    if external:
        behavior += min(20, len(external) * 2)
        findings.append(("External resources", f"{len(external)} external resource(s)", "warn"))
    if redirects:
        behavior += min(15, len(redirects) * 5)
        findings.append(("Redirect chain", f"{len(redirects)} redirect(s)", "warn"))
    sw = bool(re.search(r"serviceWorker\.register|navigator\.serviceWorker", html, re.I))
    ws = bool(re.search(r"new\s+WebSocket\s*\(", html, re.I))
    timers = bool(re.search(r"setInterval\s*\(|setTimeout\s*\(", html, re.I))
    if sw:
        behavior += 12; findings.append(("Service worker", "Service-worker registration indicator detected", "warn"))
    if ws:
        behavior += 10; findings.append(("WebSocket", "WebSocket usage indicator detected", "warn"))
    if timers:
        behavior += 4; findings.append(("Background timers", "Periodic/delayed JavaScript activity detected", "info"))

    # Honeypot is a likelihood assessment, not a definitive claim.
    if "captcha" in text or "security check" in text:
        honeypot += 6
    if len(scripts) > 25:
        honeypot += 8; findings.append(("Script density", f"High script count: {len(scripts)}", "info"))
    if "market" in text and ("deposit" in text or "vendor" in text):
        honeypot += 12; findings.append(("Marketplace pattern", "Marketplace/vendor language detected", "warn"))
    if "law enforcement" in text or "honeypot" in text:
        honeypot += 10

    phishing = min(100, phishing)
    behavior = min(100, behavior)
    honeypot = min(100, honeypot)
    risk = min(100, round(phishing * .45 + behavior * .30 + honeypot * .25))
    return findings, phishing, honeypot, behavior, risk, soup


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONT, "index.html"))

@app.get("/search-engines")
def search_engines():
    return FileResponse(os.path.join(FRONT, "search-engines.html"))

@app.post("/api/scan")
async def scan(req: ScanRequest):
    url = str(req.url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(400, "Only HTTP/HTTPS URLs are supported")
    # Opt-in Tor proxy. Default is direct HTTP(S); set DN_ASTRA_TOR_PROXY to enable Tor.
    proxy = os.getenv("DN_ASTRA_TOR_PROXY")
    transport = httpx.AsyncHTTPTransport(proxy=proxy) if proxy else None
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=20.0,
                                     headers={"User-Agent": "DN-ASTRA-Research-Scanner/0.1"}) as client:
            r = await client.get(url)
        elapsed = round((time.perf_counter() - started) * 1000)
        html = r.text[:3_000_000]
        findings, phishing, honeypot, behavior, risk, soup = score_findings(url, html, r.headers, r.history)
        content_hash = hashlib.sha256(html.encode(errors="ignore")).hexdigest()
        title = soup.title.get_text(strip=True) if soup.title else "Untitled"
        host = parsed.hostname or ""
        verdict = "LOW RISK" if risk < 30 else "MODERATE" if risk < 60 else "HIGH RISK" if risk < 80 else "CRITICAL"
        return {
            "target": url, "host": host, "status_code": r.status_code, "response_ms": elapsed,
            "title": title[:160], "content_type": r.headers.get("content-type", "unknown"),
            "content_length": len(r.content), "sha256": content_hash,
            "redirects": [str(x.url) for x in r.history] + ([str(r.url)] if r.url != url else []),
            "onion": host.lower().endswith('.onion'), "phishing": phishing,
            "honeypot": honeypot, "behavior": behavior, "risk": risk, "verdict": verdict,
            "confidence": "LOW" if risk < 25 else "MEDIUM" if risk < 70 else "HIGH",
            "service_worker": any(x[0] == "Service worker" for x in findings),
            "websocket": any(x[0] == "WebSocket" for x in findings),
            "background_timers": any(x[0] == "Background timers" for x in findings),
            "forms": len(soup.find_all('form')), "password_inputs": len(soup.select('input[type="password"]')),
            "scripts": len(soup.find_all('script')), "findings": findings,
            "note": "Assessment is heuristic. It cannot prove that a remote server is a honeypot or expose its OS-level processes."
        }
    except Exception as e:
        raise HTTPException(502, f"Scan failed: {type(e).__name__}: {str(e)[:180]}")
