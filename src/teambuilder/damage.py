import re
from decimal import Decimal, ROUND_FLOOR
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import NamedTuple

from tqdm import tqdm

from teambuilder.calc import (
    CalcError, build_request, calculate, move_category,
    move_type as get_move_type, _TYPE_CHART, TYPE_CHANGING_ABILITIES,
    )
from teambuilder.data import DB_PATH
from teambuilder.pokedex import (
    get_abilities_for_poke, learnset, that_learn, resolve_species, _query,
)

# Champions gives each stat 0-32 points, so every search below is a scan over
# 33 candidates in one batch - ~20ms, and damage is monotonic in the invested
# stat, so the first spread that clears the bar is the cheapest one.
MAX_STAT_POINTS = 32


def validate_percent(percent: float) -> float:
    try:
        value = float(percent)
    except (TypeError, ValueError) as err:
        raise ValueError("percent must be a number greater than 0 and at most 100") from err
    if not isfinite(value) or not 0 < value <= 100:
        raise ValueError("percent must be greater than 0 and at most 100")
    return value


def _move_id(move: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", move.lower())


_MOVE_STAT_OVERRIDES = {
    "bodypress": ("def", "def"),
    "foulplay": ("atk", "def"),
    "psyshock": ("spa", "def"),
}


class Investment(NamedTuple):
    points: int
    desc: str
    percent: tuple[float, float]
    damage: tuple[int, int]
    user_hp: int
    move: str | None = None        # set when the filter picked the move, not the caller
    spread: dict[str, int] | None = None  # set when the points cover more than one stat
    ability: str | None = None     # set when the filter picked it; None if none of them mattered

    def __str__(self):
        with_move = f" with {self.move}" if self.move else ""
        return f"{self.points} points{with_move}: {self.desc}"


class BestAbility(NamedTuple):
    """The attacker's hardest-hitting ability, and the damage that proves it."""

    names: tuple[str, ...]
    damage: tuple[int, int]
    desc: str

    def __str__(self):
        return f"{' / '.join(self.names)}: {self.damage[0]}-{self.damage[1]}"


def attacking_stat(move: str) -> str:
    """Return the attack stat a move normally uses, including fixed exceptions.

    Shell Side Arm is matchup-dependent and is explicitly evaluated against
    both attack stats by the solvers.
    """
    override = _MOVE_STAT_OVERRIDES.get(_move_id(move))
    if override:
        return override[0]
    category = move_category(move)
    if category is None:
        raise ValueError(f"{move!r} is not in the Champions move data")
    if category == "Status":
        raise ValueError(f"{move!r} is a Status move and deals no damage")
    return "spa" if category == "Special" else "atk"


def relevant_defense_stat(attack_type: str, move: str | None = None) -> str:
    override = _MOVE_STAT_OVERRIDES.get(_move_id(move)) if move else None
    if override:
        return override[1]
    if attack_type == "spa":
        return "spd"
    elif attack_type in ("atk", "def"):
        return "def"
    else:
        raise ValueError(f"{attack_type!r} is not in a valid attack type")


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _pin_ability(opts: dict | None, ability: str) -> dict:
    """Copy of `opts` with the ability fixed, never mutating the caller's dict."""
    return {**(opts or {}), "ability": ability}


def ko_result_row(name: str, investment: Investment, default_move: str = "Best move") -> dict:
    """The dict shape every KO endpoint and the SSE callback send to the UI."""
    return {
        "name": name,
        "points": investment.points,
        "move": investment.move or default_move,
        "ability": investment.ability or "Any",
        "desc": investment.desc,
    }


def survive_result_row(name: str, investment: Investment) -> dict:
    """The dict shape the bulk-survive endpoints and the SSE callback send to the UI."""
    spread = investment.spread or {}
    desc = investment.desc
    return {
        "name": name,
        "points": investment.points,
        "hp_invest": spread.get("hp", 0),
        "defender_invest": spread.get("def", 0) + spread.get("spd", 0),
        "ability": investment.ability or "Any",
        "desc": desc,
    }


# ---------------------------------------------------------------------------
# Natures and signed EVs ("32+", "0-")
# ---------------------------------------------------------------------------

NATURES = {
    ("atk", "+"): "Adamant", ("atk", ""): "Serious", ("atk", "-"): "Modest",
    ("spa", "+"): "Modest",  ("spa", ""): "Serious", ("spa", "-"): "Adamant",
    ("def", "+"): "Relaxed", ("def", ""): "Serious", ("def", "-"): "Hasty",
    ("spd", "+"): "Sassy",   ("spd", ""): "Serious", ("spd", "-"): "Naive",
}

# Every accepted modifier maps to "+", "" or "-"
SIGNS = {
    "+": "+", "1.1": "+",
    "": "",   "1.0": "",  None: "",
    "-": "-", "0.9": "-",
}


def split_ev(value):
    value = str(value).strip()
    if value.endswith(("+", "-")):
        return int(value[:-1]), value[-1]
    return int(value), None


def with_nature(opts, modifier, stat):
    """opts with the nature that raises/lowers `stat`, or opts untouched.

    A neutral modifier ("", "1.0", None) leaves opts alone instead of stamping
    "Serious" over whatever nature the caller had set.
    """
    if modifier not in SIGNS:
        accepted = ", ".join(repr(value) for value in SIGNS if value is not None)
        raise ValueError(f"unknown nature modifier {modifier!r}; expected one of {accepted}, or None")
    sign = SIGNS[modifier]
    if not sign:
        return opts
    try:
        nature = NATURES[stat.lower(), sign]
    except KeyError as err:
        raise ValueError(f"no nature modifier is defined for stat {stat!r}") from err
    return {**(opts or {}), "nature": nature}


def normalize_evs(evs, opts, stat):
    """Accept EVs as None, "32+", or {"def": "32+", "hp": 4}; return (ints, opts).

    A +/- on the entry for `stat` becomes the matching nature in opts. Both the
    KO side (defender dict, stat = the defence being attacked) and the survival
    side (attacker string, stat = the attacking stat) go through here.
    """
    if evs is None:
        return None, opts
    if isinstance(evs, str):
        evs = {stat: evs}
    clean = {}
    for name, raw in evs.items():
        clean[name], sign = split_ev(raw)
        if sign and name.lower() == stat.lower():
            opts = with_nature(opts, sign, stat)
    return clean, opts


# ---------------------------------------------------------------------------
# Calculator plumbing
# ---------------------------------------------------------------------------

def _evaluate(requests: list[dict], points: list[int] | None = None):
    """Runs every request through the calculator, yielding (response, Investment) pairs.

    `points` lets callers supply the real per-request cost (e.g. hp+def sum)
    instead of the request's position in the list. Defaults to the index,
    which is correct when requests were built by sweeping 0..MAX_STAT_POINTS.
    """
    point_values = points if points is not None else range(len(requests))
    for pts, response in zip(point_values, calculate(requests)):
        yield response, _investment(response, pts)


def _investment(response: dict, points: int) -> Investment:
    if "error" in response:
        raise CalcError(response["error"])
    return Investment(
        points, response["desc"], tuple(response["percent"]),
        tuple(response["range"]), response["defenderMaxHP"],
    )


def _cheapest(requests: list[dict], accept) -> Investment | None:
    """Find the cheapest accepted request with logarithmic calculator calls."""
    if not requests:
        return None

    cache: dict[int, tuple[dict, Investment]] = {}

    def at(index: int) -> tuple[dict, Investment]:
        if index not in cache:
            response = calculate(requests[index])
            cache[index] = (response, _investment(response, index))
        return cache[index]

    last = len(requests) - 1
    if not accept(at(last)[0]):
        return None

    low, high = 0, last
    while low < high:
        middle = (low + high) // 2
        if accept(at(middle)[0]):
            high = middle
        else:
            low = middle + 1
    return at(low)[1]


def _breakpoints(requests: list[dict], key, points: list[int] | None = None) -> list[Investment]:
    """Find the first request for each monotonic change in `key(response)`."""
    if not requests:
        return []

    point_values = points if points is not None else range(len(requests))
    cache: dict[int, tuple[dict, Investment]] = {}

    def at(index: int) -> tuple[dict, Investment]:
        if index not in cache:
            response = calculate(requests[index])
            cache[index] = (response, _investment(response, point_values[index]))
        return cache[index]

    breakpoints: list[Investment] = []
    start = 0
    breakpoints.append(at(start)[1])
    last = len(requests) - 1
    while start < last:
        current = key(at(start)[0])
        if key(at(last)[0]) == current:
            break
        low, high = start + 1, last
        while low < high:
            middle = (low + high) // 2
            if key(at(middle)[0]) == current:
                low = middle + 1
            else:
                high = middle
        start = low
        breakpoints.append(at(start)[1])
    return breakpoints


def _all(requests: list[dict], points: list[int] | None = None) -> list[Investment]:
    """Every Investment, one per request, in order."""
    return [investment for _, investment in _evaluate(requests, points)]


def calculate_HP_from_Breakpoints(
    breakpoints: list[Investment],
    PERCENT,
    HP,
    INVEST_IN,
    showAll=True,
    *,
    base_hp: int = 0,
):
    PERCENT = validate_percent(PERCENT)
    # Initialise the min points used above the 32/32 cap
    minPoints: int = 64
    minPairs: list[dict[str, int]] = []
    allPairs: list[dict[str, int]] = []

    for inv in breakpoints:
        dealt = inv.damage[1]
        current_hp = inv.user_hp
        points = inv.points
        pct = Decimal(str(PERCENT))
        if Decimal(dealt * 100) < pct * current_hp:
            additional_hp = 0
        else:
            additional_hp = int(
                (Decimal(dealt * 100) / pct - current_hp).to_integral_value(rounding=ROUND_FLOOR)
            ) + 1
        total_hp = base_hp + max(additional_hp, 0)
        if total_hp > MAX_STAT_POINTS:
            # We cannot survive at the given defense investment
            continue

        total_points_used = total_hp + points

        if showAll:
            allPairs.append({HP: total_hp, INVEST_IN: points})
            if additional_hp == 0:
                # 0 HP is already enough, so any more defence investment is redundant
                break
            continue

        if minPoints > total_points_used:
            # Set the new best points
            minPoints = total_points_used
            # Empty the list
            minPairs.clear()
            # Add the new best combination
            minPairs.append({HP: total_hp, INVEST_IN: points})

        elif minPoints == total_points_used:
            # Add an equally good combination
            minPairs.append({HP: total_hp, INVEST_IN: points})

        if additional_hp == 0:
            # We do not need to check any more values
            break
    if showAll:
        return allPairs

    return minPairs


def verify_Min_EVs(
    minPairs: list[dict[str, int]],
    attacker: str,
    move: str,
    defender: str,
    *,
    attacker_evs: dict | None = None,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    percent: float = 100.0,
):
    percent = validate_percent(percent)
    defense_key = next(key for key in minPairs[0] if key != "hp")

    def request_for(pair: dict[str, int]) -> dict:
        return build_request(
            attacker, move, defender,
            attacker_evs=attacker_evs,
            attacker_opts=attacker_opts,
            defender_evs={**(defender_evs or {}), **pair},
            defender_opts=defender_opts,
            move_opts=move_opts,
            field_opts=field_opts,
            defender_side=defender_side,
            attacker_side=attacker_side,
        )

    def survives(response: dict) -> bool:
        return (
            Decimal(response["range"][1] * 100)
            < Decimal(str(percent)) * response["defenderMaxHP"]
        )

    verified_by_defense = {}
    retry_pairs = []
    initial = list(zip(minPairs, _evaluate([request_for(pair) for pair in minPairs])))
    for pair, (response, investment) in initial:
        defense = pair[defense_key]
        if survives(response):
            verified_by_defense[defense] = investment._replace(
                points=sum(pair.values()), spread=pair
            )
        else:
            retry_pairs.extend(
                {**pair, "hp": hp}
                for hp in range(pair["hp"] + 1, MAX_STAT_POINTS + 1)
            )

    retries = []
    if retry_pairs:
        retries = list(zip(
            retry_pairs,
            _evaluate([request_for(pair) for pair in retry_pairs]),
        ))
    for pair, (response, investment) in retries:
        defense = pair[defense_key]
        if defense not in verified_by_defense and survives(response):
            verified_by_defense[defense] = investment._replace(
                points=sum(pair.values()), spread=pair
            )

    return [
        verified_by_defense[pair[defense_key]]
        for pair in minPairs
        if pair[defense_key] in verified_by_defense
    ]

def _required_ability(best: BestAbility, desc: str) -> str | None:
    """Report only abilities named as relevant in the damage description."""
    required = [
        name for name in best.names
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", desc, re.IGNORECASE)
    ]
    return " / ".join(required) or None


def _ability_scan(attacker: str, move: str, defender: str, *, vary: str, pick, options: dict):
    """Calculate this matchup once per ability of one side, and pick an extreme.

    `vary` is "attacker" or "defender" and says whose abilities are swapped;
    `pick` is max or min over the damage range. One node process covers every
    ability, since they all go into a single batch.
    """
    subject = attacker if vary == "attacker" else defender
    key = f"{vary}_opts"
    abilities = get_abilities_for_poke(subject)

    responses = calculate([
        # A new dict per request: mutating one shared dict would also hand the
        # caller's options back with an ability glued on.
        build_request(attacker, move, defender,
                      **{**options, key: _pin_ability(options.get(key), name)})
        for name in abilities
    ])
    for response in responses:
        if "error" in response:
            raise CalcError(response["error"])

    # Rolls scale together, so comparing ranges orders the abilities the same
    # way any single roll would. Ties are every ability that matches the
    # extreme, which is the common case: usually none of them touch this move.
    damage = pick(tuple(response["range"]) for response in responses)
    tied = tuple(
        name for name, response in zip(abilities, responses) if tuple(response["range"]) == damage
    )
    desc = next(r["desc"] for r in responses if tuple(r["range"]) == damage)
    return BestAbility(tied, damage, desc)


def most_damaging_ability(
    attacker: str,
    move: str,
    defender: str,
    *,
    attacker_evs: dict | None = None,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
) -> BestAbility:
    """Which of the attacker's abilities hits hardest here, ties included.

    The usual reason to want this is to ask the strongest version of a
    question: if the hardest-hitting ability cannot manage a KO, no set of
    that pokemon can, so the answer holds without knowing which ability the
    opponent actually runs.

    Conditional abilities are calculated with their condition unmet, and the
    two kinds are switched on differently: the pinch abilities (Overgrow,
    Blaze, Torrent, Swarm) key off current HP, so they need
    `attacker_opts={"originalCurHP": n}` with n at or under a third of max,
    while Flash Fire, Stakeout and the like key off
    `attacker_opts={"abilityOn": True}`.
    """
    return _ability_scan(
        attacker, move, defender, vary="attacker", pick=max,
        options=dict(
            attacker_evs=attacker_evs, attacker_opts=attacker_opts,
            defender_evs=defender_evs, defender_opts=defender_opts,
            move_opts=move_opts, field_opts=field_opts,
            defender_side=defender_side, attacker_side=attacker_side,
        ),
    )


def least_damaged_ability(
    defender: str,
    attacker: str,
    move: str,
    *,
    attacker_evs: dict | None = None,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
) -> BestAbility:
    """Which of the defender's abilities takes the hit best, ties included.

    The mirror of most_damaging_ability, and the same argument in reverse: if
    the most resistant ability still cannot survive, no set of that pokemon
    survives either. Defensive abilities are where this matters most - Thick
    Fat halves the damage, Levitate and Flash Fire zero it - and the ones that
    cancel a type entirely are exactly the ones a type chart would miss.

    The defender leads the signature because it is the one being asked about.
    """
    return _ability_scan(
        attacker, move, defender, vary="defender", pick=min,
        options=dict(
            attacker_evs=attacker_evs, attacker_opts=attacker_opts,
            defender_evs=defender_evs, defender_opts=defender_opts,
            move_opts=move_opts, field_opts=field_opts,
            defender_side=defender_side, attacker_side=attacker_side,
        ),
    )


def _ko_at_best_ability(
    name, move, defender, *, percent, positive_nature=False, db=DB_PATH, **options
) -> Investment | None:
    """Cheapest attacking investment with the hardest-hitting ability.

    If requested, also compares the neutral attacker options against the
    nature that raises the move's attacking stat.
    """
    stat = attacking_stat(move)
    nature_options = [options]
    if positive_nature:
        nature_stats = ("atk", "spa") if _move_id(move) == "shellsidearm" else (stat,)
        for nature_stat in nature_stats:
            raised_opts = with_nature(options.get("attacker_opts"), "+", nature_stat)
            nature_options.append({**options, "attacker_opts": raised_opts})

    cheapest = None
    for nature_opts in nature_options:
        sweep_stats = ("atk", "spa") if _move_id(move) == "shellsidearm" else (stat,)
        for sweep_stat in sweep_stats:
            best = most_damaging_ability(
                name, move, defender,
                attacker_evs={sweep_stat: MAX_STAT_POINTS},
                **nature_opts,
            )
            pinned = {
                **nature_opts,
                "attacker_opts": _pin_ability(nature_opts.get("attacker_opts"), best.names[0]),
            }
            investment = min_evs_to_ko(name, move, defender, percent=percent, **pinned)
            if investment is not None and (cheapest is None or investment.points < cheapest.points):
                cheapest = investment._replace(ability=_required_ability(best, investment.desc))
    return cheapest


# ---------------------------------------------------------------------------
# Single-matchup solvers
# ---------------------------------------------------------------------------

def min_evs_to_ko(
    attacker: str,
    move: str,
    defender: str,
    *,
    percent: float = 100.0,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
) -> Investment | None:
    """Fewest attacking stat points that guarantee `percent`% damage, or None.

    Guaranteed means the *lowest* roll clears the bar, which is the usual
    reading of "this OHKOes": a range that only sometimes reaches 100% does
    not count. For a guaranteed 2HKO set percent to 50.
    """
    percent = validate_percent(percent)
    stat = attacking_stat(move)
    if _move_id(move) == "shellsidearm":
        solutions = []
        for attacking in ("atk", "spa"):
            defense = relevant_defense_stat(attacking)
            evs, opts = normalize_evs(defender_evs, defender_opts, defense)
            solution = _cheapest(
                [
                    build_request(
                        attacker, move, defender,
                        attacker_evs={attacking: points},
                        attacker_opts=attacker_opts,
                        defender_evs=evs,
                        defender_opts=opts,
                        move_opts=move_opts,
                        field_opts=field_opts,
                        defender_side=defender_side,
                        attacker_side=attacker_side,
                    )
                    for points in range(MAX_STAT_POINTS + 1)
                ],
                lambda response: 100 * response["range"][0] / response["defenderMaxHP"] >= percent,
            )
            if solution is not None:
                solutions.append(solution)
        return min(solutions, key=lambda result: result.points) if solutions else None
    defender_evs, defender_opts = normalize_evs(
        defender_evs, defender_opts, relevant_defense_stat(stat, move)
    )

    # Foul Play uses the target's Attack, so spending points on the user's
    # Attack cannot change its damage.
    if _move_id(move) == "foulplay":
        request = build_request(
            attacker, move, defender,
            attacker_opts=attacker_opts,
            defender_evs=defender_evs,
            defender_opts=defender_opts,
            move_opts=move_opts,
            field_opts=field_opts,
            defender_side=defender_side,
            attacker_side=attacker_side,
        )
        return _cheapest(
            [request],
            lambda response: 100 * response["range"][0] / response["defenderMaxHP"] >= percent,
        )

    return _cheapest(
        [
            build_request(
                attacker, move, defender,
                attacker_evs={stat: points},
                attacker_opts=attacker_opts,
                defender_evs=defender_evs,
                defender_opts=defender_opts,
                move_opts=move_opts,
                field_opts=field_opts,
                defender_side=defender_side,
                attacker_side=attacker_side,
            )
            for points in range(MAX_STAT_POINTS + 1)
        ],
        # range[0] is the lowest roll: the damage that is always dealt.
        lambda response: 100 * response["range"][0] / response["defenderMaxHP"] >= percent,
    )


def min_evs_to_survive(
    attacker: str,
    move: str,
    defender: str,
    defender_nature: str | None = None,
    *,
    percent: float = 100.0,
    showAll: bool = False,
    attacker_opts: dict | None = None,
    attacker_evs: dict | str | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    _defense_override: str | None = None,
) -> list[Investment] | None:
    """Fewest points across HP and the relevant defence to hold `move` under
    `percent`%, or None if 32/32 cannot manage it.

    Damage moves in steps, not smoothly, so this walks the breakpoints in the
    defence the move actually attacks and works out how much HP each one needs;
    the cheapest total wins. `.points` on the result is that total, across both
    stats, and `.desc` names the spread that proves it.

    `defender_nature` is "+", "-", "1.1", "0.9", "1.0", "" or None, applied to
    the defence being invested in.

    `attacker_evs` can be:
    - A string like "32" for 32 investment in the relevant stat
    - A string like "32+" for 32 investment with maximizing nature (Adamant/Modest)
    - A string like "0-" for 0 investment with minimizing nature
    - A dict for full EV spread control
    """
    percent = validate_percent(percent)
    if _move_id(move) == "shellsidearm" and _defense_override is None:
        results = []
        for defense in ("def", "spd"):
            found = min_evs_to_survive(
                attacker, move, defender, defender_nature,
                percent=percent, showAll=True,
                attacker_opts=attacker_opts, attacker_evs=attacker_evs,
                defender_evs=defender_evs, defender_opts=defender_opts,
                move_opts=move_opts, field_opts=field_opts,
                defender_side=defender_side, attacker_side=attacker_side,
                _defense_override=defense,
            )
            results.extend(found or [])
        if not results:
            return None
        if not showAll:
            cheapest = min(inv.points for inv in results)
            results = [inv for inv in results if inv.points == cheapest]
        return results
    hp = "hp"
    stat = attacking_stat(move)
    invest = _defense_override or relevant_defense_stat(stat, move)
    defender_opts = with_nature(defender_opts, defender_nature, invest)
    attacker_evs, attacker_opts = normalize_evs(attacker_evs, attacker_opts, stat)

    base_hp = (defender_evs or {}).get(hp, 0)
    if not isinstance(base_hp, int) or not 0 <= base_hp <= MAX_STAT_POINTS:
        raise ValueError(f"defender hp points must be an integer from 0 to {MAX_STAT_POINTS}")

    breakpoints = find_damage_breakpoints(
        attacker, move, defender,
        invest=invest,
        attacker_evs=attacker_evs,
        attacker_opts=attacker_opts,
        defender_evs=defender_evs,
        defender_opts=defender_opts,
        move_opts=move_opts,
        field_opts=field_opts,
        defender_side=defender_side,
        attacker_side=attacker_side,
    )

    optimal_EVs = calculate_HP_from_Breakpoints(
        breakpoints, percent, hp, invest, showAll=True, base_hp=base_hp
    )

    # optimal_EVs is empty because we could not find a solution that survived
    if not optimal_EVs:
        return None

    verified = verify_Min_EVs(
        optimal_EVs, attacker, move, defender,
        attacker_evs=attacker_evs, attacker_opts=attacker_opts,
        defender_evs=defender_evs, defender_opts=defender_opts,
        move_opts=move_opts, field_opts=field_opts,
        defender_side=defender_side, attacker_side=attacker_side,
        percent=percent,
    )
    if not verified:
        return None
    if not showAll:
        cheapest = min(inv.points for inv in verified)
        verified = [inv for inv in verified if inv.points == cheapest]
    return verified


def find_damage_breakpoints(
    attacker: str,
    move: str,
    defender: str,
    *,
    invest: str = "def",
    attacker_evs: dict | None = None,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
) -> list[Investment]:
    """The fewest `invest` EVs needed to reach each distinct max-damage value."""
    if invest not in ("hp", "def", "spd"):
        raise ValueError(f"invest must be hp, def or spd, got {invest!r}")

    base_points = (defender_evs or {}).get(invest, 0)
    if not isinstance(base_points, int) or not 0 <= base_points <= MAX_STAT_POINTS:
        raise ValueError(
            f"defender {invest} points must be an integer from 0 to {MAX_STAT_POINTS}"
        )
    investments = list(range(base_points, MAX_STAT_POINTS + 1))
    requests = [
        build_request(
            attacker, move, defender,
            attacker_evs=attacker_evs,
            attacker_opts=attacker_opts,
            defender_evs={**(defender_evs or {}), invest: points},
            defender_opts=defender_opts,
            move_opts=move_opts,
            field_opts=field_opts,
            defender_side=defender_side,
            attacker_side=attacker_side,
        )
        for points in investments
    ]
    if _move_id(move) == "superfang":
        return _all(requests, points=investments)
    return _breakpoints(requests, key=lambda response: response["range"][1], points=investments)


# ---------------------------------------------------------------------------
# Composable filters
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DamageFilter:
    """A question for the calculator, deferred until it has candidates.

    The SQL filters in teambuilder.filters compose into one query; these
    cannot, because each one has to run the calculator per candidate. They
    compose the same way regardless: `&` runs the second check only on the
    names the first kept, so chaining narrows the work instead of doubling it.

    `run` returns {name: one Investment per check, in composition order}.
    """

    natural: str
    run: "Callable[[Iterable[str]], dict[str, tuple[Investment, ...]]]"

    def __and__(self, other: "DamageFilter") -> "DamageFilter":
        def run(candidates: Iterable[str]) -> dict[str, tuple[Investment, ...]]:
            kept = self.run(candidates)
            # A dict iterates as its keys, so this hands the survivors on.
            passed = other.run(kept)
            return {name: kept[name] + passed[name] for name in passed}

        return DamageFilter(f"{self.natural} AND\n{other.natural}", run)

    def __call__(self, candidates: Iterable[str]) -> dict[str, tuple[Investment, ...]]:
        return self.run(candidates)

    def __str__(self):
        return self.natural


def ko_filter(
    move: str,
    defender: str,
    *,
    percent: float = 100.0,
    positive_nature: bool = False,
    require_learns: bool = True,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    db: Path = DB_PATH,
    progress_callback: Callable[[str, int, int], None] | None = None,
    result_callback: Callable[[dict], None] | None = None,
) -> DamageFilter:
    """Keeps candidates that can guarantee `percent`% damage on `defender`.

    Each candidate is asked at its own hardest-hitting ability, so one that is
    dropped cannot do it with any ability. One that is kept may need an
    ability it does not always run - read `.desc` before trusting it.
    When `positive_nature` is True, the neutral result is compared with the
    nature that boosts the move's attacking stat.

    The defender is calculated exactly as `defender_opts` describes it, so its
    ability is whatever slot one happens to be. Thick Fat and friends have to
    be asked for; `survive_filter` is the side that picks abilities for the
    defender.

    `progress_callback(name, index, total)` fires before each candidate and
    `result_callback(row)` fires with a ko_result_row for each one kept. A
    callback that raises stops the run, which is how a web request cancels it.
    """
    percent = validate_percent(percent)
    options = dict(
        attacker_opts=attacker_opts, defender_evs=defender_evs, defender_opts=defender_opts,
        move_opts=move_opts, field_opts=field_opts,
        defender_side=defender_side, attacker_side=attacker_side,
    )

    def run(candidates: Iterable[str]) -> dict[str, tuple[Investment, ...]]:
        names = _species_names(candidates)
        if require_learns:
            names = list(that_learn(move, names, db=db))
        total = len(names)

        kept = {}
        for idx, name in enumerate(names):
            if progress_callback:
                progress_callback(name, idx + 1, total)

            investment = _ko_at_best_ability(
                name, move, defender, percent=percent,
                positive_nature=positive_nature, db=db, **options,
            )
            if investment is not None:
                kept[name] = (investment,)
                if result_callback:
                    result_callback(ko_result_row(name, investment, default_move=move))
        return kept

    threshold = "KOes" if percent == 100.0 else f"deals {percent}% to"
    return DamageFilter(f"{threshold} {defender} with {move}", run)


def _effectiveness(attack_type: str, defender_types: list[str]) -> float:
    """Combined type multiplier of `attack_type` against every defender type."""
    result = 1.0
    for defender_type in defender_types:
        result *= _TYPE_CHART.get(attack_type, {}).get(defender_type, 1.0)
    return result


def can_ko_any_atk(
    defender: str,
    *,
    percent: float = 100.0,
    positive_nature: bool = False,
    attacker_opts: dict | None = None,
    defender_evs: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    db: Path = DB_PATH,
    only_super_effective: bool = True,
    progress_callback: Callable[[str, int, int], None] | None = None,
    result_callback: Callable[[dict], None] | None = None,
) -> DamageFilter:
    """Keeps candidates with any attack that guarantees `percent`% on `defender`.

    The cheapest such move wins, and the result records which one it was.
    Slow by construction: every damaging move in the learnset costs two node
    processes, so this is the filter you run last, on a short list.

    If `only_super_effective` is True, only checks moves that are super effective
    against the defender's types. This significantly speeds up the calculation.
    This check accounts for type-changing abilities (Aerilate, Pixilate, etc.)
    and properly calculates combined effectiveness against dual-type defenders.

    If `progress_callback` is provided, it will be called with (current_name, current_index, total)
    for each candidate processed.

    If `result_callback` is provided, it will be called with a formatted result dict when a
    successful KO is found.

    `positive_nature` also checks the nature that raises each move's attacking stat.
    """
    percent = validate_percent(percent)
    defender = resolve_species(defender, db=db)
    rows = _query("SELECT type1, type2 FROM pokemon WHERE name = ?", [defender], db=db)
    if not rows:
        raise ValueError(f"{defender!r} is not in the pokedex")
    defender_types = [t for t in rows[0] if t]

    # Pre-computed once: which move types, and which type-changing abilities,
    # are super effective against this defender.
    se_move_types = {t for t in _TYPE_CHART if _effectiveness(t, defender_types) >= 2.0}
    se_abilities = {a for a, t in TYPE_CHANGING_ABILITIES.items()
                    if _effectiveness(t, defender_types) >= 2.0}

    options = dict(
        attacker_opts=attacker_opts, defender_evs=defender_evs, defender_opts=defender_opts,
        move_opts=move_opts, field_opts=field_opts,
        defender_side=defender_side, attacker_side=attacker_side,
    )

    def run(candidates: Iterable[str]) -> dict[str, tuple[Investment, ...]]:
        kept = {}
        candidate_list = list(_species_names(candidates))
        total = len(candidate_list)
        # Use tqdm for console output if no callback, otherwise disable it
        iterator = tqdm(candidate_list, desc=f"Attacks that KO {defender}",
                        disable=progress_callback is not None)
        for idx, name in enumerate(iterator):
            if progress_callback:
                progress_callback(name, idx + 1, total)

            # Only Normal moves can be turned super effective by -ate abilities.
            ability_se = bool(set(get_abilities_for_poke(name, db=db)) & se_abilities)

            def worth_checking(move: str) -> bool:
                if not only_super_effective:
                    return True
                if _move_id(move) in {
                    "freezedry", "flyingpress", "weatherball", "terrainpulse",
                    "terablast", "ragingbull", "aurawheel",
                }:
                    return True
                kind = get_move_type(move)
                if not kind:
                    return False  # unknown move type
                return kind in se_move_types or (kind == "Normal" and ability_se)

            cheapest = None
            for move in _damaging_moves(name, db=db):
                if not worth_checking(move):
                    continue
                investment = _ko_at_best_ability(
                    name, move, defender, percent=percent,
                    positive_nature=positive_nature, db=db, **options,
                )
                if investment is None:
                    continue
                investment = investment._replace(move=move)
                if cheapest is None or investment.points < cheapest.points:
                    cheapest = investment
                if cheapest.points == 0:
                    break  # free already, nothing can beat it

            if cheapest is not None:
                kept[name] = (cheapest,)
                if result_callback:
                    result_callback(ko_result_row(name, cheapest))
        return kept

    return DamageFilter(f"KOes {defender} with some attack", run)


def _damaging_moves(name: str, *, db: Path = DB_PATH) -> list[str]:
    """The learnset minus Status moves and minus what the calculator lacks.

    move_category is None for moves champout carries that the Champions data
    does not, and attacking_stat raises on those, so they go out together.
    """
    return [m for m in learnset(name, db=db) if move_category(m) in ("Physical", "Special")]


def survive_filter(
    attacker: str,
    move: str,
    *,
    percent: float = 100.0,
    defender_nature: str | None = None,
    require_learns: bool = True,
    attacker_evs: dict | str | None = None,
    attacker_opts: dict | None = None,
    defender_opts: dict | None = None,
    move_opts: dict | None = None,
    field_opts: dict | None = None,
    defender_side: dict | None = None,
    attacker_side: dict | None = None,
    db: Path = DB_PATH,
    progress_callback: Callable[[str, int, int], None] | None = None,
    result_callback: Callable[[dict], None] | None = None,
) -> DamageFilter:
    """Keeps candidates that can hold `attacker`'s `move` under `percent`%.

    The mirror of ko_filter: there the candidate attacks and picks its best
    ability, here the candidate defends and picks the ability that takes the
    hit best. So a candidate dropped here cannot survive with any ability, and
    one kept may be relying on an ability it does not always run.

    The attacker is calculated as given, which is the same asymmetry ko_filter
    has with its defender: if the attacker's own ability matters, pass it in
    `attacker_opts`, or ask most_damaging_ability for it first.

    Points are spread across HP and whichever defence the move attacks, since
    min_evs_to_survive walks the damage breakpoints rather than pouring
    everything into one stat - so `.points` is the total and `.desc` names the
    split that earned it.
    `defender_nature` is passed to the solver and applied to the defence the
    move targets.

    `progress_callback(name, index, total)` fires before each candidate and
    `result_callback(row)` fires with a survive_result_row for each one kept,
    exactly as in can_ko_any_atk. With a progress callback the tqdm bar is off.
    """
    percent = validate_percent(percent)
    if require_learns and not that_learn(move, [attacker], db=db):
        raise ValueError(f"{attacker} does not learn {move}")

    # The attacker is fixed for the whole run, so settle "32+" style input once.
    # Bound to new names: assigning to attacker_evs inside run() would make it
    # a local there.
    evs, a_opts = normalize_evs(attacker_evs, attacker_opts, attacking_stat(move))
    defensive_stat = relevant_defense_stat(attacking_stat(move))
    natured_defender_opts = with_nature(defender_opts, defender_nature, defensive_stat)

    def run(candidates: Iterable[str]) -> dict[str, tuple[Investment, ...]]:
        kept = {}
        names = _species_names(candidates)
        total = len(names)
        # Two node processes per candidate, same as ko_filter, so a roster-sized
        # list runs for minutes with nothing to show for it otherwise.
        iterator = tqdm(names, desc=f"Surviving {move} from {attacker}",
                        disable=progress_callback is not None)
        for idx, name in enumerate(iterator):
            if progress_callback:
                progress_callback(name, idx + 1, total)
            best = least_damaged_ability(
                name, attacker, move,
                attacker_evs=evs, attacker_opts=a_opts,
                # Max HP and both defences: the strongest version of the
                # question, for the same reason ko_filter maxes the attacking
                # stat before choosing.
                defender_evs={"hp": MAX_STAT_POINTS, "def": MAX_STAT_POINTS, "spd": MAX_STAT_POINTS},
                defender_opts=natured_defender_opts,
                move_opts=move_opts, field_opts=field_opts,
                defender_side=defender_side, attacker_side=attacker_side,
            )
            spreads = min_evs_to_survive(
                attacker, move, name, defender_nature,
                percent=percent,
                attacker_evs=evs, attacker_opts=a_opts,
                defender_opts=_pin_ability(natured_defender_opts, best.names[0]),
                move_opts=move_opts, field_opts=field_opts,
                defender_side=defender_side, attacker_side=attacker_side,
                showAll=False,
            )
            if spreads:
                investment = spreads[0]._replace(
                    ability=_required_ability(best, spreads[0].desc)
                )
                kept[name] = (investment,)
                if result_callback:
                    result_callback(survive_result_row(name, investment))
        return kept

    threshold = "survives" if percent == 100.0 else f"takes under {percent}% from"
    return DamageFilter(f"{threshold} {move} from {attacker}", run)


def can_ko(candidates: Iterable[str], move: str, defender: str, **options) -> dict[str, Investment]:
    """ko_filter run on one set of candidates: {name: cheapest spread}.

    `options` are ko_filter's, which is where they are documented; this only
    unwraps the single-check result so the common case stays a plain mapping.
    """
    return _one_check(ko_filter(move, defender, **options), candidates)


def can_survive(
    candidates: Iterable[str], attacker: str, move: str, **options
) -> dict[str, Investment]:
    """survive_filter run on one set of candidates: {name: cheapest spread}."""
    return _one_check(survive_filter(attacker, move, **options), candidates)


def _one_check(check: DamageFilter, candidates: Iterable[str]) -> dict[str, Investment]:
    return {name: found[0] for name, found in check.run(candidates).items()}


def _species_names(candidates: Iterable[str]) -> list[str]:
    """Candidates as a list, with the one mistake worth catching caught.

    A list of dex numbers reaches DuckDB as ints and fails deep inside an IN
    clause with a cast error, so say what went wrong here instead: search()
    returns whole rows, and its default columns start with the number.
    """
    names = list(candidates)
    wrong = next((n for n in names if not isinstance(n, str)), None)
    if wrong is not None:
        raise TypeError(
            f"candidates must be species names, got {wrong!r} - "
            'select them with search(..., columns="name")'
        )
    return names