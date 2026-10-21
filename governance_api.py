"""Local audit/proposal HTTP routes; caller performs Host/Origin/CSRF checks."""
import json
import urllib.parse

import bot_tools
import upgrade_proposals


def get(handler, app, parsed_url):
    if parsed_url.path == '/api/audit':
        try:
            query = urllib.parse.parse_qs(parsed_url.query)
            task_id = query.get('task_id', [None])[0]
            if task_id:
                app.platform_config.identifier(task_id)
            with app.connect() as db:
                result = bot_tools.events(db, task_id, int(query.get('offset', ['0'])[0]), query.get('decision', [None])[0])
            return handler.respond(200, result)
        except ValueError as error:
            return handler.respond(400, {'error':str(error)})
    if handler.path == '/api/upgrades' or handler.path.startswith('/api/upgrades/'):
        try:
            with app.ADMISSION_LOCK, app.connect() as db:
                if handler.path == '/api/upgrades':
                    return handler.respond(200, upgrade_proposals.list_proposals(db))
                parts = handler.path.split('/')
                if len(parts) == 4:
                    return handler.respond(200, upgrade_proposals.detail(db, app.ROOT, app.DB.parent, parts[3]))
                if len(parts) == 5 and parts[4] == 'artifact.zip':
                    payload = upgrade_proposals.download(db, app.DB.parent, parts[3])
                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/zip')
                    handler.send_header('Content-Disposition', 'attachment; filename="upgrade-'+parts[3]+'.zip"')
                    handler.send_header('Content-Length', str(len(payload)))
                    handler.end_headers()
                    try:
                        handler.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass
                    return
                raise LookupError('Không tìm thấy đề xuất')
        except LookupError as error:
            return handler.respond(404, {'error':str(error)})
        except (ValueError, OSError) as error:
            return handler.respond(409, {'error':str(error) if not isinstance(error, OSError) else 'Chưa đọc được bản sao đề xuất'})


def post(handler, app):
    if handler.path == '/api/upgrades' or handler.path.startswith('/api/upgrades/'):
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= 2000:
                raise ValueError('Nội dung đề xuất không hợp lệ')
            data = json.loads(handler.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Nội dung đề xuất không hợp lệ')
            with app.ADMISSION_LOCK:
                if handler.path == '/api/upgrades':
                    task_id = app.platform_config.identifier(data.get('task_id'))
                    status, product = app.product_files(task_id)
                    if status != 200:
                        return handler.respond(status, product)
                    if product['mode'] == 'demo':
                        raise ValueError('Không dùng bộ tệp mô phỏng làm nâng cấp ứng dụng')
                    def prepare():
                        with app.connect() as db:
                            db.execute('BEGIN IMMEDIATE')
                            return upgrade_proposals.create(db, app.ROOT, app.DB.parent, task_id, data.get('title'), product['files'], app.RUNTIME_INFO)
                    result = bot_tools.invoke(app.connect, task_id, 'result', 'propose_upgrade',
                        {'paths':[item['path'] for item in product['files']]}, prepare)
                    return handler.respond(201, result)
                parts = handler.path.split('/')
                if len(parts) != 5 or parts[4] not in ('review', 'delete'):
                    raise LookupError('Không tìm thấy thao tác đề xuất')
                with app.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if parts[4] == 'review':
                        result = upgrade_proposals.review(db, app.ROOT, app.DB.parent, parts[3], data.get('decision'), data.get('confirmation'))
                    else:
                        result = upgrade_proposals.delete(db, app.DB.parent, parts[3], data.get('confirmation'))
                    reason = ('Đã xóa bản đề xuất; giữ nguyên mã ứng dụng' if parts[4] == 'delete'
                              else 'Đã duyệt bản đề xuất; chưa áp dụng patch' if result['status'] == 'approved'
                              else 'Đã từ chối bản đề xuất')
                    bot_tools.record(db, None, 'user', 'propose_upgrade', 'ALLOW', 'completed', reason, {'proposal_id':parts[3]})
                return handler.respond(200, result)
        except bot_tools.ToolDenied as error:
            return handler.respond(403, {'error':str(error)})
        except LookupError as error:
            return handler.respond(404, {'error':str(error)})
        except (ValueError, TypeError, OSError) as error:
            return handler.respond(400, {'error':str(error) if not isinstance(error, OSError) else 'Không lưu được bản sao đề xuất; kiểm tra dung lượng và quyền thư mục data'})


def run_product_checks(app, task_id):
    status, product = app.product_files(task_id)
    if status != 200:
        return status, product
    if product['mode'] == 'demo':
        return 400, {'error':'Không chạy sản phẩm mô phỏng'}
    with app.connect() as db:
        if db.execute('SELECT COUNT(*) FROM task_checks WHERE task_id=?', (task_id,)).fetchone()[0] >= 20:
            return 400, {'error':'Đã lưu 20 lượt kiểm thử; tạo phiên bản mới để kiểm tra tiếp'}
    try:
        report = bot_tools.invoke(app.connect, task_id, 'review', 'run_python_tests',
            {'paths':[item['path'] for item in product['files']]}, lambda: app.product_runner.check_product(product['files']))
    except bot_tools.ToolDenied as error:
        return 403, {'error':str(error)}
    app.save_check(task_id, report)
    if report['status'] == 'failed':
        with app.connect() as db:
            db.execute("UPDATE tasks SET status='needs_review',stage='Kiểm thử Docker thất bại; xem báo cáo và tạo phiên bản sửa' WHERE id=? AND status IN ('completed','approved','needs_review')", (task_id,))
    return 200, dict(report, id=task_id)
