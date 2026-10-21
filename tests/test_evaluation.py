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
        self.assertEqual(len(CASES),12)
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

    def test_custom_case_acceptance_rejects_readme_only_and_measures_frozen_manifest(self):
        case=CASES[-3]
        bad=json.dumps({'files':[{'path':'README.md','content':'# Hướng dẫn'}]})
        self.assertFalse(evaluate.inspect_result(bad,case)['passed'])
        def provider(messages):
            context=json.loads(messages[1]['content'])
            if context.get('kind'):
                return json.dumps({'plan':'Tạo bộ tệp.','required_files':case['expected_files']})
            if context.get('target_path'):
                return '# Help' if context['target_path']=='README.md' else '# Python fixture\n'
            return '{"passed":true,"issues":[]}' if 'result' in context else 'Plan'
        with tempfile.TemporaryDirectory() as temporary,patch.object(app,'ollama_reply',side_effect=provider),contextlib.redirect_stdout(io.StringIO()):
            result=evaluate.run_evaluation([case],1,Path(temporary)/'custom.json')
        trial=result['trials'][0]
        self.assertTrue(trial['passed']);self.assertEqual(trial['calls'],5)
        self.assertEqual(trial['requirements']['manifest_source'],'planner')
        self.assertEqual(len(trial['content_sha256']),64)
        self.assertFalse(result['functional_tests'])

    def test_sandbox_evaluation_reports_actual_attempt_and_does_not_silently_call_it_static_success(self):
        def provider(messages):
            context=json.loads(messages[1]['content'])
            if context.get('target_path'):
                return '# Python fixture' if context['target_path']!='README.md' else '# Help'
            return '{"passed":true,"issues":[]}' if 'result' in context else 'Plan'
        with tempfile.TemporaryDirectory() as temporary,patch.object(app,'ollama_reply',side_effect=provider),contextlib.redirect_stdout(io.StringIO()):
            with patch.object(app.product_runner,'check_product',return_value={'status':'not_supported','tests':0,'output':'Zero tests'}) as runner:
                result=evaluate.run_evaluation([CASES[3]],1,Path(temporary)/'unsupported.json',sandbox=True)
            runner.assert_called_once()
            self.assertFalse(result['trials'][0]['passed']);self.assertFalse(result['functional_tests'])
            self.assertTrue(result['sandbox_requested'])
            with patch.object(app.product_runner,'check_product',return_value={'status':'passed','tests':1,'output':'Fixture test'}):
                result=evaluate.run_evaluation([CASES[3]],1,Path(temporary)/'passed.json',sandbox=True)
            self.assertTrue(result['trials'][0]['passed']);self.assertTrue(result['functional_tests'])
            trial=result['trials'][0]
            self.assertEqual(trial['execution']['content_sha256'],trial['content_sha256'])

    def test_sandbox_cli_fails_before_inference_if_local_docker_is_unavailable(self):
        with patch.object(app.product_runner,'health',return_value={'status':'unavailable'}),patch.object(evaluate,'ollama_health') as model,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error: evaluate.main(['--case','python_basic','--run','--sandbox'])
        self.assertEqual(error.exception.code,2);model.assert_not_called()
