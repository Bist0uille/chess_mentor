"""API FastAPI du coach d'échecs."""
import os

import chess
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import coach, db

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

app = FastAPI(title="Chess Mentor — coach de raisonnement")


@app.get("/api/puzzle")
def get_puzzle(min_rating: int = 600, max_rating: int = 2200, min_plies: int = 0):
    if not db.db_exists():
        raise HTTPException(503, "Base absente. Lance d'abord scripts/build_db.py.")
    puz = db.random_puzzle(min_rating, max_rating, min_plies)
    if not puz:
        raise HTTPException(404, "Aucun puzzle dans ces critères.")
    board, solution = coach.position_to_solve(puz["fen"], puz["moves"])
    return {
        "id": puz["id"],
        "fen": board.fen(),  # position À RÉSOUDRE (1er coup adverse déjà joué)
        "rating": puz["rating"],
        "themes": coach.themes_fr(puz["themes"]),
        "side_to_move": "w" if board.turn == chess.WHITE else "b",
        "n_solver_moves": (len(solution) + 1) // 2,  # nombre de coups à trouver
    }


class Attempt(BaseModel):
    id: str
    uci: str          # ex. "f3e5" ou "e7e8q"
    ply: int = 0      # quel coup du solveur (0-based)


@app.post("/api/attempt")
def post_attempt(a: Attempt):
    puz = db.get_puzzle(a.id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    board, solution = coach.board_before_solver_move(puz["fen"], puz["moves"], a.ply)
    idx = 2 * a.ply
    if idx >= len(solution):
        raise HTTPException(400, "Puzzle déjà résolu (ply hors limite).")

    expected = solution[idx]
    correct = a.uci == expected
    if not correct:
        try:
            legal = chess.Move.from_uci(a.uci) in board.legal_moves
        except ValueError:
            legal = False
        return {"correct": False, "legal": legal}

    # Coup correct : on le joue, puis la réponse adverse s'il en reste une.
    board.push_uci(expected)
    result = {"correct": True, "next_ply": a.ply + 1}
    if idx + 1 < len(solution):
        reply = solution[idx + 1]
        reply_move = chess.Move.from_uci(reply)
        result["opponent_uci"] = reply
        result["opponent_san"] = coach.to_french_san(board.san(reply_move))
        board.push(reply_move)
    # Fini s'il ne reste plus de coup solveur après celui-ci.
    result["done"] = (idx + 2) >= len(solution)
    if result["done"]:
        # Ligne complète en SAN pour l'affichage final.
        b2, sol = coach.position_to_solve(puz["fen"], puz["moves"])
        result["line_san"] = coach.solution_san_fr(b2, sol)
    return result


class HintReq(BaseModel):
    id: str
    level: int  # 1..4
    target_elo: int | None = None


@app.get("/api/solution")
def get_solution(id: str):
    """Ligne complète (coups solveur + réponses adverses) pour le rejeu visuel."""
    puz = db.get_puzzle(id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    board, solution = coach.position_to_solve(puz["fen"], puz["moves"])
    return {"uci": solution, "san": coach.solution_san_fr(board, solution)}


@app.post("/api/hint")
def post_hint(req: HintReq):
    puz = db.get_puzzle(req.id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    target = req.target_elo or puz["rating"]
    hints = coach.get_hints(puz, target)
    lvl = max(1, min(req.level, len(hints)))
    return {"level": lvl, "total_levels": len(hints), "hint": hints[lvl - 1]}


@app.get("/api/diag")
def diag():
    """Diagnostic temporaire : pourquoi la narration Claude tombe en repli ?
    N'expose JAMAIS la clé (seulement un booléen)."""
    info = {"key_set": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": coach.MODEL}
    try:
        import anthropic
        info["anthropic_version"] = getattr(anthropic, "__version__", "?")
    except Exception as e:
        info["error_import"] = f"{type(e).__name__}: {e}"
        return info
    if not info["key_set"]:
        info["error"] = "ANTHROPIC_API_KEY absente côté serveur"
        return info
    client = anthropic.Anthropic()
    # 1) appel simple
    try:
        r = client.messages.create(
            model=coach.MODEL, max_tokens=20,
            messages=[{"role": "user", "content": "Réponds uniquement : OK"}],
        )
        info["basic_ok"] = True
        info["basic_sample"] = next((b.text for b in r.content if b.type == "text"), "")
    except Exception as e:
        info["basic_ok"] = False
        info["basic_error"] = f"{type(e).__name__}: {e}"
    # 2) appel structuré (comme en prod)
    try:
        schema = {"type": "object", "properties": {"hints": {"type": "array",
                  "items": {"type": "string"}}}, "required": ["hints"],
                  "additionalProperties": False}
        r = client.messages.create(
            model=coach.MODEL, max_tokens=200,
            messages=[{"role": "user", "content": "Donne 1 indice d'échecs en français."}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        info["structured_ok"] = True
    except Exception as e:
        info["structured_ok"] = False
        info["structured_error"] = f"{type(e).__name__}: {e}"
    return info


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
