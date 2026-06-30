"""Tests de l'endpoint de retours (feedback)."""


def test_feedback_accepts_and_noops_without_kv(client):
    # Sans Vercel KV configuré : on accepte mais on ne stocke pas (pas de crash).
    r = client.post("/api/feedback", json={"text": "super appli", "vote": "up"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stored"] is False


def test_feedback_rejects_empty(client):
    r = client.post("/api/feedback", json={"text": "   ", "vote": None})
    assert r.status_code == 400


def test_feedback_list_requires_key(client):
    # Pas de FEEDBACK_ADMIN_KEY (ou mauvaise clé) → accès refusé.
    assert client.get("/api/feedback/list").status_code == 403
    assert client.get("/api/feedback/list", params={"key": "x"}).status_code == 403


def test_feedback_list_with_key(client, monkeypatch):
    monkeypatch.setenv("FEEDBACK_ADMIN_KEY", "secret123")
    r = client.get("/api/feedback/list", params={"key": "secret123"})
    assert r.status_code == 200
    assert "Retours" in r.text
