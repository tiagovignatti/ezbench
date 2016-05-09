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
import collections
import sys
import os

# Import ezbench from the utils/ folder
ezbench_dir = os.path.abspath(sys.path[0]+'/../')
sys.path.append(ezbench_dir+'/utils/')
sys.path.append(ezbench_dir+'/utils/env_dump')
from ezbench import *
from env_dump_parser import *

# constants
html_name="index.html"

def reports_to_html(reports, output, output_unit = None, title = None,
			   commit_url = None, verbose = False, reference_report = None):

	# select the right unit
	if output_unit is None:
		output_unit = "FPS"

	# Parse the results and then create one report with the following structure:
	# commit -> report_name -> benchmark -> bench results
	db = dict()
	db["commits"] = collections.OrderedDict()
	db["reports"] = list()
	db["events"] = dict()
	db["benchmarks"] = list()
	db['env_sets'] = dict()
	db["envs"] = dict()
	db["targets"] = dict()
	db["targets_raw"] = dict()
	human_envs = dict()

	# set all the targets
	if reference_report is not None and len(reference_report.commits) > 0:
		db['reference_name'] = "{} ({})".format(reference_report.name, reference_report.commits[-1].sha1)
		db['reference'] = reference_report
		for result in reference_report.commits[-1].results:
			average_raw = result.result()
			average = convert_unit(average_raw, result.unit_str, output_unit)
			average = float("{0:.2f}".format(average))
			average_raw = float("{0:.2f}".format(average_raw))
			if (not result.benchmark.full_name in db["targets"] or
				db["targets"][result.benchmark.full_name] == 0):
					db["targets"][result.benchmark.full_name] = average
					db["targets_raw"][result.benchmark.full_name] = average_raw

	for report in reports:
		db["reports"].append(report.name)

		# drop the no-op benchmark
		report.benchmarks = list(filter(lambda b: b.full_name != "no-op", report.benchmarks))

		# make sure all the benchmarks are listed in db["envs"]
		for benchmark in report.benchmarks:
			db["envs"][benchmark.full_name] = dict()

		db["events"][report.name] = list()
		for event in report.events:
			if type(event) is EventBuildBroken:
				event.commit_range.new.annotation = event.commit_range.new.sha1 + ": build broken"
				event.commit_range.new.annotation_long = str(event)
			elif type(event) is EventBuildFixed:
				event.fixed_commit_range.new.annotation = event.fixed_commit_range.new.sha1 + ": build fixed"
				event.fixed_commit_range.new.annotation_long = str(event)
			elif type(event) is EventPerfChange:
				for result in event.commit_range.new.results:
					if result.benchmark.full_name != event.benchmark.full_name:
						continue
					result.annotation = str(event)
			db["events"][report.name].append(event)

		# add all the commits
		for commit in report.commits:
			# drop the no-op results
			commit.results = list(filter(lambda r: r.benchmark.full_name != "no-op", commit.results))
			if len(commit.results) == 0 and not hasattr(commit, 'annotation'):
				continue

			if not commit.sha1 in db["commits"]:
				db["commits"][commit.sha1] = dict()
				db["commits"][commit.sha1]['reports'] = dict()
				db["commits"][commit.sha1]['commit'] = commit
				if not commit.build_broken():
					db["commits"][commit.sha1]['build_color'] = "#00FF00"
				else:
					db["commits"][commit.sha1]['build_color'] = "#FF0000"
				db["commits"][commit.sha1]['build_error'] = str(EzbenchExitCode(commit.compil_exit_code)).split('.')[1]
			db["commits"][commit.sha1]['reports'][report.name] = dict()

			# Add the results and perform some stats
			score_sum = 0
			count = 0
			for result in commit.results:
				if not result.benchmark.full_name in db["benchmarks"]:
					db["benchmarks"].append(result.benchmark.full_name)
				db["commits"][commit.sha1]['reports'][report.name][result.benchmark.full_name] = result
				average_raw = result.result()
				average = convert_unit(average_raw, result.unit_str, output_unit)
				score_sum += average
				count += 1
				result.average_raw = float("{0:.2f}".format(average_raw))
				result.average = float("{0:.2f}".format(average))
				result.margin_str = float("{0:.2f}".format(result.margin() * 100))

				# Compare to the target
				if (not result.benchmark.full_name in db["targets"] or
				db["targets"][result.benchmark.full_name] == 0):
					db["targets"][result.benchmark.full_name] = result.average
					db["targets_raw"][result.benchmark.full_name] = result.average_raw
				result.diff_target = compute_perf_difference(output_unit,
				                                             db["targets"][result.benchmark.full_name],
				                                             result.average)

				# Environment
				if result.benchmark.full_name not in human_envs:
					for envfile in result.env_files:
						if envfile is not None:
							fullpath = report.log_folder + "/" + envfile
							human_envs[result.benchmark.full_name] = EnvDumpReport(fullpath, True)
				if result.benchmark.full_name not in db['env_sets']:
					db['env_sets'][result.benchmark.full_name] = list()
				for e in range(0, len(result.env_files)):
					# Create the per-run information
					envfile = result.env_files[e]
					if envfile is None:
						continue

					fullpath = report.log_folder + "/" + envfile
					r = EnvDumpReport(fullpath, False).to_set(['^DATE',
					                                           '^ENV.ENV_DUMP_FILE',
					                                           '_PID',
					                                           'SHA1$',
					                                           '.pid$',
					                                           'X\'s pid$',
					                                           'extension count$',
					                                           'window id$'])
					tup = dict()
					tup['log_folder'] = report.name
					tup['commit'] = commit
					tup['run'] = e

					# Compare the set to existing ones
					found = False
					for r_set in db['env_sets'][result.benchmark.full_name]:
						if r  == r_set['set']:
							r_set['users'].append(tup)
							found = True

					# Add the report
					if not found:
						new_entry = dict()
						new_entry['set'] = r
						new_entry['users'] = list()
						new_entry['users'].append(tup)
						db['env_sets'][result.benchmark.full_name].append(new_entry)

			if count > 0:
				avg = score_sum / count
			else:
				avg = 0
			db["commits"][commit.sha1]['reports'][report.name]["average"] = float("{0:.2f}".format(avg))
			db["commits"][commit.sha1]['reports'][report.name]["average_unit"] = output_unit

	# Generate the environment
	for bench in human_envs:
		env = human_envs[bench]
		if env is not None:
			for key in sorted(list(env.values)):
				cur = db['envs'][bench]
				fields = key.split(":")
				for f in range(0, len(fields)):
					field = fields[f].strip()
					if f < len(fields) - 1:
						if field not in cur:
							cur[field] = dict()
						cur = cur[field]
					else:
						cur[field] = env.values[key]

	# Generate the environment diffs
	db['env_diff_keys'] = dict()
	for bench in db['env_sets']:
		final_union = set()
		for report in db['env_sets'][bench]:
			diff = db['env_sets'][bench][0]['set'] ^ report['set']
			final_union = final_union | diff
		db['env_diff_keys'][bench] = sorted(dict(final_union).keys())

	# Sort the benchmarks by name to avoid ever-changing layouts
	db["benchmarks"] = sort(db["benchmarks"])

	# Support creating new URLs
	if commit_url is not None:
		db["commit_url"] = commit_url

	# Generate the report
	html_template="""
	<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

	<%! import cgi %>
	<%! from ezbench import compute_perf_difference %>

	<html xmlns="http://www.w3.org/1999/xhtml">
		<head>
			<title>${title}</title>
			<meta http-equiv="content-type" content="text/html; charset=utf-8" />
			<style>
				body { font-size: 10pt; }
				table { font-size: 10pt; }

				/* http://martinivanov.net/2011/09/26/css3-treevew-no-javascript/ */
				.css-treeview input + label + ul
				{
					display: none;
				}
				.css-treeview input:checked + label + ul
				{
					display: block;
				}
				.css-treeview input
				{
					position: absolute;
					opacity: 0;
				}
				.css-treeview label,
				.css-treeview label::before
				{
					cursor: pointer;
				}
				.css-treeview input:disabled + label
				{
					cursor: default;
					opacity: .6;
				}
				table{
					border-collapse:collapse;
				}
				table td{
					padding:5px; border:#4e95f4 1px solid;
				}
				table tr:nth-child(odd){
					background: #b8d1f3;
				}
				table tr:nth-child(even){
					background: #dae5f4;
				}

				.env_node:hover {
					cursor: pointer;
					text-decoration: underline;
				}

				.close_button {
					color: black;
					background-color: grey;
					cursor:pointer;
				}
				.close_button:hover {
					text-decoration:underline;
				}
			</style>
			<script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
			<script type="text/javascript">
				google.charts.load('current', {'packages':['corechart', 'table']});
				google.charts.setOnLoadCallback(drawTrend);
				google.charts.setOnLoadCallback(drawDetails);
				google.charts.setOnLoadCallback(drawTable);

				var currentCommit = "${default_commit}";

				function showColumn(dataTable, chart, activColumns, series, col, show) {
					seriesCol = 0
					for (i = 0; i < col; i++)
						if (dataTable.getColumnType(i) == 'number')
							seriesCol++
					if (!show) {
						activColumns[col] = {
							label: dataTable.getColumnLabel(col),
							type: dataTable.getColumnType(col),
							calc: function () {
								return null;
							}
						};
						series[seriesCol].color = '#CCCCCC';
					}
					else {
						activColumns[col] = col;
						series[seriesCol].color = null;
					}
				}

				function showAllColumns(dataTable, chart, activColumns, series, show) {
					for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
						if (dataTable.getColumnType(i) == 'number')
							showColumn(dataTable, chart, activColumns, series, i, show)
					}
				}

				function handle_selection(sel, dataTable, series, activColumns, chart) {
					var col = sel[0].column;

					var allActive = true;
					for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
						if (dataTable.getColumnType(i) == 'number' && activColumns[i] != i) {
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

					var activeColsCount = 0;
					for (var i = 1; i < dataTable.getNumberOfColumns(); i++) {
						if (dataTable.getColumnType(i) == 'number' && activColumns[i] == i) {
							activeColsCount++;
						}
					}
					if (activeColsCount == 0)
						showAllColumns(dataTable, chart, activColumns, series, true);

					return activeColsCount
				}

				function adjustChartSize(id_chart, reportsCount, benchmarkCount) {
					var size = 75 + reportsCount * (25 + (benchmarkCount * 8));
					id_chart.style.height = size + "px";
					id_chart.style.width = "100%";
				}

				function trendUnselect() {
					trend_chart.setSelection(null);
				}

				function drawTrend() {
					var dataTable = new google.visualization.DataTable();

	<%def name="tooltip_commit_table(commit)">\\
	<h3>${db["commits"][commit]['commit'].full_name.replace('"', '&quot;')} <span class='close_button' onclick='javascript:trendUnselect();' title='Close this tooltip'>[X]</span></h3>\\
	<h4>Commit\\
	% if 'commit_url' in db:
	(<a href='${db["commit_url"].format(commit=commit)}' target='_blank'>URL</a>)\\
	% endif
	</h4><table>\\
	<tr><td><b>Author:</b></td><td>${cgi.escape(db["commits"][commit]['commit'].author)}</td></tr>\\
	<tr><td><b>Commit date:</b></td><td>${db["commits"][commit]['commit'].commit_date}</td></tr>\\
	<tr><td><b>Build exit code:</b></td><td bgcolor='${db["commits"][commit]['build_color']}'><center>${db["commits"][commit]['build_error']}</center></td></tr>\\
	% if len(db["commits"][commit]['commit'].bugs) > 0:
	<tr><td><b>Referenced bugs</b></td><td><ul>\\
	% for bug in db["commits"][commit]['commit'].bugs:
	<li><a href='${bug.replace('"', '&quot;')}' target='_blank'>${bug.replace('"', '&quot;')}</a></li>\\
	% endfor
	</ul></td></tr>\\
	% endif
	% if hasattr(db["commits"][commit]['commit'], "annotation_long"):
	<tr><td><b>Annotation:</b></td><td>${cgi.escape(db["commits"][commit]['commit'].annotation_long)}</td></tr>\\
	% endif
	</table>\\
	</%def>

	% if len(db['reports']) > 1:
					dataTable.addColumn('string', 'Commit');
					dataTable.addColumn({type: 'string', role: 'tooltip', p: { html: true }});
					% for report in db["reports"]:
					dataTable.addColumn('number', '${report}');
					% endfor
					dataTable.addRows([
					% for commit in db["commits"]:
						['${commit}', "${tooltip_commit_table(commit)}<h4>Perf</h4><table>\\
	% for report in db["reports"]:
	% if report in db["commits"][commit]['reports']:
	<tr><td><b>${report}:</b></td><td>${db["commits"][commit]['reports'][report]["average"]} ${output_unit}</td></tr>\\
	% endif
	% endfor
	</table><p></p>"\\
							% for report in db["reports"]:
								% if report in db["commits"][commit]['reports']:
	, ${db["commits"][commit]['reports'][report]["average"]}\\
								% else:
	, null\\
								% endif
							% endfor
	],
					% endfor
					]);
	% else:
					<%
						report = db["reports"][0]
					%>
					dataTable.addColumn('string', 'Commits');
					dataTable.addColumn({type: 'string', role:'annotation'});
					% for benchmark in db["benchmarks"]:
					dataTable.addColumn('number', '${benchmark}');
					dataTable.addColumn({type: 'string', role: 'tooltip', p: { html: true }});
					% endfor

					dataTable.addRows([
					% for commit in db["commits"]:
	["${commit}"\\
						% if hasattr(db["commits"][commit]['commit'], 'annotation'):
	, "${db["commits"][commit]['commit'].annotation}"\\
						%else:
	, null\\
						% endif
						% for benchmark in db["benchmarks"]:
							% if benchmark in db["commits"][commit]['reports'][report]:
	<%
		result = db["commits"][commit]['reports'][report][benchmark]
		diff_target = "{0:.2f}".format(result.diff_target)
	%>\\
	, ${diff_target}, "${tooltip_commit_table(commit)}<h4>Perf</h4><table><tr><td><b>Benchmark</b></td><td>${benchmark}</td></tr><tr><td><b>Target</b></td><td>${db['targets'][benchmark]} ${result.unit_str} (${diff_target}%)</td></tr><tr><td><b>Raw value</b></td><td>${result.average_raw} ${result.unit_str} +/- ${result.margin_str}% (n=${len(result.data)})</td></tr><tr><td><b>Converted value</b></td><td>${result.average} ${output_unit} +/- ${result.margin_str}% (n=${len(result.data)})</td></tr></table><br/>"\\
								% else:
	, null, "${benchmark}"\\
								% endif
						% endfor
	],
					% endfor
					]);
	% endif

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
					% if len(db['reports']) > 1:
						focusTarget: 'category',
						vAxis: {title: 'Average result (${output_unit})'},
					% else:
						annotations: {style: 'line', textStyle: {fontSize: 12}},
						vAxis: {title: '% of target (%)'},
					% endif
						legend: { position: 'top', textStyle: {fontSize: 12}, maxLines: 3},
						tooltip: {trigger: 'selection', isHtml: true},
						crosshair: { trigger: 'both' },
						hAxis: {title: 'Commits', slantedText: true, slantedTextAngle: 45},
						series: series,
						chartArea: {left:"6%", width:"95%"}
					};

					trend_chart = new google.visualization.LineChart(document.getElementById('trends_chart'));
					trend_chart.draw(dataTable, options);

					google.visualization.events.addListener(trend_chart, 'select', function () {
						var sel = trend_chart.getSelection();
						// See https://developers.google.com/chart/interactive/docs/reference#visgetselection
						if (sel.length > 0 && typeof sel[0].row === 'object') {
							handle_selection(sel, dataTable, series, activColumns, trend_chart)

							// Redraw the chart with the masked columns
							var view = new google.visualization.DataView(dataTable);
							view.setColumns(activColumns);
							trend_chart.draw(view, options);
						}

						if (sel.length > 0 && typeof sel[0].row === 'number') {
							// update the other graph if there were changes
							var commit = dataTable.getValue(sel[0].row, 0)
							if (commit != currentCommit) {
								currentCommit = commit;
								drawDetails();
								drawTable();
							}
						}

						if (sel.length == 0) {
							trend_chart.setSelection(null);
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
							% if report in db["commits"][commit]['reports']:
								["${report}", ${db["commits"][commit]['reports'][report]["average"]}, "<h3>${report} - Average</h3><p>\\
								% for r in db["reports"]:
	<%
										if not r in db["commits"][commit]:
											continue
										diff = compute_perf_difference(output_unit, db["commits"][commit]['reports'][report]["average"], db["commits"][commit]['reports'][r]["average"])
										diff = float("{0:.2f}".format(diff))
										btag = btagend = ""
										if r == report:
											btag="<b>"
											btagend="</b>"
									%>\\
	${btag}${r}: ${db["commits"][commit]['reports'][r]["average"]} ${output_unit} (${diff}%)${btagend}<br/>\\
								% endfor
	</p>"\\
								% for benchmark in db["benchmarks"]:
									% if benchmark in db["commits"][commit]['reports'][report]:
	, ${db["commits"][commit]['reports'][report][benchmark].average}, "<h3>${report} - ${benchmark}</h3><p>\\
										% for r in db["reports"]:
	<%
												if not r in db["commits"][commit]['reports'] or benchmark not in db["commits"][commit]['reports'][r]:
													continue
												diff = compute_perf_difference(output_unit, db["commits"][commit]['reports'][report][benchmark].average, db["commits"][commit]['reports'][r][benchmark].average)
												diff = float("{0:.2f}".format(diff))
												btag = btagend = ""
												if r == report:
													btag="<b>"
													btagend="</b>"
											%>\\
	${btag}${r}: ${db["commits"][commit]['reports'][r][benchmark].average} ${output_unit} (${diff}%)${btagend}<br/>\\
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

					// adjust the size of the chart to fit the data
					adjustChartSize(details_chart, dataTable.getNumberOfRows(), Math.floor(dataTable.getNumberOfColumns() / 2));

					var activColumns = [];
					var series = {};
					for (var i = 0; i < dataTable.getNumberOfColumns(); i++) {
						activColumns.push(i);
						if (i > 0) {
							series[i - 1] = {};
						}
					}
					series[0] = {type: 'line'};


					var options = {
						title : 'Performance of commit ' + currentCommit,
						legend: {textStyle: {fontSize: 12}},
						tooltip: {trigger: 'focus', isHtml: true},
						vAxis: {title: 'Reports', textStyle: {fontSize: 12}},
						hAxis: {title: 'Average result (${output_unit})', textStyle: {fontSize: 12}},
						seriesType: 'bars',
						orientation: 'vertical',
						series: series
					};

					var chart = new google.visualization.ComboChart(document.getElementById('details_chart'));
					chart.draw(dataTable, options);

					google.visualization.events.addListener(chart, 'select', function () {
						var sel = chart.getSelection();
						// See https://developers.google.com/chart/interactive/docs/reference#visgetselection
						if (sel.length > 0 && typeof sel[0].row === 'object') {
							activeCols = handle_selection(sel, dataTable, series, activColumns, chart)

							// reduce the size of the chart to fit the data
							adjustChartSize(details_chart, dataTable.getNumberOfRows(), activeCols);

							// Redraw the chart with the masked columns
							var view = new google.visualization.DataView(dataTable);
							view.setColumns(activColumns);
							chart.draw(view, options);
						}

						if (sel.length == 0) {
							chart.setSelection(null);
						}
					});
				}

				function drawTable() {
					% if len(db["reports"]) > 1:
						var dataTable = new google.visualization.DataTable();
						dataTable.addColumn('string', 'Benchmark');
						dataTable.addColumn('string', 'Report 1');
						dataTable.addColumn('string', 'Report 2');
						dataTable.addColumn('number', '%');
						dataTable.addColumn('string', 'Comments');

						% for commit in db["commits"]:
						if (currentCommit == "${commit}") {
							% for report1 in db["reports"]:
								% if report1 in db["commits"][commit]['reports']:
									% for report2 in db["reports"]:
										% if report2 != report1 and report2 in db["commits"][commit]['reports']:
											% for benchmark in db["benchmarks"]:
												% if (benchmark in db["commits"][commit]['reports'][report1] and benchmark in db["commits"][commit]['reports'][report2]):
												<%
													r1 = db["commits"][commit]['reports'][report1][benchmark]
													r2 = db["commits"][commit]['reports'][report2][benchmark]
													perf_diff = compute_perf_difference(r1.unit_str, r1.average_raw, r2.average_raw)
													perf_diff = "{0:.2f}".format(perf_diff)
												%>
							dataTable.addRows([['${benchmark}', '${report1}', '${report2}', ${perf_diff}, "${r1.average_raw} => ${r2.average_raw} ${r1.unit_str}"]])
												% endif
											% endfor
										% endif
									% endfor
								% endif
							% endfor
						}
						%endfor
					% else:
						var dataTable = new google.visualization.DataTable();
						dataTable.addColumn('string', 'Benchmark');
						dataTable.addColumn('string', 'Report');
						dataTable.addColumn('number', '% of target');
						dataTable.addColumn('string', 'Comments');

						% for commit in db["commits"]:
						if (currentCommit == "${commit}") {
							% for report1 in db["reports"]:
								% if report1 in db["commits"][commit]['reports']:
									% for benchmark in db["benchmarks"]:
										% if (benchmark in db["commits"][commit]['reports'][report1] and benchmark in db["targets"]):
										<%
											r1 = db["commits"][commit]['reports'][report1][benchmark]
											perf_diff = compute_perf_difference(r1.unit_str, db["targets_raw"][benchmark], r1.average_raw)
											perf_diff = "{0:.2f}".format(perf_diff)
										%>\\
dataTable.addRows([['${benchmark}', '${report1}', ${perf_diff}, "${r1.average_raw}(${report1}) => ${db["targets_raw"][benchmark]}(target) ${r1.unit_str}"]])
										% endif
									% endfor
								% endif
							% endfor
						}
						%endfor
					% endif
					var chart = new google.visualization.Table(document.getElementById('details_table'));
					chart.draw(dataTable, {showRowNumber: true, width: '100%', height: '100%'});
				}
			</script>
		</head>

		<body>
			<h1>${title}</h1>

			% if 'reference_name' in db:
				<p>With targets taken from: ${db['reference_name']}</p>
			% endif

			<h2>Trends</h2>

			<center><div id="trends_chart" style="width: 100%; height: 500px;"></div></center>

			<h2>Details</h2>

			<center><div id="details_chart" style="width: 100%; height: 500px;"></div></center>

			<center><div id="details_table" style="width: 100%; height: 500px;"></div></center>

			<h2>Events</h2>

			% for report in db['events']:
				<h3>${report}</h3>
				<ul>
				% for event in db['events'][report]:
					<li>${event}</li>
				% endfor
				</ul>
			% endfor

			<h2>Benchmarks</h2>

				% for benchmark in db["benchmarks"]:
					<h3>${benchmark}</h3>

					<div class="css-treeview">
						<%def name="outputtreenode(node, id, label, attr = '')">
							<li><input type="checkbox" id="${id}" ${attr}/><label class="env_node" for="${id}">+${label}</label><ul>
								<table>
								% for child in sorted(node):
									% if type(node[child]) is str:
										<tr><td>${child}</td><td>${node[child]}</td></tr>
									% endif
								% endfor
								</table>
								% for child in sorted(node):
									% if type(node[child]) is not str:
										${outputtreenode(node[child], "{}.{}".format(id, child.replace(' ', '_')), child, '')}
									% endif
								% endfor
							</ul></li>
						</%def>

						<ul>
							${outputtreenode(db["envs"][benchmark], benchmark + "_envroot", "Environment", 'checked="checked"')}
						</ul>
					</div>

					<table>
						<tr>
							<th>Key</th>
							% for env_set in db["env_sets"][benchmark]:
							<%
								users = ""
								for user in env_set['users']:
									if len(users) > 0:
										users += "<br/>"
									users += "{}.{}#{}".format(user['log_folder'], user['commit'].sha1, user['run'])
							%>\\
							<th>${users}</th>
							% endfor
						</tr>
						% for key in db["env_diff_keys"][benchmark]:
						<tr>
							<td>${key}</td>
							% for env_set in db["env_sets"][benchmark]:
							% if key in dict(env_set['set']):
								<td>${dict(env_set['set'])[key]}</td>
							% else:
								<td>MISSING</td>
							% endif
							% endfor
						</tr>
						% endfor
					</table>
				% endfor
		</body>

	</html>
	"""
	# Check that we have commits
	if len(db["commits"]) == 0 and verbose:
		print("No commits were found, cancelling...")
	else:
		# Create the html file
		if verbose:
			print("Generating the HTML")

		if title is None:
			report_names = [r.name for r in reports]
			title = "Performance report on the runs named '{run_name}'".format(run_name=report_names)

		html = Template(html_template).render(title=title, db=db, output_unit=output_unit,
							default_commit=list(db["commits"])[-1])

		with open(output, 'w') as f:
			f.write(html)
			if verbose:
				print("Output HTML generated at: {}".format(output))

if __name__ == "__main__":
	import argparse

	# parse the options
	parser = argparse.ArgumentParser()
	parser.add_argument("--title", help="Set the title for the report")
	parser.add_argument("--unit", help="Set the output unit (Default: FPS)")
	parser.add_argument("--output", help="Report html file path", required=True)
	parser.add_argument("--commit_url", help="HTTP URL pattern, {commit} contains the SHA1")
	parser.add_argument("--quiet", help="Be quiet when generating the report", action="store_true")
	parser.add_argument("--reference", help="Compare the benchmarks to this reference report")
	parser.add_argument("log_folder", nargs='+')
	args = parser.parse_args()

	reports = []
	for log_folder in args.log_folder:
		report_name = [x for x in log_folder.split(os.sep) if x][-1]
		try:
			sbench = SmartEzbench(ezbench_dir, report_name, readonly=True)
			report = sbench.report()
		except RuntimeError:
			report = genPerformanceReport(log_folder)
		reports.append(report)

	# Reference report
	reference = None
	if args.reference is not None:
		reference = genPerformanceReport(args.reference)

	reports_to_html(reports, args.output, args.unit, args.title,
			   args.commit_url, not args.quiet, reference)
