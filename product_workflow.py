"""Product planning integration, isolated from HTTP admission and provider code."""
import json

from product_contracts import ContractError, parse_plan, plan_messages, request_contract
from ollama_transport import EmptyResponse


def plan(app, state):
    spec = request_contract(state.get('requirements', {}), inherited=bool(state.get('source_files')))
    messages = plan_messages(dict(state, requirements=spec))
    for attempt in range(2):
        try:
            raw = app.model_reply(messages, state['mode'])
        except EmptyResponse:
            raw = ''
        try:
            text, resolved = parse_plan(raw, spec, state.get('source_files', []))
        except ContractError as error:
            if attempt:
                raise ContractError('Chưa chốt được danh sách tệp sau 2 lần lập kế hoạch: '+str(error)) from None
            app.worker_update(state['id'], stage='Điều phối · lập lại danh sách tệp chưa hợp lệ (1/1)')
            messages = [*plan_messages(dict(state, requirements=spec)),
                        {'role':'user', 'content':'Sửa phản hồi theo lỗi kiểm tra: '+str(error)}]
        else:
            with app.connect() as db:
                changed = db.execute('''UPDATE task_requirements SET spec=? WHERE task_id=?
                    AND EXISTS (SELECT 1 FROM tasks WHERE id=? AND status='running')''',
                    (json.dumps(resolved, ensure_ascii=False), state['id'], state['id'])).rowcount
                if not changed:
                    raise app.TaskCancelled()
            return text, resolved


def bind_report(files, report):
    from product_quality import content_digest
    return dict(report, content_sha256=content_digest(files))
