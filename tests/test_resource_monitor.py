from collections import namedtuple
import subprocess
import unittest
from unittest.mock import Mock, patch

import resource_monitor as resources


class ResourceMonitorTest(unittest.TestCase):
    def test_cpu_uses_shared_deltas_and_ram_is_host_wide(self):
        times=namedtuple('Times','user system idle')
        vm=Mock(total=1000,available=400,percent=60.0)
        process=Mock();process.memory_info.return_value=Mock(rss=50)
        monitor=resources.ResourceMonitor()
        with patch.object(resources.time,'monotonic',side_effect=[0,3]),patch.object(resources.psutil,'cpu_times',side_effect=[times(10,10,80),times(20,10,90)]),patch.object(resources.psutil,'virtual_memory',return_value=vm),patch.object(resources.psutil,'Process',return_value=process),patch.object(resources,'gpu_snapshot',return_value={'status':'unavailable','devices':[]}):
            first=monitor.snapshot();second=monitor.snapshot()
        self.assertIsNone(first['cpu_percent'])
        self.assertEqual(second['cpu_percent'],50.0)
        self.assertEqual(second['memory']['available_bytes'],400)
        self.assertEqual(second['app_memory_bytes'],50)

    def test_missing_gpu_tool_is_unknown_not_zero(self):
        with patch.object(resources.shutil,'which',return_value=None),patch.object(resources.subprocess,'run') as run:
            result=resources.gpu_snapshot()
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['devices'],[])
        run.assert_not_called()

    def test_gpu_uses_fixed_command_and_timeout_failure_is_reported(self):
        with patch.object(resources.shutil,'which',return_value='/tool/nvidia-smi'),patch.object(resources.subprocess,'run',return_value=Mock(stdout='GPU Test, 25, 100, 200\n')) as run:
            result=resources.gpu_snapshot()
        self.assertEqual(result['devices'][0]['percent'],25)
        self.assertEqual(result['devices'][0]['total_mb'],200)
        self.assertEqual(run.call_args.kwargs['timeout'],1)
        self.assertNotIn('shell',run.call_args.kwargs)
        with patch.object(resources.shutil,'which',return_value='/tool/nvidia-smi'),patch.object(resources.subprocess,'run',side_effect=subprocess.TimeoutExpired('nvidia-smi',1)):
            self.assertEqual(resources.gpu_snapshot()['status'],'unavailable')
