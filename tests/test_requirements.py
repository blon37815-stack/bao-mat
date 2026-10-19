import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
from task_requirements import check_requirements, template_requirements


def data_product():
    notes=[{'id':index,'title':'Ghi chú '+str(index),'content':'Nội dung','created_at':'2026-10-19T00:00:00Z'} for index in range(1,4)]
    return [{'path':'notes.json','content':json.dumps(notes)}, {'path':'config.json','content':'{"theme":"dark"}'}, {'path':'README.md','content':'Hướng dẫn'}]


class RequirementTest(unittest.TestCase):
    def test_readme_instructions_do_not_replace_actual_json_files(self):
        issues=check_requirements([{'path':'README.md','content':'Run Python to create notes.json and config.json'}],template_requirements('data'))
        self.assertEqual(len(issues),2)
        self.assertIn('notes.json',issues[0])
        self.assertIn('config.json',issues[1])
        self.assertEqual(check_requirements(data_product(),template_requirements('data')),[])

    def test_rejects_wrong_count_fields_duplicate_ids_and_invalid_dates(self):
        files=data_product()
        notes=json.loads(files[0]['content'])
        notes[1]['id']=notes[0]['id'];notes[0]['content']='';notes[2]['created_at']='yesterday'
        files[0]['content']=json.dumps(notes);files[1]['content']='[]'
        issues=check_requirements(files,template_requirements('data'))
        self.assertTrue(any('trùng id' in issue for issue in issues))
        self.assertTrue(any('content' in issue for issue in issues))
        self.assertTrue(any('ISO 8601' in issue for issue in issues))
        self.assertTrue(any('config.json' in issue for issue in issues))
        files[0]['content']='{"name":"person"}'
        self.assertTrue(any('3 ghi chú' in issue for issue in check_requirements(files,template_requirements('data'))))

    def test_missing_files_override_ai_pass_and_trigger_repair(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(app,'DB',Path(temporary)/'tasks.db'):
            spec=template_requirements('data')
            with app.connect() as db:
                db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('task','Mẫu dữ liệu JSON','ollama','queued','','{}','now'))
                db.execute('INSERT INTO task_products VALUES (?,1)',('task',))
                db.execute('INSERT INTO task_requirements VALUES (?,?)',('task',json.dumps(spec)))
            bad=json.dumps({'files':[{'path':'README.md','content':'Hướng dẫn sinh JSON'}]})
            good=json.dumps({'files':data_product()})
            with patch.object(app,'ollama_reply',side_effect=['Plan',bad,'{"passed":true,"issues":[]}',good,'{"passed":true,"issues":[]}']) as model:
                app.run('task','Mẫu dữ liệu JSON','ollama')
            self.assertEqual(model.call_count,5)
            self.assertIn('notes.json',json.loads(model.call_args_list[3].args[0][1]['content'])['review'])
            self.assertEqual(json.loads(model.call_args_list[0].args[0][1]['content'])['requirements'],spec)
            task=app.list_tasks()['tasks'][0]
            self.assertEqual(task['status'],'completed')
            self.assertEqual(task['requirements'],spec)
            _,history=app.task_history('task')
            self.assertFalse(json.loads(history['steps'][2]['output'])['passed'])

    def test_readme_only_never_passes_or_gets_approved_and_retry_keeps_spec(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(app,'DB',Path(temporary)/'tasks.db'):
            spec=template_requirements('data')
            with app.connect() as db:
                db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('task','Mẫu dữ liệu JSON','ollama','queued','','{}','now'))
                db.execute('INSERT INTO task_products VALUES (?,1)',('task',))
                db.execute('INSERT INTO task_requirements VALUES (?,?)',('task',json.dumps(spec)))
            bad=json.dumps({'files':[{'path':'README.md','content':'Hướng dẫn'}]})
            with patch.object(app,'ollama_reply',side_effect=['Plan',bad,'{"passed":true,"issues":[]}',bad,'{"passed":true,"issues":[]}',bad,'{"passed":true,"issues":[]}']):
                app.run('task','Mẫu dữ liệu JSON','ollama')
            task=app.list_tasks()['tasks'][0]
            self.assertEqual(task['status'],'needs_review')
            self.assertFalse(json.loads(json.loads(task['output'])['review'])['passed'])
            self.assertEqual(app.task_action('task','approve')[0],409)
            with patch.object(app,'enqueue_task'):
                status,result=app.retry_task('task')
            self.assertEqual(status,202)
            self.assertEqual(app.get_requirements(result['id']),spec)
