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

from mako.template import Template
import pprint
import collections
import argparse
import sys
import os

# Import ezbench from the utils/ folder
sys.path.append(os.path.abspath(sys.path[0]+'/../utils/'))
from ezbench import *

# constants
html_name="index.html"

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("--title", help="Set the title for the report")
parser.add_argument("--unit", help="Set the output unit (Default: ms)")
parser.add_argument("--output", help="Report html file path", required=True)
parser.add_argument("log_folder", nargs='+')
args = parser.parse_args()

# select the right unit
if args.unit is not None:
	output_unit = args.unit
else:
	output_unit = "ms"

# Parse the results and then create one report with the following structure:
# commit -> report_name -> benchmark -> bench results
db = dict()
db["commits"] = collections.OrderedDict()
db["reports"] = args.log_folder
db["benchmarks"] = list()
for log_folder in args.log_folder:
	print("{f}: ".format(f=log_folder), end="")
	report = genPerformanceReport(log_folder)

	# add all the commits
	for commit in report.commits:
		if not commit.sha1 in db["commits"]:
			db["commits"][commit.sha1] = dict()
		db["commits"][commit.sha1][log_folder] = dict()

		# Add the results and compute the average performance
		score_sum = 0
		count = 0
		for result in commit.results:
			if not result.benchmark.full_name in db["benchmarks"]:
				db["benchmarks"].append(result.benchmark.full_name)
			db["commits"][commit.sha1][log_folder][result.benchmark.full_name] = result
			orig_avr_runs = sum(result.data) / float(len(result.data))
			average = convert_unit(orig_avr_runs, result.unit_str, output_unit)
			score_sum += average
			count += 1
			result.average = float("{0:.2f}".format(average))
		db["commits"][commit.sha1][log_folder]["average"] = float("{0:.2f}".format(score_sum / count))
		db["commits"][commit.sha1][log_folder]["average_unit"] = output_unit

# Sort the benchmarks by name to avoid ever-changing layouts
db["benchmarks"] = sort(db["benchmarks"])
pprint.pprint(db)

# Generate the report
html_template="""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml">

    <head>
        <title>${title}</title>
        <meta http-equiv="content-type" content="text/html; charset=utf-8" />
        <style>
            body {{ font-size: 10pt}}
        </style>
        <script type="text/javascript" src="https://www.google.com/jsapi"></script>
        <script type="text/javascript">
            google.load('visualization', '1', {packages: ['corechart']});
            google.setOnLoadCallback(drawTrend);
            google.setOnLoadCallback(drawDetails);

            var currentCommit = "${default_commit}";

            function showColumn(dataTable, chart, activColumns, series, col, show) {
                if (!show) {
                    activColumns[col] = {
                        label: dataTable.getColumnLabel(col),
                        type: dataTable.getColumnType(col),
                        calc: function () {
                            return null;
                        }
                    };
                    series[col - 1].color = '#CCCCCC';
                }
                else {
                    activColumns[col] = col;
                    series[col - 1].color = null;
                }
            }

            function showAllColumns(dataTable, chart, activColumns, series, show) {
                for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
                    showColumn(dataTable, chart, activColumns, series, i, show)
                }
            }

            function drawTrend() {
                var dataTable = new google.visualization.DataTable();
                dataTable.addColumn('string', 'Commit');
                % for report in db["reports"]:
                dataTable.addColumn('number', '${report}');
                % endfor
                //dataTable.addColumn({ type: "string", role: "tooltip", p: { html: true }});
                dataTable.addRows([
                % for commit in db["commits"]:
                    ['${commit}'\\
                        % for report in db["reports"]:
                            % if report in db["commits"][commit]:
, ${db["commits"][commit][report]["average"]}\\
                            % else:
, null\\
                            % endif
                        % endfor
],
                % endfor
                ]);

                var activColumns = [];
                var series = {};
                for (var i = 0; i < dataTable.getNumberOfColumns(); i++) {
                    activColumns.push(i);
                    if (i > 0) {
                        series[i - 1] = {};
                    }
                }

                var options = {
                    chart: {
                        title: 'Performance trend across multiple commits'
                    },
                    legend: { position: 'top', textStyle: {fontSize: 12}, maxLines: 3},
                    focusTarget: 'category',
                    tooltip: {trigger: 'selection', isHtml: true},
                    crosshair: { trigger: 'both' },
                    hAxis: {title: 'Commits', slantedText: true, slantedTextAngle: 45},
                    vAxis: {title: 'Average result (${output_unit})'},
                    series: series,
                    chartArea: {left:"6%", width:"95%"}
                };

                var chart = new google.visualization.LineChart(document.getElementById('trends_chart'));
                chart.draw(dataTable, options);

                google.visualization.events.addListener(chart, 'select', function () {
                    var sel = chart.getSelection();
                    // See https://developers.google.com/chart/interactive/docs/reference#visgetselection
                    if (sel.length > 0 && typeof sel[0].row === 'object') {
                        var col = sel[0].column;

                        var allActive = true;
                        for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
                            if (activColumns[i] != i) {
                                allActive = false;
                            }
                        }
                        if (activColumns[col] == col) {
                            // The clicked columns is active
                            if (allActive) {
                                showAllColumns(dataTable, chart, activColumns, series, false);
                                showColumn(dataTable, chart, activColumns, series, col, true);
                            } else {
                                showColumn(dataTable, chart, activColumns, series, col, false);
                            }
                        }
                        else {
                            // The clicked columns is inactive, show it
                            showColumn(dataTable, chart, activColumns, series, col, true);
                        }

                        var allHidden = true;
                        for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
                            if (activColumns[i] == i) {
                                allHidden = false;
                            }
                        }
                        if (allHidden)
                            showAllColumns(dataTable, chart, activColumns, series, true);

                        // Redraw the chart with the masked columns
                        var view = new google.visualization.DataView(dataTable);
                        view.setColumns(activColumns);
                        chart.draw(view, options);
                    }

                    if (sel.length > 0 && typeof sel[0].row === 'number') {
                        // update the other graph if there were changes
                        var commit = dataTable.getValue(sel[0].row, 0)
                        if (commit != currentCommit) {
                            currentCommit = commit;
                            drawDetails();
                        }
                    }

                    if (sel.length == 0) {
                        chart.setSelection(null);
                    }
                });
            }

           function drawDetails() {
                var dataTable = new google.visualization.DataTable();
                dataTable.addColumn('string', 'Report');
                dataTable.addColumn('number', 'Average');
                dataTable.addColumn({type: 'string', role: 'tooltip', p: { html: true }});
                % for benchmark in db["benchmarks"]:
                dataTable.addColumn('number', '${benchmark}');
                dataTable.addColumn({type: 'string', role: 'tooltip', p: { html: true }});
                % endfor

                % for commit in db["commits"]:
                if (currentCommit == "${commit}") {
                    dataTable.addRows([
                    % for report in db["reports"]:
                        % if report in db["commits"][commit]:
                             ["${report}", ${db["commits"][commit][report]["average"]}, "<h3>${report} - ${benchmark}</h3><p>\\
                             % for r in db["reports"]:
<%
                                     if not r in db["commits"][commit]:
                                         continue
                                     if db["commits"][commit][report]["average"] != 0:
                                         diff = db["commits"][commit][r]["average"] / db["commits"][commit][report]["average"] * 100
                                         diff = float("{0:.2f}".format(diff))
                                     else:
                                        diff = "ERR"
                                     btag = btagend = ""
                                     if r == report:
                                         btag="<b>"
                                         btagend="</b>"
                                 %>\\
${btag}${r}: ${db["commits"][commit][r]["average"]} ${output_unit} (${diff}%)${btagend}<br/>\\
                            % endfor
</p>"\\
                            % for benchmark in db["benchmarks"]:
                                % if benchmark in db["commits"][commit][report]:
, ${db["commits"][commit][report][benchmark].average}, "<h3>${report} - ${benchmark}</h3><p>\\
                                    % for r in db["reports"]:
<%
                                            if not r in db["commits"][commit] or benchmark not in db["commits"][commit][r]:
                                                continue
                                            if db["commits"][commit][report][benchmark].average != 0:
                                                diff = db["commits"][commit][r][benchmark].average / db["commits"][commit][report][benchmark].average * 100
                                                diff = float("{0:.2f}".format(diff))
                                            else:
                                                diff = "ERR"
                                            btag = btagend = ""
                                            if r == report:
                                                btag="<b>"
                                                btagend="</b>"
                                        %>\\
${btag}${r}: ${db["commits"][commit][r][benchmark].average} ${output_unit} (${diff}%)${btagend}<br/>\\
                                    % endfor
</p>"\\
                           % else:
, null, "${benchmark}"\\
                           % endif
                        % endfor
],
                        % endif
                    % endfor
                    ]);
                }
                % endfor

                // count the number of active rows and columns
                var entries = dataTable.getNumberOfColumns() * dataTable.getNumberOfRows();
                var size = (entries * 10);
                if (size < 300)
                    size = 300;
                details_chart.style.height = size + "px";
                details_chart.style.width = "100%";

                var options = {
                    title : 'Performance of commit ' + currentCommit,
                    tooltip: {trigger: 'focus', isHtml: true},
                    vAxis: {title: 'Reports'},
                    hAxis: {title: 'Average result (${output_unit})'},
                    seriesType: 'bars',
                    orientation: 'vertical',
                    series: {0: {type: 'line'}}
                };

                var chart = new google.visualization.ComboChart(document.getElementById('details_chart'));
                chart.draw(dataTable, options);
            }
        </script>
    </head>

    <body>
        <h1>${title}</h1>

        <h2>Trends</h2>

        <center><div id="trends_chart" style="width: 100%; height: 500px;"></div></center>

        <h2>Details</h2>

        <!-- TODO: Height should be dependent on the number of results -->
        <center><div id="details_chart" style="width: 100%; height: 500px;"></div></center>

    </body>

</html>
"""


# Create the html file
print("Generating the HTML")

if args.title is not None:
    title = args.title
else:
    title = "Performance report on the run named '{run_name}'".format(run_name=args.log_folder)

html = Template(html_template).render(title=title, db=db, output_unit=output_unit,
				      default_commit=list(db["commits"])[-1])

with open(args.output, 'w') as f:
    f.write(html)
    print("Output HTML generated at: {0}".format(args.output))
