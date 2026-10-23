"""HTTP admission for tasks; manifests are frozen before file generation."""
import json
import re
import uuid

from product_contracts import ContractError, missing_paths, request_contract


def submit(handler, app):
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 20000:
            raise ValueError()
        data = json.loads(handler.rfile.read(length))
        prompt, mode = data.get('prompt'), data.get('mode', 'demo')
        command = app.task_commands.parse(prompt)
        review_only = False
        if command:
            name, argument = command
            if name == 'verify':
                status, report = app.run_product_checks(argument)
                return handler.respond(status, report)
            if name == 'code-review':
                data = dict(data, parent_id=argument, expert='architect', template='', product=False)
                prompt = 'Rà soát bộ mã nguồn đính kèm, liệt kê lỗi có bằng chứng, vị trí và cách sửa. Chỉ tạo báo cáo, không tạo lại bộ tệp và không tuyên bố đã chạy kiểm thử.'
                review_only = True
            else:
                data = dict(data, template='plan' if name == 'plan' else name,
                            expert='planner' if name == 'plan' else name, product=name != 'plan',
                            product_kind='data' if name=='data' else 'application')
                prompt = argument
        product = data.get('product', False)
        template = data.get('template', '')
        requirements = app.template_requirements(template)
        chosen_expert = data.get('expert', 'auto')
        expert = app.resolve_expert(chosen_expert, template)
        limit = app.valid_call_limit(data['call_limit']) if 'call_limit' in data else app.get_policy()['default_call_limit']
        parent_id = data.get('parent_id')
        document_ids = data.get('document_ids', [])
        project_id = app.platform_config.identifier(data.get('project_id', 'default'))
        if not isinstance(document_ids, list):
            raise ValueError()
        if parent_id is not None and (not isinstance(parent_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',parent_id)):
            raise ValueError()
        if type(product) is not bool or type(data.get('repair_missing',False)) is not bool:
            raise ValueError()
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4000 or mode not in ('demo','ai','ollama'):
            raise ValueError()
    except app.task_commands.CommandError as error:
        return handler.respond(400, {'error':str(error)})
    except (ValueError, TypeError, AttributeError):
        return handler.respond(400, {'error':'Nhập nhiệm vụ từ 1–4000 ký tự và chế độ hợp lệ'})
    if mode == 'ai' and not app.os.environ.get('OPENAI_API_KEY'):
        return handler.respond(400, {'error':'Chưa cấu hình OPENAI_API_KEY trong môi trường máy chủ'})
    source = None
    if parent_id:
        status, parent = app.product_files(parent_id)
        if status != 200:
            return handler.respond(status, parent)
        source = json.dumps(parent['files'],ensure_ascii=False)
        if len(source.encode('utf-8')) > 80000:
            return handler.respond(413, {'error':'Bộ mã gốc vượt 80 KB; hãy chọn sản phẩm nhỏ hơn để sửa bằng mô hình hiện tại'})
        with app.connect() as db:
            parent_row = db.execute('SELECT prompt FROM tasks WHERE id=?',(parent_id,)).fetchone()
            parent_runtime = app.platform_config.task_runtime(db,parent_id)
        if parent_row is None:
            return handler.respond(409, {'error':'Bản gốc đã thay đổi; hãy chọn lại'})
        previous = app.task_source(parent_id)
        original = ((previous['parent_prompt']+'\n\n') if previous else '')+parent_row['prompt']
        if len(original) > 12000:
            return handler.respond(413, {'error':'Chuỗi yêu cầu quá dài; hãy tạo nhiệm vụ độc lập với yêu cầu được tóm tắt'})
        parent_project = (parent_runtime or {}).get('project_id','default')
        if 'project_id' in data and project_id != parent_project:
            return handler.respond(400, {'error':'Phiên bản sửa phải cùng dự án với bản gốc'})
        project_id = parent_project
        product = True
        parent_spec = app.get_requirements(parent_id)
        if requirements and parent_spec:
            if requirements.get('template') != parent_spec.get('template'):
                return handler.respond(400, {'error':'Tạo nhiệm vụ độc lập để đổi mẫu; phiên bản sửa giữ tiêu chí gốc.'})
            requirements = parent_spec
        else:
            requirements = requirements or parent_spec
        if 'expert' not in data:
            expert = app.get_assignment(parent_id)['expert']
        elif chosen_expert == 'auto':
            expert = app.resolve_expert('auto', requirements.get('template',''))
    if requirements.get('required_files'):
        product = True
    if review_only:
        product = False
    try:
        if product:
            requirements = request_contract(requirements, data.get('required_files'), data.get('product_kind'), inherited=bool(parent_id))
            if data.get('repair_missing'):
                if not parent_id:
                    raise ContractError('Chọn bản gốc trước khi bổ sung tệp thiếu.')
                targets = missing_paths(parent['files'], requirements)
                if not targets:
                    raise ContractError('Không còn tệp bắt buộc thiếu hoặc rỗng; dùng Yêu cầu chỉnh sửa để sửa chức năng.')
                requirements['repair_files'] = targets
        else:
            requirements = {}
    except ContractError as error:
        return handler.respond(400, {'error':str(error)})
    with app.ADMISSION_LOCK:
        if app.TASK_QUEUE.full():
            return handler.respond(429, {'error':'Hàng đợi đầy; hãy đợi hoặc hủy một việc đang chờ'})
        task_id = uuid.uuid4().hex
        with app.connect() as db:
            if parent_id and not db.execute('SELECT 1 FROM tasks WHERE id=?',(parent_id,)).fetchone():
                return handler.respond(409, {'error':'Bản gốc đã thay đổi; hãy chọn lại'})
            try:
                app.platform_config.snapshot(db,task_id,mode,project_id=project_id,expert=expert,app_version=app.RUNTIME_INFO)
                app.workspace_data.snapshot_documents(db,task_id,document_ids)
            except ValueError as error:
                db.rollback()
                return handler.respond(400, {'error':str(error)})
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',(task_id,prompt.strip(),mode,'queued','Chờ','{}',app.utc_now()))
            app.workspace_data.snapshot_bots(db,task_id)
            app.snapshot_memory(db,task_id,project_id)
            db.execute('INSERT INTO task_products VALUES (?,?)',(task_id,int(product)))
            db.execute('INSERT INTO task_requirements VALUES (?,?)',(task_id,json.dumps(requirements,ensure_ascii=False)))
            db.execute('INSERT INTO task_assignment VALUES (?,?,?,?)',(task_id,expert,limit,app.ECC_COMMIT if expert!='none' else ''))
            if source is not None:
                db.execute('INSERT INTO task_sources VALUES (?,?,?,?)',(task_id,parent_id,source,original))
        app.enqueue_task(task_id,prompt.strip(),mode)
    return handler.respond(201, {'id':task_id,'expert':expert,'call_limit':limit,'requirements':requirements})
