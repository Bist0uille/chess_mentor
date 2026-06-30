# Analyse — Chess Mentor face au besoin initial

> Document d'évaluation. Met en regard l'idée de départ et l'application livrée,
> avec les résultats des tests automatiques et un backlog priorisé.

## 1. Le besoin initial

> Face à un problème d'échecs (≈ 2000 sur Lichess/Chess.com), on est « dans le vague » :
> on voit la solution mais pas **le raisonnement qui y mène**. L'idée : un **coach** qui
> **repère les signaux faibles** (roi sans fuite, pièce non défendue, pièces alignées,
> défenseur surchargé…) et **explique sa façon de penser**, comme quand on donne un
> problème 1000 à un joueur 500 en verbalisant son raisonnement. Utilisable **du 500 au
> 2000**, l'objectif étant de muscler la *manière de raisonner*, pas de mémoriser.

Critères de réussite implicites :
- (A) Identifier des **signaux vérifiés** d'une position (pas du vague).
- (B) **Expliquer le raisonnement** menant à la solution.
- (C) Aide **progressive** (indice léger → solution).
- (D) Comprendre **pourquoi un coup marche** et **pourquoi un autre échoue**.
- (E) **Adapté au niveau** (500 → 2000).

## 2. Ce qui est livré

| Domaine | Livré |
|---|---|
| Données | Base Lichess (CC0) embarquée, ~1500 puzzles notés + thèmes officiels FR |
| Détecteurs (A) | `signal_detectors.py` : pièce en prise/sous-défendue, sécurité du roi (cases de fuite, dernier rang), alignements, doubles attaques, échecs/coups forçants — **déterministe, vérifié** |
| Explication (B) | `explain.py` : annotateur qui **décortique la solution coup par coup** (échec qui force, capture défendue/non, sacrifice, interposition, coup tranquille + menace, réponse forcée, mat) ; **liste cumulative « Pourquoi ces coups »** |
| Indices progressifs (C) | 4 niveaux centrés sur la solution : orientation → signal clé du 1er coup → motif + case-clé → solution expliquée |
| Pourquoi ça échoue (D) | Moteur **Lozza** (navigateur) : **réfutation chiffrée** des mauvais coups + flèche rouge, **barre d'évaluation** |
| Multi-coups | Résolution complète (réponses adverses jouées), navigateur ⏮◀▶⏭ + flèches clavier |
| Exploration | Jeu libre après résolution (voir la suite) |
| i18n | 100 % français : thèmes (libellés Lichess), notation française R/D/T/F/C |
| Plateforme | Web (échiquier cliquable, flèches clic-droit, cases légales, promotion), thème sombre, responsive, déployé sur Vercel |

## 3. Résultats des tests automatiques

`bash scripts/test.sh` — **25 tests pytest + 1 test JS, tous verts.**
- Détecteurs : couverture des thèmes (fourchette, mat du couloir, pièce en prise, mat en 1) **8/8**.
- Annotateur `explain` : **1500/1500** puzzles → notes cohérentes (longueur = solution, non vides),
  accords en genre, notation FR.
- API : formes correctes ; **joueur parfait multi-coups 1500/1500** ; `?id=` déterministe.
- i18n : libellés alignés sur Lichess ; thèmes inconnus ignorés.
- JS (moteur) : convention de mat de Lozza et signes d'évaluation corrects.
- E2E (Playwright) : chargement, **résolution par glisser**, **réfutation**, **indice**,
  **exploration** — OK.

## 4. Adéquation au besoin

### Ce qui répond bien
- **(A) Signaux faibles** : réellement calculés et vérifiés — pas de vague, pas d'hallucination.
- **(C) Progressivité** : l'échelle 4 indices correspond exactement à l'esprit « du vague au précis ».
- **(D) Pourquoi ça échoue** : la réfutation moteur est concrète et chiffrée — gros atout pédagogique,
  et **gratuit** (navigateur).
- **(B) partiellement** : chaque coup de la solution est expliqué factuellement et correctement.

### Écarts vs l'objectif « pensée de grand maître »
1. **Explications factuelles, pas un vrai raisonnement de GM.** L'annotateur dit *ce que fait* un
   coup (échec, capture, fourchette…), mais pas la **démarche** d'un fort joueur : génération de
   coups-candidats, **élimination** des alternatives, plan, « j'ai d'abord regardé les coups
   forçants parce que… ». C'est la conséquence directe d'avoir **désactivé le LLM** (coût). →
   *écart principal vis-à-vis de l'intention de départ.*
2. **« Pourquoi pas cet autre bon coup ? »** absent côté indices : la réfutation ne se déclenche que
   si l'utilisateur **joue** un coup. On ne compare pas spontanément la solution aux alternatives
   plausibles.
3. **(E) Adaptation au niveau encore légère.** Le niveau choisi filtre la difficulté et ajuste un
   peu le ton, mais les explications ne sont pas vraiment **reformulées** pour un 500 vs un 2000.
4. **Couverture limitée** : ~1500 puzzles (sous-ensemble), pas toute la base Lichess ; pas de suivi
   de progression / répétition espacée / profil joueur.
5. **Détails** : sous-promotion forcée en dame en mode exploration ; pas de son ; le moteur Lozza
   (≈ 2400) suffit pour réfuter mais est en deçà de Stockfish pour les positions très subtiles.

## 5. Backlog priorisé

| Priorité | Action | Impact | Effort |
|---|---|---|---|
| ⭐⭐⭐ | **Réactiver le LLM en hybride** (ancré sur `explain`+signaux) pour une vraie prose de coach adaptée au niveau — déjà câblé (`CHESS_COACH_LLM=on`), reste à soigner le prompt « raisonnement candidat/élimination » et à le rendre activable par l'utilisateur | Comble l'écart #1 et #3 | Moyen |
| ⭐⭐⭐ | **Coups-candidats & « pourquoi pas X »** : utiliser Lozza pour proposer 2-3 coups plausibles et expliquer pourquoi ils sont moins bons (sans attendre une erreur) | Comble #2, cœur du « raisonnement » | Moyen |
| ⭐⭐ | **Adapter les explications au niveau** (500 : plus guidé/encourageant ; 2000 : plus dense, vocabulaire technique) — côté gabarits et/ou LLM | #3, fidélité « 500→2000 » | Faible-moyen |
| ⭐⭐ | **Élargir la base** (plus de puzzles, filtres par motif/thème) + choisir un thème précis à travailler | #4 | Faible |
| ⭐ | **Profil & progression** : historique, puzzles ratés à revoir, rating perso | rétention | Moyen |
| ⭐ | Sous-promotion choisie en exploration ; option moteur Stockfish-WASM ; sons | finitions | Faible |

## Conclusion

L'application **répond bien au socle** du besoin (signaux vérifiés, indices progressifs,
explication des bons et mauvais coups, le tout en français et gratuit). Le **principal écart**
avec l'ambition « un grand maître qui explique sa pensée » vient de la **désactivation du LLM**
pour maîtriser les coûts : les explications sont justes mais restent *descriptives* plutôt que
*stratégiques* (candidats, élimination, plan). Les deux chantiers à plus fort impact sont donc
la **narration LLM hybride** et l'**analyse des coups-candidats** — les deux s'appuient sur des
fondations déjà en place (`explain.py`, moteur Lozza, flag `CHESS_COACH_LLM`).
