"""Tests de l'annotateur déterministe (explain) et de la notation française."""
import chess

from app import coach, explain


def test_line_notes_robust(all_puzzles):
    for p in all_puzzles:
        board, sol = coach.position_to_solve(p["fen"], p["moves"])
        notes = explain.line_notes(board, sol)
        assert len(notes) == len(sol)
        assert all(isinstance(n, str) and n for n in notes)


def test_french_notation():
    assert coach.to_french_san("Qxe7+") == "Dxe7+"
    assert coach.to_french_san("Nf3") == "Cf3"
    assert coach.to_french_san("Rxe8#") == "Txe8#"
    assert coach.to_french_san("Kg1") == "Rg1"
    assert coach.to_french_san("exd5") == "exd5"      # prise de pion inchangée
    assert coach.to_french_san("O-O") == "O-O"
    assert coach.to_french_san("e8=Q") == "e8=D"


def test_hint_count_and_focus(all_puzzles):
    # 4 indices non vides ; l'indice 4 contient bien la 1re pièce/coup de la solution.
    for p in all_puzzles[:200]:
        board, sol = coach.position_to_solve(p["fen"], p["moves"])
        hints = explain.build_hints(board, sol, p["themes"], 1200)
        assert len(hints) == 4 and all(h for h in hints)
        assert hints[3].startswith("Solution")


def test_capture_gender_agreement():
    # « la tour … défendue » (féminin) et « tu la gagnes ».
    # Position : tour blanche en e1 peut prendre une tour noire non défendue en e8.
    fen = "4r1k1/8/8/8/8/8/8/4R1K1 w - - 0 1"  # Te1 prend Te8 (non défendue)
    board = chess.Board(fen)
    notes = explain.line_notes(board, ["e1e8"])
    assert "défendue" in notes[0]            # accord féminin
    assert "tour" in notes[0]


def test_mate_sentence():
    # Mat du couloir simple : Td1-d8#
    fen = "6k1/5ppp/8/8/8/8/8/3R2K1 w - - 0 1"
    board = chess.Board(fen)
    notes = explain.line_notes(board, ["d1d8"])
    assert "mat" in notes[0].lower()
