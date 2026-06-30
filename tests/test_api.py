"""Tests des endpoints de l'API (TestClient FastAPI)."""
from app import coach, db


def test_puzzle_shape(client):
    p = client.get("/api/puzzle").json()
    assert set(["id", "fen", "rating", "themes", "side_to_move", "n_solver_moves"]) <= p.keys()
    assert p["side_to_move"] in ("w", "b")
    assert p["n_solver_moves"] >= 1


def test_puzzle_by_id(client, all_puzzles):
    pid = all_puzzles[0]["id"]
    p = client.get(f"/api/puzzle?id={pid}").json()
    assert p["id"] == pid  # déterminisme (lien partageable / e2e)


def test_hints_four(client):
    pid = client.get("/api/puzzle").json()["id"]
    h = client.get(f"/api/hints?id={pid}").json()["hints"]
    assert len(h) == 4 and all(h)


def test_solution_shape(client):
    pid = client.get("/api/puzzle").json()["id"]
    s = client.get(f"/api/solution?id={pid}").json()
    assert len(s["uci"]) == len(s["san"]) == len(s["notes"]) >= 1


def test_attempt_wrong(client):
    pid = client.get("/api/puzzle").json()["id"]
    r = client.post("/api/attempt", json={"id": pid, "uci": "a1a1", "ply": 0}).json()
    assert r["correct"] is False


def test_diag_removed(client):
    assert client.get("/api/diag").status_code == 404


def test_perfect_player_full(client, all_puzzles):
    """Le joueur parfait résout 100% de la base via l'API (multi-coups)."""
    solved = 0
    for p in all_puzzles:
        _, sol = coach.position_to_solve(p["fen"], p["moves"])
        ply, ok = 0, True
        while True:
            r = client.post("/api/attempt",
                            json={"id": p["id"], "uci": sol[2 * ply], "ply": ply}).json()
            if not r.get("correct"):
                ok = False
                break
            if r["done"]:
                break
            ply = r["next_ply"]
        solved += int(ok)
    assert solved == len(all_puzzles), f"{solved}/{len(all_puzzles)}"
