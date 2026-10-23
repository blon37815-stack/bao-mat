"""Read-only host sampling. It never kills processes or controls hardware limits."""
import csv
from datetime import datetime, timezone
import io
import math
import shutil
import subprocess
import threading
import time

import psutil


def gpu_snapshot():
    binary=shutil.which('nvidia-smi')
    if not binary:
        return {'status':'unavailable','devices':[],'message':'Chưa đọc được GPU; cần NVIDIA và nvidia-smi trên PATH.'}
    try:
        result=subprocess.run([binary,'--query-gpu=name,utilization.gpu,memory.used,memory.total',
                               '--format=csv,noheader,nounits'],capture_output=True,text=True,
                              encoding='utf-8',errors='replace',check=True,timeout=1)
        devices=[]
        for row in list(csv.reader(io.StringIO(result.stdout)))[:8]:
            if len(row)!=4:
                continue
            name,load,used,total=[field.strip() for field in row]
            used,total=float(used),float(total)
            percent=float(load) if load not in ('N/A','[N/A]') else None
            if not math.isfinite(used) or not math.isfinite(total) or used<0 or total<=0:
                continue
            if percent is not None and (not math.isfinite(percent) or not 0<=percent<=100):
                percent=None
            devices.append({'name':name,'percent':percent,'used_mb':used,'total_mb':total})
        if devices:
            return {'status':'ready','devices':devices,'message':'Số liệu NVIDIA do nvidia-smi cung cấp.'}
    except (OSError,ValueError,subprocess.SubprocessError):
        pass
    return {'status':'unavailable','devices':[],'message':'Không đọc được số liệu GPU ở lần lấy mẫu này.'}


class ResourceMonitor:
    def __init__(self):
        self.lock=threading.Lock()
        self.previous_cpu=None
        self.cached=None
        self.sample_time=0
        self.gpu=None
        self.gpu_time=0

    def snapshot(self):
        with self.lock:
            now=time.monotonic()
            if self.cached is not None and now-self.sample_time<2:
                return dict(self.cached)
            cpu,memory,rss=None,None,None
            try:
                times=psutil.cpu_times()
                total=sum(times)-getattr(times,'guest',0)-getattr(times,'guest_nice',0)
                idle=times.idle+getattr(times,'iowait',0)
                if self.previous_cpu:
                    delta=total-self.previous_cpu[0]
                    if delta>0:
                        cpu=round(max(0,min(100,100*(1-(idle-self.previous_cpu[1])/delta))),1)
                self.previous_cpu=(total,idle)
                vm=psutil.virtual_memory()
                memory={'total_bytes':vm.total,'available_bytes':vm.available,'percent':vm.percent}
                rss=psutil.Process().memory_info().rss
            except (OSError,psutil.Error):
                pass
            if self.gpu is None or now-self.gpu_time>=5:
                self.gpu=gpu_snapshot();self.gpu_time=now
            self.cached={'sampled_at':datetime.now(timezone.utc).isoformat(),'cpu_percent':cpu,
                         'memory':memory,'app_memory_bytes':rss,'gpu':self.gpu,
                         'scope':'Máy đang chạy máy chủ ứng dụng; RAM app không bao gồm tiến trình Ollama.'}
            self.sample_time=now
            return dict(self.cached)


MONITOR=ResourceMonitor()
