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

from array import array
from numpy import *
import subprocess
import glob
import csv
import sys
import os
import re

# Ezbench runs
class Ezbench:
    def __init__(self, ezbench_path, repo_path, make_command = None,
                 report_name = None, tests_folder = None):
        self.ezbench_path = ezbench_path
        self.repo_path = repo_path
        self.make_command = make_command
        self.report_name = report_name
        self.tests_folder = tests_folder

    def __ezbench_cmd_base(self, benchmarks, benchmark_excludes = [], rounds = None):
        ezbench_cmd = []
        ezbench_cmd.append(self.ezbench_path)
        ezbench_cmd.append("-p"); ezbench_cmd.append(self.repo_path)

        for benchmark in benchmarks:
            ezbench_cmd.append("-b"); ezbench_cmd.append(benchmark)

        for benchmark_excl in benchmark_excludes:
            ezbench_cmd.append("-B"); ezbench_cmd.append(benchmark_excl)

        if rounds is not None:
            ezbench_cmd.append("-r"); ezbench_cmd.append(str(rounds))

        if self.make_command is not None:
            ezbench_cmd.append("-m"); ezbench_cmd.append(self.make_command)
        if self.report_name is not None:
            ezbench_cmd.append("-N"); ezbench_cmd.append(self.report_name)
        if self.tests_folder is not None:
            ezbench_cmd.append("-T"); ezbench_cmd.append(self.tests_folder)

        return ezbench_cmd

    def __run_ezbench(self, cmd):
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print("\n\nERROR: The following command '{}' failed with the error code {}. Here is its output:\n\n'{}'".format(" ".join(cmd), e.returncode, e.output.decode()))
            return False
        return True

    def run_commits(self, commits, benchmarks, benchmark_excludes = [], rounds = None):
        ezbench_cmd = self.__ezbench_cmd_base(benchmarks, benchmark_excludes, rounds)

        for commit in commits:
            ezbench_cmd.append(commit)

        return self.__run_ezbench(ezbench_cmd)

    def run_commit_range(self, head, commit_count, benchmarks, benchmark_excludes = [], rounds = None):
        ezbench_cmd = self.__ezbench_cmd_base(benchmarks, benchmark_excludes, rounds)

        ezbench_cmd.append("-H"); ezbench_cmd.append(head)
        ezbench_cmd.append("-n"); ezbench_cmd.append(commit_count)

        return self.__run_ezbench(ezbench_cmd)

# Report parsing
class Benchmark:
    def __init__(self, full_name, unit="undefined"):
        self.full_name = full_name
        self.prevValue = -1
        self.unit_str = unit

class BenchResult:
    def __init__(self, commit, benchmark, data_raw_file, unit_str):
        self.commit = commit
        self.benchmark = benchmark
        self.data_raw_file = data_raw_file
        self.data = []
        self.runs = []
        self.unit_str = unit_str

class Commit:
    def __init__(self, sha1, full_name, compile_log, patch, label):
        self.sha1 = sha1
        self.full_name = full_name
        self.compile_log = compile_log
        self.patch = patch
        self.results = []
        self.geom_mean_cache = -1
        self.label = label

    def geom_mean(self):
        if self.geom_mean_cache >= 0:
            return self.geom_mean_cache

        # compute the variance
        s = 1
        n = 0
        for result in self.results:
            if len(result.data) > 0:
                s *= array(result.data).mean()
                n = n + 1
        if n > 0:
            value = s ** (1 / n)
        else:
            value = 0

        geom_mean_cache = value
        return value

class Report:
    def __init__(self, benchmarks, commits, notes):
        self.benchmarks = benchmarks
        self.commits = commits
        self.notes = notes

def readCsv(filepath, wantFrametime = False):
    data = []

    with open(filepath, 'rt') as f:
        reader = csv.reader(f)
        try:
            hasSniffer = csv.Sniffer().has_header(f.read(1024))
        except:
            hasSniffer = False
            pass

        try:
            if hasSniffer:
                f.seek(0)
                next(f)
            else:
                f.seek(0)
            for row in reader:
                if len(row) > 0 and not row[0].startswith("# "):
                    try:
                        data.append(float(row[0]))
                    except ValueError as e:
                        sys.stderr.write('Error in file %s, line %d: %s\n' % (filepath, reader.line_num, e))
        except csv.Error as e:
            sys.stderr.write('file %s, line %d: %s\n' % (filepath, reader.line_num, e))
            return []

    # Convert to frametime if needed
    if wantFrametime:
        for i in range(0, len(data)):
            data[i] = 1000.0 / data[i]

    return data

def readCommitLabels():
    labels = dict()
    try:
        f = open( "commit_labels", "r")
        try:
            labelLines = f.readlines()
        finally:
            f.close()
    except IOError:
        return labels

    for labelLine in labelLines:
        fields = labelLine.split(" ")
        sha1 = fields[0]
        label = fields[1].split("\n")[0]
        labels[sha1] = label

    return labels

def readNotes():
    try:
        with open("notes", 'rt') as f:
            return f.readlines()
    except:
        return []

def genPerformanceReport(log_folder, wantFrametime = False, silentMode = False):
    benchmarks = []
    commits = []
    labels = dict()

    # Save the current working directory and switch to the log folder
    cwd = os.getcwd()
    os.chdir(log_folder)

    # Look for the commit_list file
    try:
        f = open( "commit_list", "r")
        try:
            commitsLines = f.readlines()
        finally:
            f.close()
    except IOError:
        sys.stderr.write("The log folder '{0}' does not contain a commit_list file\n".format(log_folder))
        return (commits, benchmarks)

    # Read all the commits' labels
    labels = readCommitLabels()

    # Check that there are commits
    if (len(commitsLines) == 0):
        sys.stderr.write("The commit_list file is empty\n")
        sys.exit(2)

    # Gather all the information from the commits and generate the images
    if not silentMode:
        print ("Reading the results for {0} commits".format(len(commitsLines)))
    commits_txt = ""
    table_entries_txt = ""
    for commitLine in commitsLines:
        full_name = commitLine.strip(' \t\n\r')
        sha1 = commitLine.split()[0]
        compile_log = sha1 + "_compile_log"
        patch = sha1 + ".patch"
        label = labels.get(sha1, sha1)
        commit = Commit(sha1, full_name, compile_log, patch, label)

        # find all the benchmarks
        benchFiles = glob.glob("{sha1}_bench_*".format(sha1=commit.sha1));
        benchs_txt = ""
        for benchFile in benchFiles:
            # Skip when the file is a run file (finishes by #XX)
            if re.search(r'#\d+$', benchFile) is not None:
                continue

            # Skip on error files
            if re.search(r'\.(stderr|stdout|errors)$', benchFile) is not None:
                continue

            # Get the bench name
            bench_name = benchFile.replace("{sha1}_bench_".format(sha1=commit.sha1), "")

            # Find the right Benchmark or create one if none are found
            try:
                benchmark = next(b for b in benchmarks if b.full_name == bench_name)
            except StopIteration:
                benchmark = Benchmark(bench_name)
                benchmarks.append(benchmark)

            if wantFrametime:
                unit = "ms"
            else:
                unit = "FPS"

            # Create the result object
            result = BenchResult(commit, benchmark, benchFile, unit)

            # Check that the result file has the same default v
            if benchmark.unit_str != unit:
                if benchmark.unit_str != "undefined":
                    msg = "The unit used by the benchmark '{bench}' changed from '{unit_old}' to '{unit_new}' in commit {commit}"
                    print(msg.format(bench=bench_name,
                                     unit_old=benchmark.unit_str,
                                     unit_new=unit,
                                     commit=commit.sha1))
                benchmark.unit_str = unit

            # Read the data and abort if there is no data
            result.data = readCsv(benchFile, wantFrametime)
            if len(result.data) == 0:
                continue

            # Look for the runs
            runsFiles = glob.glob("^{benchFile}#[0-9]+".format(benchFile=benchFile));
            for runFile in runsFiles:
                data = readCsv(runFile, wantFrametime)
                if len(data) > 0:
                    result.runs.append(data)

            # Add the result to the commit's results
            commit.results.append(result)

        # Add the commit to the list of commits
        commit.results = sorted(commit.results, key=lambda res: res.benchmark.full_name)
        commits.append(commit)

    # Sort the list of benchmarks
    benchmarks = sorted(benchmarks, key=lambda bench: bench.full_name)

    # Read the notes before going back to the original folder
    notes = readNotes()

    # Go back to the original folder
    os.chdir(cwd)

    return Report(benchmarks, commits, notes)

def getPerformanceResultsCommitBenchmark(commit, benchmark, wantFrametime = False):
    for result in commit.results:
        if result.benchmark != benchmark:
            continue

        return array(result.data)

    return array([])

def getResultsBenchmarkDiffs(commits, benchmark, wantFrametime = False):
    results = []

    # Compute a report per application
    i = 0
    origValue = -1
    for commit in commits:
        resultFound = False
        for result in commit.results:
            if result.benchmark != benchmark:
                continue

            value = array(result.data).mean()
            if origValue > -1:
                if wantFrametime:
                    diff = (origValue * 100.0 / value) - 100.0
                else:
                    diff = (value * 100.0 / origValue) - 100.0
            else:
                origValue = value
                diff = 0

            results.append([i, diff])
            resultFound = True

        if not resultFound:
            results.append([i, NaN])
        i = i + 1

    return results

def getResultsGeomDiffs(commits, wantFrametime = False):
    results = []

    # Compute a report per application
    i = 0
    origValue = -1
    for commit in commits:
        value = commit.geom_mean()
        if origValue > -1:
            if wantFrametime:
                diff = (origValue * 100.0 / value) - 100.0
            else:
                diff = (value * 100.0 / origValue) - 100.0
        else:
            origValue = value
            diff = 0

        results.append([i, diff])
        i = i + 1

    return results
