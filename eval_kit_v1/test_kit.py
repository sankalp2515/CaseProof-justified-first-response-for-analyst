import unittest,json
from pathlib import Path
from evaluate import score,load_input
from verify_kit import verify
BASE=Path(__file__).resolve().parent
class KitTests(unittest.TestCase):
 def test_integrity(self):self.assertEqual(verify()['cases'],48)
 def test_no_gold_in_model_input(self):
    d=load_input('CP009');s=json.dumps(d);self.assertNotIn('acceptable_next_request',s);self.assertNotIn('private_gold',s);self.assertNotIn('followup',s);self.assertEqual(len(d['artifacts']),3)
 def test_no_future_in_initial_loader(self):
    with self.assertRaises(ValueError):load_input('CP009','after_followup')
 def test_invalid_case_path_rejected(self):
    with self.assertRaises(ValueError):load_input('../private_gold/CP009')
 def test_missing_results_stay_in_denominator(self):
    r=score([]);self.assertEqual(r['case_count'],20);self.assertEqual(r['stage_count'],32);self.assertEqual(r['missing_or_failed_stages'],32);self.assertEqual(r['field_exact_match']['correct'],0);self.assertGreater(r['field_exact_match']['total'],0)
 def test_false_complete_counted(self):
    r=score([{'case_id':'CP017','stage_id':'initial','disposition':'COMPLETE_HANDOFF'}]);self.assertEqual(r['critical_flagged_stages'],1)
 def test_duplicate_prediction_rejected(self):
    with self.assertRaises(ValueError):score([{'case_id':'CP017'},{'case_id':'CP017'}])
 def test_no_request_not_credited_to_missing_output(self):
    r=score([]);self.assertEqual(r['no_request_decision']['correct'],0)
 def test_unknown_prediction_stage_rejected(self):
    with self.assertRaises(ValueError):score([{'case_id':'CP017','stage_id':'typo'}])
 def test_invalid_split_rejected(self):
    with self.assertRaises(ValueError):score([],'typo')
if __name__=='__main__':unittest.main()
