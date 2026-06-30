"""Stockage des retours utilisateurs via Vercel KV (Upstash Redis, API REST).

Aucune dépendance : on parle à l'API REST Upstash en HTTP (urllib). Si les
variables d'environnement ne sont pas présentes (dev local), le stockage est
simplement désactivé (les appels renvoient None / [] sans planter).
"""
import json
import os
import urllib.request
from typing import List, Optional

FEEDBACK_KEY = "feedback"


def _creds():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return url, token


def kv_enabled() -> bool:
    url, token = _creds()
    return bool(url and token)


def kv_command(*args) -> Optional[object]:
    """Exécute une commande Redis via l'API REST Upstash. Renvoie `result` ou None."""
    url, token = _creds()
    if not (url and token):
        return None
    body = json.dumps([str(a) for a in args]).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/"),
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8")).get("result")


def push_feedback(record: dict) -> bool:
    """Ajoute un retour (JSON) à la liste. True si stocké, False si KV désactivé."""
    if not kv_enabled():
        return False
    kv_command("RPUSH", FEEDBACK_KEY, json.dumps(record, ensure_ascii=False))
    return True


def list_feedback() -> List[dict]:
    """Renvoie tous les retours (plus récents d'abord)."""
    if not kv_enabled():
        return []
    raw = kv_command("LRANGE", FEEDBACK_KEY, 0, -1) or []
    out = []
    for s in raw:
        try:
            out.append(json.loads(s))
        except (ValueError, TypeError):
            out.append({"text": str(s)})
    out.reverse()
    return out
