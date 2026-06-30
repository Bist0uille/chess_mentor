"""Tests des traductions de thèmes (libellés officiels Lichess)."""
from app import coach


def test_official_theme_labels():
    expect = {
        "fork": "Fourchette", "hangingPiece": "Pièce en prise",
        "backRankMate": "Mat du couloir", "quietMove": "Coup silencieux",
        "smotheredMate": "Mat à l'étouffée", "short": "Court problème",
        "middlegame": "Milieu de jeu", "endgame": "Finale",
    }
    for key, fr in expect.items():
        assert coach.THEME_FR.get(key) == fr


def test_themes_fr_ignores_unknown():
    out = coach.themes_fr("fork unknownTheme middlegame")
    assert out == ["Fourchette", "Milieu de jeu"]


def test_themes_fr_empty():
    assert coach.themes_fr("") == []
    assert coach.themes_fr(None) == []
