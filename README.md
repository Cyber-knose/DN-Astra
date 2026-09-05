# DN ASTRA

**Created by Priyanshu Jangra**

Darknet Threat Intelligence & Website Risk Analyzer — starter implementation.

## Features
- FastAPI backend
- Website/onion URL scanning
- Heuristic phishing and honeypot likelihood assessment
- Browser-observable service/background indicators
- HTML fingerprinting and SHA-256
- Animated cyber-intelligence frontend
- Darknet search-engine reference page
- Optional SOCKS/Tor proxy via `DN_ASTRA_TOR_PROXY`

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000`.

For onion access, configure a local Tor SOCKS proxy and set `DN_ASTRA_TOR_PROXY` before starting the app. Never expose the Tor proxy publicly.

## Production hardening
Run scanning in an isolated container/VM, add authentication, rate limiting, outbound network policy, maximum response size, scan queue/timeouts, audit logs and a separate database. Do not execute downloaded scripts/files.

## Important limitation
The honeypot and phishing values are heuristic risk indicators. A remote website cannot reveal its server's OS-level process list through ordinary HTTP; the tool only reports browser-observable/network-level signals and supplied evidence.


## Creator
DN ASTRA is created by **Priyanshu Jangra**.
