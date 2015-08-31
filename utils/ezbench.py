from array import array
from numpy import *
import glob
import csv
import sys
import os
import re

class Benchmark:
    def __init__(self, full_name):
        self.full_name = full_name
        self.prevValue = -1

class BenchResult:
    def __init__(self, commit, benchmark, data_raw_file):
        self.commit = commit
        self.benchmark = benchmark
        self.data_raw_file = data_raw_file
        self.data = []
        self.runs = []

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
                if len(row) > 0:
                    data.append(float(row[0]))
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
            if re.search(r'.errors$', benchFile) is not None:
                continue

            # Get the bench name
            bench_name = benchFile.replace("{sha1}_bench_".format(sha1=commit.sha1), "")

            # Find the right Benchmark or create one if none are found
            try:
                benchmark = next(b for b in benchmarks if b.full_name == bench_name)
            except StopIteration:
                benchmark = Benchmark(bench_name)
                benchmarks.append(benchmark)

            # Create the result object
            result = BenchResult(commit, benchmark, benchFile)

            # Read the data and abort if there is no data
            result.data = readCsv(benchFile, wantFrametime)
            if len(result.data) == 0:
                continue

            # Look for the runs
            runsFiles = glob.glob("{benchFile}#*".format(benchFile=benchFile));
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

    # Go back to the original folder
    os.chdir(cwd)

    return Report(benchmarks, commits, readNotes())

def getPerformanceResultsCommitBenchmark(commit, benchmark, wantFrametime = False):
    for result in commit.results:
        if result.benchmark != benchmark:
            continue

        return array(result.data)

    return []

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
