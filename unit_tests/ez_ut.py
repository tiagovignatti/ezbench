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

import random
import pygit2
import shutil
import sys
import os

# Import ezbench from the utils/ folder
ezbench_dir = os.path.abspath(sys.path[0] + "/../")
sys.path.append(ezbench_dir + '/utils/')
from ezbench import *

def perf_bisect_repo_dir():
	if not hasattr(perf_bisect_repo_dir, 'repo_dir'):
		ezbench = Ezbench(ezbench_dir + "/core.sh", "bisect_test")
		run = ezbench.run_commits(['HEAD'], ['no-op'], dry_run=True)
		perf_bisect_repo_dir.repo_dir = run.repo_dir
	return perf_bisect_repo_dir.repo_dir

def create_new_commit(repo, ref, template, state):
	values = ""
	for entry in state:
		values += "{} = {}\n".format(entry, state[entry])
	data = template.decode().replace("#{OVERRIDE_VALUES_HERE}\n", values)

	commit_msg = "{},{},{},{}".format(state['perf'], state['variance'],
								state['build_broken'], state['exec_broken'])

	data_oid = repo.create_blob(data)
	tip = repo.revparse_single(ref)

	tb = repo.TreeBuilder(tip.tree)
	tb.insert('perf.py', data_oid, pygit2.GIT_FILEMODE_BLOB_EXECUTABLE)
	new_tree = tb.write()
	author = pygit2.Signature('EzBench unit test', 'unit@test.com')
	return repo.create_commit(ref, author, author, commit_msg, new_tree, [tip.id])

def report_cleanup(report_name):
	try:
		shutil.rmtree('{ezbench_dir}/logs/{name}'.format(ezbench_dir=ezbench_dir,
                                                         name=report_name))
	except FileNotFoundError as e:
		print(e)
		pass

def create_report(base_sha1, head_sha1, max_variance = 0.025, reuse_data=True):
	report_name = "unit_test"
	if not reuse_data:
		report_cleanup(report_name)

	# create the initial workload
	sbench = SmartEzbench(ezbench_dir, report_name)
	sbench.set_profile("bisect_test")

	sbench.force_benchmark_rounds(head_sha1, 'perf_bisect', 3)
	sbench.force_benchmark_rounds(base_sha1, 'perf_bisect', 3)

	# Run until all the enhancements are made!
	git_history = sbench.git_history()
	while True:
		sbench.schedule_enhancements(git_history, max_variance=max_variance, commit_schedule_max=100)
		if not sbench.run():
			break

	report = sbench.report(git_history)

	if not reuse_data:
		report_cleanup(report_name)

	return report

def parse_commit_title(title):
	# title = '3c91150 162,1,False,False'
	f = title.split(',')
	return int(f[0]), int(f[1]), f[2] == "True", f[3] == "True"

def commit_info(commit):
	return parse_commit_title(commit.full_name.split(' ')[1])

def check_commit_variance(actual, measured, max_variance):
	return abs(actual - measured) < max_variance * actual

def do_stats(data, unit):
	adata = array(data)
	mean, var, std = stats.bayes_mvs(adata, alpha=0.95)
	margin = (mean[1][1] - mean[1][0]) / 2 / mean[0]
	msg = "{:.2f}{}, +/- {:.2f} (std={:.2f}, min={:.2f}{}, max={:.2f}{})"
	return msg.format(mean[0], unit, margin, std[0], adata.min(), unit, adata.max(), unit)

def find_event_from_commit(repo, report, type_event, sha1):
	for e in report.events:
		if type(e) is not type_event:
			continue
		if e.benchmark.full_name != 'perf_bisect':
			continue

		# If the range is one commit, we can easily find the commit by just
		# comparing strings
		if e.commit_range.distance() == 1:
			if repo.revparse_single(e.commit_range.new.sha1).hex == sha1:
				return e
		else:
			# XXX: Fixme
			print("find_event_from_commit: commit ranges of more than 1 commit are not supported yet")

	return None
