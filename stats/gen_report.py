#!/usr/bin/python3

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from numpy import *
import subprocess
import argparse
import glob
import csv
import sys
import os

# constants
html_name="index.html"
report_folder="ezbench_report/"

class Benchmark:
    def __init__(self, full_name):
        self.full_name = full_name
        self.prevValue = -1

class BenchResult:
    def __init__(self, commit, benchmark, data_raw_file, img_src_name, sparkline_img):
        self.commit = commit
        self.benchmark = benchmark
        self.data_raw_file = data_raw_file
        self.img_src_name = img_src_name
        self.sparkline_img = sparkline_img
        self.data = []

class Commit:
    def __init__(self, sha1, full_name, compile_log):
        self.sha1 = sha1
        self.full_name = full_name
        self.compile_log = compile_log
        self.results = []

benchmarks = []
commits = []

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("log_folder")
args = parser.parse_args()

# Look for the commit_list file
os.chdir(args.log_folder)

try:
    f = open( "commit_list", "r")
    try:
        commitsLines = f.readlines()
    finally:
        f.close()
except IOError:
    sys.stderr.write("The log folder '{0}' does not contain a commit_list file\n".format(args.log_folder))
    sys.exit(1)

# Check that there are commits
if (len(commitsLines) == 0):
    sys.stderr.write("The commit_list file is empty\n")
    sys.exit(2)

# Gather all the information from the commits and generate the images
print ("Reading the results for {0} commits".format(len(commitsLines)))
commits_txt = ""
table_entries_txt = ""
for commitLine in commitsLines:
    full_name = commitLine.strip(' \t\n\r')
    sha1 = commitLine.split()[0]
    compile_log = sha1 + "_compile_log"
    commit = Commit(sha1, full_name, compile_log)

    # find all the benchmarks
    benchFiles = glob.glob("{sha1}_bench_*".format(sha1=commit.sha1));
    benchs_txt = ""
    for benchFile in benchFiles:
        # Get the bench name
        bench_name = benchFile.replace("{sha1}_bench_".format(sha1=commit.sha1), "")

        # Find the right Benchmark or create one if none are found
        try:
            benchmark = next(b for b in benchmarks if b.full_name == bench_name)
        except StopIteration:
            benchmark = Benchmark(bench_name)
            benchmarks.append(benchmark)

        # Create the result object
        result = BenchResult(commit, benchmark, benchFile,
                             report_folder + benchFile + ".svg",
                             report_folder + benchFile + ".spark.svg")

        # Read the data
        with open(benchFile, 'rt') as f:
            if (csv.Sniffer().has_header(f.read(1024))):
                f.seek(0)
                next(f)
            else:
                f.seek(0)
            reader = csv.reader(f)
            try:
                for row in reader:
                    result.data.append(float(row[0]))
            except csv.Error as e:
                sys.stderr.write('file %s, line %d: %s' % (benchFile, reader.line_num, e))
                sys.exit(3)

        # Add the result to the commit's results
        commit.results.append(result)

    # Add the commit to the list of commits
    commit.results = sorted(commit.results, key=lambda res: res.benchmark.full_name)
    commits.append(commit)

# Sort the list of benchmarks
benchmarks = sorted(benchmarks, key=lambda bench: bench.full_name)

# Create a folder for the results
if not os.path.isdir(report_folder):
    try:
        os.mkdir(report_folder)
    except OSError:
        print ("Error while creating the report folder")

def getResultsBenchmarkDiffs(benchmark):
    prevValue = -1
    results = []

    # Compute a report per application
    i = 0
    for commit in commits:
        for result in commit.results:
            if result.benchmark != benchmark:
                continue

            value = array(result.data).mean()

            if prevValue >= 0:
                diff = (value * 100.0 / prevValue) - 100.0
            else:
                diff = 0
            prevValue = value

            results.append([i, diff])
        i = i + 1

    return results

# Generate the trend graph
print("Generating the trend graph")
f = plt.figure(figsize=(17,3))
plt.xlabel('Commit #')
plt.ylabel('Perf. diff. with the prev. commit (%)')
plt.grid(True)
for i in range(len(benchmarks)):
    data = getResultsBenchmarkDiffs(benchmarks[i])

    x_val = [x[0] for x in data]
    y_val = [x[1] for x in data]

    plt.plot(x_val, y_val, label=benchmarks[i].full_name)

#plt.xticks(range(len(x)), x_val, rotation='vertical')
plt.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
           ncol=3, mode="expand", borderaxespad=0.)
plt.savefig(report_folder + 'overview.svg', bbox_inches='tight')
plt.close()

def kde_scipy(x, x_grid, bandwidth=0.2, **kwargs):
    kde = gaussian_kde(x, bw_method=bandwidth, **kwargs)
    return kde.evaluate(x_grid)

# Generate the spark lines
print("Generating the sparklines",end="",flush=True)
for commit in commits:
    for result in commit.results:
        fig, ax = plt.subplots(1,1,figsize=(1.25,.3))
        plt.ylim(0, amax(result.data))
        plt.plot(result.data, linewidth=0.8)

        # remove all the axes
        plt.axis('off')
        for k,v in ax.spines.items():
            v.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])

        plt.savefig(result.sparkline_img, bbox_inches='tight', transparent=True)
        plt.close()
        print('.',end="",flush=True)
print(" DONE")


# Generate the large images
print("Generating the runs' output image",end="",flush=True)
for commit in commits:
    for result in commit.results:
        f = plt.figure(figsize=(19.5, 2))
        gs = gridspec.GridSpec(1, 2, width_ratios=[4, 1])
        x = array(result.data)
        ax1 = plt.subplot(gs[0])
        plt.title("Time series across all the runs")
        plt.xlabel('Run #')
        plt.ylabel('FPS')
        ax1.plot(x)

        ax2 = plt.subplot(gs[1])
        plt.title("FPS distribution")
        plt.xlabel('FPS')
        x_grid = linspace(amin(x) * 0.95, amax(x) * 1.05, 1000)
        for bandwidth in [0.2]:
            ax2.plot(x_grid, kde_scipy(x, x_grid, bandwidth=bandwidth),
                    label='bw={0}'.format(bandwidth), linewidth=1, alpha=1)
        ax2.hist(x, 100, fc='gray', histtype='stepfilled', alpha=0.3, normed=True, label='histogram')

        plt.tight_layout()
        plt.savefig(result.img_src_name, bbox_inches='tight')
        plt.close()
        print('.',end="",flush=True)
print(" DONE")

# Generate the report
html_template="""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml">

    <head>
        <title>Performace report on the run named '{run_name}'</title>
    </head>

    <body>
        <h1>Performace report on the run named '{run_name}'</h1>

        <h2>Trends</h2>

        <center><img src="{report_folder}/overview.svg" alt="Trends"/></center>

        <h2>Stats</h2>

        <table border="1" style="">
            <tr>
                <th>Commit SHA1</th>
                <th>Geometric mean</th>
                {tbl_hdr_benchmarks}
            </tr>
            {tbl_entries}
        </table>

        <h2>Commits</h2>
            {commits}
    </body>

</html>
"""

table_commit_template="""
            <tr>
                <td><a href="#commit_{sha1}">{sha1}</a></td>
                <td>{geom_mean}</td>
                {tbl_res_benchmarks}
            </tr>
"""

table_entry_template="""
<td bgcolor="{color}">
    <a href="#commit_{sha1}_bench_{bench_name}">
        {value:.2f} ({diff:.2f} %)
        <img src="{sparkline_img}" alt="Test's time series and density of probability" />
    <a/>
</td>"""

commit_template="""
    <h3 id="commit_{sha1}">{commit}</h3>
    Here is the <a href="{compile_log}">compilation logs</a> and list of benchmarks found for commit {sha1}:
    {benchs}"""

bench_template="""
    <h4 id="commit_{sha1}_bench_{bench_name}">{bench_name}</h4>

    <p><a href="{raw_data_file}">Original data</a></p>

    <img src="{img_src}" alt="Test's time series and density of probability" />"""

# For all commits
print("Generating the HTML")
commits_txt = ""
tbl_entries_txt = ""
for commit in commits:
    benchs_txt = ""
    tbl_res_benchmarks = ""
    for result in commit.results:
        value = array(result.data).mean()

        if result.benchmark.prevValue > 0:
            diff = (value * 100.0 / result.benchmark.prevValue) - 100.0
        else:
            diff = 0
        result.benchmark.prevValue = value

        if diff < -1.5:
            color = "#FF0000"
        elif diff > 1.5:
            color = "#00FF00"
        else:
            color = "#FFFFFF"

        # Generate the html
        benchs_txt += bench_template.format(sha1=commit.sha1,
                                            bench_name=result.benchmark.full_name,
                                            img_src=result.img_src_name,
                                            raw_data_file=result.data_raw_file)


        tbl_res_benchmarks += table_entry_template.format(sha1=commit.sha1,
                                                          bench_name=result.benchmark.full_name,
                                                          sparkline_img=result.sparkline_img,
                                                          value=value,
                                                          diff=diff,
                                                          color=color)

    # generate the html
    tbl_entries_txt += table_commit_template.format(sha1=commit.sha1, geom_mean=0,
                                                   tbl_res_benchmarks=tbl_res_benchmarks)
    commits_txt += commit_template.format(commit=commit.full_name,
                                          sha1=commit.sha1,
                                          benchs=benchs_txt,
                                          compile_log=commit.compile_log)

# generate the table's header
tbl_hdr_benchmarks = ""
for benchmark in benchmarks:
    tbl_hdr_benchmarks += "<th>{benchmark}</th>\n".format(benchmark=benchmark.full_name)

# Generate the final html file
html = html_template.format(run_name=args.log_folder,
                            commits=commits_txt,
                            tbl_entries=tbl_entries_txt,
                            tbl_hdr_benchmarks=tbl_hdr_benchmarks,
                            report_folder=report_folder);

with open(html_name, 'w') as f:
    f.write(html)
    print("Output HTML generated at: {0}/{1}".format(os.getcwd(), html_name))
