# Handoff: teambuilder review and work plan

- Date: 2026-11-10
- From: Claude (review session with Mateo)
- To: Claude Code

## 1. How to use this document

- This document comes from a read-only review. The review ran no project code and changed no source file.
- Each bug in section 4 comes from a read of the source. Write a test that fails first. Then write the fix.
- Line numbers refer to the work copy of 2026-11-10. Search for the quoted names if the lines moved.
- Section 7 gives the order of work. Section 8 lists questions for Mateo. Ask each question before you start the related task.

## 1a. Status snapshot for the current branch

This roadmap tracks the remaining work. Some earlier defects have already been fixed in the working tree; those closed items are intentionally omitted from the backlog below so the document reflects the outstanding issues and features only.

## 2. Project map

| Path | Role |
| --- | --- |
| `calc.js` | Node wrapper for `@smogon/calc`. NDJSON on stdin and stdout. `--serve` keeps one process alive. Champions is generation 0. |
| `src/teambuilder/calc.py` | Request builder, subprocess plumbing, species name map, static type chart. |
| `src/teambuilder/damage.py` | Solvers (`min_evs_to_ko`, `min_evs_to_survive`) and roster filters (`ko_filter`, `can_ko_any_atk`, `survive_filter`). |
| `src/teambuilder/data.py` | Parser from the champout dumps to DuckDB. Tables: `pokemon`, `moves`, `pokemon_moves`. |
| `src/teambuilder/filters.py`, `pokedex.py` | Composable SQL filters and queries. |
| `src/teambuilder/main.py` | Typer CLI: `build-db`, `find`, `ko`, `survive`, `calc`, `category`, `raw`. |
| `src/teambuilder/web_server.py`, `api_helpers.py`, `templates/`, `static/` | Flask app. Pages: Calculator, Search, Bulk KO, Bulk Survive. jQuery 1.9.1 and Select2. |
| `test_api_helpers.py`, `test_ko.py`, `test_ko2.py` | unittest files at the root. They need the built database and Node. |
| `flake.nix`, `Dockerfile` | Deploy paths (gunicorn). |

Data facts from `champout/parse`:

- 396 species entries. 82 are Mega forms.
- 46 entries belong to the five families in `calc.COSMETIC_FORMS`. The calculator sees 5 species there. 41 entries are duplicates for damage work.
- 575 moves.
- Names contain spaces, a curly apostrophe and accents: `Charizard-Mega Y`, `Farfetch’d`, `Vivillon-Poké Ball`, `Tauros-Paldea Combat`.

Game rules that matter:

- Each stat takes 0 to 32 stat points. Each Pokémon has 66 stat points in total.
- The code enforces the 32 limit (`calc.js`, `damage.MAX_STAT_POINTS`). No code knows the 66 limit.

Position of the project:

- Pikalytics already offers usage data, a team builder, speed tiers and a damage calculator for Champions.
- The distinct value of this project is the inverse solver: "how many points does this take" and "which Pokémon of the roster manage this".
- The features in section 6 extend that solver to speed, to sets, to a full spread and to a full team.

Commands:

```bash
uv run teambuilder build-db     # champout dumps -> teambuilder.duckdb
uv run test                     # unittest discovery at the root
uv run web                      # Flask on port 5000
uv run demo
```

## 3. Ground rules

- The repository uses jj, colocated with git. Plain `git log` failed in the review environment (`unknown repository extension: relativeworktrees`). Use `jj`.
- `champout/`, `damage-calc/`, `node_modules/`, `teambuilder.duckdb` and `result` are external checkouts or build products. Leave them unchanged.
- Write identifiers, comments and commit text in English.
- The README asks for human verification of each number against the calculator. For each change to solver logic, give Mateo two matchups to check by hand.
- One bug or one feature per change. Keep each change small enough for Mateo to read in full.
- The CLI and the Python API stay first-class. The web app is a client of the same functions.
- Do not scrape third-party sites for usage data.

## 4. Bugs

Status at review time: found by read, not reproduced. This backlog lists the remaining issues only; fixed defects have been removed to keep the roadmap current.

### High

#### B2. Calculator page stays on "Calculating..." after a server error

- Where: `static/js/calculator.js:545-582` (no `error` callback), `web_server.py:445-446` (`_respond` returns HTTP 400).
- Trigger: select a Status move. The move list holds the full learnset. `attacking_stat` raises `ValueError`. The server answers 400. jQuery skips the `success` callback.
- Fix: add an `error` callback that shows `xhr.responseJSON.message`. Remove Status moves from the Calculator move list, or mark them as disabled.
- Related: an empty percent field sends `null` (`calculator.js:506`). The server then compares a number with `None`. Validate percent on both sides (number, more than 0, at most 100 for survive).

### Medium

#### B4. Survive solver ignores HP points that the caller supplies

- Where: `damage.py:219-231`, `damage.py:281`.
- Cause: `find_damage_breakpoints` measures `user_hp` with the HP points of the caller included. `calculate_HP_from_Breakpoints` returns the extra HP only. `verify_Min_EVs` then overwrites `hp` with that extra value.
- Example: `teambuilder survive A M D --defender-evs '{"hp": 10}'` with 0 extra HP necessary. The reported spread has `hp: 0`. That spread does not survive.
- The 32 limit check at `damage.py:227` also ignores the preset points.
- Fix: treat preset HP as a floor. Solve for total HP points. Apply the limit to the total. Report the total.

#### B5. "Only super effective" prefilter drops moves with a dynamic type

- Where: `damage.py:744-753`, `damage.py:775-781`. The checkbox is on by default (`templates/bulk_ko.html:109`).
- Cause: the prefilter uses the static move type and the static chart in `calc._TYPE_CHART`.
- The Champions move list contains Freeze-Dry, Flying Press, Weather Ball, Terrain Pulse, Tera Blast, Raging Bull and Aura Wheel.
- Effect: Bulk KO skips Freeze-Dry against Water types and Weather Ball in Sun against Grass types, for example.
- Fix, option 1: ask the calculator. Add the final move type and the type effectiveness to the `calc.js` response. Check first that `result.move.type` holds the final type in `mechanics/champions.ts`. Run one batch of 0-point calcs per candidate as the prefilter.
- Fix, option 2: keep the static prefilter and add an allowlist for these moves.

#### B6. Docker image runs gunicorn with default settings

- Where: last line of `Dockerfile`. `flake.nix` passes `--workers 2 --threads 4 --timeout 120`.
- Effect: one sync worker. One Bulk scan blocks every other request. The default 30 s worker timeout is expected to stop a long stream.
- Fix: use the same flags as the flake. Declare gunicorn as a project dependency (optional group `web`) in place of `uv pip install`.

#### B7. Three calculator versions

- Local: `node_modules/@smogon/calc` is a symlink to `damage-calc/calc` at commit `e7fd7e5` (package version 0.11.0).
- `package.json`, `package-lock.json` and `flake.nix`: npm `@smogon/calc` 0.12.0.
- `Dockerfile`: builds commit `e7fd7e5`, then `npm install ./damage-calc/calc` rewrites `package.json` inside the image.
- The README section "Getting the damage calculator" says the npm package has no Champions support. `flake.nix` assumes the opposite.
- Risk: dev, Docker and Nix give different numbers or different rosters.
- Fix: select one source. Confirm that the npm 0.12.0 tarball contains `dist/mechanics/champions.js`. Then align README, Dockerfile and local setup. Add a start check in `calc.js`: generation 0 resolves a known species, or the process exits with a clear message.

#### B8. Name lookup is exact in DuckDB and normalised in the calculator

- Where: `filters.py:46-59`, `pokedex.py:45-74`, `damage.py:678`, `damage.py:744`, `damage.py:857`.
- Effect: `teambuilder find --type grass` returns 0 rows. `ko_filter("close combat", ...)` drops each candidate. No error appears. `teambuilder ko` accepts the same text because `calc.js` applies `toID`.
- `demo.py:32` uses `Charizard-Mega-Y`. The database name is `Charizard-Mega Y`. That call works only because it goes to the calculator directly.
- Fix: see I3 (id columns and one resolver function). Unknown names raise `ValueError` with the closest match.

#### B9. Stat choice by move category is wrong for four moves in the game

- Where: `damage.py:49-71`.
- Moves in the Champions list: Body Press (attacks with Def), Psyshock (hits Def), Foul Play (uses the Atk of the target), Shell Side Arm (category depends on the matchup).
- Effect: the KO solver sweeps a stat that does nothing for Body Press and Foul Play. The survive solver sweeps the wrong defence for Psyshock. The README lists two of the four as known caveats.
- Fix: a per-move override table `{move_id: (attacker_stat, defender_stat)}`. For Foul Play the attacker sweep returns the 0-point result. For Shell Side Arm evaluate both defences.

#### B11. Hazard, Leech Seed and Salt Cure switches do not change solver results

- Where: the solvers compare `range` with the percent (`damage.py:484`, `damage.py:220`). The calculator uses `isSR`, `spikes`, `isSeeded` and `isSaltCured` for the KO chance text only.
- Effect: the switches are visible on the solver pages and change no answer.
- Fix: decide with Mateo (question Q4). Options: remove the switches from solver pages, or convert hazard damage into a lower KO threshold.

### Low

| Id | Where | Problem | Fix |
| --- | --- | --- | --- |
| B12 | `bulk_ko.js:266-283` | `appendResult` reads the row count before the append. The counter stays one behind. | Count after the append. Use a `rows` array as in `bulk_survive.js`. |
| B13 | `web_server.py:93`, `web_server.py:107`, `bulk_common.js:51` | Item names `KingKin` and `Manectrite`. The calculator names are `King's Rock` and `Manectite`. | Build the item list from the calculator (see I3). |
| B14 | `search.js`, `performServerSearch` | The sort order is lost when the move filter is active. | Apply the same sort to server results. |
| B15 | `damage.py:226` | `ceil(x + 0.01)` adds 1 HP too many when the fraction of `x` is 0.99 or more. Percent 0 divides by zero. | Use integer arithmetic: smallest HP with `dealt * 100 < percent * hp`. Reject percent 0. |
| B16 | `damage.py:261-290` | `verify_Min_EVs` recalculates and verifies nothing. Super Fang damage grows with HP, so the linear HP model fails below 100%. | Keep only pairs whose recalculated max roll passes the threshold. |
| B17 | `calculator.js:46`, `calculator.js:233-239` | Handlers for `#minOnly` and `#allResults`. The template has no such elements. | Delete, or add the switch and filter rows in `renderResults`. |
| B18 | `calculator.js:156`, `search.js` `displayResults`, option strings in `bulk_ko.js` and `bulk_survive.js` | HTML built from unescaped text. | Use the `esc` helper or jQuery element constructors. |
| B19 | `filters.py:30` | `~(a & b)` prints `not a AND b ` with a trailing space. The text reads as `(not a) AND b`. | Wrap composite text in parentheses. |
| B20 | `damage.py:140` | An unknown nature modifier raises a bare `KeyError`. | Raise `ValueError` with the accepted values. |
| B21 | `web_server.py:57-65` | The 404 branch is unreachable. `learnset` returns an empty list for unknown names. | Resolve the name first (I3). |
| B22 | `bulk_ko.js:90` | Species name goes into a URL without `encodeURIComponent`. | Encode it. |
| B23 | `calc.py:107-112` | `species()` uses `startswith` for cosmetic families. A future form such as a Mega of one of these species collapses to the base form. | Match an explicit list of cosmetic form names. |
| B24 | `src/teambuilder/__init__.py` | Leftover `main()` that prints "Hello from teambuilder!". | Delete. |

## 5. Improvements to the current code

### Current staged change: solver performance

The staged changes address I2's solver and calculator I/O work: minimum-point
and damage-breakpoint searches use binary search, calculator request batches
are written while responses are read, and identical requests share entries in
a bounded per-process LRU cache. Focused tests cover the search thresholds,
batch writing and cache behavior.

### I1. Test base and CI

- Move tests to `tests/`. Use pytest. Remove the `sys.path.insert` lines.
- Add unit tests for solver arithmetic with a fake `calculate`. These tests need no Node and no database.
- Mark the tests that need Node and the database as `integration`.
- Add a GitHub Actions workflow: ruff, unit tests, then integration tests after `build-db`.
- Add golden tests: 20 fixed matchups with expected `range` values from the pinned calculator. A calculator bump that changes a number then fails loudly.

### I2. Performance of the solvers

- Damage is monotonic in the swept stat. Replace the 33-request scan in `min_evs_to_ko` and in the breakpoint search with a binary search (about 6 requests).
- `calc._served` sends one line and waits for one answer. Send the full batch with a writer thread and read all answers. Keep the lock.
- `get_abilities_for_poke`, `learnset` and the type query open one DuckDB connection per call. Load the pokedex into memory once per process.
- Collapse cosmetic forms before a bulk scan. Report the family once.
- Cache bulk results per normalised request (LRU in memory). The database and the calculator are static per deploy.
- Limit concurrent bulk scans per worker. Each scan holds a thread and the calculator lock.

### I3. Data layer

- Add an `id` column to `pokemon` and `moves` with the `toID` rule (`[^a-z0-9]` removed, lower case).
- Add one resolver: `resolve_species(text)`, `resolve_move(text)`, `resolve_ability(text)`, `resolve_item(text)`. Each returns the canonical name or raises `ValueError` with a suggestion.
- Extend `moves` with calculator data: type, category, base power, priority, target (spread or single), flags (contact, sound, punch). One Node dump at build time, as `_CATEGORY_DUMP` does today.
- Add `abilities` and `items` tables from the generation 0 data of the calculator. Serve `/api/items` from the table.
- Add `teambuilder reconcile`: list species, moves and abilities that exist in champout and not in the calculator, and the reverse.
- Replace the static `_TYPE_CHART` with a dump of `gen.types`.

### I4. API and front end

- One error shape for all routes: `{"success": false, "error": "..."}` with a 4xx status. All AJAX calls have an `error` callback.
- One shared JS file for navigation, item load, Select2 setup and the field form. Four files repeat this code today.
- Sort stream results by points on the client. Add column sort to both bulk tables.
- Put the form state in the URL query. A user then shares a calc as a link.
- Update jQuery. Version 1.9.1 is from 2013.

### I5. Documentation

- The README says that no front end exists and that the npm package lacks Champions. Both statements are stale.
- Document the web routes and the deploy flags in one place.

## 6. New features

Sizes: S (one change), M (two to four changes), L (five or more changes).

### F1. Speed tools (M)

Goal: answer "who moves first" and "how many points to outspeed X".

- Add request type `stats` to `calc.js`. It returns the final stats of one Pokémon from the calculator. This keeps one stat formula.
- New module `speed.py`:
  - `effective_speed(set, conditions)`. Conditions: stage, Tailwind (x2), Choice Scarf (x1.5), Iron Ball (x0.5), paralysis (x0.5), weather and terrain speed abilities (x2).
  - `min_points_to_outspeed(species, target_speed, nature_options)`.
  - `speed_tiers(sets, conditions)`: sorted table. Trick Room reverses the order.
- CLI: `teambuilder speed <species>`, `teambuilder outspeed <species> <target>`.
- Web: page "Speed". Columns: base, 0 points, 32 points, 32 points with a positive nature, with Scarf, in Tailwind. Highlight the team of the user.
- Done when: unit tests cover each modifier, and the page shows the full roster in less than one second.

### F2. Sets repository (M)

Goal: calculate against sets that players run, not bare stat lines.

- Source: `src/js/data/sets/champions.js` in the damage-calc repository (`SETDEX_CHAMPIONS`). The local sparse checkout does not contain this path.
- Fetch the file at the pinned commit in the build (flake `fetchurl`, Dockerfile sparse path, README step).
- Table `sets(species, set_name, ability, item, nature, moves, hp, atk, def, spa, spd, spe, source)`. Map the short keys `hp, at, df, sa, sd, sp` under `sps` to the long names.
- API: `/api/sets/<species>`. UI: a set picker in each Pokémon field. The picker fills item, ability, nature and points.
- Python: `get_sets(species)`, and `set_opts(set)` that returns calculator `opts`.
- Done when: `build-db` imports every set, and `reconcile` reports the sets whose species, move, item or ability names do not resolve.

### F3. Team object with paste import and export (M)

Goal: one team as the unit of work for F4, F5 and F6.

- `team.py`: dataclasses `PokemonSet` and `Team`. Parser and writer for the Showdown paste text.
- Ask Mateo for a sample Champions paste first (question Q1). Confirm how the paste writes stat points.
- Validation: species in the roster, moves in the learnset, ability of the species, item in the item table, 0 to 32 per stat, 66 in total. Duplicate species and duplicate items are warnings until Mateo confirms the regulation (question Q2).
- CLI: `teambuilder team check team.txt`.
- Web: a team bar on each page. Storage in `localStorage`. Share as a compressed URL fragment. No server storage.
- Done when: a paste survives a parse and write round trip unchanged.

### F4. Threat matrix (L). Depends on F1, F2, F3

Goal: one screen that shows how one set stands against the metagame.

- Input: one set of the user and a threat list. Default threat list: every set from F2 for a list of species that the user selects. Also accept a second team.
- For each threat set, one row:
  - strongest move of the threat into the user set: damage range, percent, survive yes or no;
  - strongest move of the user set into the threat: damage range, percent, KO class (OHKO, 2HKO);
  - speed relation from F1.
- One batch of calculator requests per matrix.
- CLI: `teambuilder matrix team.txt --slot 1 --threats threats.txt`. Web: page "Matchups" with a sortable table.
- Done when: a matrix of one set against 100 threat sets returns in less than five seconds.

### F5. Spread optimiser with the 66-point budget (L). Depends on B4, B9, I2, F1

Goal: the cheapest full spread that meets several benchmarks at once. This is the core feature of the project.

- Input: one Pokémon (species, item, ability), nature mode (fixed or free) and a list of constraints.
- Constraint types: `survive(attacker_set, move, percent, field)`, `ko(defender_set, move, percent, field)`, `outspeed(target_speed)`, `underspeed(target_speed)`.
- Method, per candidate nature:
  1. Speed constraints give a minimum and a maximum for Spe points.
  2. Each KO constraint gives a minimum for Atk or SpA points (binary search). Take the largest.
  3. Survive constraints share HP. For each HP value from 0 to 32, find the minimum Def points for all physical constraints and the minimum SpD points for all special constraints. Keep the HP value with the lowest sum.
  4. Add the parts. Reject totals above 66.
- Candidate natures: neutral, plus each nature that raises a stat with a requirement.
- Output: the cheapest legal spread, the spare points, and one calculator description per constraint as proof. If no legal spread exists, name the constraints that conflict.
- CLI: `teambuilder optimise spec.json`. Web: page "Spread" with a constraint list editor. Constraints accept sets from F2.
- Done when: unit tests with a fake calculator prove minimality against brute force on a small grid.

### F6. Team analysis (M). Depends on I3, F3

Goal: the checks that players do by hand on each new team.

- Defensive chart: for each attack type, count the team members that are weak, neutral, resistant and immune. Use the chosen ability of each set (Levitate, Flash Fire, Water Absorb, Volt Absorb, Motor Drive, Sap Sipper, Lightning Rod, Storm Drain, Dry Skin, Thick Fat, Heatproof).
- Offensive coverage: the roster species (or F2 sets) that no move on the team hits for super effective damage.
- Role checklist from move and ability data: Fake Out, redirection, speed control (Tailwind, Trick Room, Icy Wind, Electroweb), Intimidate, priority, spread moves, Protect count, weather and terrain setters.
- Partner search from the README: "shares no weakness with these five", "resists the types that hit these two". Build these as SQL filters on a `type_matchup` table.
- Done when: `teambuilder team analyse team.txt` prints the three sections, and the web team bar opens the same data.

### F7. Damage filters on the command line, and `|` (M)

- From the README next steps.
- CLI: `teambuilder scan --type Ice --ko "Garchomp" --survive "Garchomp:Earthquake"`.
- `|` semantics: keep one result tuple per name. A branch that fails gives `None` in its position.

### F8. Search upgrades (S each). Depends on I3

- Ability filter in the Search page. The backend filter exists.
- More than one move.
- Move property filter: "learns a Physical Grass move with base power of 90 or more".
- Matchup filter: "resists Ground", "immune to Fake Out".
- Switch that hides cosmetic duplicates.

### Out of scope

- Usage data scrape from third-party sites.
- Accounts and server-side team storage.
- Battle simulation.

## 7. Order of work

Updated order for the current branch state:

1. Validate the current fixes and the associated tests.
2. I1 (tests and CI) and B7 (one calculator version). All later work needs both.
3. Remaining high bugs: B2, then the rest of the solver correctness fixes.
4. Medium bugs: B4, B5, B6, B8 with I3, B9, B11.
5. Low bug cleanup: B12-B24 in a single pass.
6. I2 (performance) and the remaining data-model work in I3.
7. F1 (speed), F2 (sets), F3 (team).
8. F8 (search), F7 (CLI filters).
9. F4 (threat matrix), F6 (team analysis).
10. F5 (spread optimiser).
11. I4 and I5 alongside the features that touch the same files.

## 8. Questions for Mateo

- Q1. Give one Champions team as Showdown paste text. How does the paste write stat points?
- Q2. Which team rules does the current regulation apply (duplicate species, duplicate items, Mega limit)?
- Q3. For B11: remove the hazard switches from solver pages, or include hazard damage in the KO threshold?
- Q4. For B7: is npm `@smogon/calc` 0.12.0 the version of record, or the pinned commit?
- Q5. Which deploy path stays: Nix only, or Nix and Docker?
- Q6. The README says that the author does not plan a front end. A front end exists now. Do the new features target the web pages, the CLI, or both?
