
import json
import re
import subprocess
import threading
from functools import cache
from pathlib import Path
from typing import overload

ROOT = Path(__file__).resolve().parents[2]
CALC_JS = ROOT / "calc.js"

# Champions. calc.js documents why 0 is the Champions generation.
DEFAULT_GEN = 0

# One node process dumps every move's category, which beats paying for a
# process per lookup. Printed as {move id: "Physical" | "Special" | "Status"},
# with null for the entries (Z-moves, Max moves) that carry no category.
_CATEGORY_DUMP = """
const {Generations} = require('@smogon/calc');
const gen = Generations.get(Number(process.argv[1]));
const categories = {};
for (const move of gen.moves) categories[move.id] = move.category || null;
console.log(JSON.stringify(categories));
"""

# Similarly dump move types for type effectiveness filtering
_TYPE_DUMP = """
const {Generations} = require('@smogon/calc');
const gen = Generations.get(Number(process.argv[1]));
const types = {};
for (const move of gen.moves) types[move.id] = move.type || null;
console.log(JSON.stringify(types));
"""


class CalcError(RuntimeError):
    """A request the calculator refused, or a node process that failed."""


def move_category(move: str, gen: int = DEFAULT_GEN) -> str | None:
    """"Physical", "Special", "Status", or None if the move is not in `gen`.

    None means the move exists in champout but not in this generation's data
    (or is a Z/Max entry with no category), so it is worth distinguishing from
    "Status" rather than treating every unknown as a non-attacking move.
    """
    return _categories(gen).get(_to_id(move))


def move_type(move: str, gen: int = DEFAULT_GEN) -> str | None:
    """The type of a move, or None if the move is not in `gen`."""
    return _move_types(gen).get(_to_id(move))


@overload
def calculate(request: dict) -> dict: ...


@overload
def calculate(request: list[dict]) -> list[dict]: ...


def calculate(request: dict | list[dict]) -> dict | list[dict]:
    """Run one request, or a list of them in a single node process.

    A list returns a list of responses in the same order, errors included as
    `{"error": ...}` entries so one bad request does not lose the batch. A
    single request returns a single response, and raises CalcError instead.
    """
    batch = request if isinstance(request, list) else [request]
    lines = [json.dumps(r) for r in batch]
    responses = _served(lines)
    if responses is None:
        stdout = _node([str(CALC_JS)], "\n".join(lines))
        responses = [json.loads(line) for line in stdout.splitlines() if line.strip()]

    if isinstance(request, list):
        return responses
    if "error" in responses[0]:
        raise CalcError(responses[0]["error"])
    return responses[0]


# Champout names 42 species the calculator does not have, and every one of them
# resolves cleanly - each mapping below was checked by comparing base stats.
#
# The cosmetic families are one species to the calculator: Furfrou's nine trims,
# Vivillon's eighteen patterns, Florges' flower colours, Alcremie's creams and
# swirls, and Maushold's Family of Four all share their base form's stats.
COSMETIC_FORMS = ("Furfrou", "Vivillon", "Florges", "Alcremie", "Maushold")

# These two are not missing, only named differently. Gourgeist-Jumbo is
# 85/100/122/58/75/54, which is the calculator's Gourgeist-Super, and champout's
# bare Aegislash is 60/50/140/50/140/60, its Shield forme - the one it stands in
# until it attacks. Ask for Aegislash-Blade explicitly if you want that side.
RENAMED = {"Gourgeist-Jumbo": "Gourgeist-Super", "Aegislash": "Aegislash-Shield"}


def species(name: str) -> str:
    """The calculator's name for a champout species.

    Applied to both sides of every request, so the rest of the code can keep
    using champout's names throughout. A response describes whoever was
    calculated, so a Furfrou-Star request comes back talking about Furfrou.
    """
    if name in RENAMED:
        return RENAMED[name]
    for base in COSMETIC_FORMS:
        if name.startswith(base):
            return base
    return name


def build_request(
    attacker: str,
    move: str,
    defender: str,
    *,
    attacker_evs: dict | None = None,
    defender_evs: dict | None = None,
    attacker_opts: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    gen: int = DEFAULT_GEN,
    request_id=None,
) -> dict:
    """Assemble one calculate() request.
    The `*_opts` dicts are merged over the defaults, so passing
    `field_opts={"gameType": "Singles"}` overrides the gameType below, and
    `attacker_opts={"evs": ...}` overrides attacker_evs.
    """
    request = {
        "gen": gen,
        "attacker": {
            "name": species(attacker),
            "opts": {"evs": attacker_evs or {}, **(attacker_opts or {})},
        },
        "defender": {
            "name": species(defender),
            "opts": {"evs": defender_evs or {}, **(defender_opts or {})},
        },
        "move": {"name": move, **(move_opts or {})},
        # Champions is played in doubles.
        "field": {"gameType": "Doubles", **(field_opts or {})},
    }


    # Add side conditions if provided
    if defender_side:
        request["defenderSide"] = defender_side
    if attacker_side:
        request["attackerSide"] = attacker_side

    # Only worth sending when there is one: calc.js echoes it back, which is
    # how a response is matched to its request in a batch.
    if request_id is not None:
        request["id"] = request_id
    return request


@cache
def _categories(gen: int) -> dict[str, str | None]:
    return json.loads(_node(["-e", _CATEGORY_DUMP, str(gen)]))


@cache
def _move_types(gen: int) -> dict[str, str | None]:
    return json.loads(_node(["-e", _TYPE_DUMP, str(gen)]))


# Starting node costs about 100 ms and a calculation about 0.1 ms, so the slow
# filters - two batches per candidate and move - spent nearly all their time on
# startup. One `calc.js --serve` process is kept for every batch instead. The
# lock is for the web server, whose requests run on threads of their own.
_server: subprocess.Popen | None = None
_server_lock = threading.Lock()


def _served(lines: list[str]) -> list[dict] | None:
    """Responses from the long-lived calc.js, or None if it is not answering.

    Lines go one at a time, each answer read before the next is sent: a whole
    batch written up front would fill the pipe back while nobody reads it, and
    both sides would wait on each other. None leaves the batch to a one-off
    process, which runs it the old way and reports node's own error if there
    is one - the next batch starts a fresh server.
    """
    global _server
    with _server_lock:
        try:
            if _server is None or _server.poll() is not None:
                # stderr is the library's chatter (see calc.js); nothing reads
                # it, so it cannot be a pipe that fills up and blocks node.
                _server = subprocess.Popen(
                    ["node", str(CALC_JS), "--serve"], cwd=ROOT, text=True,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            responses = []
            stdin = _server.stdin
            stdout = _server.stdout
            if stdin is None or stdout is None:
                raise BrokenPipeError
            for line in lines:
                stdin.write(line + "\n")
                stdin.flush()
                answer = stdout.readline()
                if not answer:
                    raise BrokenPipeError
                responses.append(json.loads(answer))
            return responses
        except (OSError, ValueError):
            if _server is not None:
                _server.kill()
            _server = None
            return None


def _node(args: list[str], stdin: str = "") -> str:
    # cwd is the project root so node resolves @smogon/calc from node_modules.
    # calc.js keeps stdout to one JSON response per line - failures included -
    # and pushes the library's own chatter to stderr, so stderr only matters
    # when nothing came back at all.
    process = subprocess.run(
        ["node", *args], input=stdin, capture_output=True, text=True, cwd=ROOT
    )
    if not process.stdout.strip():
        raise CalcError(process.stderr.strip() or "node produced no output")
    return process.stdout


def _to_id(name: str) -> str:
    # The library keys its data by id: "Grassy Glide" is grassyglide, and
    # "Farfetch'd" (with either apostrophe) is farfetchd.
    return re.sub(r"[^a-z0-9]+", "", name.lower())


# Type effectiveness chart for Champions (same as standard Pokemon type chart)
# Values: 2.0 = super effective, 0.5 = not very effective, 0.0 = immune, 1.0 = neutral
_TYPE_CHART = {
    "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground": {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying": {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark": {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
}


# What each type-changing ability turns a move into. Normalize changes every
# move; the rest only change Normal ones. Dragonize is Champions' own, on
# Feraligatr-Mega. One table, so a new -ate ability cannot be added to one
# check and missed by the other.
TYPE_CHANGING_ABILITIES = {
    "Aerilate": "Flying",
    "Pixilate": "Fairy",
    "Galvanize": "Electric",
    "Refrigerate": "Ice",
    "Dragonize": "Dragon",
    "Normalize": "Normal",
}


def is_super_effective(
    move: str,
    defender_types: list[str],
    gen: int = DEFAULT_GEN,
    attacker_ability: str | None = None,
) -> bool:
    """Check if a move is super effective against the defender's types.

    Returns True if the move is super effective (2x or more) against the
    defender's type combination (combined effectiveness of both types).

    If attacker_ability is provided, accounts for type-changing abilities:
    - Aerialate: Normal moves become Flying
    - Pixilate: Normal moves become Fairy
    - Galvanize: Normal moves become Electric
    - Refrigerate: Normal moves become Ice
    - Dragonize: Normal moves become Dragon
    - Normalize: All moves become Normal
    """
    move_type_name = move_type(move, gen)
    if not move_type_name:
        return False  # Unknown move type, don't filter

    # Apply type-changing abilities
    if attacker_ability in TYPE_CHANGING_ABILITIES and (
        move_type_name == "Normal" or attacker_ability == "Normalize"
    ):
        move_type_name = TYPE_CHANGING_ABILITIES[attacker_ability]

    # Calculate combined effectiveness against all defender types
    combined_effectiveness = 1.0
    for defender_type in defender_types:
        if not defender_type:
            continue
        effectiveness = _TYPE_CHART.get(move_type_name, {}).get(defender_type, 1.0)
        combined_effectiveness *= effectiveness

    return combined_effectiveness >= 2.0
