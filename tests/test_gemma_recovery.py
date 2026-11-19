import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import gemma4_openrouter as g
from scripts import gemma_reasoning_recovery as recovery

class RecoveryTests(unittest.TestCase):
    def response(self,finish='stop'):
        return {'id':'test-request','provider':'test','choices':[{'finish_reason':finish,'message':{
            'content':json.dumps({'label':0,'source_type':'internal','reason':'test'})}}],
            'usage':{'completion_tokens':4096,'cost':.001,'completion_tokens_details':{'reasoning_tokens':4000}}}

    def test_recovery_keeps_temperature_zero_and_original_sampling(self):
        with patch.object(g,'urlopen',return_value=io.StringIO(json.dumps(self.response()))) as send:
            g.classify_email('email','test',reasoning_enabled=True,max_output_tokens=4096,sampling=recovery.SAMPLING,seed=2)
        payload=json.loads(send.call_args.args[0].data)
        self.assertEqual(payload['temperature'],0)
        self.assertEqual(payload['seed'],2)
        self.assertNotIn('top_p',payload)
        self.assertNotIn('top_k',payload)
        self.assertEqual(payload['reasoning'],{'enabled':True})
        self.assertNotEqual(g.config_hash(seed=2),g.config_hash())
        self.assertNotEqual(g.config_hash(seed=2),g.config_hash(seed=3))
        self.assertEqual(g.config_hash(reasoning_enabled=True,max_output_tokens=4096),
                            g.config_hash(reasoning_enabled=True,max_output_tokens=4096,sampling=recovery.SAMPLING))

    def test_repetition_retry_keeps_required_settings_and_provider(self):
        with patch.object(g,'urlopen',return_value=io.StringIO(json.dumps(self.response()))) as send:
            g.classify_email('email','test',reasoning_enabled=True,max_output_tokens=4096,
                             seed=2,provider_only='darkbloom',repetition_penalty=1.1)
        payload=json.loads(send.call_args.args[0].data)
        self.assertEqual(payload['temperature'],0)
        self.assertEqual(payload['seed'],2)
        self.assertEqual(payload['reasoning'],{'enabled':True})
        self.assertEqual(payload['repetition_penalty'],1.1)
        self.assertEqual(payload['provider']['only'],['darkbloom'])
        self.assertFalse(payload['provider']['allow_fallbacks'])
        self.assertNotEqual(g.config_hash(seed=2),g.config_hash(seed=2,repetition_penalty=1.1))

    def test_incomplete_response_keeps_accounting_metadata(self):
        with patch.object(g,'urlopen',return_value=io.StringIO(json.dumps(self.response('length')))):
            with self.assertRaises(g.ClassificationResponseError) as caught:
                g.classify_email('email','test',reasoning_enabled=True)
        self.assertEqual(caught.exception.metadata['cost'],.001)
        self.assertEqual(caught.exception.metadata['request_id'],'test-request')
        self.assertNotIn('content',caught.exception.metadata)

    def test_bounded_retry_is_journaled_and_resumable(self):
        row={'source_row':112,'email':'email','label':0}
        failure=g.ClassificationResponseError('length',self.response('length'))
        success={'prediction':0,'reason':'test','source_type':'internal','reasoning_enabled':True,'cost':.002}
        with tempfile.TemporaryDirectory() as folder,patch.object(recovery,'JOURNAL',Path(folder)/'attempts.jsonl'):
            with patch.object(g,'classify_email',side_effect=[failure,success]) as classify:
                result=recovery.recover_one(row,'test',[])
            self.assertEqual(result['max_output_tokens'],8192)
            self.assertTrue(all(c.kwargs['seed']==2 for c in classify.call_args_list))
            self.assertEqual([c.kwargs['max_output_tokens'] for c in classify.call_args_list],[4096,8192])
            records=recovery.history()
            self.assertEqual([r['status'] for r in records],['response_error','success'])
            self.assertAlmostEqual(sum(r['cost'] for r in records),.003)
            with patch.object(recovery,'DATA',Path(folder)):
                saved=recovery.completed([row],records)
            self.assertEqual(list(saved),[112])

    def test_retry_budget_exhaustion_makes_no_more_calls(self):
        row={'source_row':112,'email':'email','label':0}
        history=[{'source_row':112,'status':'response_error','max_output_tokens':cap,'provider_only':provider,'repetition_penalty':penalty} for cap,provider,penalty in recovery.ATTEMPTS]
        with patch.object(g,'classify_email') as classify:
            self.assertIsNone(recovery.recover_one(row,'test',history))
            classify.assert_not_called()

if __name__=='__main__':unittest.main()
