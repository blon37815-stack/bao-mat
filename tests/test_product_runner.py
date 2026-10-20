import os
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

from ollama_transport import InferenceCancelled
import product_runner


def bundle(test):
    return [{'path':'main.py','content':'def add(a,b):\n return a+b\n'},
            {'path':'tests/test_main.py','content':test}]


class RunnerBoundaryTest(unittest.TestCase):
    def test_missing_docker_and_unsupported_files_do_not_execute_on_host(self):
        with patch.object(product_runner.shutil,'which',return_value=None), patch.object(product_runner.subprocess,'Popen') as process:
            self.assertEqual(product_runner.check_product(bundle('raise RuntimeError("untrusted")'))['status'], 'unavailable')
            self.assertEqual(product_runner.check_product([{'path':'app.js','content':'throw Error()'}])['status'], 'not_supported')
            process.assert_not_called()

    def test_invalid_paths_and_cancelled_job_never_launch_docker(self):
        event = threading.Event(); event.set()
        with patch.object(product_runner.subprocess,'Popen') as process:
            with self.assertRaises(ValueError): product_runner.check_product([{'path':'../../escape.py','content':'bad'}])
            with self.assertRaises(InferenceCancelled): product_runner.check_product(bundle('pass'), event)
            process.assert_not_called()


@unittest.skipUnless(os.environ.get('BAO_TEST_DOCKER') == '1', 'Set BAO_TEST_DOCKER=1 for real isolated product execution')
class RealDockerRunnerTest(unittest.TestCase):
    def setUp(self):
        if product_runner.health()['status'] != 'ready': self.skipTest('Docker image unavailable')

    def test_real_tests_and_isolation_probes_pass(self):
        test = '''import os, socket, unittest
from main import add
class ProductTest(unittest.TestCase):
 def test_function(self): self.assertEqual(add(2,3),5)
 def test_nonroot_and_readonly(self):
  self.assertNotEqual(os.getuid(),0)
  with self.assertRaises(OSError): open('/source/outside.txt','w')
  with self.assertRaises(OSError): open('/outside.txt','w')
 def test_no_network(self):
  with self.assertRaises(OSError): socket.create_connection(('1.1.1.1',443),timeout=.2)
'''
        report = product_runner.check_product(bundle(test))
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['tests'], 3)
        self.assertEqual(report['isolation']['network'], 'none')

    def test_failure_and_zero_tests_are_not_passed(self):
        report = product_runner.check_product(bundle('import unittest\nclass T(unittest.TestCase):\n def test_bad(self): self.assertEqual(1,2)\n'))
        self.assertEqual(report['status'], 'failed')
        self.assertIn('AssertionError', report['output'])
        self.assertEqual(product_runner.check_product(bundle('x=1'))['status'], 'not_supported')

    def test_cancellation_stops_an_infinite_test_and_removes_container(self):
        event = threading.Event()
        timer = threading.Timer(2, event.set); timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(InferenceCancelled):
                product_runner.check_product(bundle('import unittest\nclass T(unittest.TestCase):\n def test_forever(self):\n  while True: pass\n'), event)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic()-started, 12)
        remaining = subprocess.run(['docker','ps','-aq','--filter','name=bao-mat-check-'], check=True, capture_output=True)
        self.assertEqual(remaining.stdout.strip(), b'')

    def test_stdout_flood_cannot_grow_the_host_capture_without_bound(self):
        test = "import os\nfd=os.open('/proc/1/fd/1',os.O_WRONLY)\nfor i in range(1000): os.write(fd,b'x'*65536)\n"
        report = product_runner.check_product(bundle(test))
        self.assertEqual(report['status'], 'failed')
        self.assertIn('vượt giới hạn', report['output'])
