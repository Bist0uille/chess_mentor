# ♟️ Chess Mentor — coach de raisonnement

Un coach d'échecs qui n'apprend pas à *mémoriser* des solutions, mais à
**raisonner**. Au lieu de balancer le coup, il identifie les **signaux faibles**
d'une position (roi sans case de fuite, pièce non défendue, pièces alignées,
double attaque…) et déroule un raisonnement progressif, comme un entraîneur.

> L'idée : reproduire ce qu'un joueur fort fait quand il donne un problème 1000
> à un joueur 500 *en expliquant son raisonnement* — ça muscle la façon de
> penser. Utilisable du débutant (800) au joueur avancé (2000+).

## Comment ça marche

```
Base de puzzles Lichess (FEN + solution + rating + thèmes)
            │
            ▼
   signal_detectors.py   ← détecteurs DÉTERMINISTES (python-chess) = vérité-terrain
            │                (pièce en prise, roi enfermé, alignements, double attaque…)
            ▼
        coach.py          ← met les signaux VÉRIFIÉS en mots façon coach
            │                (Claude API ; repli sur gabarits si pas de clé)
            ▼
   FastAPI + échiquier web (chessboard.js) — indices progressifs 1→4, multi-coups
```

Le cœur, ce sont les **détecteurs** : ils calculent des faits vérifiables, qui
**ancrent** la narration du modèle. Le coach n'invente jamais un coup ou une
pièce — il ne reformule que ce que les détecteurs ont prouvé.

## Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# (optionnel) reconstruire la base depuis Lichess — déjà fournie dans data/
python scripts/build_db.py --limit 1500

# narration Claude (sinon : indices-gabarits déterministes)
export ANTHROPIC_API_KEY=sk-ant-...

uvicorn app.main:app --reload   # http://localhost:8000
```

## Déploiement Vercel

Le projet est prêt pour Vercel (Python serverless) :
- `api/index.py` expose l'app ASGI, `vercel.json` route tout vers elle.
- La base `data/puzzles.sqlite` est embarquée (lecture seule).
- Pour activer la narration Claude en ligne : ajouter `ANTHROPIC_API_KEY` dans
  les variables d'environnement du projet Vercel (sinon, indices-gabarits).

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/puzzle?min_rating=&max_rating=&min_plies=` | tire un puzzle (sans la solution) |
| POST | `/api/attempt {id, uci, ply}` | valide le coup du solveur, joue la réponse adverse |
| POST | `/api/hint {id, level}` | indice progressif (1=nudge → 4=ligne) |

## Structure

```
api/index.py            entrée Vercel (ASGI)
app/
  main.py               endpoints FastAPI
  db.py                 accès SQLite
  signal_detectors.py   détecteurs de signaux (le cœur)
  coach.py              indices progressifs + Claude (+ repli gabarits)
  static/               échiquier web (chessboard.js)
data/puzzles.sqlite     base de puzzles (Lichess, CC0)
scripts/build_db.py     (re)construit la base
```

Données : [base ouverte de puzzles Lichess](https://database.lichess.org/) (CC0).
