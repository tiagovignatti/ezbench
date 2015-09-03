#!/usr/bin/env python3

from ezbench import *
import subprocess
import argparse
import sys
import os

# Start by checking what the user wants to monitor!
parser = argparse.ArgumentParser()
parser.add_argument("--path", "-p", help="Repository path")
parser.add_argument("log_folder")
args = parser.parse_args()

if len(args.path) == 0:
    print ("You need to specify a path to the git repo using -p.")
    exit(1)

labels_path = os.path.abspath(args.log_folder + "/commit_labels")
if os.path.exists(labels_path):
    shouldAbort = input("The commit labels file '{}' already exists and will be deleted.\nAbort? (y/N)".format(labels_path)).lower() == 'y'
    if shouldAbort:
        exit(0)
    print()
f = open(labels_path, 'w')

report = genPerformanceReport(args.log_folder, False)

# Move to the repo's list
os.chdir(args.path)

for commit in report.commits:
    gitCommandLine = ["/usr/bin/git", "show", "--format=%ci", "--date=local", "-s", commit.sha1]
    date = subprocess.check_output(gitCommandLine).decode().split(' ')[0]
    val = "{commit_sha1} {label}\n".format(commit_sha1=commit.sha1, label=date)
    f.write(val)
    print(val, end="")
print("Output written to '{}'".format(labels_path))