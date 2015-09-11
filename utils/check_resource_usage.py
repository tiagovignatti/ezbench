#!/usr/bin/env python3

"""
Copyright (c) 2015, Intel Corporation

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of Intel Corporation nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import optparse
import psutil
import time
import sys
import os

interval=1 # Not true, but it is a good-enough value!
processes = dict()

class Process:
    def __init__(self, pid, reportId):
        try:
            p = psutil.Process(pid)
            times = p.cpu_times()
            self.pid = pid
            self.comm = p.name()
            self.ppid = p.ppid()
            self.utime = times.user
            self.stime = times.system
            self.reportId = reportId
        except:
            self.pid = pid
            self.reportId = 0
            pass

def readFile(path):
    try:
        f = open(path, "r")
        return f.read()
    except IOError:
        sys.stderr.write("Could not read file '{0}'".format(path))
        return ""

def log(msg):
    timeStr=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    print (timeStr + ": " + msg)

def computeCpuUsage(prev, new):
    if prev == None:
        prev_utime = 0
        prev_stime = 0
    else:
        prev_utime = prev.utime
        prev_stime = prev.stime

    userPercent=(new.utime - prev_utime) * 100 / interval
    systemPercent=(new.stime - prev_stime) * 100 / interval
    return (userPercent, systemPercent)

def gen_report(p, firstRun, reportId):
    if firstRun:
        return

    if os.getpid() == p.pid or p.pid in ignorePids:
        return

    # TODO: Check if a process died and another one took its pid by checking starttime

    if not p.pid in processes:
        log ("Process {pid} ({comm}) got created".format(pid=p.pid, comm=p.comm))
        prev = None
    else:
        prev = processes[p.pid]

    user,system = computeCpuUsage(prev, p)
    if (user + system) >= 0.5:
        log ("Process {pid} ({name}) has CPU usage: user = {user:0.1f}%, system = {system:0.1f}%".format(pid=pid,
                                                                                                           name=p.comm,
                                                                                                           user=user,
                                                                                                           system=system))

# Start by checking what the user wants to monitor!
p = optparse.OptionParser()
p.add_option('--cpu', '-c', action='store_true', default=False, help="Monitor the global cpu activity")
p.add_option('--disk', '-d', action='store_true', default=False, help="Monitor the globaldisk activity")
p.add_option('--network', '-n', action='store_true', default=False, help="Monitor the global network activity")
p.add_option('--ignorepids', '-i', action='store', type="string", default="", help="Ignore the following pids from the per-process cpu report")
options, arguments = p.parse_args()

ignorePids = []
for pid in options.ignorepids.split(","):
    ignorePids.append(int(pid))
print ("Warning: The CPU report will ignore the following pids {0}\n".format(ignorePids))

firstRun = True
reportId = 1
prevIoCounters = psutil.disk_io_counters()
prevNetCounters = psutil.net_io_counters()
while True:
    # Check CPU usage
    if options.cpu:
        cpu_usage = psutil.cpu_percent(interval) * psutil.cpu_count(True)
        if cpu_usage > 1.0:
            log ("HIGH CPU usage: {cpu_usage}%".format(cpu_usage=cpu_usage))
    else:
        time.sleep(interval)

    # Check the cpu usage per process
    pids = psutil.pids()
    for pid in pids:
            p = Process(pid, reportId)
            if p.reportId == 0:
                continue
            gen_report(p, firstRun, reportId)
            processes[p.pid] = p

    # Check for died processes
    toDel=[]
    for pid in processes:
        if processes[pid].reportId != reportId:
            log ("Process {pid} ({comm}) died".format(pid=pid, comm=processes[pid].comm))
            toDel.append(pid)

    # Delete the old pids
    for pid in toDel:
        processes.pop(pid, None)

    # Check the IOs
    if options.disk:
        io_counters = psutil.disk_io_counters()
        if io_counters.read_count > prevIoCounters.read_count:
            log ("Increased disk read count: +{count} ({volume} B)".format(count=io_counters.read_count - prevIoCounters.read_count,
                                                                        volume=io_counters.read_bytes - prevIoCounters.read_bytes))
        if io_counters.write_count > prevIoCounters.write_count:
            log ("Increased disk write count: +{count} ({volume} B)".format(count=io_counters.write_count - prevIoCounters.write_count,
                                                                        volume=io_counters.write_bytes - prevIoCounters.write_bytes))
        prevIoCounters = io_counters

    # Check the network
    if options.network:
        netCounters = psutil.net_io_counters()
        if netCounters.packets_recv > prevNetCounters.packets_recv:
            log ("Incoming packets: {count} ({volume} B)".format(count=netCounters.packets_recv - prevNetCounters.packets_recv,
                                                                volume=netCounters.bytes_recv - prevNetCounters.bytes_recv))
        if netCounters.packets_sent > prevNetCounters.packets_sent:
            log ("Outgoing packets : {count} ({volume} B)".format(count=netCounters.packets_sent - prevNetCounters.packets_sent,
                                                                volume=netCounters.bytes_sent - prevNetCounters.bytes_sent))
        prevNetCounters = netCounters

    firstRun = False
    reportId = reportId + 1
