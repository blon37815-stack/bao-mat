"""Opt-in, sequential local Ollama evaluation; generated code is never executed."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import statistics
import tempfile
import time
import uuid

import app
from artifacts import parse_files, check_files
from evaluation_cases import CASES
from maintenance import ollama_health
from runtime_version import RUNTIME_INFO
from task_requirements import template_requirements, check_requirements


def inspect_result(result, case):
    try:
        files = parse_files(result)
    except ValueError as error:
        return {'passed':False,'issues':[str(error)],'checked':0,'skipped':0}
    issues = check_requirements(files,template_requirements(case['template']))
    checks = check_files(files)
    issues += [item['path']+': '+item['message'] for item in checks['findings'] if item['status']=='failed']
    if checks['status']!='passed':
        issues.append('Chưa có kết quả kiểm tra cú pháp đạt ở các tệp được hỗ trợ.')
    if case.get('unicode_notes') or case.get('escaped_notes'):
        try:
            notes = json.loads(next(file['content'] for file in files if file['path']=='notes.json'))
            texts = [note['content'] for note in notes]
            if case.get('unicode_notes') and not any(any(ord(char)>127 for char in text) for text in texts):
                issues.append('Ghi chú chưa có tiếng Việt có dấu theo ca đánh giá.')
            if case.get('escaped_notes') and not any('\n' in text and '"' in text for text in texts):
                issues.append('Chưa có content chứa cả xuống dòng và dấu ngoặc kép.')
        except (ValueError,KeyError,TypeError,StopIteration):
            issues.append('Không đọc được nội dung ghi chú để đánh giá ca bổ sung.')
    return {'passed':not issues,'issues':issues,'checked':checks['checked'],'skipped':checks['skipped']}


def summaries(trials):
    grouped = {}
    for trial in trials:
        grouped.setdefault(trial['case_id'],[]).append(trial)
    result = {}
    for name,group in grouped.items():
        count = len(group)
        passed = sum(trial.get('passed',False) for trial in group)
        result[name] = {'trials':count,'passed':passed,'pass_rate':passed/count,
                        'first_pass':sum(trial.get('first_pass',False) for trial in group),
                        'median_seconds':statistics.median(trial['seconds'] for trial in group),
                        'target_met':passed/count>=.8 if count>=10 and group[0]['template']=='data' else None}
    return result


def checkpoint(path, report):
    report['summary'] = summaries(report['trials'])
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False,suffix='.tmp') as saved:
        temporary = Path(saved.name)
        json.dump(report,saved,ensure_ascii=False,indent=2)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run_evaluation(cases, repeat, output):
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    report = {'provider':'ollama','model':os.environ.get('OLLAMA_MODEL','qwen3:4b'),
              'app':RUNTIME_INFO,'started_at':app.utc_now(),'status':'running','functional_tests':False,
              'acceptance':'Final artifact static checks AND completed workflow; target >=8/10 for each JSON case.',
              'trials':[],'summary':{}}
    # Reserve a new report; never overwrite results from an earlier evaluation.
    with output.open('x',encoding='utf-8') as saved:
        json.dump(report,saved,ensure_ascii=False,indent=2)
    original_db = app.DB
    try:
        with tempfile.TemporaryDirectory(prefix='bao-mat-evaluation-') as temporary:
            app.DB = Path(temporary)/'tasks.sqlite3'
            for case in cases:
                for number in range(1,repeat+1):
                    task_id = uuid.uuid4().hex
                    with app.connect() as db:
                        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',(task_id,case['prompt'],'ollama','queued','','{}',app.utc_now()))
                        db.execute('INSERT INTO task_products VALUES (?,1)',(task_id,))
                        db.execute('INSERT INTO task_requirements VALUES (?,?)',(task_id,json.dumps(template_requirements(case['template']),ensure_ascii=False)))
                    print(f"{case['id']} {number}/{repeat}",flush=True)
                    started = time.monotonic()
                    trial = {'case_id':case['id'],'template':case['template'],'repeat':number,'task_id':task_id}
                    try:
                        app.run(task_id,case['prompt'],'ollama')
                    except KeyboardInterrupt:
                        trial.update(status='interrupted',passed=False,first_pass=False,seconds=round(time.monotonic()-started,3))
                        report['trials'].append(trial)
                        raise
                    with app.connect() as db:
                        row = db.execute(app.TASK_SELECT+' WHERE t.id=?',(task_id,)).fetchone()
                    task = app.public_task(row)
                    check = inspect_result(json.loads(task['output']).get('result',''),case)
                    _,history = app.task_history(task_id)
                    first = next((step['output'] for step in history['steps'] if step['role']=='result' and step['status']=='completed'),'')
                    trial.update(status=task['status'],passed=check['passed'] and task['status']=='completed',
                                 first_pass=inspect_result(first,case)['passed'] if first else False,
                                 issues=check['issues'],checked=check['checked'],skipped=check['skipped'],
                                 calls=task['model_calls'],seconds=round(time.monotonic()-started,3))
                    report['trials'].append(trial)
                    checkpoint(output,report)
                    print('  '+('Đạt tĩnh và luồng' if trial['passed'] else 'Chưa đạt')+f" · {trial['seconds']} giây · {trial['calls']} yêu cầu",flush=True)
            report['status'] = 'completed'
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
    except Exception:
        report['status'] = 'error'
        raise
    finally:
        app.DB = original_db
        report['finished_at'] = app.utc_now()
        checkpoint(output,report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['all','data','python','web'],default='all')
    parser.add_argument('--case',choices=[case['id'] for case in CASES])
    parser.add_argument('--repeat',type=int,default=1)
    parser.add_argument('--run',action='store_true',help='Actually call local Ollama; without this flag only list cases.')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args(argv)
    if not 1<=args.repeat<=100:
        parser.error('--repeat must be 1..100')
    cases = [case for case in CASES if (not args.case or case['id']==args.case) and (args.suite=='all' or case['template']==args.suite)]
    if not cases:
        parser.error('Case and suite do not match')
    if not args.run:
        for case in cases:print(case['id']+' · '+case['template']+' · '+case['prompt'])
        print('Chỉ liệt kê. Thêm --run để gọi Ollama; không chạy mã sản phẩm.')
        return 0
    if any(case['template']=='web' for case in cases) and shutil.which('node') is None:
        parser.error('Web evaluation needs Node.js syntax checks; install Node or choose --suite data/python')
    health = ollama_health(os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434'),os.environ.get('OLLAMA_MODEL','qwen3:4b'))
    if health['status']!='ready':
        parser.error('Ollama/model not ready; no inference was started')
    output = args.output or Path('data/evaluations')/('evaluation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.json')
    report = run_evaluation(cases,args.repeat,output)
    print('Báo cáo: '+str(output.resolve()))
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))
    return 130 if report['status']=='interrupted' else 0 if all(trial['passed'] for trial in report['trials']) else 1


if __name__=='__main__':
    raise SystemExit(main())
