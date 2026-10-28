"""teambuilder/api_helpers.py - turn request payloads into calculator options.

Every calculator route used to re-implement these inline. `data` can be
request.json (a dict) or request.args (a MultiDict); both work here.
"""
from functools import reduce
from operator import and_

# Form field name -> damage-calculator property on the defender's side.
DEFENDER_SIDE_FLAGS = {
    "isReflect": "isReflect",
    "isLightScreen": "isLightScreen",
    "isAuroraVeil": "isAuroraVeil",
    "isFriendGuard": "isFriendGuard",
    "isProtect": "isProtected",
    "isLeechSeed": "isSeeded",
    "isSaltCure": "isSaltCured",
}
ALL_STATS = ("hp", "atk", "def", "spa", "spd", "spe")
FIELD_STATE_KEYS = {
    "Gravity": "isGravity",
    "MagicRoom": "isMagicRoom",
    "WonderRoom": "isWonderRoom",
    "FairyAura": "isFairyAura",
}


def truthy(value, default: bool = True) -> bool:
    """'true'/'True'/True -> True. JSON bodies send bools, query strings send text."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _as_list(data, key) -> list:
    if hasattr(data, "getlist"):
        values = data.getlist(key)
        if not values and key == "field":
            values = data.getlist("field[]") or data.getlist("fieldState")
        return values
    value = data.get(key, [])
    if not value and key == "field":
        value = data.get("field[]", data.get("fieldState", []))
    return [value] if isinstance(value, str) else list(value)


def item_ability_opts(data, prefix: str, *, ability: bool = True) -> dict:
    """{'item': ..., 'ability': ...} from f'{prefix}_item' / f'{prefix}_ability'."""
    opts = {}
    if data.get(f"{prefix}_item"):
        opts["item"] = data[f"{prefix}_item"]
    if ability and data.get(f"{prefix}_ability"):
        opts["ability"] = data[f"{prefix}_ability"]
    return opts


def add_boost(opts: dict, data, key: str, stats) -> None:
    """Apply one boost value from the request to several stats (mutates opts)."""
    if data.get(key):
        boosts = opts.setdefault("boosts", {})
        for stat in stats:
            boosts[stat] = int(data[key])


def build_field_opts(data) -> dict:
    """Terrain, weather and global field toggles.

    A supplied battle format is used on both calculator pages.
    """
    field_opts = {}
    for key in ("terrain", "weather"):
        if data.get(key):
            field_opts[key] = data[key]
    if data.get("format"):
        field_opts["gameType"] = data["format"].capitalize()
    for state in _as_list(data, "field"):
        if state in FIELD_STATE_KEYS:
            field_opts[FIELD_STATE_KEYS[state]] = True
    return field_opts


def apply_matchup_conditions(data, field_opts: dict) -> None:
    """Add both sides' battle conditions and defender hazards to the field.

    The one block that was identical in /api/survival and /api/ko-calculation.
    """
    attacker_side: dict[str, bool] = {}
    if truthy(data.get("isHelpingHand"), default=False):
        attacker_side["isHelpingHand"] = True
    if truthy(data.get("isCharge"), default=False):
        attacker_side["isCharge"] = True
    if truthy(data.get("isPowerTrickLeft"), default=False):
        attacker_side["isPowerTrick"] = True
    if attacker_side:
        field_opts["attackerSide"] = attacker_side

    defender_side: dict[str, bool | int] = {
        calc_flag: True
        for form_flag, calc_flag in DEFENDER_SIDE_FLAGS.items()
        if truthy(data.get(form_flag), default=False)
    }
    if truthy(data.get("isPowerTrickRight"), default=False):
        defender_side["isPowerTrick"] = True
    if data.get("spikes") not in (None, "", "0", 0):
        defender_side["spikes"] = int(data["spikes"])
    if truthy(data.get("isSR"), default=False):
        defender_side["isSR"] = True
    if defender_side:
        field_opts["defenderSide"] = defender_side


def build_matchup_options(data) -> tuple[dict, dict, dict]:
    """(attacker_opts, defender_opts, field_opts) for the single-matchup routes."""
    attacker_opts = item_ability_opts(data, "attacker")
    add_boost(attacker_opts, data, "attacker_boost", ("atk", "spa"))   # the move picks which one matters

    defender_opts = item_ability_opts(data, "defender")
    add_boost(defender_opts, data, "defender_boost", ("def", "spd"))

    field_opts = build_field_opts(data)
    apply_matchup_conditions(data, field_opts)
    return attacker_opts, defender_opts, field_opts


def build_bulk_ko_kwargs(data) -> dict:
    """Keyword arguments for can_ko / can_ko_any_atk, empty values as None."""
    defender_evs = {s: int(data[f"defender_{s}"]) for s in ("hp", "def", "spd") if data.get(f"defender_{s}")}
    field_opts = build_field_opts(data)
    apply_matchup_conditions(data, field_opts)
    return dict(
        percent=float(data.get("percent", 100.0)),
        positive_nature=truthy(data.get("positive_nature"), default=False),
        defender_evs=defender_evs or None,
        defender_opts=item_ability_opts(data, "defender") or None,
        attacker_opts=item_ability_opts(data, "attacker", ability=False) or None,
        field_opts=field_opts or None,
        defender_side=data.get("defender_side") or None,
        attacker_side=data.get("attacker_side") or None,
    )


def candidate_names(data, min_stats=("bst",)) -> list[str]:
    """Species passing the page's pre-filters: a type plus any `filter_min_<stat>`."""
    from teambuilder.filters import ability, has_type, min_stat
    from teambuilder.pokedex import search, search_names

    parts = []
    if data.get("filter_type1"):
        parts.append(has_type(data["filter_type1"]))
    if data.get("filter_ability"):
        parts.append(ability(data["filter_ability"]))
    for stat in min_stats:
        if data.get(f"filter_min_{stat}"):
            parts.append(min_stat(stat, int(data[f"filter_min_{stat}"])))

    if parts:
        return [row[0] for row in search(reduce(and_, parts), columns="name")]
    return search_names()
