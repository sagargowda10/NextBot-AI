"""Send a signed fake GitHub 'ping' or 'push' to your receiver - tests the setup without GitHub.

python send_test_event.py                                         # -> http://localhost:5000
python send_test_event.py https://YOUR-NGROK-URL.ngrok-free.app push  # through ngrok
"""

import hashlib
import hmac
import json
import os
import sys
import urllib.request
import uuid

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/")
event = sys.argv[2] if len(sys.argv) > 2 else "ping"
secret = os.environ["GITHUB_WEBHOOK_SECRET"]
payload = {
    "ping": {
        "zen": "Test delivery from send_test_event.py",
        "repository": {"full_name": "local/test"},
    },
    "push": {
        "ref": "refs/heads/main",
        "repository": {"full_name": "local/test"},
        "pusher": {"name": "local-test"},
        "head_commit": {"message": "Test commit from send_test_event.py"},
        "commits": [
            {"id": uuid.uuid4().hex, "message": "Test commit from send_test_event.py"}
        ],
    },
}[event]
body = json.dumps(payload).encode()
req = urllib.request.Request(
    f"{base}/github/webhook",
    data=body,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": str(uuid.uuid4()),
        "X-Hub-Signature-256": "sha256="
        + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "ngrok-skip-browser-warning": "1",
    },
)
with urllib.request.urlopen(req, timeout=15) as res:
    print(res.status, res.read().decode())
