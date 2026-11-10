"""Sheet 5_Performance, 'Document processing time (upload to ready)', and sheet 4 row I4 (60+ chunks, batches of 50).
Uploads each file to YOUR company, waits until the document is ready or failed, and prints one table row per file.
Cost: one embedding call per 50 chunks (a 20-page PDF is usually 2-5 calls). Env: ADMIN_EMAIL, ADMIN_PASSWORD.
  python real_run/run_ingestion_timing.py HR_Policy.pdf Safety.docx
Make sure the company service is started or at least that documents may be uploaded (see RUNBOOK)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from common import client, env, hdr, login

if len(sys.argv) < 2:
    sys.exit(__doc__)
c = client()
h = hdr(login(c, env("ADMIN_EMAIL"), env("ADMIN_PASSWORD")))
print("Document | Type | Size (MB) | Chunks created | Processing time (s) | Result")
for path in sys.argv[1:]:
    name = os.path.basename(path)
    data = open(path, "rb").read()
    t = time.perf_counter()
    r = c.post("/company/documents", headers=h, files=[("files", (name, data))])
    if r.status_code != 202:
        print(f"{name} | upload refused: {r.status_code} {r.text[:150]}"); continue
    doc = None
    while time.perf_counter() - t < 900:
        time.sleep(1)
        docs = [d for d in c.get("/company/documents", headers=h).json() if d["filename"] == name]
        doc = docs[0] if docs else None
        if doc and doc["status"] in ("ready", "failed"):
            break
    secs = time.perf_counter() - t
    if not doc:
        print(f"{name} | not found after upload"); continue
    print(f"{name} | {doc['file_type']} | {len(data) / 1e6:.2f} | {doc['chunks']} | {secs:.1f} | {doc['status']}{' - ' + str(doc['error_message']) if doc['error_message'] else ''}")
