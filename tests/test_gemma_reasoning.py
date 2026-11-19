import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.gemma4_openrouter import classify_email, config_hash, run_classifier

class ReasoningTest(unittest.TestCase):
    def test_payload_and_telemetry(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'label': 0, 'source_type': 'internal', 'reason': 'Routine business'})}}], 'usage': {'completion_tokens_details': {'reasoning_tokens': 0}}}
        for setting in (None, False, True):
            with self.subTest(setting=setting), patch('scripts.gemma4_openrouter.urlopen', return_value=io.StringIO(json.dumps(response))) as request:
                result = classify_email('email', 'test', reasoning_enabled=setting, max_output_tokens=4096)
                payload = json.loads(request.call_args.args[0].data)
                self.assertEqual(payload['max_tokens'], 4096)
                if setting is None:
                    self.assertNotIn('reasoning', payload)
                else:
                    self.assertEqual(payload['reasoning'], {'enabled': setting})
                    self.assertEqual(result['reasoning_tokens'], 0)
                    self.assertFalse(result['reasoning_returned'])

    def test_reasoning_usage_is_recorded(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'label': 0, 'source_type': 'internal', 'reason': 'Routine business'}),
            'reasoning': 'reported thinking'}}],
            'usage': {'completion_tokens_details': {'reasoning_tokens': 727}}}
        with patch('scripts.gemma4_openrouter.urlopen', return_value=io.StringIO(json.dumps(response))):
            result = classify_email('email', 'test', reasoning_enabled=True, max_output_tokens=4096)
        self.assertEqual(result['reasoning_tokens'], 727)
        self.assertTrue(result['reasoning_returned'])

    def test_failure_preserves_completed_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'results.csv'
            rows = [{'source_row': i, 'email': str(i), 'label': 0} for i in range(3)]
            def classify(email, *_args):
                if email == '1':
                    raise ValueError('incomplete response')
                return {'prediction': 0, 'source_type': 'internal', 'reason': 'test', 'truncated': False}
            with patch('scripts.gemma4_openrouter.classify_email', side_effect=classify):
                with self.assertRaisesRegex(RuntimeError, 'row 1'):
                    run_classifier(rows, path, 'test', max_workers=1)
            import csv
            with path.open(newline='') as f:
                saved = list(csv.DictReader(f))
            self.assertIn('0', [r['source_row'] for r in saved])
            self.assertNotIn('1', [r['source_row'] for r in saved])

    def test_settings_cannot_mix_on_resume(self):
        self.assertNotEqual(config_hash(), config_hash(reasoning_enabled=False))
        self.assertNotEqual(config_hash(reasoning_enabled=True), config_hash(reasoning_enabled=True, max_output_tokens=4096))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'results.csv'
            rows = [{'source_row': 0, 'email': 'email', 'label': 0}]
            fake = {'prediction': 0, 'source_type': 'internal', 'reason': 'test', 'truncated': False}
            with patch('scripts.gemma4_openrouter.classify_email', return_value=fake):
                run_classifier(rows, path, 'test')
            with self.assertRaisesRegex(ValueError, 'different input, label, or settings'):
                run_classifier(rows, path, '', reasoning_enabled=False)
            with self.assertRaisesRegex(ValueError, 'different input, label, or settings'):
                run_classifier(rows, path, '', max_output_tokens=4096)

if __name__ == '__main__':
    unittest.main()
