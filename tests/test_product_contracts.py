import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import app
from artifacts import parse_files
from product_contracts import ContractError, manifest_paths, parse_plan, request_contract
from product_quality import content_digest, report
from task_requirements import check_requirements, template_requirements
from file_generation import generate_files


FILES = {
    'src/main.py':'def total(values):\n    return sum(values)\n',
    'tests/test_main.py':'import unittest\nfrom src.main import total\nclass T(unittest.TestCase):\n def test_total(self): self.assertEqual(total([1,2]),3)\n',
    'README.md':'# Công cụ tính tổng\nChương trình và kiểm thử đi kèm.\n',
}


class ContractUnitTest(unittest.TestCase):
    def test_manifest_rejects_unsafe_colliding_or_unbounded_paths(self):
        for value in (None, 'main.py', [], ['../main.py'], ['/main.py'], ['C:/main.py'],
                      ['CON.py'], ['a.py','A.py'], ['src','src/main.py'], ['main.py']*2,
                      ['x'+str(i)+'.py' for i in range(31)], [False]):
            with self.subTest(value=value), self.assertRaises(ContractError):
                manifest_paths(value)

    def test_readme_and_tests_alone_do_not_make_an_application(self):
        for files in (['README.md'], ['tests/test_main.py','README.md'], ['tests/helpers.py','README.md']):
            with self.assertRaises(ContractError):
                request_contract({}, files)
        docs = request_contract({}, ['README.md'], 'documents')
        self.assertEqual(check_requirements([{'path':'README.md','content':'# Tài liệu'}],docs), [])
        data = request_contract({}, ['people.json'], 'data')
        self.assertEqual(data['kind'], 'data')

    def test_template_and_parent_constraints_cannot_be_weakened(self):
        original = template_requirements('python')
        augmented = request_contract(original, ['helpers.py'])
        self.assertEqual(augmented['required_files'], [*original['required_files'],'helpers.py'])
        with self.assertRaises(ContractError): request_contract(original, [], 'documents')
        with self.assertRaises(ContractError): request_contract(original, [], 'data', inherited=True)
        with self.assertRaises(ContractError): request_contract({}, False)
        self.assertNotIn('repair_files',request_contract(dict(original,repair_files=['main.py'])))

    def test_plan_is_bounded_and_preserves_original_files_without_obeying_extra_fields(self):
        spec = request_contract({})
        raw = json.dumps({'plan':'Kế hoạch','required_files':['main.py'],'tools':['shell'],'call_limit':100})
        text, planned = parse_plan(raw,spec,[{'path':'extra.txt','content':'keep'}])
        self.assertEqual(planned['required_files'],['main.py','extra.txt'])
        self.assertNotIn('tools',planned); self.assertNotIn('call_limit',planned)
        for raw in ('not JSON','{}','{"plan":"P","required_files":["README.md"]}',
                    json.dumps({'plan':'P','required_files':[str(i)+'.py' for i in range(13)]})):
            with self.assertRaises(ContractError): parse_plan(raw,spec)

    def test_empty_required_files_are_not_complete_and_source_hash_is_order_independent(self):
        spec = request_contract({},['main.py','README.md'])
        files = [{'path':'main.py','content':' '},{'path':'README.md','content':'# Help'}]
        self.assertIn('rỗng',check_requirements(files,spec)[0])
        self.assertEqual(content_digest(files),content_digest(list(reversed(files))))
        changed = [dict(f,content=f['content']+'x') for f in files]
        self.assertNotEqual(content_digest(files),content_digest(changed))

    def test_quality_separates_static_checks_from_real_execution_and_stale_evidence(self):
        files = [{'path':p,'content':c} for p,c in FILES.items()]
        spec = request_contract({},list(FILES))
        syntax = {'status':'passed','checked':2,'skipped':1,'findings':[]}
        value = report(files,spec,syntax)
        self.assertEqual(value['status'],'static_only'); self.assertFalse(value['functional_verified'])
        execution = {'status':'passed','tests':1,'output':'ok','content_sha256':content_digest(files)}
        self.assertTrue(report(files,spec,syntax,execution)['functional_verified'])
        self.assertEqual(report(files,spec,syntax,dict(execution,tests=0))['execution']['status'],'not_supported')
        for digest in ('old',None):
            value = report(files,spec,syntax,dict(execution,content_sha256=digest))
            self.assertEqual(value['execution']['status'],'not_run'); self.assertFalse(value['functional_verified'])
        demo = report(files,spec,syntax,execution,demo=True)
        self.assertFalse(demo['functional_verified']); self.assertEqual(demo['status'],'demo')

    def test_missing_files_override_passed_ai_and_syntax_in_quality_report(self):
        spec = request_contract({},list(FILES))
        value = report([{'path':'README.md','content':'# Help'}],spec,
                       {'status':'not_supported','checked':0,'skipped':1,'findings':[]},
                       ai_review={'passed':True,'issues':[]})
        self.assertEqual(value['status'],'blocked'); self.assertFalse(value['complete'])
        self.assertEqual(value['missing_files'],['src/main.py','tests/test_main.py'])

    def test_legacy_products_without_manifest_are_unverified_and_repairs_cannot_touch_frozen_files(self):
        value=report([{'path':'README.md','content':'# Help'}],{},
                     {'status':'not_supported','checked':0,'skipped':1,'findings':[]})
        self.assertFalse(value['complete']);self.assertEqual(value['status'],'needs_review')
        state={'requirements':dict(request_contract({},list(FILES)),repair_files=['src/main.py']),
               'source_files':[{'path':p,'content':c} for p,c in FILES.items()],
               'review':'Bad README','repair_paths':['README.md']}
        with patch('file_generation.clean_content') as clean, self.assertRaises(ContractError):
            generate_files(state,lambda messages:'changed',lambda *args:None)
        clean.assert_not_called()


class ContractWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        for name,value in (('DB',Path(temporary.name)/'tasks.db'),('TASK_QUEUE',app.TaskQueue(10)),('ACTIVE_CANCEL',{})):
            change=patch.object(app,name,value);change.start();self.addCleanup(change.stop)
        change=patch.object(app,'enqueue_task');change.start();self.addCleanup(change.stop)
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port);self.addCleanup(self.close)
        self.generated=[]

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def post(self,path,data,protected=True):
        headers={'Content-Type':'application/json'}
        if protected: headers['X-CSRF-Token']=app.CSRF_TOKEN
        request=urllib.request.Request(self.base+path,json.dumps(data).encode(),headers)
        with urllib.request.urlopen(request) as response: return json.load(response)

    def get(self,path):
        with urllib.request.urlopen(self.base+path) as response: return json.load(response)

    def task(self,**changes):
        return self.post('/api/tasks',dict(prompt='Tạo công cụ tính tổng',mode='ollama',product=True,expert='none',**changes))['id']

    def provider(self,messages):
        context=json.loads(messages[1]['content'])
        if context.get('target_path'):
            self.generated.append(context['target_path']); return FILES[context['target_path']]
        if 'kind' in context:
            return json.dumps({'plan':'Tạo chương trình, kiểm thử và hướng dẫn.','required_files':list(FILES)})
        return '{"passed":true,"issues":[]}' if 'result' in context else 'Kế hoạch'

    def run_task(self,task,provider=None):
        with patch.object(app,'ollama_reply',side_effect=provider or self.provider):
            app.run(task,'Tạo công cụ tính tổng','ollama')
        return self.get('/api/tasks/'+task)

    def test_custom_product_plans_manifest_then_generates_each_file_and_exports_exact_files(self):
        task=self.task()
        self.assertEqual(self.get('/api/tasks/'+task)['requirements']['manifest_source'],'pending_plan')
        value=self.run_task(task)
        self.assertEqual(value['status'],'completed');self.assertEqual(value['model_calls'],5)
        self.assertEqual(value['generation_method'],'per_file');self.assertEqual(self.generated,list(FILES))
        self.assertEqual(value['requirements']['manifest_source'],'planner')
        quality=self.get('/api/tasks/'+task+'/quality')
        self.assertTrue(quality['complete']);self.assertFalse(quality['functional_verified'])
        with urllib.request.urlopen(self.base+'/api/tasks/'+task+'/artifact.zip') as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive: self.assertEqual(archive.namelist(),list(FILES))

    def test_readme_only_plan_is_rejected_twice_and_no_result_or_approval_is_created(self):
        task=self.task()
        with patch.object(app,'ollama_reply',return_value='{"plan":"Help","required_files":["README.md"]}') as provider:
            app.run(task,'Tạo công cụ tính tổng','ollama')
        value=self.get('/api/tasks/'+task)
        self.assertEqual(value['status'],'needs_review');self.assertEqual(provider.call_count,2)
        self.assertNotIn('result',json.loads(value['output']));self.assertIn('danh sách',value['stage'])
        self.assertEqual(app.task_action(task,'approve')[0],409)

    def test_invalid_plan_is_repaired_once_within_same_call_budget(self):
        task=self.task();plans=0
        def provider(messages):
            nonlocal plans
            if 'kind' in json.loads(messages[1]['content']):
                plans+=1
                if plans==1: return 'Kế hoạch không có JSON'
            return self.provider(messages)
        value=self.run_task(task,provider)
        self.assertEqual(value['status'],'completed');self.assertEqual(value['model_calls'],6)
        limited=self.task(call_limit=1)
        value=self.run_task(limited,lambda messages:'invalid')
        self.assertEqual(value['model_calls'],1);self.assertEqual(value['status'],'needs_review')
        self.assertEqual(self.generated,list(FILES))

    def test_explicit_manifest_is_frozen_and_bad_output_repairs_only_missing_file(self):
        task=self.task(required_files=list(FILES));first=True
        def provider(messages):
            nonlocal first
            context=json.loads(messages[1]['content'])
            if context.get('target_path')=='src/main.py' and first:
                first=False;self.generated.append('src/main.py')
                return '{"files":[{"path":"README.md","content":"Instructions only"}]}'
            return self.provider(messages)
        value=self.run_task(task,provider)
        self.assertEqual(value['status'],'completed')
        self.assertEqual(self.generated,[*FILES,'src/main.py'])
        self.assertEqual(value['requirements']['manifest_source'],'user')

    def test_missing_only_revision_keeps_original_and_does_not_regenerate_good_files(self):
        task=self.task(required_files=list(FILES))
        original={'result':json.dumps({'files':[{'path':'README.md','content':'# Giữ nguyên tuyệt đối'}]})}
        app.update(task,status='needs_review',output=json.dumps(original))
        child=self.post('/api/tasks',{'prompt':'Bổ sung tệp thiếu','mode':'ollama','parent_id':task,'expert':'none','repair_missing':True})['id']
        value=self.run_task(child)
        self.assertEqual(value['status'],'completed');self.assertEqual(self.generated,['src/main.py','tests/test_main.py'])
        files=parse_files(json.loads(value['output'])['result'])
        self.assertEqual(next(f['content'] for f in files if f['path']=='README.md'),'# Giữ nguyên tuyệt đối')
        self.assertEqual(json.loads(self.get('/api/tasks/'+task)['output']),original)
        full=self.post('/api/tasks',{'prompt':'Sửa mọi tệp','mode':'ollama','parent_id':child})['id']
        self.assertNotIn('repair_files',self.get('/api/tasks/'+full)['requirements'])
        status,manual=app.save_product_revision(child,[dict(f,content=f['content']+'\n') for f in files])
        self.assertEqual(status,201)
        self.assertNotIn('repair_files',self.get('/api/tasks/'+manual['id'])['requirements'])
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/api/tasks',{'prompt':'Không thiếu','mode':'ollama','parent_id':child,'repair_missing':True})

    def test_required_fields_are_validated_before_queue_or_provider_and_parent_kind_is_preserved(self):
        with app.connect() as db: before=db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        for data in ({'required_files':['../main.py']},{'required_files':['README.md']},{'required_files':'main.py'},
                     {'product_kind':'root'},{'repair_missing':True}):
            with self.subTest(data=data),self.assertRaises(urllib.error.HTTPError) as error: self.task(**data)
            self.assertEqual(error.exception.code,400)
        with app.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],before)
        task=self.task(template='data')
        app.update(task,status='needs_review',output=json.dumps({'result':json.dumps({'files':[{'path':'README.md','content':'# Data'}]})}))
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/api/tasks',{'prompt':'Weaken','mode':'ollama','parent_id':task,'product_kind':'documents'})
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/api/tasks',{'prompt':'Weaken','mode':'ollama','parent_id':task,'template':'web'})

    def test_documents_only_are_explicit_and_quality_never_claims_functional_tests(self):
        task=self.task(product_kind='documents',required_files=['README.md'])
        value=self.run_task(task)
        self.assertEqual(value['status'],'needs_review')
        quality=self.get('/api/tasks/'+task+'/quality')
        self.assertTrue(quality['complete']);self.assertEqual(quality['kind'],'documents')
        self.assertFalse(quality['functional_verified']);self.assertEqual(quality['syntax']['status'],'not_supported')

    def test_quality_does_not_run_product_and_binds_only_matching_execution_reports(self):
        task=self.task(required_files=list(FILES));self.run_task(task)
        runner={'status':'passed','tests':1,'output':'Passed fixture'}
        with patch.object(app.product_runner,'check_product',return_value=runner) as mocked:
            self.get('/api/tasks/'+task+'/quality');mocked.assert_not_called()
            self.post('/api/tasks/'+task+'/run-tests',{})
        quality=self.get('/api/tasks/'+task+'/quality')
        self.assertTrue(quality['functional_verified'])
        with app.connect() as db:
            latest=json.loads(db.execute('SELECT spec FROM task_checks WHERE task_id=?',(task,)).fetchone()['spec'])
        self.assertEqual(latest['content_sha256'],quality['content_sha256'])
        app.save_check(task,dict(runner,content_sha256='old'))
        self.assertFalse(self.get('/api/tasks/'+task+'/quality')['functional_verified'])

    def test_cancel_during_planning_does_not_commit_a_new_manifest_or_start_files(self):
        task=self.task()
        def provider(messages):
            app.task_action(task,'cancel');return self.provider(messages)
        value=self.run_task(task,provider)
        self.assertEqual(value['status'],'cancelled');self.assertFalse(self.generated)
        self.assertEqual(value['requirements']['manifest_source'],'pending_plan')

    def test_new_submission_still_requires_csrf_and_quality_respects_tool_revocation(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/tasks',{'prompt':'P','product':True},protected=False)
        self.assertEqual(error.exception.code,403)
        task=self.task(required_files=list(FILES));self.run_task(task)
        with app.connect() as db:
            app.bot_tools.save_policy(db,'review',[])
        with self.assertRaises(urllib.error.HTTPError) as error: self.get('/api/tasks/'+task+'/quality')
        self.assertEqual(error.exception.code,403)

    def test_approval_cannot_override_known_syntax_or_bound_test_failure(self):
        task=self.task(required_files=list(FILES));self.run_task(task)
        bad=[{'path':p,'content':'def broken(' if p=='src/main.py' else c} for p,c in FILES.items()]
        status, child=app.save_product_revision(task,bad)
        self.assertEqual(status,201)
        self.assertEqual(app.task_action(child['id'],'approve')[0],409)
        with patch.object(app.product_runner,'check_product',return_value={'status':'failed','tests':1,'output':'Fixture failed'}):
            self.post('/api/tasks/'+task+'/run-tests',{})
        self.assertEqual(app.task_action(task,'approve')[0],409)

    def test_slash_data_command_overrides_default_application_kind_without_weakening_template(self):
        task=self.post('/api/tasks',{'prompt':'/data Dữ liệu mẫu','mode':'demo','product_kind':'application'})['id']
        spec=self.get('/api/tasks/'+task)['requirements']
        self.assertEqual(spec['kind'],'data');self.assertEqual(spec['template'],'data')
