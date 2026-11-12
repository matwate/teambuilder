import json
import unittest
from threading import Event
from unittest.mock import patch

from teambuilder import calc


class FakeStdin:
    def __init__(self):
        self.payload = ""
        self.write_count = 0
        self.written = Event()

    def write(self, payload):
        self.payload += payload
        self.write_count += 1
        return len(payload)

    def flush(self):
        self.written.set()


class FakeStdout:
    def __init__(self, stdin):
        self.stdin = stdin
        self.responses = []

    def readline(self):
        if not self.responses:
            if not self.stdin.written.wait(1):
                return ""
            requests = [json.loads(line) for line in self.stdin.payload.splitlines()]
            if len(requests) != 2:
                raise AssertionError("the writer should send the whole request batch")
            self.responses = [json.dumps({"id": request["id"]}) + "\n" for request in requests]
        return self.responses.pop(0)


class FakeServer:
    def __init__(self):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(self.stdin)

    def poll(self):
        return None

    def kill(self):
        pass


class CalculatorBatchTests(unittest.TestCase):
    def test_writer_sends_full_batch_while_responses_are_read(self):
        server = FakeServer()
        previous_server = calc._server
        calc._server = None
        try:
            with patch("teambuilder.calc.subprocess.Popen", return_value=server):
                result = calc._served(['{"id":1}', '{"id":2}'])
        finally:
            calc._server = previous_server

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(server.stdin.write_count, 1)

    def test_identical_requests_share_cached_calculation(self):
        calc._calculation_cache.clear()
        answer = {"id": "cache-test", "range": [1, 2]}
        with patch("teambuilder.calc._served", return_value=[answer]) as served:
            requests = [
                {"id": "cache-test", "attacker": {"name": "Pikachu"}},
                {"attacker": {"name": "Pikachu"}, "id": "cache-test"},
            ]
            self.assertEqual(calc.calculate(requests), [answer, answer])
            self.assertEqual(calc.calculate(requests[0]), answer)

        served.assert_called_once()
        self.assertEqual(len(served.call_args.args[0]), 1)


if __name__ == "__main__":
    unittest.main()
