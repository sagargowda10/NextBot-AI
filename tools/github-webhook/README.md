# GitHub webhook receiver (Flask)

GitHub → ngrok (HTTPS) → `POST /github/webhook` → HMAC-SHA256 signature check → MongoDB Atlas → live dashboard at `/`.

| Endpoint | Purpose |
|---|---|
| `POST /github/webhook` | GitHub deliveries (`ping`, `push`, `workflow_run`, others stored generically). 401 on a bad signature, 202 when accepted, duplicates (redeliveries) ignored by `X-GitHub-Delivery`. |
| `GET /` | Dashboard of recent events, refreshes every 5 s |
| `GET /api/events` | Same as JSON |
| `GET /health` | `{"status": "ok", "store": "mongodb" \| "memory"}` |

```powershell
cd tools\github-webhook
py -3.12 -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then edit GITHUB_WEBHOOK_SECRET and MONGO_URL
python app.py               # http://localhost:5000
python send_test_event.py   # signed test ping -> shows on the dashboard
ngrok http 5000             # public HTTPS URL for GitHub
pytest -q                   # 5 tests (also run in CI)
```
Secrets live only in `tools/github-webhook/.env` (git-ignored) and in GitHub's webhook settings.
