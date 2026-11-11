import sys
import unittest

sys.path.insert(0, 'src')

from teambuilder.damage import can_ko_any_atk
from teambuilder.pokedex import search_names


class KoAnyAtkRegressionTests(unittest.TestCase):
    def test_can_ko_any_atk_returns_results_on_a_small_sample(self):
        candidates = search_names()[:10]
        filter_obj = can_ko_any_atk('Charizard-Mega Y', only_super_effective=True)
        results = filter_obj.run(candidates)

        self.assertTrue(results)
        self.assertLessEqual(len(results), len(candidates))


if __name__ == '__main__':
    unittest.main()
