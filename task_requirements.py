"""Deterministic acceptance checks for the built-in product templates."""
import json
from datetime import datetime

TEMPLATE_FILES = {
    'web':['index.html','style.css','app.js','README.md'],
    'python':['main.py','tests/test_main.py','README.md'],
    'data':['notes.json','config.json','README.md'],
}


def template_requirements(template):
    if template not in ('','plan',*TEMPLATE_FILES):
        raise ValueError('Unknown task template')
    if template not in TEMPLATE_FILES:
        return {}
    spec = {'template':template, 'required_files':list(TEMPLATE_FILES[template]),
            'instructions':'Tạo từng tệp thực tế trong files. Không chỉ mô tả cách tạo hoặc nhúng tất cả mã vào README.'}
    if template=='data':
        spec['data_schema'] = 'notes.json là mảng đúng 3 ghi chú: id duy nhất (chuỗi hoặc số nguyên), title và content không rỗng, created_at dạng ISO 8601. config.json là đối tượng JSON.'
    return spec


def check_requirements(files, spec):
    contents = {file['path']:file['content'] for file in files}
    issues = ['Thiếu tệp thực tế '+path+' trong files; mã nằm trong README không thay thế được tệp này.'
              for path in spec.get('required_files',[]) if path not in contents]
    if spec.get('template')!='data':
        return issues
    for path in ('notes.json','config.json'):
        if path not in contents:
            continue
        try:
            value = json.loads(contents[path])
        except (ValueError,RecursionError):
            issues.append(path+': JSON không hợp lệ.')
            continue
        if path=='config.json':
            if not isinstance(value,dict):
                issues.append('config.json phải là đối tượng JSON.')
            continue
        if not isinstance(value,list) or len(value)!=3:
            issues.append('notes.json phải là mảng đúng 3 ghi chú theo mẫu đã chọn.')
            continue
        seen = set()
        for index,note in enumerate(value,1):
            if not isinstance(note,dict):
                issues.append(f'Ghi chú {index} phải là đối tượng JSON.')
                continue
            identifier = note.get('id')
            if type(identifier) not in (str,int) or (isinstance(identifier,str) and not identifier.strip()):
                issues.append(f'Ghi chú {index} thiếu id hợp lệ.')
            elif str(identifier) in seen:
                issues.append(f'Ghi chú {index} bị trùng id.')
            else:
                seen.add(str(identifier))
            for field in ('title','content'):
                if not isinstance(note.get(field),str) or not note[field].strip():
                    issues.append(f'Ghi chú {index} thiếu {field} không rỗng.')
            try:
                timestamp = note.get('created_at')
                if not isinstance(timestamp,str) or 'T' not in timestamp:
                    raise ValueError()
                datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            except ValueError:
                issues.append(f'Ghi chú {index} thiếu created_at dạng ISO 8601.')
    return issues
