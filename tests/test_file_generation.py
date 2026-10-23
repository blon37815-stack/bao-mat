import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
from artifacts import parse_files
from file_generation import clean_content, generate_files, repair_paths
from ollama_transport import EmptyResponse
from task_requirements import template_requirements


def valid_notes():
    return json.dumps([{'id':i,'title':'Ghi chú','content':'Dòng 1\nDòng 2','created_at':'2026-10-19T00:00:00Z'} for i in range(3)],ensure_ascii=False)


class FileGenerationTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        patcher=patch.object(app,'DB',Path(self.temporary.name)/'tasks.db')
        patcher.start();self.addCleanup(patcher.stop)
        with app.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('task','Bộ dữ liệu ghi chú','ollama','queued','','{}',app.utc_now()))
            db.execute('INSERT INTO task_products VALUES (?,1)',('task',))
            db.execute('INSERT INTO task_requirements VALUES (?,?)',('task',json.dumps(template_requirements('data'))))
        self.generated=[]

    def provider(self,messages):
        context=json.loads(messages[1]['content'])
        path=context.get('target_path')
        if path:
            self.generated.append(path)
            return {'notes.json':valid_notes(),'config.json':'{"theme":"dark"}','README.md':'# Hướng dẫn\nĐọc notes.json.'}[path]
        return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch'

    def result(self):
        return app.list_tasks()['tasks'][0]

    def test_template_runs_real_graph_and_assembles_raw_files_in_application(self):
        with patch.object(app,'ollama_reply',side_effect=self.provider) as model:
            app.run('task','Bộ dữ liệu ghi chú','ollama')
        task=self.result()
        self.assertEqual(task['status'],'completed')
        self.assertEqual(task['generation_method'],'per_file')
        self.assertEqual(task['model_calls'],5)
        files=parse_files(json.loads(task['output'])['result'])
        self.assertEqual([file['path'] for file in files],self.generated)
        self.assertEqual(json.loads(files[0]['content'])[0]['content'],'Dòng 1\nDòng 2')
        second=json.loads(model.call_args_list[2].args[0][1]['content'])
        self.assertEqual(second['manifest'],['notes.json','config.json','README.md'])
        self.assertEqual(second['existing_files'][0]['content'],files[0]['content'])
        _,report=app.export_task('task','all')
        self.assertIn('Sinh từng tệp riêng',report.decode())
        self.assertIn('Số lượt yêu cầu mô hình: 5',report.decode())

    def test_syntax_failure_only_regenerates_broken_file(self):
        config_calls=0
        def provider(messages):
            nonlocal config_calls
            context=json.loads(messages[1]['content'])
            if context.get('target_path')=='config.json':
                config_calls+=1
                if config_calls==1:
                    self.generated.append('config.json')
                    return '{broken json'
            return self.provider(messages)
        with patch.object(app,'ollama_reply',side_effect=provider):
            app.run('task','Bộ dữ liệu ghi chú','ollama')
        self.assertEqual(self.result()['status'],'completed')
        self.assertEqual(self.generated,['notes.json','config.json','README.md','config.json'])
        _,history=app.task_history('task')
        before={file['path']:file['content'] for file in parse_files(history['steps'][1]['output'])}
        after={file['path']:file['content'] for file in parse_files(history['steps'][3]['output'])}
        self.assertEqual(before['notes.json'],after['notes.json'])
        self.assertEqual(before['README.md'],after['README.md'])
        self.assertNotEqual(before['config.json'],after['config.json'])

    def test_scoped_ai_feedback_repairs_one_file_and_unscoped_feedback_repairs_all(self):
        for scoped in (True,False):
            self.generated=[];reviews=0
            def provider(messages):
                nonlocal reviews
                context=json.loads(messages[1]['content'])
                if 'result' in context and 'target_path' not in context:
                    reviews+=1
                    if reviews==1:
                        value={'passed':False,'issues':['README chưa mô tả trường dữ liệu']}
                        if scoped:value['file_issues']=[{'path':'README.md','issues':['Thiếu mô tả']}]
                        return json.dumps(value)
                return self.provider(messages)
            with self.subTest(scoped=scoped),patch.object(app,'ollama_reply',side_effect=provider):
                app.run('task','Bộ dữ liệu ghi chú','ollama')
            self.assertEqual(self.result()['status'],'completed')
            self.assertEqual(self.generated,['notes.json','config.json','README.md']+(['README.md'] if scoped else ['notes.json','config.json','README.md']))

    def test_cancel_between_files_preserves_completed_file_without_starting_next(self):
        def provider(messages):
            context=json.loads(messages[1]['content'])
            if context.get('target_path')=='config.json':
                app.task_action('task','cancel')
            return self.provider(messages)
        with patch.object(app,'ollama_reply',side_effect=provider):
            app.run('task','Bộ dữ liệu ghi chú','ollama')
        task=self.result()
        self.assertEqual(task['status'],'cancelled')
        self.assertEqual(self.generated,['notes.json','config.json'])
        files=parse_files(json.loads(task['output'])['result'])
        self.assertEqual([file['path'] for file in files],['notes.json'])
        self.assertEqual(task['model_calls'],3)
        self.assertNotIn('task',app.ACTIVE_CANCEL)

    def test_source_revision_keeps_and_updates_existing_extra_files(self):
        state={'requirements':template_requirements('data'),'source_files':[{'path':'extra.txt','content':'old'}],'prompt':'Sửa extra.txt'}
        calls=[]
        def reply(messages):
            context=json.loads(messages[1]['content']);calls.append(context['target_path'])
            return 'new' if context['target_path']=='extra.txt' else self.provider(messages)
        output,failures=generate_files(state,reply,lambda *args:None)
        self.assertEqual(failures,[])
        self.assertEqual(calls,['notes.json','config.json','README.md','extra.txt'])
        self.assertEqual(parse_files(output)[-1],{'path':'extra.txt','content':'new'})

    def test_fences_and_envelopes_preserve_literal_escapes_and_reject_wrong_target(self):
        code='print("\\n")'
        self.assertEqual(clean_content('```python\n'+code+'\n```','main.py'),code)
        envelope=json.dumps({'files':[{'path':'main.py','content':code}]})
        self.assertEqual(clean_content(envelope,'main.py'),code)
        with self.assertRaises(ValueError):clean_content(envelope,'notes.json')
        with self.assertRaises(ValueError):clean_content('','main.py')
        with self.assertRaises(ValueError):clean_content('x'*100001,'main.py')

    def test_unrecognized_ai_path_falls_back_to_manifest_and_bad_scoping_is_rejected(self):
        spec=template_requirements('data')
        result=repair_paths([],spec,{'passed':False,'issues':['Bad'],'file_issues':[{'path':'../../outside','issues':['Bad']}]},{})
        self.assertEqual(result,spec['required_files'])
        for scoped in ('wrong',[{'path':'notes.json','issues':[]}],[{'path':'notes.json','issues':['']}],None):
            self.assertIsNone(app.parse_review(json.dumps({'passed':False,'issues':['Bad'],'file_issues':scoped})))
        self.assertIsNone(app.parse_review('{"passed":true,"issues":[],"file_issues":[{"path":"x","issues":["bad"]}]}'))

    def test_empty_provider_response_is_a_file_failure_and_only_that_file_is_retried(self):
        attempts=0
        def provider(messages):
            nonlocal attempts
            context=json.loads(messages[1]['content'])
            if context.get('target_path')=='config.json':
                attempts+=1
                if attempts==1:
                    self.generated.append('config.json')
                    raise EmptyResponse('Empty Ollama response')
            return self.provider(messages)
        with patch.object(app,'ollama_reply',side_effect=provider):
            app.run('task','Bộ dữ liệu ghi chú','ollama')
        self.assertEqual(self.result()['status'],'completed')
        self.assertEqual(self.generated,['notes.json','config.json','README.md','config.json'])
