import json
from collections.abc import Callable

import typer

from teambuilder import data
from teambuilder.calc import CalcError, build_request, calculate, move_category
from teambuilder.damage import min_evs_to_ko, min_evs_to_survive
from teambuilder.filters import (
    STATS,
    Filter,
    ability,
    has_type,
    learns,
    max_stat,
    min_stat,
    stat_between,
)
from teambuilder.pokedex import search

app = typer.Typer(
    help="Search the Champions pokedex and calculate damage.",
    no_args_is_help=True,
    add_completion=False,
)

# Shared between the two calculator commands: stat spreads and option blobs
# are JSON because they mirror the calculator's own request format, which the
# README documents in full.
JSON_HELP = "JSON object, e.g. '{\"nature\": \"Adamant\"}'"


@app.command("build-db")
def build_db():
    """Parse the champout dumps into the DuckDB database."""
    data.build()


@app.command()
def find(
    type_: list[str] = typer.Option([], "--type", "-t", help="Has this type. Repeatable."),
    move: list[str] = typer.Option([], "--learns", "-l", help="Learns this move. Repeatable."),
    abilities: list[str] = typer.Option(
        [], "--ability", "-a", help="Has any one of these abilities. Repeatable."
    ),
    minimum: list[str] = typer.Option([], "--min", help="stat=value, e.g. --min atk=120."),
    maximum: list[str] = typer.Option([], "--max", help="stat=value, e.g. --max spe=60."),
    between: list[str] = typer.Option(
        [], "--between", help="stat=low:high, e.g. --between bst=400:600."
    ),
    order_by: str = typer.Option("number", "--order-by", help="SQL ORDER BY clause."),
    show_filter: bool = typer.Option(True, help="Print the filter before the results."),
):
    """Find pokemon matching every criterion given.

    Types, moves and stat bounds are ANDed together; abilities are ORed with
    each other, since a pokemon only ever has one at a time.
    """
    filters = [has_type(t) for t in type_]
    filters += [learns(m) for m in move]
    filters += [_stat_filter(min_stat, spec) for spec in minimum]
    filters += [_stat_filter(max_stat, spec) for spec in maximum]
    filters += [_range_filter(spec) for spec in between]
    if abilities:
        any_ability = ability(abilities[0])
        for name in abilities[1:]:
            any_ability = any_ability | ability(name)
        filters.append(any_ability)

    combined = None
    for one in filters:
        combined = one if combined is None else combined & one

    if show_filter and combined is not None:
        typer.echo(f"{combined}\n")

    rows = search(combined, columns="number, name, type1, type2, bst", order_by=order_by)
    for number, name, type1, type2, bst in rows:
        types = type1 if type2 is None else f"{type1}/{type2}"
        typer.echo(f"{number:>4}  {name:<24} {types:<18} {bst}")
    typer.echo(f"\n{len(rows)} result{'' if len(rows) == 1 else 's'}")


@app.command()
def ko(
    attacker: str,
    move: str,
    defender: str,
    percent: float = typer.Option(100.0, help="Damage to guarantee, as % of the defender's HP."),
    attacker_opts: str = typer.Option("{}", help=JSON_HELP),
    defender_evs: str = typer.Option("{}", help=JSON_HELP),
    defender_opts: str = typer.Option("{}", help=JSON_HELP),
    move_opts: str = typer.Option("{}", help=JSON_HELP),
    field_opts: str = typer.Option("{}", help=JSON_HELP),
):
    """Fewest attacking stat points that guarantee the damage."""
    _report(
        lambda: min_evs_to_ko(
            attacker, move, defender,
            percent=percent,
            attacker_opts=_json(attacker_opts, "--attacker-opts"),
            defender_evs=_json(defender_evs, "--defender-evs"),
            defender_opts=_json(defender_opts, "--defender-opts"),
            move_opts=_json(move_opts, "--move-opts"),
            field_opts=_json(field_opts, "--field-opts"),
        ),
        f"no spread up to 32 points deals {percent}%",
    )


@app.command()
def survive(
    attacker: str,
    move: str,
    defender: str,
    percent: float = typer.Option(100.0, help="Damage to stay under, as % of the defender's HP."),
    attacker_evs: str = typer.Option("{}", help=JSON_HELP),
    attacker_opts: str = typer.Option("{}", help=JSON_HELP),
    defender_evs: str = typer.Option("{}", help=JSON_HELP),
    defender_opts: str = typer.Option("{}", help=JSON_HELP),
    move_opts: str = typer.Option("{}", help=JSON_HELP),
    field_opts: str = typer.Option("{}", help=JSON_HELP),
):
    """Fewest HP and defence points that hold the damage under the threshold."""
    # min_evs_to_survive lists every tied spread, cheapest first; one is enough.
    _report(
        lambda: (min_evs_to_survive(
            attacker, move, defender,
            percent=percent,
            attacker_evs=_json(attacker_evs, "--attacker-evs"),
            attacker_opts=_json(attacker_opts, "--attacker-opts"),
            defender_evs=_json(defender_evs, "--defender-evs"),
            defender_opts=_json(defender_opts, "--defender-opts"),
            move_opts=_json(move_opts, "--move-opts"),
            field_opts=_json(field_opts, "--field-opts"),
        ) or [None])[0],
        f"no HP/defence spread up to 32/32 points holds the damage under {percent}%",
    )


@app.command()
def category(move: str):
    """Print whether a move is Physical, Special or Status."""
    typer.echo(move_category(move) or "not in the Champions move data")


@app.command("calc")
def calc_command(
    attacker: str,
    move: str,
    defender: str,
    attacker_evs: str = typer.Option("{}", help=JSON_HELP),
    attacker_opts: str = typer.Option("{}", help=JSON_HELP),
    defender_evs: str = typer.Option("{}", help=JSON_HELP),
    defender_opts: str = typer.Option("{}", help=JSON_HELP),
    move_opts: str = typer.Option("{}", help=JSON_HELP),
    field_opts: str = typer.Option("{}", help=JSON_HELP),
    show_json: bool = typer.Option(False, "--json", help="Print the whole response."),
):
    """Run one damage calculation."""
    request = build_request(
        attacker, move, defender,
        attacker_evs=_json(attacker_evs, "--attacker-evs"),
        attacker_opts=_json(attacker_opts, "--attacker-opts"),
        defender_evs=_json(defender_evs, "--defender-evs"),
        defender_opts=_json(defender_opts, "--defender-opts"),
        move_opts=_json(move_opts, "--move-opts"),
        field_opts=_json(field_opts, "--field-opts"),
    )
    try:
        response = calculate(request)
    except CalcError as err:
        raise typer.BadParameter(str(err)) from err
    typer.echo(json.dumps(response, indent=2) if show_json else response["desc"])


@app.command()
def raw(
    file: typer.FileText = typer.Argument(
        "-", help="File of newline-delimited JSON requests, or - for stdin."
    ),
):
    """Run raw calculator requests, one JSON object per line.

    The escape hatch for anything the other commands cannot express: the
    request format is documented at the top of calc.js.
    """
    requests = [json.loads(line) for line in file if line.strip()]
    for response in calculate(requests):
        typer.echo(json.dumps(response))


def _report(search_for, empty_message: str):
    # Called rather than passed a result so a rejected move or species comes
    # out as a usage error, not a traceback.
    try:
        result = search_for()
    except (ValueError, CalcError) as err:
        raise typer.BadParameter(str(err)) from err
    if result is None:
        typer.echo(empty_message)
        raise typer.Exit(1)
    typer.echo(f"{result.points} points")
    typer.echo(result.desc)


def _json(text: str, option: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as err:
        raise typer.BadParameter(f"{option} is not valid JSON: {err}") from err
    if not isinstance(value, dict):
        raise typer.BadParameter(f"{option} must be a JSON object, got {type(value).__name__}")
    return value


def _stat_filter(make: Callable[..., Filter], spec: str) -> Filter:
    stat, _, value = spec.partition("=")
    if not value:
        raise typer.BadParameter(f"expected stat=value, got {spec!r}")
    return make(_stat(stat), _int(value, spec))


def _range_filter(spec: str) -> Filter:
    stat, _, bounds = spec.partition("=")
    low, _, high = bounds.partition(":")
    if not low or not high:
        raise typer.BadParameter(f"expected stat=low:high, got {spec!r}")
    return stat_between(_stat(stat), _int(low, spec), _int(high, spec))


def _stat(stat: str) -> str:
    if stat not in STATS:
        raise typer.BadParameter(f"unknown stat {stat!r}, expected one of {', '.join(STATS)}")
    return stat


def _int(value: str, spec: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise typer.BadParameter(f"{value!r} in {spec!r} is not a number") from None


if __name__ == "__main__":
    app()
