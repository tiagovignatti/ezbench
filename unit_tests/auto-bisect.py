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

from ez_ut import *
import argparse
import datetime
import pygit2
import time
import sys
import os

# Import ezbench from the utils/ folder
ezbench_dir = os.path.abspath(sys.path[0] + "/../")
sys.path.append(ezbench_dir + '/utils/')
from ezbench import *

# parse the options
parser = argparse.ArgumentParser()
parser.add_argument("-r", dest='reuse_data', action="store_true",
					help="Do not reset the state")
args = parser.parse_args()

def create_new_branch(repo, base_commit, branch_name, template, state, max_commits):
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

		last_commit = create_new_commit(repo, ref, template, state)

	return last_commit

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
	HEAD = create_new_branch(repo, initial_commit, branch_name,
                          template, copy.deepcopy(state), 1000)
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
		if result.benchmark.full_name != 'perf_bisect':
			continue

		o_perf, o_variance, o_build, o_exec = commit_info(e.commit_range.old)
		n_perf, n_variance, n_build, n_exec = commit_info(e.commit_range.new)
		wanted = EventPerfChange(e.benchmark, e.commit_range, o_perf, n_perf, 1.0)

		if (not o_exec and n_exec) or (o_exec and not n_exec):
			if e.diff() != -1 and e.diff() != float("+inf"):
				print("False positive: {} => real perf change was {} to {}".format(e, o_perf, n_perf))
				false_positive += 1
		else:
			rel_error = abs(wanted.diff() - e.diff()) * 100.0
			relative_error.append(rel_error)
			if o_perf == n_perf or rel_error > max_variance * 100.0:
				print("False positive: {} => real perf change was {} to {}".format(e, o_perf, n_perf))
				false_positive += 1

total_changes = 0
false_negatives = 0
p_perf = 100
p_build = False
p_exec = False
r = 0
HEAD = repo.revparse_single('HEAD')
for commit in repo.walk(HEAD.oid, pygit2.GIT_SORT_REVERSE):
	# Skip the first commit
	if commit.message == "template\n":
		continue

	c_perf, c_var, c_build, c_exec = parse_commit_title(commit.message)

	if p_perf != c_perf:
		e = find_event_from_commit(repo, report, EventPerfChange, commit.hex)
		if not e:
			print("False negative: commit {} changed perf from {} to {}".format(commit.hex, p_perf, c_perf))
			false_negatives += 1
		total_changes += 1

	#if (not p_exec and c_perf) or (p_exec and not c_perf):


	# Copy the new values to the previous ones before iterating
	p_perf = c_perf
	p_build = c_build
	p_exec = c_exec

print("Stats (max error wanted = {:.2f}%):".format(max_variance * 100.0))
print("	  Average sampling error: {}".format(do_stats(sample_error, '%')))
print("	Average perf. rel. error: {}".format(do_stats(relative_error, '%')))
print("")
print("Tests:")
print("	Too large variance: {} / {}".format(variance_too_high, len(sample_error)))
print("	   False positives: {} / {}".format(false_positive, len(report.events)))
print("	   False negatives: {} / {}".format(false_negatives, total_changes))

sys.exit(variance_too_high == 0 and false_positive == 0)
