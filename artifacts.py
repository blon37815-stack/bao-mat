"""Validate model-generated text files and package them without executing code."""
import io
import json
import re
import unicodedata
import zipfile

MAX_FILES = 30
MAX_FILE_BYTES = 100_000
MAX_TOTAL_BYTES = 1_000_000


def parse_files(text):
    if len(text.encode('utf-8')) > MAX_TOTAL_BYTES * 2:
        raise ValueError('Phản hồi tạo tệp quá lớn')
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError('Bộ tệp phải là JSON gồm files: [{path, content}]') from None
    files = value.get('files') if isinstance(value, dict) else None
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('Bộ sản phẩm cần từ 1 đến 30 tệp')
    result, seen, total = [], set(), 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('content'), str):
            raise ValueError('Mỗi tệp cần path và content dạng văn bản')
        path = unicodedata.normalize('NFC', item['path'])
        parts = path.split('/')
        if len(path) > 200 or any(not part or part in ('.', '..') or part.endswith((' ', '.')) for part in parts):
            raise ValueError('Đường dẫn tệp không an toàn')
        if any(ord(char) < 32 or ord(char) == 127 or char in '\\:<>"|?*' for char in path):
            raise ValueError('Tên tệp chứa ký tự không hợp lệ')
        for part in parts:
            stem = part.split('.')[0].upper()
            if stem in {'CON','PRN','AUX','NUL','CONIN$','CONOUT$'} or re.fullmatch(r'(COM|LPT)[0-9¹²³]', stem):
                raise ValueError('Tên tệp dành riêng cho Windows')
            if part.casefold() in ('.git', '.venv'):
                raise ValueError('Không tạo thư mục Git hoặc môi trường ảo')
        folded = path.casefold()
        if folded in seen or any(folded.startswith(old+'/') or old.startswith(folded+'/') for old in seen):
            raise ValueError('Tên tệp bị trùng hoặc xung đột thư mục')
        seen.add(folded)
        size = len(item['content'].encode('utf-8'))
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Bộ tệp vượt giới hạn dung lượng')
        result.append({'path':path, 'content':item['content']})
    return result


def zip_files(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.writestr(item['path'], item['content'].encode('utf-8'))
    return buffer.getvalue()
