import copy
import json
from pathlib import Path
import tempfile
import unittest
from sled.corpus import DATA_CONFIGS, public_split
from sled.generation import generate
from sled.policy_v2 import reconcile
from sled.scoring import score
from sled.environment import PublicStore
from sled.storage import export_episode, load_episode
from sled.transforms import transform
from sled.validation import verify_episode, InvalidData
from support import ROOT


class ExtendedTests(unittest.TestCase):
    def test_hand_calculated_fx_and_period(self):
        e=json.loads((ROOT/'fixtures/manual_fx_period.json').read_text())
        result=verify_episode(e)
        self.assertEqual({f['type']:f['expected_amount_minor'] for f in result['findings']},{'fx_conversion':100000,'period_cutoff':4500000})
        self.assertEqual(score(reconcile(e['public'],e['public']['manifest'],e['public']['policy']),e['truth'],PublicStore(e['public']).evidence_ids(),0)['f1'],1)

    def test_all_scenario_families(self):
        for index,config in enumerate(DATA_CONFIGS):
            with self.subTest(index=index):
                e=generate(710000+index,config); verify_episode(e)
                answer=reconcile(e['public'],e['public']['manifest'],e['public']['policy'])
                self.assertEqual(score(answer,e['truth'],PublicStore(e['public']).evidence_ids(),0)['f1'],1)

    def test_exact_fx_rounding_ties(self):
        original=json.loads((ROOT/'fixtures/manual_fx_period.json').read_text())
        for rate,rounding,expected in [('0.5','ROUND_HALF_EVEN',0),('1.5','ROUND_HALF_EVEN',2),('0.5','ROUND_HALF_UP',1)]:
            e=copy.deepcopy(original); p=e['public']; p['policy']['rounding']=rounding; p['manifest']['rounding']=rounding
            p['payments'][0]['amount_minor']=1
            p['fx'][1]['rate']=rate
            # A positive book amount makes every rounding result observable as an FX discrepancy.
            for r in p['ledger']:
                if r['payment_id']:
                    if r['debit_minor']:r['debit_minor']=100
                    else:r['credit_minor']=100
                    r['timestamp']=p['payments'][0]['timestamp']
            from sled.validation import audit_public
            found=audit_public(p)
            self.assertEqual(next(x for x in found if x['type']=='fx_conversion')['expected_amount_minor'],100-expected)

    def test_exponents_offsets_and_alternative_witnesses(self):
        for base in ['KZT','JPY','KWD','USD','EUR']:
            e=generate(931,{'base_currency':base,'period_start':'2026-02-01T00:00:00-12:00','period_days':28,'cutoff_target':'invoice'})
            changed=transform(e,fields=['row_id','doc_id','invoice_id','payment_id','entity_id'],tables=['ledger','fx','payments','invoices'])
            self.assertEqual(verify_episode(changed)['issue_count'],4)
            answer=reconcile(changed['public'],changed['public']['manifest'],changed['public']['policy'])
            self.assertEqual(score(answer,changed['truth'],PublicStore(changed['public']).evidence_ids(),0)['f1'],1)

    def test_storage_roundtrip_and_null_csv(self):
        e=generate(5)
        with tempfile.TemporaryDirectory() as folder:
            export_episode(e,folder)
            self.assertEqual(load_episode(folder),e)
            self.assertIn('null',(Path(folder)/'public/ledger.csv').read_text())

    def test_train_dev_disjoint(self):
        a=public_split('train'); b=public_split('dev')
        self.assertEqual((len(a),len(b)),(10,10))
        self.assertFalse({x[0] for x in a}&{x[0] for x in b})
        self.assertFalse({x[2]['public']['manifest']['episode_id'] for x in a}&{x[2]['public']['manifest']['episode_id'] for x in b})

    def test_provenance_and_requested_counts_cannot_be_faked(self):
        e=generate(5,{'allocation_mode':'missing'})
        verify_episode(e)
        e['provenance']['config']['fx_count']+=1
        with self.assertRaises(InvalidData):verify_episode(e)
        e=generate(5); e['provenance']['modifications'][0]['before']['debit_minor']+=1
        with self.assertRaises(InvalidData):verify_episode(e)
