import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import providers


class CompleteDetailTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.w=app.Workbench(Path(self.directory.name)/'detail.sqlite3')
        self.case=self.w.create_case('Fictional detail preservation test')['id']
        self.node=self.w.node(self.case,'person','Fictional Person')

    def tearDown(self):
        self.w.store.db.close();self.directory.cleanup()

    def evidence(self,raw,snippet='Short source description'):
        return self.w.save_evidence(self.case,self.node['id'],'fixture',{'raw':raw,'snippet':snippet,'source':'Synthetic offline fixture','entities':[]})

    def test_complete_report_contains_contact_and_unknown_details(self):
        raw={'full_name':'Fictional Person','phone':'+12025550123','email':'fictional@example.com',
             'address':'123 Example Street','unknown_detail':'unique investigative detail',
             'biography':'x'*1601+'important tail detail','authorization':'secret fixture credential'}
        self.evidence(raw)
        report=self.w.report(self.case)
        for value in (raw['phone'],raw['email'],raw['address'],raw['unknown_detail'],'important tail detail'):
            self.assertIn(value,report['text'])
        self.assertNotIn('secret fixture credential',report['text'])
        self.assertEqual(report['format'],'complete-evidence-v2')
        self.assertIn('Complete graph snapshot',report['text'])

    def test_search_finds_raw_fields_after_record_thirty_and_no_eight_result_cap(self):
        for i in range(36):self.evidence({'rare_keyword':f'needle-{i}','raw_only':'needle'})
        results=self.w.search_evidence(self.case,'needle')
        self.assertEqual(len(results),36)
        answer=self.w.action({'action':'question','case_id':self.case,'question':'needle'})
        self.assertEqual(len(answer['evidence_ids']),36)
        self.assertIn('needle-35',answer['answer'])
        self.assertIn('raw_only',answer['answer'])

    def test_all_eligible_fields_reach_ai_context_or_request_stops(self):
        for i in range(32):self.evidence({'field':f'full record {i}'},'x'*1400+'FULL-TAIL')
        selected,text=self.w.context(self.case)
        self.assertEqual(len(selected),32)
        self.assertIn('FULL-TAIL',text)
        self.assertIn('full record 31',text)
        with patch.dict(os.environ,{'ATLAS_AI_MAX_CONTEXT_CHARS':'100'}):
            with patch.object(app.connectors,'ai') as ai:
                with self.assertRaisesRegex(ValueError,'No excerpts were substituted'):
                    self.w.report(self.case,True)
                ai.assert_not_called()
            self.assertEqual(len(self.w.report(self.case)['evidence_ids']),32)

    def test_exclusions_are_explicit_and_searchable(self):
        e=self.evidence({'field':'needle excluded by analyst'})
        self.w.store.update('evidence',e['id'],review='excluded')
        report=self.w.report(self.case)
        self.assertEqual(report['excluded_evidence_ids'],[e['id']])
        self.assertEqual(report['evidence_ids'],[])
        self.assertEqual(self.w.search_evidence(self.case,'needle')[0]['review'],'excluded')

    def test_long_notes_and_all_extracted_leads_are_retained(self):
        notes='n'*5001+'trailing case note'
        node=self.w.action({'action':'review','case_id':self.case,'table':'nodes','id':self.node['id'],'review':'unreviewed','notes':notes})
        self.assertEqual(node['notes'],notes)
        r=providers.result('email_osint_industries',{'records':[{'email':f'p{i}@example.com'} for i in range(20)]})
        self.assertIn('p19@example.com',r['snippet'])

    def test_state_does_not_repeat_entire_reports_in_every_poll(self):
        self.evidence({'field':'complete data'})
        report=self.w.report(self.case)
        self.assertNotIn('text',self.w.state(self.case)['reports'][0])
        self.assertIn('complete data',self.w.store.get('reports',report['id'])['text'])


if __name__=='__main__':unittest.main()
