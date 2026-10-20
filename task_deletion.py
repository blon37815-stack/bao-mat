"""Delete one finished task, retaining other versions and their source snapshots."""
import hashlib
import json

TASK_TABLES = ('task_steps','task_timing','task_memory','task_products','task_requirements',
               'task_sources','task_generation','task_assignment','task_documents','task_bot_preferences',
               'task_runtime','task_checks')


def deletion_plan(db, task_id):
    row=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    if row is None:raise LookupError('Không tìm thấy công việc; có thể đã được xóa')
    if row['status'] in ('queued','running'):
        raise ValueError('Hãy hoàn tất hoặc hủy công việc trước khi xóa')
    records={'task':dict(row)}
    for table in TASK_TABLES:
        records[table]=sorted([dict(item) for item in db.execute('SELECT * FROM '+table+' WHERE task_id=?',(task_id,))],key=lambda item:json.dumps(item,sort_keys=True))
    records['cleanup']=[dict(item) for item in db.execute('SELECT c.* FROM task_step_cleanup c JOIN task_steps s ON s.id=c.step_id WHERE s.task_id=? ORDER BY c.step_id',(task_id,))]
    records['children']=[dict(item) for item in db.execute('SELECT task_id,parent_id FROM task_sources WHERE parent_id=? ORDER BY task_id',(task_id,))]
    records['retries']=[dict(item) for item in db.execute('SELECT * FROM task_retries WHERE parent_id=? OR child_id=? ORDER BY parent_id',(task_id,task_id))]
    related={item['task_id'] for item in records['children']}
    related.update(item[key] for item in records['retries'] for key in ('parent_id','child_id') if item[key]!=task_id)
    related={item for item in related if db.execute('SELECT 1 FROM tasks WHERE id=?',(item,)).fetchone()}
    records['related_live']=sorted(related)
    digest=hashlib.sha256(json.dumps(records,ensure_ascii=True,sort_keys=True).encode()).hexdigest()
    return {'id':task_id,'prompt':row['prompt'],'status':row['status'],'steps':len(records['task_steps']),
            'related':len(related),'fingerprint':digest,
            'content_bytes':len(row['output'].encode('utf-8'))+sum(len(item['output'].encode('utf-8')) for item in records['task_steps'])}


def apply_deletion(db, plan, timestamp):
    current=deletion_plan(db,plan['id'])
    if current['fingerprint']!=plan['fingerprint']:
        raise ValueError('Công việc đã thay đổi; hãy xem trước lại')
    task_id=plan['id']
    if current['related']:
        db.execute('INSERT INTO deleted_tasks VALUES (?,?,?)',(task_id,current['prompt'][:120],timestamp))
    db.execute('DELETE FROM task_step_cleanup WHERE step_id IN (SELECT id FROM task_steps WHERE task_id=?)',(task_id,))
    for table in TASK_TABLES:db.execute('DELETE FROM '+table+' WHERE task_id=?',(task_id,))
    db.execute('DELETE FROM tasks WHERE id=?',(task_id,))
    return current
