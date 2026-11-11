import unittest
from unittest.mock import patch

from teambuilder.damage import _breakpoints, _cheapest


def response(value: int) -> dict:
    return {
        "desc": "test",
        "percent": [value, value],
        "range": [value, value],
        "defenderMaxHP": 100,
    }


class SolverSearchTests(unittest.TestCase):
    def test_cheapest_uses_binary_search(self):
        requests = [{"points": points} for points in range(33)]

        def calculate(request):
            return response(request["points"])

        with patch("teambuilder.damage.calculate", side_effect=calculate) as calc:
            result = _cheapest(requests, lambda answer: answer["range"][0] >= 21)

        if result is None:
            self.fail("Solver did not find an investment")
        self.assertEqual(result.points, 21)
        self.assertLessEqual(calc.call_count, 7)

    def test_breakpoints_searches_each_monotonic_transition(self):
        requests = [{"points": points} for points in range(33)]

        def calculate(request):
            points = request["points"]
            return response(32 - points // 8)

        with patch("teambuilder.damage.calculate", side_effect=calculate) as calc:
            results = _breakpoints(requests, key=lambda answer: answer["range"][1])

        self.assertEqual([result.points for result in results], [0, 8, 16, 24, 32])
        self.assertLess(calc.call_count, len(requests))


if __name__ == "__main__":
    unittest.main()
