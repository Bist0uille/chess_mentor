/* Tests unitaires des fonctions pures de engine.js (Node, sans framework). */
const assert = require("assert");
const { whiteEval, formatEval } = require("../app/static/engine.js");

// Convention Lozza : « mate 0 » = mat en 1 ; signe >= 0 ⇒ le trait gagne.
assert.deepStrictEqual(whiteEval({ mate: 0, stm: "w" }), { mate: 1 });   // Blancs matent
assert.strictEqual(formatEval(whiteEval({ mate: 0, stm: "w" })), "#1");

assert.deepStrictEqual(whiteEval({ mate: 0, stm: "b" }), { mate: -1 });  // Noirs matent
assert.strictEqual(formatEval(whiteEval({ mate: 0, stm: "b" })), "#-1");

assert.strictEqual(whiteEval({ mate: 1, stm: "w" }).mate, 2);            // mate 1 = mat en 2
assert.ok(whiteEval({ mate: -1, stm: "w" }).mate < 0);                   // trait maté

// Évaluation en centipions : signe selon le trait.
assert.strictEqual(whiteEval({ cp: 120, stm: "w" }).cp, 120);
assert.strictEqual(whiteEval({ cp: 120, stm: "b" }).cp, -120);

// Formatage.
assert.strictEqual(formatEval({ cp: 230 }), "+2,3");
assert.strictEqual(formatEval({ cp: -150 }), "-1,5");
assert.strictEqual(formatEval(null), "—");

console.log("test_engine.js : OK");
