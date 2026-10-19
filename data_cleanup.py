"""Plan and apply explicitly requested cleanup; no scheduling or automatic deletion."""
import hashlib
import json


def cleanup_plan(db, scope, cutoff):
    if scope not in ('history','tasks'):
        raise ValueError('Unknown cleanup scope')
    if scope=='history':
        rows = db.execute('''SELECT s.id,s.task_id,s.output,t.prompt FROM task_steps s
            JOIN tasks t ON t.id=s.task_id LEFT JOIN task_timing tm ON tm.task_id=t.id
            WHERE t.status NOT IN ('queued','running') AND COALESCE(tm.finished_at,t.created)<? AND s.output!=''
            ORDER BY s.id''',(cutoff,)).fetchall()
        protected = 0
    else:
        rows = db.execute('''SELECT t.id,t.id AS task_id,t.output,t.prompt,t.status FROM tasks t
            LEFT JOIN task_timing tm ON tm.task_id=t.id
            WHERE t.status NOT IN ('queued','running') AND COALESCE(tm.finished_at,t.created)<?
            AND NOT EXISTS (SELECT 1 FROM task_sources s WHERE s.parent_id=t.id OR s.task_id=t.id)
            AND NOT EXISTS (SELECT 1 FROM task_retries r WHERE r.parent_id=t.id OR r.child_id=t.id)
            ORDER BY t.id''',(cutoff,)).fetchall()
        older = db.execute('''SELECT COUNT(*) FROM tasks t LEFT JOIN task_timing tm ON tm.task_id=t.id
            WHERE t.status NOT IN ('queued','running') AND COALESCE(tm.finished_at,t.created)<?''',(cutoff,)).fetchone()[0]
        protected = older-len(rows)
    records = [dict(row) for row in rows]
    digest = hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    unique_tasks = list(dict.fromkeys(row['task_id'] for row in records))
    return {'scope':scope,'cutoff':cutoff,'ids':[row['id'] for row in records], 'fingerprint':digest,
            'items':len(records),'tasks':len(unique_tasks),'protected':protected,
            'content_bytes':sum(len(row['output'].encode('utf-8')) for row in records),
            'examples':[{'id':row['task_id'],'prompt':row['prompt'][:120]} for row in records[:5]]}


def apply_cleanup(db, plan, timestamp):
    current = cleanup_plan(db,plan['scope'],plan['cutoff'])
    if current['fingerprint']!=plan['fingerprint']:
        raise ValueError('Dữ liệu đã thay đổi; hãy xem trước lại')
    ids = current['ids']
    if plan['scope']=='history':
        db.executemany('INSERT OR REPLACE INTO task_step_cleanup VALUES (?,?)',[(step_id,timestamp) for step_id in ids])
        db.executemany("UPDATE task_steps SET output='' WHERE id=?",[(step_id,) for step_id in ids])
    else:
        db.execute('CREATE TEMP TABLE cleanup_targets (id TEXT PRIMARY KEY)')
        db.executemany('INSERT INTO cleanup_targets VALUES (?)',[(task_id,) for task_id in ids])
        db.execute('DELETE FROM task_step_cleanup WHERE step_id IN (SELECT id FROM task_steps WHERE task_id IN (SELECT id FROM cleanup_targets))')
        for table in ('task_steps','task_timing','task_memory','task_products','task_requirements','task_sources','task_generation','task_assignment','task_documents','task_bot_preferences'):
            db.execute('DELETE FROM '+table+' WHERE task_id IN (SELECT id FROM cleanup_targets)')
        db.execute('DELETE FROM tasks WHERE id IN (SELECT id FROM cleanup_targets)')
    return current
