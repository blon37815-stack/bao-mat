"""Explicit dashboard command adapters; not an ECC shell/plugin interpreter."""
import re

COMMANDS = {
    'plan': 'Lập kế hoạch bằng chuyên gia planner',
    'python': 'Tạo bộ tệp Python theo mẫu',
    'web': 'Tạo bộ tệp web theo mẫu',
    'data': 'Tạo bộ tệp JSON theo mẫu',
    'code-review': 'Rà soát bằng AI bộ tệp của một mã nhiệm vụ; không chạy mã',
    'verify': 'Chạy unittest Python trong Docker cho một mã nhiệm vụ',
}


class CommandError(ValueError):
    pass


def parse(prompt):
    if not isinstance(prompt, str) or not prompt.startswith('/'):
        return None
    match = re.fullmatch(r'/([a-z-]+)(?:\s+([\s\S]+))?', prompt.strip())
    if not match or match[1] not in COMMANDS:
        raise CommandError('Lệnh chưa hỗ trợ. Dùng '+', '.join('/'+key for key in COMMANDS))
    argument = (match[2] or '').strip()
    if not argument:
        raise CommandError('Cần nội dung hoặc mã nhiệm vụ sau /'+match[1])
    if match[1] in ('verify', 'code-review') and not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', argument):
        raise CommandError('Lệnh này chỉ nhận một mã nhiệm vụ')
    return match[1], argument
