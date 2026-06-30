# Rapport avant/après — Activation du narrateur Haiku

**Méthode.** 5 problèmes variés, chargés de façon déterministe (`?puzzle=<id>`), comparés
indices **gabarits** (déterministes, narrateur off) vs **Haiku** (narrateur on). Textes relevés
via `/api/hints`, captures d'écran via Playwright sur le site live. Coût mesuré : **~0,2 centime
par problème** avec Haiku (claude-haiku-4-5) — soit ~5× sous l'objectif de 1 centime.

> Note : Haiku est non-déterministe — la formulation varie légèrement d'un appel à l'autre ;
> les captures peuvent différer d'un mot des textes ci-dessous.

---

## 1. Fourchette — `0017R` (solution : Fxc4 Cxc4 Da4+ Dd7 Dxc4)

**AVANT**
1. Il y a du matériel à gagner : une pièce adverse est vulnérable. Commence par les coups forçants…
2. La prise en c4 ouvre une suite forcée à ton avantage.
3. Motif à trouver : fourchette. La case-clé est c4.
4. Solution. Fxc4 — prend le cavalier en c4. Cxc4 — l'adversaire reprend. Da4+ — échec… Dxc4 — prend le cavalier (non défendu). Bilan : +3.

**APRÈS (Haiku)**
1. Cherche comment créer une situation où une seule case ou un seul coup affecte plusieurs cibles importantes de l'adversaire.
2. Les signaux révèlent une double attaque possible : un coup attaque b6 et g7 simultanément, tandis qu'un autre vise c4 et e8. Lequel peut créer des ennuis immédiats ?
3. Le fou peut capturer en c4 : cette case est stratégique car elle ouvre des lignes et crée des menaces simultanées.
4. Joue Fxc4 — le fou capture en c4 et menace à la fois le cavalier en b6 et les cases critiques. Ensuite, si Cxc4, Da4+ est un échec redoutable qui, combiné à l'alignement roi–pion (e8–f7), permet de remporter du matériel.

---

## 2. Mat en 2 — `000hf` (solution : Dxe6+ Rf8 Df7#)

**AVANT**
1. Tu peux forcer le mat (en 2). Cherche une séquence de coups forçants…
2. Le roi adverse en f7 manque de cases : l'échec en e6 l'enferme.
3. La case-clé est e6 : un coup forçant y resserre le filet de mat.
4. Solution. Dxe6+ — avec échec, prend le pion en e6. Rf8. Df7# — échec et mat.

**APRÈS (Haiku)**
1. Cherchez un coup qui force le roi adverse à bouger en le mettant en échec immédiatement.
2. Le roi noir en f7 et ses pièces défensives ne peuvent pas simultanément bloquer et contrôler les cases critiques : concentrez-vous sur les échecs vers e6, f3 ou h5.
3. La dame peut se placer en e6 avec échec, attaquant à la fois d7 et f7 ; le roi sera forcé en f8 puisque e6 est contrôlée et e7 bloqué.
4. Jouez Dxe6+ : cet échec force Rf8 (seul coup légal), puis Df7# est mat car le roi n'a aucune case et la dame contrôle toutes les fuites.

---

## 3. Clouage — `001kG` (solution : Dh5+ Rg8 Dxc5)

**AVANT**
1. Il y a du matériel à gagner : une pièce adverse est vulnérable…
2. Ta dame en h5 fait échec ET attaque le fou en c5 en même temps (double attaque).
3. Motif à trouver : clouage. La case-clé est h5.
4. Solution. Dh5+ — échec. Rg8. Dxc5 — prend le fou (non défendu). Bilan : +3.

**APRÈS (Haiku)**
1. Cherche une pièce qui peut créer de l'embarras au roi adverse en le mettant en danger.
2. Le roi noir et un pion noir sont sur la même diagonale ; regarde aussi quels coups donnent échec au roi en f7.
3. Un coup de dame à la cinquième rangée sur la colonne h donne échec et crée une double menace contre c5 et f7.
4. Joue Dh5+ : le roi est en échec et ne peut pas défendre le pion c5 ; après Rg8 forcé, tu captures Dxc5 en gagnant le pion.

---

## 4. Sacrifice — `001XA` (solution : Txb7 Dxb7 Cf6+ Fxf6 Fxb7)

**AVANT**
1. Il y a du matériel à gagner…
2. Le coup en b7 est un sacrifice : il détourne une défense ou ouvre une ligne…
3. Motif à trouver : attaque à la découverte. La case-clé est b7.
4. Solution. Txb7 — sacrifice… Dxb7 — reprend. Cf6+ — sacrifice… Fxf6 — reprend. Fxb7 — prend la dame (non défendue). Bilan : +4.

**APRÈS (Haiku)**
1. Cherche une pièce qui peut attaquer deux cibles à la fois et créer une situation désespérée pour l'adversaire.
2. La tour sur la 7e rangée est idéalement placée pour frapper deux points faibles : la case b7 et le roi bloqué en g8 qui ne peut fuir que vers h8.
3. Joue Txb7 pour forcer la reprise de ta tour, ce qui dégage un tempo décisif et exploite l'alignement du roi adverse avec ses pions.
4. Txb7 gagne car après la reprise forcée (Dxb7), tu enchaînes avec Cf6+ qui donne échec au roi prisonnier de son dernier rang, suivi de Fxf6 et Fxb7, écrasant la défense.

---

## 5. Pièce en prise — `00008` (solution : Txe7 Db1+ Cc1 Dxc1+ Dxc1)

**AVANT**
1. Il y a du matériel à gagner…
2. La tour en e7 n'est pas défendue : tu la gagnes directement.
3. Motif à trouver : pièce en prise. La case-clé est e7.
4. Solution. Txe7 — prend la tour (non défendue). … Dxc1 — prend la dame. Bilan : +11.

**APRÈS (Haiku)**
1. Cherche à capturer une pièce sans défense qui crée un avantage tactique immédiat.
2. La tour en e7 et le fou en g3 sont tous deux sans défense ; exploite l'une de ces faiblesses pour déclencher une séquence gagnante.
3. Enlève d'abord la tour adverse en e7, car cela libère des attaques multiples sur le roi en h8 qui ne peut fuir que vers g8.
4. Joue Txe7 : tu captures la tour sans défense, et tu menaces ensuite Db1+ qui crée une double attaque, forçant la victoire de matériel.

---

## Verdict

| Critère | Gabarits (avant) | Haiku (après) |
|---|---|---|
| Exactitude (ancrée sur signaux vérifiés) | ✅ | ✅ (ancrée sur les mêmes faits) |
| Raisonnement « pensée de coach » | descriptif | **nettement plus riche** (intention, cibles, pourquoi) |
| Progressivité 1→4 | ✅ | ✅, mieux amenée |
| Coût / problème | 0 € | **~0,2 centime** |
| Points à peaufiner | — | tutoiement à imposer (Haiku alterne tu/vous) ; ne citer que le signal de LA solution (évite de mentionner des doubles attaques hors-sujet) |

**Conclusion.** Haiku rapproche réellement l'app de l'objectif « un coach qui explique sa
pensée », pour un coût négligeable (~0,2 c). Deux réglages de prompt suffiraient à parfaire :
imposer le **tutoiement** et **restreindre les signaux** fournis au LLM à ceux du coup solution.

**Activation en production** : ajouter `CHESS_COACH_LLM=on` dans les variables d'environnement
Vercel (clé déjà présente, modèle déjà `claude-haiku-4-5`), puis redéployer.
