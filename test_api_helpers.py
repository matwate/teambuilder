import sys
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "src"))

from werkzeug.datastructures import MultiDict

from teambuilder.api_helpers import (
    build_bulk_ko_kwargs,
    build_matchup_options,
    candidate_names,
)
from teambuilder.calc import build_request, calculate
from teambuilder.damage import (
    BestAbility, Investment, _required_ability, ko_filter, ko_result_row, survive_filter,
)
from teambuilder.pokedex import get_abilities_for_poke
from teambuilder.web_server import app, run_bulk_survive, stream_events


class MatchupOptionsTests(unittest.TestCase):
    def test_maps_calculator_field_controls_to_damage_calculator_sides(self):
        data = {
            "format": "singles",
            "terrain": "Electric",
            "weather": "Rain",
            "field": ["Gravity", "MagicRoom", "WonderRoom", "FairyAura"],
            "isHelpingHand": True,
            "isCharge": True,
            "isPowerTrickLeft": True,
            "isPowerTrickRight": True,
            "isReflect": True,
            "isLightScreen": True,
            "isAuroraVeil": True,
            "isFriendGuard": True,
            "isProtect": True,
            "isLeechSeed": True,
            "isSaltCure": True,
            "spikes": "2",
            "isSR": True,
        }

        attacker_opts, defender_opts, field_opts = build_matchup_options(data)

        self.assertEqual(attacker_opts, {})
        self.assertEqual(defender_opts, {})
        self.assertEqual(
            field_opts,
            {
                "gameType": "Singles",
                "terrain": "Electric",
                "weather": "Rain",
                "isGravity": True,
                "isMagicRoom": True,
                "isWonderRoom": True,
                "isFairyAura": True,
                "attackerSide": {
                    "isHelpingHand": True,
                    "isCharge": True,
                    "isPowerTrick": True,
                },
                "defenderSide": {
                    "isReflect": True,
                    "isLightScreen": True,
                    "isAuroraVeil": True,
                    "isFriendGuard": True,
                    "isProtected": True,
                    "isSeeded": True,
                    "isSaltCured": True,
                    "isPowerTrick": True,
                    "spikes": 2,
                    "isSR": True,
                },
            },
        )

    def test_single_calculation_returns_damage_range_and_description(self):
        result = calculate(build_request("Charizard", "Flamethrower", "Venusaur"))

        self.assertIsInstance(result["range"], list)
        self.assertEqual(len(result["range"]), 2)
        self.assertGreater(result["range"][1], result["range"][0])
        self.assertIn("vs.", result["desc"])

    def test_helping_hand_increases_damage_in_built_calculation(self):
        attacker_opts, defender_opts, field_opts = build_matchup_options(
            {"isHelpingHand": True}
        )
        base = calculate(build_request("Charizard", "Flamethrower", "Venusaur"))
        boosted = calculate(
            build_request(
                "Charizard",
                "Flamethrower",
                "Venusaur",
                attacker_opts=attacker_opts or None,
                defender_opts=defender_opts or None,
                field_opts=field_opts or None,
            )
        )

        self.assertGreater(boosted["range"][1], base["range"][1])

    def test_charge_increases_damage_for_electric_moves(self):
        attacker_opts, defender_opts, field_opts = build_matchup_options({"isCharge": True})
        base = calculate(build_request("Pikachu", "Thunderbolt", "Gyarados"))
        boosted = calculate(
            build_request(
                "Pikachu",
                "Thunderbolt",
                "Gyarados",
                attacker_opts=attacker_opts or None,
                defender_opts=defender_opts or None,
                field_opts=field_opts or None,
            )
        )

        self.assertGreater(boosted["range"][1], base["range"][1])

    def test_bulk_ko_field_settings_match_calculator_conditions(self):
        kwargs = build_bulk_ko_kwargs({
            "format": "doubles",
            "terrain": "Electric",
            "weather": "Rain",
            "field": ["Gravity", "MagicRoom", "FairyAura"],
            "isHelpingHand": True,
            "isCharge": True,
            "isPowerTrickLeft": True,
            "isPowerTrickRight": True,
            "isSR": True,
            "spikes": "3",
            "isReflect": True,
            "isLightScreen": True,
            "isAuroraVeil": True,
            "isFriendGuard": True,
            "isProtect": True,
            "isLeechSeed": True,
            "isSaltCure": True,
        })

        self.assertEqual(kwargs["field_opts"], {
            "gameType": "Doubles",
            "terrain": "Electric",
            "weather": "Rain",
            "isGravity": True,
            "isMagicRoom": True,
            "isFairyAura": True,
            "attackerSide": {
                "isHelpingHand": True,
                "isCharge": True,
                "isPowerTrick": True,
            },
            "defenderSide": {
                "isReflect": True,
                "isLightScreen": True,
                "isAuroraVeil": True,
                "isFriendGuard": True,
                "isProtected": True,
                "isSeeded": True,
                "isSaltCured": True,
                "isPowerTrick": True,
                "spikes": 3,
                "isSR": True,
            },
        })
        self.assertFalse(kwargs["positive_nature"])

    def test_bulk_ko_positive_nature_is_opt_in(self):
        self.assertTrue(build_bulk_ko_kwargs({"positive_nature": "true"})["positive_nature"])
        self.assertFalse(build_bulk_ko_kwargs({"positive_nature": "false"})["positive_nature"])

    def test_bulk_survive_maps_repeated_field_states_and_conditions(self):
        data = MultiDict([
            ("attacker", "Pikachu"),
            ("move", "Thunderbolt"),
            ("attacker_evs", "32+"),
            ("defender_nature", "1.1"),
            ("format", "singles"),
            ("terrain", "Electric"),
            ("weather", "Rain"),
            ("field[]", "Gravity"),
            ("field[]", "WonderRoom"),
            ("spikes", "2"),
            ("isHelpingHand", "true"),
            ("isCharge", "true"),
            ("isPowerTrickLeft", "true"),
            ("isSR", "true"),
            ("isReflect", "true"),
            ("isLightScreen", "true"),
            ("isAuroraVeil", "true"),
            ("isFriendGuard", "true"),
            ("isProtect", "true"),
            ("isLeechSeed", "true"),
            ("isSaltCure", "true"),
            ("isPowerTrickRight", "true"),
        ])

        with patch("teambuilder.web_server.can_survive", return_value={}) as calculate_survival:
            run_bulk_survive(["Snorlax"], data)

        options = calculate_survival.call_args.kwargs
        self.assertEqual(options["field_opts"], {
            "gameType": "Singles",
            "terrain": "Electric",
            "weather": "Rain",
            "isGravity": True,
            "isWonderRoom": True,
            "attackerSide": {
                "isHelpingHand": True,
                "isCharge": True,
                "isPowerTrick": True,
            },
            "defenderSide": {
                "isReflect": True,
                "isLightScreen": True,
                "isAuroraVeil": True,
                "isFriendGuard": True,
                "isProtected": True,
                "isSeeded": True,
                "isSaltCured": True,
                "isPowerTrick": True,
                "spikes": 2,
                "isSR": True,
            },
        })
        self.assertEqual(options["defender_nature"], "1.1")

    def test_bulk_survive_ability_filter_excludes_ineligible_species(self):
        names = candidate_names({"filter_ability": "Drought"})

        self.assertIn("Ninetales", names)
        self.assertNotIn("Venusaur", names)
        self.assertTrue(all(
            "Drought" in get_abilities_for_poke(name)
            for name in names
        ))

    def test_search_applies_defense_bounds_sent_by_the_ui(self):
        with app.test_client() as client:
            response = client.post(
                "/api/search",
                json={
                    "move": "Flamethrower",
                    "defender_min": 150,
                    "defender_max": 160,
                },
            )

        self.assertEqual(response.status_code, 200)
        results = response.get_json()["results"]
        self.assertTrue(results)
        self.assertTrue(all(150 <= pokemon["def"] <= 160 for pokemon in results))

    def test_bulk_pages_render_the_shared_calculator_field_panel(self):
        with app.test_client() as client:
            calculator = client.get("/")
            bulk_ko = client.get("/bulk-ko")
            bulk_survive = client.get("/bulk-survive")

        for response in (calculator, bulk_ko, bulk_survive):
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'<fieldset class="field-info">', response.data)
            self.assertIn(b'id="helpingHand"', response.data)
            self.assertIn(b'id="powerTrickR"', response.data)
            self.assertIn(b'name="fieldState"', response.data)

        self.assertIn(b'id="defender_nature"', bulk_survive.data)
        self.assertIn(b'id="attacker_nature"', bulk_ko.data)
        self.assertIn(b"Required Ability", bulk_survive.data)
        self.assertIn(b"<th>HP</th>", bulk_survive.data)
        self.assertIn(b"<th>Def</th>", bulk_survive.data)
        self.assertIn(b'class="result-table"', bulk_ko.data)
        self.assertIn(b'class="result-table"', bulk_survive.data)
        self.assertRegex(calculator.data, rb'<input(?=[^>]*id="singles-format")(?=[^>]*checked)[^>]*>')
        for response in (bulk_ko, bulk_survive):
            self.assertRegex(response.data, rb'<input(?=[^>]*id="doubles-format")(?=[^>]*checked)[^>]*>')

    def test_bulk_ko_checks_nature_that_raises_the_move_stat(self):
        for move, expected_nature in (("Close Combat", "Adamant"), ("Flamethrower", "Modest")):
            with self.subTest(move=move):
                checked_natures = []

                def fake_minimum(_attacker, _move, _defender, *, attacker_opts=None, **_kwargs):
                    nature = (attacker_opts or {}).get("nature", "Serious")
                    checked_natures.append(nature)
                    points = 2 if nature == expected_nature else 4
                    return Investment(points, nature, (0.0, 0.0), (1, 2), 100)

                with (
                    patch(
                        "teambuilder.damage.most_damaging_ability",
                        return_value=BestAbility(("Blaze",), (1, 2), ""),
                    ),
                    patch("teambuilder.damage.min_evs_to_ko", side_effect=fake_minimum),
                    patch("teambuilder.damage._required_ability", return_value="Blaze"),
                ):
                    found = ko_filter(
                        move, "Snorlax", require_learns=False, positive_nature=True
                    ).run(["Pikachu"])

                self.assertIn("Serious", checked_natures)
                self.assertIn(expected_nature, checked_natures)
                self.assertEqual(found["Pikachu"][0].points, 2)

    def test_bulk_survive_nature_follows_move_defense_stat(self):
        cases = (("Close Combat", "Relaxed"), ("Flamethrower", "Sassy"))
        for move, expected_nature in cases:
            with self.subTest(move=move):
                with (
                    patch(
                        "teambuilder.damage.least_damaged_ability",
                        return_value=BestAbility(("Thick Fat",), (1, 2), ""),
                    ) as ability_scan,
                    patch(
                        "teambuilder.damage.min_evs_to_survive",
                        return_value=[
                            Investment(
                                1, "test -- Thick Fat", (0.0, 0.0), (1, 2), 100,
                                spread={"hp": 1},
                            )
                        ],
                    ) as minimum_spread,
                ):
                    found = survive_filter(
                        "Pikachu", move, require_learns=False, defender_nature="1.1",
                        progress_callback=lambda *_: None,
                    ).run(["Snorlax"])

                self.assertEqual(
                    ability_scan.call_args.kwargs["defender_opts"]["nature"],
                    expected_nature,
                )
                self.assertEqual(minimum_spread.call_args.args[3], "1.1")
                self.assertEqual(
                    minimum_spread.call_args.kwargs["defender_opts"]["nature"],
                    expected_nature,
                )
                self.assertFalse(minimum_spread.call_args.kwargs["showAll"])
                self.assertEqual(found["Snorlax"][0].ability, "Thick Fat")

    def test_only_abilities_named_in_the_damage_description_are_required(self):
        best = BestAbility(("Bulletproof",), (0, 0), "")
        self.assertEqual(
            _required_ability(best, "Weather Ball vs. Bulletproof Chesnaught-Mega: 0-0"),
            "Bulletproof",
        )

        best = BestAbility(("Lightning Rod",), (145, 172), "")
        self.assertIsNone(
            _required_ability(best, "Weather Ball vs. 28 HP / 30 SpD Sceptile-Mega: 145-172")
        )

    def test_ko_result_row_displays_any_when_no_ability_is_required(self):
        investment = Investment(
            1, "32 Atk Choice Band Garchomp ...", (0.0, 0.0), (1, 2), 100
        )
        self.assertEqual(ko_result_row("Garchomp", investment)["ability"], "Any")

    def test_closing_stream_stops_worker(self):
        started = Event()
        stopped = Event()

        def task(emit):
            started.set()
            try:
                while True:
                    emit({"type": "progress"})
            finally:
                stopped.set()

        with app.test_request_context():
            response = stream_events(task)
            events = iter(response.response)
            next(events)
            self.assertTrue(started.is_set())
            events.close()

        self.assertTrue(stopped.wait(timeout=1))

    def test_bulk_ko_stream_endpoint_used_by_page_exists(self):
        with (
            patch("teambuilder.web_server.candidate_names", return_value=["Pikachu"]),
            patch(
                "teambuilder.web_server.run_bulk_ko",
                return_value=[{"name": "Pikachu", "move": "Thunderbolt"}],
            ) as run,
            app.test_client() as client,
        ):
            response = client.get(
                "/api/bulk-ko-stream",
                query_string=[
                    ("defender", "Gyarados"),
                    ("move", "Thunderbolt"),
                    ("field[]", "Gravity"),
                    ("isCharge", "true"),
                ],
                buffered=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"type": "batch_results"', response.data)
        self.assertIn(b'"success": true', response.data)
        self.assertEqual(run.call_args.args[0], ["Pikachu"])
        self.assertEqual(run.call_args.args[1].getlist("field[]"), ["Gravity"])
        self.assertIsNotNone(run.call_args.kwargs["progress_callback"])

if __name__ == "__main__":
    unittest.main()
