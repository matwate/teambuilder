// calc.js - damage calculations, one JSON request per line of stdin.
//
// Reads newline-delimited JSON on stdin and writes one JSON response per line
// to stdout, in order. A single request on its own line is just the one-line
// case of that, so the loop costs nothing when only one calc is needed:
//
//   {
//     "id": "any value you want echoed back",   // optional
//     "gen": 0,                                 // optional, 0-9, default 0
//     "attacker": {"name": "Rillaboom",
//                  "opts": {"item": "Choice Band", "nature": "Adamant",
//                           "evs": {"atk": 32}, "boosts": {"atk": 1}}},
//     "defender": {"name": "Snorlax",
//                  "opts": {"evs": {"hp": 32, "def": 32}}},
//     "move": "Grassy Glide",                   // or {"name": ..., "isCrit": true}
//     "field": {"terrain": "Grassy",            // optional
//               "defenderSide": {"isReflect": true}}
//   }
//
// Every key inside "opts"/"field" is passed straight through to the library,
// so the full option sets are the ones in damage-calc/calc/src/state.ts:
// State.Pokemon, State.Move, State.Field and State.Side.
//
// In Champions (gen 0) "evs" carries STAT POINTS, 0-32, not EVs - the library
// takes the number as-is (stats.ts: calcStatChampions). See STAT POINTS below.
const {calculate, Generations, Pokemon, Move, Field} = require('@smogon/calc');

// The library reports the errors it was told to suppress with console.log
// (util.ts: error), which would land in the middle of the JSON on stdout - a
// zero-damage roll prints two such lines. Anything it prints goes to stderr
// instead, leaving stdout as one JSON response per line and nothing else.
console.log = (...args) => console.error(...args);
const write = (value) => process.stdout.write(JSON.stringify(value) + "\n");

// Pokemon Champions is generation 0: calc.ts dispatches on MECHANICS[gen.num]
// and slot 0 is calculateChampions, ahead of RBY at 1. That only exists in the
// git checkout under damage-calc/ - the published @smogon/calc 0.11.0 stops at
// GenerationNum 1-9 and has no champions mechanics at all, so gen 0 there
// silently runs RBY against missing data. See the README for the build.
// Generations.get does not validate its argument, and a bad one only surfaces
// later as "Cannot read properties of undefined", so check it here.
const DEFAULT_GEN = 0;
const champions = Generations.get(DEFAULT_GEN);
if (
  !champions ||
  !champions.species ||
  !champions.moves ||
  !champions.species.get('pikachu') ||
  !champions.moves.get('thunderbolt')
) {
  throw new Error(
    'The installed @smogon/calc package does not include Pokémon Champions generation 0 data.'
  );
}

// STAT POINTS: Champions replaced EVs with stat points, and the calculator
// models that by reading the "evs" field as stat points when gen is 0:
//
//   hp    = base + sp + 75          (stats.ts: calcStatChampions)
//   other = floor(nature * (base + sp + 20))
//
// So do NOT convert with EV = 8 * sp - 4: pass the stat point value itself.
// Nothing clamps it - 252 stat points is accepted and quietly returns a
// Rillaboom with 436 Atk - so the range is enforced here instead. Level and
// IVs are ignored entirely in gen 0 (pokemon.ts forces level 50 and IVs 31).
const MAX_STAT_POINTS = 32;

function respond(request) {
  const num = request.gen === undefined ? DEFAULT_GEN : request.gen;
  if (!Number.isInteger(num) || num < 0 || num > 9) {
    throw new Error(`gen must be an integer 0-9, got ${JSON.stringify(request.gen)}`);
  }
  const gen = Generations.get(num);

  const attacker = pokemon(gen, request.attacker, 'attacker');
  const defender = pokemon(gen, request.defender, 'defender');

  // A move may be given as a bare name or as an object with extra options.
  const move = typeof request.move === 'string' ? {name: request.move} : request.move;
  if (!move || !move.name) throw new Error('move is required');
  if (!gen.moves.get(toID(move.name))) throw new Error(`unknown move: ${move.name}`);

  const result = calculate(
    gen, attacker, defender, new Move(gen, move.name, move), new Field(request.field || {})
  );

  const [min, max] = result.range();
  const maxHP = defender.maxHP();
  const response = {
    // fullDesc throws on a zero-damage roll (an immunity: Earthquake into a
    // Flying type) unless err is false, and an immunity is a legitimate
    // answer to ask for, not a failure - desc.ts:282.
    desc: result.fullDesc('%', false),
    // Multi-hit moves give an array per hit, so this is passed through as-is.
    rolls: result.damage,
    range: [min, max],
    // What the range means for this defender, which is the part worth reading.
    percent: [round(100 * min / maxHP), round(100 * max / maxHP)],
    // kochance throws on some move/field combinations it cannot describe;
    // false asks it to stay quiet instead, and it can still return no text.
    koChance: result.kochance(false).text || null,
    defenderMaxHP: maxHP,
  };
  if (request.id !== undefined) response.id = request.id;
  return response;
}

function pokemon(gen, side, which) {
  if (!side || !side.name) throw new Error(`${which}.name is required`);
  // Unknown species also fail late and unhelpfully inside the constructor.
  if (!gen.species.get(toID(side.name))) throw new Error(`unknown species: ${side.name}`);
  const opts = side.opts || {};
  if (gen.num === 0) checkStatPoints(opts.evs, which);
  return new Pokemon(gen, side.name, opts);
}

function checkStatPoints(evs, which) {
  for (const [stat, sp] of Object.entries(evs || {})) {
    if (!Number.isInteger(sp) || sp < 0 || sp > MAX_STAT_POINTS) {
      throw new Error(
        `${which}.opts.evs.${stat} must be 0-${MAX_STAT_POINTS} stat points in Champions, ` +
        `got ${JSON.stringify(sp)} (EV spreads do not carry over)`
      );
    }
  }
}

// The library indexes its data by ID, not by display name: "Choice Band" is
// choiceband, "Farfetch'd" is farfetchd. util.toID is not exported, so the
// same normalisation is repeated here for the existence checks above.
function toID(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function round(n) {
  return Math.round(n * 10) / 10;
}

// One bad line reports its own error and the rest still run, so a long batch
// is never lost to a single typo. The exit code says whether any line failed.
let failed = false;

function answer(line) {
  let id;
  try {
    const request = JSON.parse(line);
    id = request.id;
    return respond(request);
  } catch (err) {
    // Stay JSON on the way out too, so the caller parses one format either
    // way, and keep the id so a failure is still matched to its request.
    failed = true;
    return id === undefined ? {error: err.message} : {error: err.message, id};
  }
}

if (process.argv.includes('--serve')) {
  // Long-lived: answer each line as it arrives and stay up until stdin
  // closes, so the caller pays node's startup once rather than per batch.
  // calc.py keeps one of these running - see calculate() there.
  require('readline')
    .createInterface({input: process.stdin})
    .on('line', (line) => { if (line.trim()) write(answer(line)); });
} else {
  for (const line of require('fs').readFileSync(0, 'utf8').split('\n')) {
    if (line.trim()) write(answer(line));
  }
  if (failed) process.exitCode = 1;
}
