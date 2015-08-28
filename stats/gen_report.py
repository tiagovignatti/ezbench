#!/usr/bin/env python3

from matplotlib.patches import Rectangle
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import argparse
import sys
import os

# Import ezbench from the utils/ folder
sys.path.append(os.path.abspath(sys.path[0]+'/../utils/'))
from ezbench import *

# constants
html_name="index.html"
report_folder="ezbench_report/"

def genFileNameReportImg(report_folder, data_raw_file):
    return report_folder + data_raw_file + ".svg"

def genFileNameSparkline(report_folder, data_raw_file):
    return report_folder + data_raw_file + ".spark.svg"

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("--frametime", help="Use frame times instead of FPS",
                    action="store_true")
parser.add_argument("log_folder")
args = parser.parse_args()

# Parse the report
report = genPerformanceReport(args.log_folder, args.frametime)

# Generate the labels for the commits
commitsLabels = []
for commit in report.commits:
    commitsLabels.append(commit.label)

# Create a folder for the results
os.chdir(args.log_folder)
if not os.path.isdir(report_folder):
    try:
        os.mkdir(report_folder)
    except OSError:
        print ("Error while creating the report folder")

# Generate the trend graph
print("Generating the trend graph")
f = plt.figure(figsize=(17,3))
plt.xlabel('Commits')
plt.ylabel('Perf. diff. with the first commit (%)')
plt.grid(True)

data = getResultsGeomDiffs(report.commits)
x_val = [x[0] for x in data]
y_val = [x[1] for x in data]
plt.plot(x_val, y_val, label="Geometric mean")

for i in range(len(report.benchmarks)):
    data = getResultsBenchmarkDiffs(report.commits, report.benchmarks[i])

    x_val = [x[0] for x in data]
    y_val = [x[1] for x in data]

    plt.plot(x_val, y_val, label=report.benchmarks[i].full_name)

plt.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
           ncol=4, mode="expand", borderaxespad=0.)
plt.xticks(range(len(commitsLabels)), commitsLabels, size='small', rotation=70)
plt.savefig(report_folder + 'overview.svg', bbox_inches='tight')
plt.close()

def kde_scipy(x, x_grid, bandwidth=0.2, **kwargs):
    kde = gaussian_kde(x, bw_method=bandwidth, **kwargs)
    return kde.evaluate(x_grid)

# Generate the spark lines
print("Generating the sparklines",end="",flush=True)
for commit in report.commits:
    for result in commit.results:
        fig, ax = plt.subplots(1,1,figsize=(1.25,.3))
        r_max = amax(result.data)
        if r_max > 0:
            plt.ylim(0, r_max)
        plt.plot(result.data, linewidth=0.8)

        # remove all the axes
        plt.axis('off')
        for k,v in ax.spines.items():
            v.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])

        plt.savefig(genFileNameSparkline(report_folder, result.data_raw_file),
                    bbox_inches='tight', transparent=True)
        plt.close()
        print('.',end="",flush=True)
print(" DONE")


# Generate the large images
plt.rcParams.update({'font.size': 9})
print("Generating the runs' output image",end="",flush=True)
for c in range (0, len(report.commits)):
    commit = report.commits[c]
    for r in range (0, len(commit.results)):
        result = commit.results[r]
        img_src_name = genFileNameReportImg(report_folder, result.data_raw_file)
        try:
            f = plt.figure(figsize=(19.5, 4))
            gs = gridspec.GridSpec(2, 2, width_ratios=[4, 1])
            x = array(result.data)
            ax1 = plt.subplot(gs[0])
            plt.title("Time series across all the runs")
            plt.xlabel('Run #')
            if args.frametime:
                plt.ylabel('Frametime (ms)')
            else:
                plt.ylabel('FPS')

            YAvg = mean(x)
            boxYMin = YAvg * 0.99
            boxYMax = YAvg * 1.01
            ax1.plot(x, label="cureport.")
            ax1.add_patch(Rectangle((0, boxYMin), len(x), boxYMax - boxYMin, alpha=.2, facecolor="green", label="2% box"))
            if c > 0:
                ax1.plot(report.commits[c - 1].results[r].data, label="prev.")
            plt.legend()

            ax2 = plt.subplot(gs[1])
            if args.frametime:
                plt.title("Frametime distribution (ms)")
                plt.ylabel('Frametime (ms)')
            else:
                plt.title("FPS distribution")
                plt.ylabel('FPS')
            x_grid = linspace(amin(x) * 0.95, amax(x) * 1.05, 1000)
            for bandwidth in [0.2]:
                ax2.plot(x_grid, kde_scipy(x, x_grid, bandwidth=bandwidth),
                        label='bw={0}'.format(bandwidth), linewidth=1, alpha=1)
            ax2.hist(x, 100, fc='gray', histtype='stepfilled', alpha=0.3, normed=True, label='histogram')

            ax3 = plt.subplot(gs[2])
            plt.title("Time series of the runs")
            if args.frametime:
                plt.xlabel('Frametime sample')
                plt.ylabel('Frametime (ms)')
            else:
                plt.xlabel('FPS sample')
                plt.ylabel('FPS')

            for i in range(0, len(result.runs)):
                ax3.plot(result.runs[i], label="{0}".format(i))
                if len(result.runs) <= 40:
                    plt.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=3, ncol=20, mode="expand", borderaxespad=0.)

            plt.tight_layout()
            plt.savefig(img_src_name, bbox_inches='tight')
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("Failed to generate {filename}: {error} at {fname}:{line}".format(filename=img_src_name,
                                                                                    error=str(e), fname=fname,
                                                                                    line=exc_tb.tb_lineno))
        plt.close()
        print('.',end="",flush=True)
print(" DONE")

# Generate the report
html_template="""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml">

    <head>
        <title>Performance report on the run named '{run_name}'</title>
        <style>
            body {{ font-size: 10pt}}
        </style>
    </head>

    <body>
        <h1>Performance report on the run named '{run_name}'</h1>

        <h2>Trends</h2>

        <center><img src="{report_folder}/overview.svg" alt="Trends"/></center>

        <h2>Stats</h2>

        <table border="1" style="">
            <tr>
                <th>Commit #</th>
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
                <td>{commitNum}</td>
                <td><a href="#commit_{sha1}">{sha1}</a></td>
                <td bgcolor="{geom_color}">{geom_mean:.2f} ({geom_diff:+.2f} %)</td>
                {tbl_res_benchmarks}
            </tr>
"""

table_entry_template="""
<td bgcolor="{color}">
    <a href="#commit_{sha1}_bench_{bench_name}">
        {value:.2f} ({diff:+.2f} %)
        <img src="{sparkline_img}" alt="Test's time series and density of probability" />
    <a/>
</td>"""

table_entry_no_results_template="""<td bgcolor="#FFFF00"><center>NO DATA</center>"""

commit_template="""
    <h3 id="commit_{sha1}">{commit}</h3>
    <p><a href="{patch}">Patch</a> <a href="{compile_log}">Compilation logs</a></p>
    <table border="1" style="">
        <tr>
            <th>Commit #</th>
            <th>Commit SHA1</th>
            <th>Geometric mean</th>
            {tbl_hdr_benchmarks}
        </tr>
        {commit_results}
    </table>
    {benchs}"""

bench_template="""
    <h4 id="commit_{sha1}_bench_{bench_name}">{bench_name} (commit <a href="#commit_{sha1}">{commit}</a>)</h4>

    <p><a href="{raw_data_file}">Original data</a></p>

    <img src="{img_src}" alt="Test's time series and density of probability" />"""

def computeDiffAndColor(prev, new):
    if prev > 0:
        if args.frametime:
            diff = (prev * 100.0 / new) - 100.0
        else:
            diff = (new * 100.0 / prev) - 100.0
    else:
        diff = 0

    if diff < -1.5 or diff == float('inf'):
        color = "#FF0000"
    elif diff > 1.5:
        color = "#00FF00"
    else:
        color = "#FFFFFF"

    return diff, color


# Create the html file
print("Generating the HTML")

# generate the table's header
tbl_hdr_benchmarks = ""
for benchmark in report.benchmarks:
    tbl_hdr_benchmarks += "<th>{benchmark}</th>\n".format(benchmark=benchmark.full_name)

# generate the reports for each commits
commits_txt = ""
tbl_entries_txt = ""
geom_prev = -1
i = 0
for commit in report.commits:
    benchs_txt = ""
    tbl_res_benchmarks = ""
    for benchmark in report.benchmarks:
        result = None
        for res in commit.results:
            if res.benchmark == benchmark:
                result = res
                break

        if result != None:
            value = array(result.data).mean()
            diff, color = computeDiffAndColor(result.benchmark.prevValue, value)
            result.benchmark.prevValue = value

            img_src_name = genFileNameReportImg(report_folder, result.data_raw_file)
            sparkline_img = genFileNameSparkline(report_folder, result.data_raw_file)

            # Generate the html
            benchs_txt += bench_template.format(sha1=commit.sha1,
                                                commit=commit.full_name,
                                                bench_name=result.benchmark.full_name,
                                                img_src=img_src_name,
                                                raw_data_file=result.data_raw_file)

            tbl_res_benchmarks += table_entry_template.format(sha1=commit.sha1,
                                                            bench_name=result.benchmark.full_name,
                                                            sparkline_img=sparkline_img,
                                                            value=value,
                                                            diff=diff,
                                                            color=color)
        else:
            tbl_res_benchmarks += table_entry_no_results_template

    # generate the html
    diff, color = computeDiffAndColor(geom_prev, commit.geom_mean())
    geom_prev = commit.geom_mean()
    commit_results = table_commit_template.format(commitNum=i, sha1=commit.sha1,
                                                  geom_mean=commit.geom_mean(),
                                                  geom_diff=diff, geom_color=color,
                                                  tbl_res_benchmarks=tbl_res_benchmarks)
    tbl_entries_txt += commit_results
    commits_txt += commit_template.format(commit=commit.full_name,
                                          sha1=commit.sha1,
                                          benchs=benchs_txt,
                                          compile_log=commit.compile_log,
                                          tbl_hdr_benchmarks=tbl_hdr_benchmarks,
                                          commit_results=commit_results,
                                          patch=commit.patch)
    i += 1

# Generate the final html file
html = html_template.format(run_name=args.log_folder,
                            commits=commits_txt,
                            tbl_entries=tbl_entries_txt,
                            tbl_hdr_benchmarks=tbl_hdr_benchmarks,
                            report_folder=report_folder);

with open(html_name, 'w') as f:
    f.write(html)
    print("Output HTML generated at: {0}/{1}".format(os.getcwd(), html_name))
