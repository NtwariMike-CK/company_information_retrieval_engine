"""Generate a Postman v2.1 collection from the FastAPI OpenAPI schema.
Usage (from backend/):  python scripts/export_postman.py ../postman/company-rag.postman_collection.json"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402

spec = app.openapi()


def deref(s):
    if "$ref" in s:
        node = spec
        for part in s["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return deref(node)
    return s


def example(s, depth=0):
    s = deref(s)
    if "anyOf" in s:
        non_null = [x for x in s["anyOf"] if x.get("type") != "null"]
        return example(non_null[0], depth) if non_null else None
    if "example" in s: return s["example"]
    if s.get("default") is not None and s.get("type") != "object": return s["default"]
    t = s.get("type")
    if "enum" in s: return s["enum"][0]
    if t == "object" or "properties" in s:
        if depth > 3: return {}
        req = set(s.get("required", []))
        return {k: example(v, depth + 1) for k, v in s.get("properties", {}).items() if k in req or "default" in deref(v) or depth == 0}
    if t == "array": return [example(s.get("items", {}), depth + 1)]
    if t == "string":
        f = s.get("format")
        return {"email": "user@example.com", "uuid": "{{id}}", "date-time": "2026-01-01T00:00:00Z"}.get(f, "string")
    if t == "integer": return s.get("minimum", 1)
    if t == "number": return 0.5
    if t == "boolean": return True
    return None


folders = {}
for path, methods in spec["paths"].items():
    for method, op in methods.items():
        tag = (op.get("tags") or ["Other"])[0]
        url_path = path.replace("{", ":").replace("}", "")
        req = {"method": method.upper(), "header": [], "description": op.get("description", op.get("summary", "")),
               "url": {"raw": "{{baseUrl}}" + url_path, "host": ["{{baseUrl}}"], "path": url_path.strip("/").split("/"),
                       "variable": [{"key": p["name"], "value": "{{id}}"} for p in op.get("parameters", []) if p["in"] == "path"],
                       "query": [{"key": p["name"], "value": "", "disabled": True} for p in op.get("parameters", []) if p["in"] == "query"]}}
        body = (op.get("requestBody") or {}).get("content", {})
        if "application/json" in body:
            req["header"].append({"key": "Content-Type", "value": "application/json"})
            req["body"] = {"mode": "raw", "raw": json.dumps(example(body["application/json"]["schema"]), indent=2), "options": {"raw": {"language": "json"}}}
        elif "multipart/form-data" in body:
            req["body"] = {"mode": "formdata", "formdata": [{"key": "files", "type": "file", "src": []}]}
        item = {"name": op.get("summary") or f"{method.upper()} {path}", "request": req, "response": []}
        if path in ("/auth/login", "/public/register"):
            item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                "const r = pm.response.json();",
                "if (r.access_token) { pm.collectionVariables.set('token', r.access_token); }"]}}]
        if path.endswith("/impersonate"):
            item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                "const r = pm.response.json();", "if (r.access_token) { pm.collectionVariables.set('token', r.access_token); }"]}}]
        folders.setdefault(tag, []).append(item)

collection = {
    "info": {"name": "Company RAG Chatbot API", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
             "description": "1) Run Auth > Log in with a user body. The token is saved automatically. 2) Call any endpoint. Replace {{id}} path variables."},
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
    "variable": [{"key": "baseUrl", "value": "http://localhost:8000"}, {"key": "token", "value": ""}, {"key": "id", "value": ""}],
    "item": [{"name": t, "item": items} for t, items in sorted(folders.items(), key=lambda kv: ["Auth", "SuperAdmin", "Company Admin", "Employee Chat"].index(kv[0]) if kv[0] in ["Auth", "SuperAdmin", "Company Admin", "Employee Chat"] else 9)],
}
out = Path(sys.argv[1] if len(sys.argv) > 1 else "company-rag.postman_collection.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(collection, indent=2))
print(f"wrote {out} ({sum(len(i['item']) for i in collection['item'])} requests)")
