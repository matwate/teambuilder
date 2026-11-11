from pathlib import Path
from difflib import get_close_matches
import re

import duckdb

from teambuilder.data import DB_PATH
from teambuilder.filters import Filter


def _query(sql: str, params: list, *, db: Path = DB_PATH) -> list[tuple]:
    with duckdb.connect(db, read_only=True) as con:
        return con.execute(sql, params).fetchall()


def _to_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def resolve_species(name: str, *, db: Path = DB_PATH) -> str:
    names = [row[0] for row in _query("SELECT name FROM pokemon", [], db=db)]
    matches = { _to_id(canonical): canonical for canonical in names }
    if _to_id(name) in matches:
        return matches[_to_id(name)]
    suggestion = get_close_matches(name, names, n=1, cutoff=0.6)
    hint = f" Did you mean {suggestion[0]!r}?" if suggestion else ""
    raise ValueError(f"{name!r} is not in the pokedex.{hint}")


def resolve_move(move: str, *, db: Path = DB_PATH) -> str:
    names = [row[0] for row in _query("SELECT DISTINCT move FROM pokemon_moves", [], db=db)]
    matches = {_to_id(canonical): canonical for canonical in names}
    if _to_id(move) in matches:
        return matches[_to_id(move)]
    suggestion = get_close_matches(move, names, n=1, cutoff=0.6)
    hint = f" Did you mean {suggestion[0]!r}?" if suggestion else ""
    raise ValueError(f"{move!r} is not in the move data.{hint}")


def resolve_ability(ability: str, *, db: Path = DB_PATH) -> str:
    rows = _query(
        "SELECT ability FROM ("
        "SELECT ability1 AS ability FROM pokemon UNION "
        "SELECT ability2 AS ability FROM pokemon UNION "
        "SELECT ability_hidden AS ability FROM pokemon"
        ") WHERE ability IS NOT NULL GROUP BY ability",
        [],
        db=db,
    )
    names = [row[0] for row in rows]
    matches = {_to_id(canonical): canonical for canonical in names}
    if _to_id(ability) in matches:
        return matches[_to_id(ability)]
    suggestion = get_close_matches(ability, names, n=1, cutoff=0.6)
    hint = f" Did you mean {suggestion[0]!r}?" if suggestion else ""
    raise ValueError(f"{ability!r} is not in the ability data.{hint}")


def search(
    filters: Filter | None = None,
    *,
    columns: str = "number, name, type1, type2",
    order_by: str = "number",
    db: Path = DB_PATH,
) -> list[tuple]:
    # "TRUE" is a valid WHERE, so no-filters needs no special case.
    where = filters.sql if filters else "TRUE"
    params = filters.params if filters else ()
    sql = f"SELECT {columns} FROM pokemon p WHERE {where} ORDER BY {order_by}"

    return _query(sql, list(params), db=db)

def search_names(
    filters: Filter | None = None,
    *,
    order_by: str = "number",
    db: Path = DB_PATH,
) -> list[str]:
    # "TRUE" is a valid WHERE, so no-filters needs no special case.
    columns = "name"
    where = filters.sql if filters else "TRUE"
    params = filters.params if filters else ()
    sql = f"SELECT {columns} FROM pokemon p WHERE {where} ORDER BY {order_by}"

    return [x[0] for x in _query(sql, list(params), db=db)] 




def get_abilities_for_poke(name: str, *, db: Path = DB_PATH) -> tuple[str, ...]:
    """The distinct abilities a pokemon can have, in slot order.

    Most entries repeat a slot ("Overgrow/Overgrow/Chlorophyll"), so the
    duplicates are dropped - dict.fromkeys keeps the first occurrence of each.
    """
    canonical = resolve_species(name, db=db)
    rows = _query(
        "SELECT ability1, ability2, ability_hidden FROM pokemon WHERE name = ?",
        [canonical],
        db=db,
    )
    return tuple(dict.fromkeys(a for a in rows[0] if a))


def that_learn(move: str, names: list[str], *, db: Path = DB_PATH) -> list[str]:
    """The subset that actually has the move, in the order given.

    Without this a search happily reports that Snorlax KOes things with Leaf
    Storm, since the calculator will calculate any move for any pokemon.
    """
    if not names:
        return []
    canonical_move = resolve_move(move, db=db)
    placeholders = ", ".join(["?"] * len(names))
    rows = _query(
        "SELECT pokemon FROM pokemon_moves "
        "WHERE regexp_replace(lower(move), '[^a-z0-9]', '', 'g') = ? "
        f"AND regexp_replace(lower(pokemon), '[^a-z0-9]', '', 'g') IN ({placeholders})",
        [_to_id(canonical_move), *(_to_id(name) for name in names)],
        db=db,
    )
    learners = {_to_id(row[0]) for row in rows}
    return [name for name in names if _to_id(name) in learners]


def learnset(name: str, db:Path = DB_PATH) -> list[str]:
    """Every move `name` learns, once each, sorted by name.

    Sorted rather than left to a set, whose order for strings changes with each
    process's hash seed: callers that keep the first of several tied moves
    would otherwise name a different one every run.
    """
    canonical = resolve_species(name, db=db)
    rows = _query(
            "SELECT DISTINCT move FROM pokemon_moves WHERE pokemon = ? ORDER BY move",
            [canonical],
            db=db
    )
    return [row[0] for row in rows]
