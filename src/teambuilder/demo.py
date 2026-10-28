"""A worked example of the whole pipeline, wired to `uv run demo`."""

from teambuilder.damage import (
    can_ko,
    can_ko_any_atk,
    min_evs_to_ko,
    min_evs_to_survive,
    survive_filter,
)
from teambuilder.filters import (
    ability,
    has_type,
    learns,
    max_stat,
    min_stat,
    stat_between,
)
from teambuilder.pokedex import search

def print_survival_result(attacker, move, defender, defender_nature, **kwargs):
    result = min_evs_to_survive(attacker, move, defender, defender_nature, **kwargs)
    print(f"{attacker} {move} vs {defender}:")
    if result:
        for inv in result:
            print(f"  {inv}")
    else:
        print("  No viable spread found")

def main():
    print()
    print_survival_result(
        "Charizard-Mega-Y",
        "Weather Ball",
        "Kingambit",
        "1.0",
        percent=100,
        defender_opts={"item":"Occa Berry"},
        attacker_evs="0",
        field_opts={"weather":"Sun"},
        showAll=True
    )
    f = (
        has_type("Grass")
        & stat_between("bst", 400, 600)
        & min_stat("atk", 90)
        & max_stat("spe", 120)
        & learns("Swords Dance")
        & (ability("Chlorophyll") | ability("Overgrow"))
    )
    print(f"Search Filter:\n{f}")
    print()
    for row in search(f, columns="name, type1, type2, atk, spe, bst"):
        print(row)

    print()
    print("Minimum points for Blaziken to always OHKO Incineroar:")
    print(" ", min_evs_to_ko("Blastoise", "Water Spout", "Charizard",field_opts={"weather":"Rain"},defender_evs={"spd":32}))

    print()

    print("Which pokemon can KO mega salamence with triple axel while being base 100 or higher")

    speedy = [row[0] for row in search(min_stat("spe", 130), columns="name")]
    for name, investment in can_ko(speedy, "Triple Axel", "Salamence-Mega").items():
        print(f"  {name:<20} {investment.points} points")

    print("Which pokemon are under 60 speed and survive a mega mence hyper voice")
    slow = [row[0] for row in search(max_stat("spe", 60), columns="name")]
    mence_survival = survive_filter("Salamence-Mega", "Hyper Voice", attacker_evs={"spa": 32 } )
    for name, (investment, ) in mence_survival(slow).items():
        spread = " / ".join(
            f"{points} {stat}" for stat, points in (investment.spread or {}).items()
        )
        print(f"  {name:<20} {investment.points:>2} points to survive  ({spread})")


    print()
    filter = (
         can_ko_any_atk("Salamence-Mega", defender_evs={"hp": 2})
    )
    print("Which base 130 spe mons manage this")
    print(f"{filter}\n")
    # One Investment per AND-ed filter, in composition order - so this unpacks
    # one while `filter` is a single check, and needs another name for every
    # check added to the chain.
    for name, (ko,) in filter(speedy).items():
        print(f"  {name:<20} {ko.points} points to KO with {ko.move}")


if __name__ == "__main__":
    main()