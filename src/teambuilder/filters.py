"""Composable SQL filters over the pokemon table.

A filter is a WHERE fragment plus the values its placeholders need. Keeping
those two things together is what makes filters composable: when you glue two
fragments with AND, you glue their parameter lists in the same order, so the
values still line up with the `?`s left to right in the final query.

Every fragment here refers to the table as `p`, which is the alias
`pokedex.search` gives it. The two have to agree.
"""

from dataclasses import dataclass


def _to_id(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", value.lower())


@dataclass(frozen=True, slots=True)
class Filter:
    """A `WHERE` fragment and the values for its `?` placeholders."""

    sql: str
    natural: str 
    params: tuple[object, ...] = ()

    def __and__(self, other: "Filter") -> "Filter":
        return self._combine("AND", other)

    def __or__(self, other: "Filter") -> "Filter":
        return self._combine("OR", other)

    def __invert__(self) -> "Filter":
        return Filter(f"NOT ({self.sql})", f"not ({self.natural})", self.params)

    def _combine(self, op: str, other: "Filter") -> "Filter":
        # Parens keep precedence explicit in the SQL, so mixing & and | never
        # surprises. The description uses layout instead of parens: AND ends
        # the line, OR keeps its operands together on one.
        # self.params first because self.sql comes first in the string.
        separator = f" {op}\n" if op == "AND" else f" {op} "
        return Filter(
            f"({self.sql} {op} {other.sql})",
            f"{self.natural}{separator}{other.natural}",
            self.params + other.params,
        )

    def __str__(self): return self.natural

def has_type(type_: str) -> Filter:
    return Filter(
        "lower(?) IN (lower(p.type1), lower(coalesce(p.type2, p.type1)))",
        f"Is of type: {type_}",
        (type_,),
    )

def has_type1(type_: str) -> Filter:
    return Filter("p.type1 = ?", f"Type 1 is: {type_}", (type_,))

def has_type2(type_: str) -> Filter:
    return Filter("p.type2 = ?", f"Type 2 is: {type_}", (type_,))

def learns(move: str) -> Filter:
    from teambuilder.pokedex import resolve_move

    canonical = resolve_move(move)
    return Filter(
        "EXISTS (SELECT 1 FROM pokemon_moves m WHERE m.pokemon = p.name "
        "AND regexp_replace(lower(m.move), '[^a-z0-9]', '', 'g') = ?)",
        f"Learns: {canonical}",
        (_to_id(canonical),),
    )

def ability(ability: str) -> Filter:
    from teambuilder.pokedex import resolve_ability

    canonical = resolve_ability(ability)
    return Filter(
        "regexp_replace(lower(?), '[^a-z0-9]', '', 'g') IN "
        "(regexp_replace(lower(p.ability1), '[^a-z0-9]', '', 'g'), "
        "regexp_replace(lower(p.ability2), '[^a-z0-9]', '', 'g'), "
        "regexp_replace(lower(p.ability_hidden), '[^a-z0-9]', '', 'g'))",
        f"Ability: {canonical}",
        (canonical,),
    )



STATS = ("hp", "atk", "def", "spa", "spd", "spe", "bst")


def _column(stat: str) -> str:
    """Validate a stat name, since a column has to be interpolated, not bound.

    Placeholders only stand for values, never identifiers, so `stat` ends up
    in the SQL as text - checking it against STATS is what keeps that safe.
    The quotes let "def" through: it is a column here but a keyword in SQL.
    """
    if stat not in STATS:
        raise ValueError(f"unknown stat {stat!r}, expected one of {', '.join(STATS)}")
    return f'p."{stat}"'


def min_stat(stat: str, value: int) -> Filter:
    return Filter(f"{_column(stat)} >= ?", f"At Least {value} {stat}", (value,))


def max_stat(stat: str, value: int) -> Filter:
    return Filter(f"{_column(stat)} <= ?", f"At Most {value} {stat}", (value,))


def stat_between(stat: str, low: int, high: int) -> Filter:
    # BETWEEN is inclusive on both ends, like min_stat & max_stat would be.
    return Filter(f"{_column(stat)} BETWEEN ? AND ?", f"{stat} between {low} and {high}", (low, high))
