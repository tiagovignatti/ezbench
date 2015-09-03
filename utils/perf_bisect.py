#!/usr/bin/env python3

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
def check_commit_perf(ezbench_base_cmd, commit, logs_dir):
    cmd = list(ezbench_base_cmd)
    cmd.append(commit)

    # Call ezbench
    try:
        check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print("\n\nERROR: The following command '{}' failed with the error code {}. Here is its output:\n\n'{}'".format(" ".join(cmd), e.returncode, e.output.decode()))
        sys.exit(1)

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

# Create the command line for ezbench
ezbench_cmd = []
ezbench_cmd.append(ezbench_dir + "ezbench.sh")
ezbench_cmd.append("-p"); ezbench_cmd.append(args.repo_path)
ezbench_cmd.append("-b"); ezbench_cmd.append(args.benchmark + '$')
ezbench_cmd.append("-r"); ezbench_cmd.append(str(args.rounds))
if args.make_cmd is not None:
    ezbench_cmd.append("-m"); ezbench_cmd.append(args.make_cmd)
ezbench_cmd.append("-N"); ezbench_cmd.append(reportName)

print("Checking the performance of:")

# First, try the before and after commits
print("\tBEFORE_COMMIT: ", end="",flush=True)
before_perf = check_commit_perf(ezbench_cmd, args.BEFORE_COMMIT, logs_dir)
print("Performance index {before_perf}".format(before_perf=before_perf))

print("\tAFTER_COMMIT:  ", end="",flush=True)
after_perf = check_commit_perf(ezbench_cmd, args.AFTER_COMMIT, logs_dir)
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
    perf = check_commit_perf(ezbench_cmd, "HEAD", logs_dir)
    res = checkPerformance(before_perf, after_perf, threshold, perf)
    print("Performance index = {perf} (diffThreshold = {diff}). Marking as {res}\n".format(perf=perf,
                                                                                           diff=perf - threshold,
                                                                                           res=res.upper()))
    output = check_output(['git', 'bisect', res]).decode()
    print(output, end="")

firstBad = output.split(" ")[0]
print ("Change introduced by commit {}".format(firstBad))

check_output(['git', 'bisect', 'reset'], stderr=subprocess.STDOUT)
