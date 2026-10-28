from pathlib import Path

import duckdb

from teambuilder.data import DB_PATH
from teambuilder.filters import Filter


def _query(sql: str, params: list, *, db: Path = DB_PATH) -> list[tuple]:
    with duckdb.connect(db, read_only=True) as con:
        return con.execute(sql, params).fetchall()


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
    rows = _query(
        "SELECT ability1, ability2, ability_hidden FROM pokemon WHERE name = ?", [name], db=db
    )
    if not rows:
        raise ValueError(f"{name!r} is not in the pokedex")
    return tuple(dict.fromkeys(a for a in rows[0] if a))


def that_learn(move: str, names: list[str], *, db: Path = DB_PATH) -> list[str]:
    """The subset that actually has the move, in the order given.

    Without this a search happily reports that Snorlax KOes things with Leaf
    Storm, since the calculator will calculate any move for any pokemon.
    """
    if not names:
        return []
    placeholders = ", ".join(["?"] * len(names))
    rows = _query(
        f"SELECT pokemon FROM pokemon_moves WHERE move = ? AND pokemon IN ({placeholders})",
        [move, *names],
        db=db,
    )
    learners = {row[0] for row in rows}
    return [name for name in names if name in learners]


def learnset(name: str, db:Path = DB_PATH) -> list[str]:
    """Every move `name` learns, once each, sorted by name.

    Sorted rather than left to a set, whose order for strings changes with each
    process's hash seed: callers that keep the first of several tied moves
    would otherwise name a different one every run.
    """
    rows = _query(
            "SELECT DISTINCT move FROM pokemon_moves WHERE pokemon = ? ORDER BY move",
            [name],
            db=db
    )
    return [row[0] for row in rows]
