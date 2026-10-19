import io
import json
import unittest
import zipfile
from artifacts import parse_files, zip_files


class ArtifactTest(unittest.TestCase):
    def encode(self, path, content='Nội dung tiếng Việt'):
        return json.dumps({'files':[{'path':path,'content':content}]})

    def test_zip_roundtrip_keeps_paths_and_unicode(self):
        files = parse_files(json.dumps({'files':[{'path':'README.md','content':'Hướng dẫn'}, {'path':'src/main.py','content':'print("Chào")'}]}))
        with zipfile.ZipFile(io.BytesIO(zip_files(files))) as archive:
            self.assertEqual(archive.namelist(), ['README.md','src/main.py'])
            self.assertEqual(archive.read('src/main.py').decode(), 'print("Chào")')

    def test_rejects_unsafe_windows_and_traversal_paths(self):
        for path in ('../x','a/../../x','/etc/x','C:/x','a\\b','a//b','./a','a/./b',
                     'file:stream','CON.txt','a/NUL','COM1.py','a.','a ','a/','a\n.py', '.git/config','.venv/bin/python'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                parse_files(self.encode(path))

    def test_rejects_collisions_and_size_limits(self):
        for paths in (['A.py','a.py'], ['src','src/main.py'], ['src/main.py','src']):
            with self.assertRaises(ValueError):
                parse_files(json.dumps({'files':[{'path':path,'content':''} for path in paths]}))
        for value in ('{}','[]','not json',json.dumps({'files':[]}), self.encode('a','x'*100001),json.dumps({'files':[{'path':str(i),'content':''} for i in range(31)]})):
            with self.assertRaises(ValueError):
                parse_files(value)

    def test_accepts_fenced_json_and_literal_code(self):
        files = parse_files('```json\n'+self.encode('example.txt','Thẻ <think> là ví dụ')+'\n```')
        self.assertIn('<think>', files[0]['content'])

    def test_static_checks_distinguish_failed_passed_and_skipped(self):
        from artifacts import check_files
        report = check_files([
            {'path':'good.py','content':'print("Chào")'},
            {'path':'bad.py','content':'return 1'},
            {'path':'good.json','content':'{"title":"Ghi chú"}'},
            {'path':'bad.json','content':'{"value":NaN}'},
            {'path':'app.js','content':'not checked'}])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['checked'], 4)
        self.assertEqual(report['skipped'], 1)
        self.assertEqual([item['status'] for item in report['findings']], ['passed','failed','passed','failed','skipped'])

    def test_static_check_does_not_execute_python(self):
        import tempfile
        from pathlib import Path
        from artifacts import check_files
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary)/'must-not-exist.txt'
            report = check_files([{'path':'danger.py','content':f'open({str(marker)!r}, "w").write("executed")\nraise RuntimeError("must not execute")'}])
            self.assertEqual(report['status'], 'passed')
            self.assertFalse(marker.exists())
        self.assertEqual(check_files([{'path':'index.html','content':'<html>'}])['status'], 'not_supported')

    def test_checker_timeout_is_unverified(self):
        import subprocess
        from unittest.mock import patch
        from artifacts import check_files
        with patch('artifacts.subprocess.run', side_effect=subprocess.TimeoutExpired('checker', 8)):
            self.assertEqual(check_files([{'path':'a.py','content':'pass'}])['status'], 'unavailable')
