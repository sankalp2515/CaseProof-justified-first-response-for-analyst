import unittest,json
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def call(path,body=None,key=None):
    headers={'Content-Type':'application/json'}
    if key:headers['Idempotency-Key']=key
    req=Request('http://127.0.0.1:8765'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urlopen(req) as r:return r.status,json.loads(r.read())
    except HTTPError as e:return e.code,json.loads(e.read())

class MockTests(unittest.TestCase):
 def setUp(self):call('/reset',{})
 def test_scope_and_catalog(self):
    code,health=call('/health');self.assertEqual(code,200);self.assertTrue(health['synthetic']);self.assertFalse(health['ai_implemented'])
    self.assertEqual(len(call('/catalog')[1]),48)
 def test_future_evidence_and_private_files_not_served(self):
    self.assertEqual(call('/case?id=CP009&stage=followup')[0],403)
    self.assertEqual(call('/case?id=CP009&stage=anything')[0],422)
    self.assertEqual(call('/private_gold/CP009.json')[0],404)
    self.assertEqual(call('/artifact?case=CP009&id=../private_gold')[0],404)
 def test_authorized_response(self):
    self.assertEqual(len(call('/case?id=CP009')[1]['artifacts']),3)
    self.assertFalse(call('/reveal',{'case_id':'CP009','request_id':'clarify_amount'})[1]['available'])
    self.assertTrue(call('/reveal',{'case_id':'CP009','request_id':'request_reference_crop'})[1]['available'])
    self.assertEqual(call('/case?id=CP009&stage=followup')[0],200)
 def test_approval_and_idempotency(self):
    body={'case_id':'CP009','human_approved':False,'approved_revision':1,'disposition':'COMPLETE_HANDOFF'}
    self.assertEqual(call('/tickets',body,'qa-ticket')[0],422)
    body['human_approved']=True
    code,ticket=call('/tickets',body,'qa-ticket');self.assertEqual(code,201);self.assertFalse(ticket['official_report'])
    self.assertEqual(call('/tickets',body,'qa-ticket')[1]['ticket_id'],ticket['ticket_id'])
    body['approved_revision']=2;self.assertEqual(call('/tickets',body,'qa-ticket')[0],409)
 def tearDown(self):call('/reset',{})
if __name__=='__main__':unittest.main()
