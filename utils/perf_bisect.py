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

from subprocess import call,check_output
from numpy import *
import subprocess
import argparse
import shutil
import sys
import os

ezbench_dir = os.path.abspath(sys.path[0]+'/../') + '/'

# Import ezbench from the utils/ folder
sys.path.append(ezbench_dir + 'utils/')
from ezbench import *

# function that tests the performance of one commit
def check_commit_perf(ezbench, commit, benchmark, logs_dir):
    # Run ezbench
    if ezbench.run_commits([commit], [benchmark + '$']) == False:
        return 0.0

    # parse the logs, read the perf of the last entry!
    r = genPerformanceReport(logs_dir, True, True)

    if len(r.benchmarks) != 1:
        print ("Error: Expected one benchmark result for commit {} but got !".format(commit, len(r.benchmarks)))
        sys.exit(1)

    # read the perf report of the last entry!
    return getPerformanceResultsCommitBenchmark(r.commits[-1], r.benchmarks[0], True).mean()

def checkPerformance(beforePerf, afterPerf, threshold, perf):
    if beforePerf > afterPerf:
        if (perf > threshold):
            res = "good"
        else:
            res = "bad"
    else:
        if (perf > threshold):
            res = "bad"
        else:
            res = "good"
    return res

def isEndOfBisect(git_output):
    return "first bad commit" in git_output.split('\n')[0]

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("-p", dest='repo_path', help="Git repository's path",
                    action="store", required=True)
parser.add_argument("-b", dest='benchmark', help="Benchmark to run",
                    action="store", required=True)
parser.add_argument("-r", dest='rounds', help="Number of execution rounds",
                    action="store", type=int, nargs='?', const=3)
parser.add_argument("-m", dest='make_cmd', help="Compilation command",
                    action="store")
parser.add_argument("BEFORE_COMMIT")
parser.add_argument("AFTER_COMMIT")
args = parser.parse_args()

# compute the report name
reportName = "bisect_{benchmark}_{BEFORE_COMMIT}_{AFTER_COMMIT}".format(benchmark=args.benchmark,
                                                                        BEFORE_COMMIT=args.BEFORE_COMMIT,
                                                                        AFTER_COMMIT=args.AFTER_COMMIT)
logs_dir = os.path.abspath(ezbench_dir + '/logs/' + reportName)  + '/'

# Check if the report dir already exists and ask for deletion
if os.path.exists(logs_dir):
    shouldAbort = input("The log directory '{}' already exists and will be deleted.\nAbort? (y/N)".format(logs_dir)).lower() == 'y'
    if shouldAbort:
        exit(0)
    shutil.rmtree(logs_dir, ignore_errors=True)
    print()

ezbench = Ezbench(ezbench_path=ezbench_dir + "ezbench.sh",
                  repo_path=args.repo_path,
                  make_command = args.make_cmd,
                  report_name=reportName)

print("Checking the performance of:")

# First, try the before and after commits
print("\tBEFORE_COMMIT: ", end="",flush=True)
before_perf = check_commit_perf(ezbench, args.BEFORE_COMMIT, args.benchmark, logs_dir)
print("Performance index {before_perf}".format(before_perf=before_perf))

print("\tAFTER_COMMIT:  ", end="",flush=True)
after_perf = check_commit_perf(ezbench, args.AFTER_COMMIT, args.benchmark, logs_dir)
print("Performance index {after_perf}".format(after_perf=after_perf))
print()

# Find the threshold
threshold = (before_perf + after_perf) / 2
overThreshold = checkPerformance(before_perf, after_perf, threshold, threshold + 1).upper()
underThreshold = checkPerformance(before_perf, after_perf, threshold, threshold - 1).upper()

print("Setting the performance threshold to {threshold}.".format(threshold=threshold))
print("\tIf a commit's perf is > {threshold}, then the commit is {res}".format(threshold=threshold,
                                                                               res=overThreshold))
print("\tIf a commit's perf is < {threshold}, then the commit is {res}".format(threshold=threshold,
                                                                               res=underThreshold))
print()

print("Starting the bisecting process.")
print()

# Start the bisecting feature
os.chdir(args.repo_path)
check_output(['git', 'bisect', 'start'], stderr=subprocess.STDOUT)
check_output(['git', 'bisect', 'good', args.BEFORE_COMMIT], stderr=subprocess.STDOUT)
output = check_output(['git', 'bisect', 'bad', args.AFTER_COMMIT], stderr=subprocess.STDOUT).decode()
print(output, end="")

while not isEndOfBisect(output):
    perf = check_commit_perf(ezbench, "HEAD", args.benchmark, logs_dir)
    res = checkPerformance(before_perf, after_perf, threshold, perf)
    print("Performance index = {perf} (diffThreshold = {diff}). Marking as {res}\n".format(perf=perf,
                                                                                           diff=perf - threshold,
                                                                                           res=res.upper()))
    output = check_output(['git', 'bisect', res]).decode()
    print(output, end="")

firstBad = output.split(" ")[0]
print ("Change introduced by commit {}".format(firstBad))

check_output(['git', 'bisect', 'reset'], stderr=subprocess.STDOUT)
