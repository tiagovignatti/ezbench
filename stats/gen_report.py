#!/usr/bin/env python3

from matplotlib.patches import Rectangle
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from mako.template import Template
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

data = getResultsGeomDiffs(report.commits, args.frametime)
x_val = [x[0] for x in data]
y_val = [x[1] for x in data]
plt.plot(x_val, y_val, label="Geometric mean")

for i in range(len(report.benchmarks)):
    data = getResultsBenchmarkDiffs(report.commits, report.benchmarks[i], args.frametime)

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
        <title>Performance report on the run named '${run_name}'</title>
        <style>
            body {{ font-size: 10pt}}
        </style>
    </head>

    <%def name="makeTableheader(benchmarks)">
        <tr>
            <th>Commit</th>
            <th>Geometric mean</th>
            % for benchmark in benchmarks:
                <th>${benchmark.full_name}</th>
            % endfor
        </tr>
    </%def>

    <%def name="makeCommitRow(commit, benchmarks)">
        <tr>
            <td><a href="#commit_${commit.sha1}">${commit.label}</a></td>
            <td bgcolor="${commit.geom_color}">${commit.geom} (${commit.geom_diff} %)</td>
            % for benchmark in benchmarks:
            <%
                    result = None
                    for res in commit.results:
                        if res.benchmark == benchmark:
                            result = res
                            sparkline_img = report_folder + result.data_raw_file + ".spark.svg"
                            break
            %>
                % if result.value != None:
                    <td bgcolor="${result.color}">
                        <a href="#commit_${commit.sha1}_bench_${benchmark.full_name}">
                            ${result.value} (${result.diff} %)
                            <img src="${sparkline_img}" alt="Test's time series and density of probability" />
                        <a/>
                    </td>
                % else:
                    <td bgcolor="#FFFF00"><center>NO DATA</center></td>
                % endif
            % endfor
        </tr>
    </%def>

    <body>
        <h1>Performance report on the run named '${run_name}'</h1>

        <h2>Trends</h2>

        <center><img src="${report_folder}/overview.svg" alt="Trends"/></center>

        % if len(notes) > 0:
        <h2>Notes</h2>
            <ul>
            % for note in notes:
                <li>${note}</li>
            % endfor
            </ul>
        % endif

        <h2>Stats</h2>

        <table border="1" style="">
            ${makeTableheader(benchmarks)}
            % for commit in commits:
                ${makeCommitRow(commit, benchmarks)}
            % endfor
        </table>

        <h2>Commits</h2>
        % for commit in commits:
            <h3 id="commit_${commit.sha1}">${commit.label} - ${commit.full_name}</h3>
            <p><a href="${commit.patch}">Patch</a> <a href="${commit.compile_log}">Compilation logs</a></p>
            <table border="1" style="">
                ${makeTableheader(benchmarks)}
                ${makeCommitRow(commit, benchmarks)}
            </table>

            % for benchmark in benchmarks:
            <%
                    result = None
                    for res in commit.results:
                        if res.benchmark == benchmark:
                            result = res
                            sparkline_img = report_folder + result.data_raw_file + ".spark.svg"
                            break
            %>
                % if result.value != None:
                    <h4 id="commit_${commit.sha1}_bench_${benchmark.full_name}}">${benchmark.full_name} (commit <a href="#commit_${commit.sha1}">${commit.full_name}</a>)</h4>

                    <p><a href="${result.data_raw_file}">Original data</a></p>

                    <img src="${result.img_src_name}" alt="Test's time series and density of probability" />
                % endif
            % endfor
        % endfor
    </body>

</html>
"""

def computeDiffAndColor(prev, new):
    if prev > 0:
        if args.frametime:
            diff = (prev * 100.0 / new) - 100.0
        else:
            diff = (new * 100.0 / prev) - 100.0
    else:
        diff = 0

    diff = float("{0:.2f}".format(diff))

    if diff < -1.5 or diff == float('inf'):
        color = "#FF0000"
    elif diff > 1.5:
        color = "#00FF00"
    else:
        color = "#FFFFFF"

    return diff, color


# Create the html file
print("Generating the HTML")

geom_prev = -1
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
            result.value = float("{0:.2f}".format(array(result.data).mean()))
            result.diff, result.color = computeDiffAndColor(result.benchmark.prevValue,
                                                            result.value)
            result.benchmark.prevValue = result.value

            result.img_src_name = genFileNameReportImg(report_folder, result.data_raw_file)
            result.sparkline_img = genFileNameSparkline(report_folder, result.data_raw_file)

    commit.geom = float("{0:.2f}".format(commit.geom_mean()))
    commit.geom_diff, commit.geom_color = computeDiffAndColor(geom_prev, commit.geom)
    geom_prev = commit.geom

html = Template(html_template).render(run_name=args.log_folder,
                                      report_folder=report_folder,
                                      benchmarks=report.benchmarks,
                                      commits=report.commits,
                                      notes=report.notes)

with open(html_name, 'w') as f:
    f.write(html)
    print("Output HTML generated at: {0}/{1}".format(os.getcwd(), html_name))
