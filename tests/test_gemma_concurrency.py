import tempfile
import os
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.gemma4_openrouter import run_classifier


class ConcurrentCheckpointTest(unittest.TestCase):
    def test_ten_requests_and_resume(self):
        rows = [{"source_row": i, "email": f"email {i}", "label": 0} for i in range(20)]
        lock = threading.Lock()
        active = peak = calls = 0

        def fake_classify(*_args):
            nonlocal active, peak, calls
            with lock:
                active += 1
                calls += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {"prediction": 0, "source_type": "internal", "reason": "test", "truncated": False, "model": "test", "request_id": "", "input_tokens": 1, "output_tokens": 1, "cost": 0}

        fd, name = tempfile.mkstemp(suffix=".csv", dir=Path.cwd())
        os.close(fd)
        path = Path(name)
        try:
            with patch("scripts.gemma4_openrouter.classify_email", fake_classify):
                first = run_classifier(rows, path, "test-key", max_workers=10)
                second = run_classifier(rows, path, "", max_workers=10)
                self.assertEqual(len(first), 20)
                self.assertEqual(len(second), 20)
                self.assertEqual(calls, 20)
                self.assertGreater(peak, 1)
                self.assertLessEqual(peak, 10)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
