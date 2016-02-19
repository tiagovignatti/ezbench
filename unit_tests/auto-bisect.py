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

import argparse
import datetime
import random
import pprint
import pygit2
import shutil
import signal
import time
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

def create_new_commit(repo, ref, state):
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

def create_new_branch(repo, base_commit, branch_name, state, max_commits):
	repo.create_branch(branch_name, base_commit)
	ref = 'refs/heads/'+branch_name

	last_commit = None

	for i in range(0, max_commits):
		# Treat every variable independently
		changes = False
		if random.random() > 0.98:
			state['perf'] = int(state['perf'] * (1.0075 + random.randn() / 10))
			changes = True
		if not state['build_broken'] and random.random() > 0.995:
			state['build_broken'] = True
			changes = True
		elif state['build_broken'] and random.random() > 0.75:
			state['build_broken'] = False
			changes = True

		if not state['exec_broken'] and random.random() > 0.995:
			state['exec_broken'] = True
			changes = True
		elif state['exec_broken'] and random.random() > 0.75:
			state['exec_broken'] = False
			changes = True

		if not changes:
			state['noise_commit'] += 1

		last_commit = create_new_commit(repo, ref, state)

	return last_commit

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

def commit_info(commit):
	# commit.full_name = '3c91150 162,1,False,False'
	f = commit.full_name.split(' ')[1].split(',')
	return int(f[0]), int(f[1]), f[2] == "True", f[3] == "True"

def check_commit_variance(actual, measured, max_variance):
	return abs(actual - measured) < max_variance * actual

def do_stats(data, unit):
	adata = array(data)
	mean, var, std = stats.bayes_mvs(adata, alpha=0.95)
	margin = (mean[1][1] - mean[1][0]) / 2 / mean[0]
	msg = "{:.2f}{}, +/- {:.2f} (std={:.2f}, min={:.2f}{}, max={:.2f}{})"
	return msg.format(mean[0], unit, margin, std[0], adata.min(), unit, adata.max(), unit)

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("-r", dest='reuse_data', action="store_true",
					help="Do not reset the state")
args = parser.parse_args()

# Generate the git history
repo = pygit2.Repository(perf_bisect_repo_dir())
initial_commit = next(repo.walk(repo.revparse_single('HEAD').oid, pygit2.GIT_SORT_REVERSE))

if not args.reuse_data:
	random.seed(42)
	repo.checkout(repo.lookup_reference('refs/heads/master'))
	for branch in repo.listall_branches(pygit2.GIT_BRANCH_LOCAL):
		if branch.startswith("tmp_"):
			repo.lookup_branch(branch).delete() # Clean all the tmp branches we create
	branch_name = datetime.now().strftime('tmp_%Y-%m-%d_%H-%M-%S')
	template = repo[initial_commit.tree['perf.py'].id].data

	# Initial state
	state = dict()
	state['perf'] = 100
	state['sample_distribution_mode'] = 0
	state['variance'] = 1
	state['build_broken'] = False
	state['exec_broken'] = False
	state['noise_commit'] = 0

	# implement a state machine
	HEAD = create_new_branch(repo, initial_commit, branch_name, copy.deepcopy(state), 1000)
	repo.checkout('refs/heads/'+branch_name)

# List the events
max_variance = 0.025
report = create_report(initial_commit.hex[0:7],
                       repo.revparse_single('HEAD').hex[0:7],
                       max_variance, args.reuse_data)

# test the variance of every commit
variance_too_high = 0
sample_error = []
for commit in report.commits:
	# FIXME: instead of skipping this commit, replace the template commit by the
	# actual first sample!
	if commit.full_name.endswith("template"):
		continue
	for result in commit.results:
		# Check that the results are for the right benchmark
		if result.benchmark.full_name != 'perf_bisect':
			continue

		e_perf, e_var, e_build, e_exec = commit_info(commit)

		# if the commit was expected to fail running, force the performance to 0
		if e_build or e_exec:
			e_perf = 0

		if e_perf > 0:
			error = abs(e_perf - result.result()) * 100.0 / e_perf
		else:
			error = 0

		sample_error.append(error)
		if error > max_variance * 100:
			msg = "Commit {}'s performance differs significantly from the target, {} vs {}"
			print(msg.format(commit.sha1, result.result(), e_perf))
			variance_too_high += 1

false_positive = 0
relative_error = []
for e in report.events:
	if type(e) is EventPerfChange:
		o_perf, o_variance, o_build, o_exec = commit_info(e.commit_range.old)
		n_perf, n_variance, n_build, n_exec = commit_info(e.commit_range.new)
		wanted = EventPerfChange(e.benchmark, e.commit_range, o_perf, n_perf, 1.0)

		if (not o_exec and n_exec) or (o_exec and not n_exec):
			if e.diff() != -1 and e.diff() != float("+inf"):
				print("{} => Was a false positive, real perf was {} to {}".format(e, o_perf, n_perf))
				false_positive += 1
		else:
			rel_error = abs(wanted.diff() - e.diff()) * 100.0
			relative_error.append(rel_error)
			if o_perf == n_perf or rel_error > max_variance * 100.0:
				print("{} => Was a false positive, real perf was {} to {}".format(e, o_perf, n_perf))
				false_positive += 1

print("Stats (max error wanted = {:.2f}%):".format(max_variance * 100.0))
print("	  Average sampling error: {}".format(do_stats(sample_error, '%')))
print("	Average perf. rel. error: {}".format(do_stats(relative_error, '%')))
print("")
print("Tests:")
print("	Too large variance: {} / {}".format(variance_too_high, len(sample_error)))
print("	   False positives: {} / {}".format(false_positive, len(report.events)))

sys.exit(variance_too_high == 0 and false_positive == 0)
