"""Tests E2E (Playwright) — pilotent un vrai navigateur sur le serveur local.

Se skippent proprement si Playwright/Chromium ne sont pas installés.
"""
import pytest

pytest.importorskip("playwright.sync_api")

import chess  # noqa: E402

from app import coach  # noqa: E402


def _select(all_puzzles, white=True, n=1):
    for p in all_puzzles:
        b, sol = coach.position_to_solve(p["fen"], p["moves"])
        if not sol or any(len(m) > 4 for m in sol):   # évite les promotions
            continue
        if (b.turn == chess.WHITE) != white:
            continue
        if (len(sol) + 1) // 2 != n:
            continue
        return p, b, sol
    return None, None, None


def _goto(page, server_url, pid):
    page.goto(f"{server_url}/?puzzle={pid}")
    page.wait_for_function("window.__cm && window.__cm().puzzleId")
    page.wait_for_selector("#board img")  # pièces chargées


def _drag(page, frm, to):
    a = page.locator(f'#board [data-square="{frm}"]').bounding_box()
    b = page.locator(f'#board [data-square="{to}"]').bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=10)
    page.mouse.up()


def test_page_loads(page, server_url):
    page.goto(server_url)
    page.wait_for_function("window.__cm && window.__cm().puzzleId")  # un puzzle est chargé
    page.wait_for_selector("#board [data-square]")
    assert page.locator("#board [data-square]").count() == 64
    assert "Trait aux" in page.locator("#meta").inner_text()  # méta du puzzle affichée


def test_solve_mate_in_one(page, server_url, all_puzzles):
    p, board, sol = _select(all_puzzles, white=True, n=1)
    if not p:
        pytest.skip("pas de mat en 1 (blancs) sans promotion")
    _goto(page, server_url, p["id"])
    _drag(page, sol[0][:2], sol[0][2:4])
    page.wait_for_function("window.__cm().solved === true", timeout=5000)
    st = page.locator("#status").inner_text()
    assert "Résolu" in st
    assert page.locator("#movelog").is_visible()
    # exploration activée après résolution
    assert page.evaluate("window.__cm().explore") is True


def test_wrong_move_shows_refutation(page, server_url, all_puzzles):
    p, board, sol = _select(all_puzzles, white=True, n=1)
    if not p:
        pytest.skip("aucun puzzle adapté")
    # un coup légal différent de la solution
    wrong = next((m.uci() for m in board.legal_moves if m.uci() != sol[0]), None)
    if not wrong:
        pytest.skip("pas de coup alternatif")
    _goto(page, server_url, p["id"])
    _drag(page, wrong[:2], wrong[2:4])
    # la carte de réfutation (moteur) apparaît
    page.wait_for_selector("#refute", state="visible", timeout=8000)
    assert page.locator("#refute").is_visible()


def test_hint_appears(page, server_url, all_puzzles):
    p, _, _ = _select(all_puzzles, white=True, n=1)
    if not p:
        pytest.skip("aucun puzzle adapté")
    _goto(page, server_url, p["id"])
    page.click("#hint")
    page.wait_for_selector("#hints li", timeout=5000)
    assert page.locator("#hints li").count() >= 1


def _select_nonmate(all_puzzles):
    """Puzzle (blancs, sans promo) dont la position finale n'est PAS terminale."""
    for p in all_puzzles:
        b, sol = coach.position_to_solve(p["fen"], p["moves"])
        if not sol or any(len(m) > 4 for m in sol) or b.turn != chess.WHITE:
            continue
        end = b.copy()
        for m in sol:
            end.push(chess.Move.from_uci(m))
        if not end.is_game_over() and any(end.legal_moves):
            return p, b, sol, end
    return None, None, None, None


def test_explore_after_solved(page, server_url, all_puzzles):
    p, board, sol, end = _select_nonmate(all_puzzles)
    if not p:
        pytest.skip("aucun puzzle non-mat adapté")
    _goto(page, server_url, p["id"])
    # joue tous les coups du solveur (l'app répond automatiquement entre chaque)
    for k in range(0, len(sol), 2):
        _drag(page, sol[k][:2], sol[k][2:4])
        page.wait_for_timeout(400)
    page.wait_for_function("window.__cm().solved === true", timeout=6000)
    before = page.evaluate("window.__cm().histLen")
    mv = next(iter(end.legal_moves))               # un coup légal de la position finale
    _drag(page, mv.uci()[:2], mv.uci()[2:4])
    page.wait_for_function(f"window.__cm().histLen > {before}", timeout=5000)
    assert page.evaluate("window.__cm().histLen") > before
