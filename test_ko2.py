import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, 'src')

from teambuilder.calc import is_super_effective
from teambuilder.damage import Investment, can_ko_any_atk
from teambuilder.pokedex import learnset


class SuperEffectiveMoveRegressionTests(unittest.TestCase):
    def test_aerodactyl_mega_has_super_effective_moves_vs_fire_flying(self):
        moves = learnset('Aerodactyl-Mega')
        se_moves = [m for m in moves if is_super_effective(m, ['Fire', 'Flying'])]

        self.assertGreater(len(se_moves), 0)
        self.assertIn('Meteor Beam', se_moves)

    def test_single_candidate_can_ko_run_is_fast_and_valid(self):
        results = can_ko_any_atk('Charizard-Mega Y', only_super_effective=True).run(['Aerodactyl-Mega'])

        self.assertIn('Aerodactyl-Mega', results)
        self.assertGreater(results['Aerodactyl-Mega'][0].points, -1)

    def test_dragonize_makes_normal_moves_eligible_against_dragon(self):
        with (
            patch("teambuilder.damage._query", return_value=[("Dragon", None)]),
            patch("teambuilder.damage.get_abilities_for_poke", return_value=["Dragonize"]),
            patch("teambuilder.damage._damaging_moves", return_value=["Normal Move"]),
            patch("teambuilder.damage.get_move_type", return_value="Normal"),
            patch(
                "teambuilder.damage._ko_at_best_ability",
                return_value=Investment(0, "test", (0.0, 0.0), (1, 2), 100),
            ) as ko_check,
        ):
            results = can_ko_any_atk("Dragonite").run(["Feraligatr-Mega"])

        self.assertIn("Feraligatr-Mega", results)
        ko_check.assert_called_once()


if __name__ == '__main__':
    unittest.main()
