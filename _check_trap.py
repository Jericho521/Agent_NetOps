import urllib.request, json

BASE = "http://127.0.0.1:8000/api"
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
    method="POST", headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=5) as r:
    token = json.loads(r.read())["access_token"]
print("login ok")

headers = {"Authorization": f"Bearer {token}"}

def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

print("status:", get("/traps/status"))
print("rules:", len(get("/traps/rules")))
print("logs:", len(get("/traps/logs")))
