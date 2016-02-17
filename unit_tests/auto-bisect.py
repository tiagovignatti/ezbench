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

	commit_msg = "{perf}, {variance}".format(perf=state['perf'], variance=state['variance'])

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
		if random.random() > 0.9:
			state['perf'] = int(state['perf'] * (1 + random.randn() / 10))
			changes = True
		if not changes:
			state['noise_commit'] += 1

		last_commit = create_new_commit(repo, ref, state)

	return last_commit

def report_cleanup(report_name):
    try:
        shutil.rmtree('{ezbench_dir}/logs/{name}'.format(ezbench_dir=ezbench_dir,
                                                         name=report_name))
    except FileNotFoundError:
            pass

def create_report(base_sha1, head_sha1):
	report_name = "unit_test"
	#report_cleanup(report_name)

	# create the initial workload
	sbench = SmartEzbench(ezbench_dir, report_name)
	sbench.set_profile("bisect_test")

	sbench.force_benchmark_rounds(head_sha1, 'perf_bisect', 3)
	sbench.force_benchmark_rounds(base_sha1, 'perf_bisect', 3)

	# Run until all the enhancements are made!
	git_history = sbench.git_history()
	while True:
		sbench.schedule_enhancements(git_history)
		if not sbench.run():
			break

	report = sbench.report(git_history)

	#report_cleanup(report_name)

	return report

# Generate the git history
repo = pygit2.Repository(perf_bisect_repo_dir())
repo.checkout(repo.lookup_reference('refs/heads/master'))
for branch in repo.listall_branches(pygit2.GIT_BRANCH_LOCAL):
	if branch.startswith("tmp_"):
		repo.lookup_branch(branch).delete() # Clean all the tmp branches we create
initial_commit = next(repo.walk(repo.revparse_single('HEAD').oid, pygit2.GIT_SORT_REVERSE))
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
report = create_report(initial_commit.hex[0:7], repo.revparse_single('HEAD').hex[0:7])
for event in report.events:
    print(event)