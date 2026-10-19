import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import evaluate
from evaluation_cases import CASES
from test_file_generation import valid_notes


class EvaluationTest(unittest.TestCase):
    def test_listing_does_not_contact_ollama(self):
        with patch.object(evaluate,'ollama_health') as health,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(evaluate.main([]),0)
        health.assert_not_called()
        self.assertEqual(len(CASES),9)
        self.assertIn('data_escaping',output.getvalue())

    def test_evaluation_isolated_from_user_database_and_counts_actual_graph_calls(self):
        original = app.DB
        def provider(messages):
            context=json.loads(messages[1]['content'])
            if context.get('target_path'):
                return {'notes.json':valid_notes(),'config.json':'{}','README.md':'# Mẫu'}[context['target_path']]
            return '{"passed":true,"issues":[]}' if 'result' in context else 'Plan'
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'evaluation.json'
            with patch.object(app,'ollama_reply',side_effect=provider),contextlib.redirect_stdout(io.StringIO()):
                report=evaluate.run_evaluation([CASES[0]],2,output)
            self.assertEqual(app.DB,original)
            self.assertEqual(report['status'],'completed')
            self.assertFalse(report['functional_tests'])
            self.assertEqual([trial['calls'] for trial in report['trials']],[5,5])
            self.assertEqual(report['summary']['data_basic']['passed'],2)
            self.assertIsNone(report['summary']['data_basic']['target_met'])
            self.assertEqual(json.loads(output.read_text(encoding='utf-8')),report)
            with self.assertRaises(FileExistsError):
                evaluate.run_evaluation([CASES[0]],1,output)

    def test_target_requires_ten_trials_and_eight_passes(self):
        trials=[{'case_id':'data_basic','template':'data','passed':i<8,'seconds':i,'first_pass':False} for i in range(10)]
        self.assertTrue(evaluate.summaries(trials)['data_basic']['target_met'])
        self.assertIsNone(evaluate.summaries(trials[:9])['data_basic']['target_met'])
        trials[0]['passed']=False
        self.assertFalse(evaluate.summaries(trials)['data_basic']['target_met'])

    def test_extra_json_cases_detect_missing_unicode_and_escaping(self):
        files=[{'path':'notes.json','content':valid_notes()},{'path':'config.json','content':'{}'},{'path':'README.md','content':'# Mẫu'}]
        self.assertTrue(evaluate.inspect_result(json.dumps({'files':files}),CASES[1])['passed'])
        self.assertFalse(evaluate.inspect_result(json.dumps({'files':files}),CASES[2])['passed'])
        notes=json.loads(files[0]['content']);notes[0]['content']='Dòng 1\nDòng "2"'
        files[0]['content']=json.dumps(notes)
        self.assertTrue(evaluate.inspect_result(json.dumps({'files':files}),CASES[2])['passed'])

    def test_evaluation_can_measure_supervised_team_with_an_explicit_budget(self):
        def provider(messages):
            context=json.loads(messages[1]['content'])
            if context.get('target_path'):
                self.assertIn('supervise',context)
                return {'notes.json':valid_notes(),'config.json':'{}','README.md':'# Mẫu'}[context['target_path']]
            return '{"passed":true,"issues":[]}' if 'result' in context else 'Giao việc theo tiêu chí'
        with tempfile.TemporaryDirectory() as temporary,patch.object(app,'ollama_reply',side_effect=provider),contextlib.redirect_stdout(io.StringIO()):
            report=evaluate.run_evaluation([CASES[0]],1,Path(temporary)/'supervised.json','auto',6)
        self.assertTrue(report['trials'][0]['passed'])
        self.assertEqual(report['trials'][0]['calls'],6)
        self.assertEqual(report['expert'],'auto')
        self.assertEqual(report['call_limit'],6)
