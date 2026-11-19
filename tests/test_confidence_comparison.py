import math
import unittest
import numpy as np
from scripts.confidence_comparison import parse_scores, canonical
from scripts.evaluate_confidence import scores, fit_calibrator, calibrate

class ConfidenceTests(unittest.TestCase):
    def response(self, alternatives):
        return {'choices':[{'message':{},'logprobs':{'content':[{'token':'1','logprob':math.log(.6),'top_logprobs':alternatives}]}}], 'usage':{'completion_tokens_details':{'reasoning_tokens':0}}}

    def test_normalized_probability(self):
        r=parse_scores(self.response([{'token':'0','logprob':math.log(.2)},{'token':'1','logprob':math.log(.6)}]))
        self.assertAlmostEqual(r['probability'],.75)
        self.assertAlmostEqual(r['label_probability_mass'],.8)

    def test_missing_alternative_is_not_zero(self):
        r=parse_scores(self.response([{'token':'1','logprob':math.log(.6)}]))
        self.assertEqual(r['status'],'missing_label_probability')
        self.assertEqual(r['probability'],'')

    def test_metrics_with_tied_scores(self):
        s=scores([0,1],[.5,.5])
        self.assertAlmostEqual(s['brier'],.25)
        self.assertAlmostEqual(s['log_loss'],math.log(2))
        self.assertAlmostEqual(s['roc_auc'],.5)
        self.assertAlmostEqual(s['average_precision'],.5)

    def test_calibration_reduces_known_overconfidence(self):
        p=np.array([.01]*100+[.99]*100)
        y=np.array([0]*80+[1]*20+[0]*20+[1]*80)
        params=fit_calibrator(p,y);pred=calibrate(p,params)
        self.assertLess(scores(y,pred)['brier'],scores(y,p)['brier'])
        self.assertGreater(params['slope'],0)
        self.assertTrue(np.all((pred>0)&(pred<1)))
        extremes=calibrate([.999999,.9999999],params)
        self.assertLess(extremes[0],extremes[1])

    def test_duplicate_normalization(self):
        self.assertEqual(canonical('abc\r\n  def'),canonical('abc\n def'))

if __name__=='__main__':unittest.main()
