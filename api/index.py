"""Point d'entrée ASGI pour Vercel (@vercel/python détecte la variable `app`)."""
import os
import sys

# Rend le package `app` importable depuis la racine du projet.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (ASGI app exposée à Vercel)
