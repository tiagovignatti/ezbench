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

from email.utils import parsedate_tz, mktime_tz
from collections import namedtuple
from datetime import datetime
from dateutil import relativedelta
from array import array
from enum import Enum
from numpy import *
import subprocess
import atexit
import pprint
import fcntl
import time
import json
import glob
import copy
import csv
import sys
import os
import re

# Ezbench runs
class EzbenchExitCode(Enum):
    NO_ERROR = 0
    ARG_PROFILE_NAME_MISSING = 11
    ARG_PROFILE_INVALID = 12
    ARG_OPTARG_MISSING = 13
    ARG_GIT_REPO_MISSING = 14
    OS_SHELL_GLOBSTAT_MISSING = 30
    OS_LOG_FOLDER_CREATE_FAILED = 31
    OS_CD_GIT_REPO = 32
    GIT_STASH_FAILED = 50
    GIT_INVALID_COMMIT_ID = 50
    COMP_DEP_UNK_ERROR = 70
    COMPILATION_FAILED = 71
    DEPLOYMENT_FAILED = 72
    DEPLOYMENT_ERROR = 73
    REBOOT_NEEDED = 74
    TEST_INVALID_NAME = 100
    UNK_ERROR = 255

class EzbenchRun:
    def __init__(self, commits, benchmarks, predicted_execution_time, repo_dir, repo_head, deployed_commit, exit_code):
        self.commits = commits
        self.benchmarks = benchmarks
        self.predicted_execution_time = predicted_execution_time
        self.repo_dir = repo_dir
        self.repo_head = repo_head
        self.deployed_commit = deployed_commit
        self.exit_code = EzbenchExitCode(exit_code)

    def success(self):
        return self.exit_code == EzbenchExitCode.NO_ERROR

class Ezbench:
    def __init__(self, ezbench_path, profile = None, repo_path = None,
                 make_command = None, report_name = None, tests_folder = None,
                 run_config_script = None):
        self.ezbench_path = ezbench_path
        self.profile = profile
        self.repo_path = repo_path
        self.make_command = make_command
        self.report_name = report_name
        self.tests_folder = tests_folder
        self.run_config_script = run_config_script

    def __ezbench_cmd_base(self, benchmarks, benchmark_excludes = [], rounds = None, dry_run = False):
        ezbench_cmd = []
        ezbench_cmd.append(self.ezbench_path)

        if self.profile is not None:
            ezbench_cmd.append("-P"); ezbench_cmd.append(self.profile)

        if self.repo_path is not None:
            ezbench_cmd.append("-p"); ezbench_cmd.append(self.repo_path)

        for benchmark in benchmarks:
            ezbench_cmd.append("-b"); ezbench_cmd.append(benchmark)

        for benchmark_excl in benchmark_excludes:
            ezbench_cmd.append("-B"); ezbench_cmd.append(benchmark_excl)

        if rounds is not None:
            ezbench_cmd.append("-r"); ezbench_cmd.append(str(rounds))

        if self.make_command is not None:
            ezbench_cmd.append("-m"); ezbench_cmd.append(self.make_command)
        if self.report_name is not None:
            ezbench_cmd.append("-N"); ezbench_cmd.append(self.report_name)
        if self.tests_folder is not None:
            ezbench_cmd.append("-T"); ezbench_cmd.append(self.tests_folder)
        if self.run_config_script is not None:
            ezbench_cmd.append("-c"); ezbench_cmd.append(self.run_config_script)

        if dry_run:
            ezbench_cmd.append("-k")

        return ezbench_cmd

    def __run_ezbench(self, cmd, dry_run = False, verbose = False):
        exit_code = None

        if verbose:
            print(cmd)

        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
            exit_code = EzbenchExitCode.NO_ERROR
        except subprocess.CalledProcessError as e:
            exit_code = EzbenchExitCode(e.returncode)
            output = e.output.decode()
            pass

        # we need to parse the output
        commits= []
        benchmarks = []
        pred_exec_time = 0
        deployed_commit = ""
        repo_dir = ""
        head_commit = ""
        re_commit_list = re.compile('^Testing \d+ commits: ')
        re_repo = re.compile('^Repo = (.*), HEAD = (.*), deployed version = (.*)$')
        for line in output.split("\n"):
            m_commit_list = re_commit_list.match(line)
            m_repo = re_repo.match(line)
            if line.startswith("Tests that will be run:"):
                benchmarks = line[24:].split(" ")
                if benchmarks[-1] == '':
                    benchmarks.pop(-1)
            elif line.find("estimated finish date:") >= 0:
                pred_exec_time = ""
            elif m_repo is not None:
                repo_dir, head_commit, deployed_commit = m_repo.groups()
            elif m_commit_list is not None:
                commits = line[m_commit_list.end():].split(" ")
                while '' in commits:
                    commits.remove('')
            elif exit_code == EzbenchExitCode.TEST_INVALID_NAME and line.endswith("do not exist"):
                print(line)

        if exit_code != EzbenchExitCode.NO_ERROR:
            print("\n\nERROR: The following command '{}' failed with the error code {}. Here is its output:\n\n'{}'".format(" ".join(cmd), exit_code, output))

        return EzbenchRun(commits, benchmarks, pred_exec_time, repo_dir, head_commit, deployed_commit, exit_code)

    def run_commits(self, commits, benchmarks, benchmark_excludes = [],
                    rounds = None, dry_run = False, verbose = False):
        ezbench_cmd = self.__ezbench_cmd_base(benchmarks, benchmark_excludes, rounds, dry_run)

        for commit in commits:
            ezbench_cmd.append(commit)

        return self.__run_ezbench(ezbench_cmd, dry_run, verbose)

    def run_commit_range(self, head, commit_count, benchmarks, benchmark_excludes = [],
                         rounds = None, dry_run = False, verbose = False):
        ezbench_cmd = self.__ezbench_cmd_base(benchmarks, benchmark_excludes, rounds, dry_run)

        ezbench_cmd.append("-H"); ezbench_cmd.append(head)
        ezbench_cmd.append("-n"); ezbench_cmd.append(commit_count)

        return self.__run_ezbench(ezbench_cmd, dry_run, verbose)

# Smart-ezbench-related classes
class Criticality(Enum):
    II = 0
    WW = 1
    EE = 2
    DD = 3

class RunningMode(Enum):
    INITIAL = 0
    RUN = 1
    PAUSE = 2
    ERROR = 3
    ABORT = 4

def list_smart_ezbench_report_names(ezbench_dir, updatedSince = 0):
    log_dir = ezbench_dir + '/logs'
    state_files = glob.glob("{log_dir}/*/smartezbench.state".format(log_dir=log_dir));

    reports = []
    for state_file in state_files:
        if updatedSince > 0 and os.path.getmtime(state_file) < updatedSince:
            continue

        start = len(log_dir) + 1
        stop = len(state_file) - 19
        reports.append(state_file[start:stop])

    return reports

class TaskEntry:
    def __init__(self, commit, benchmark, rounds):
        self.commit = commit
        self.benchmark = benchmark
        self.rounds = rounds

class SmartEzbench:
    def __init__(self, ezbench_dir, report_name, readonly = False):
        self.readonly = readonly
        self.ezbench_dir = ezbench_dir
        self.log_folder = ezbench_dir + '/logs/' + report_name
        self.smart_ezbench_state = self.log_folder + "/smartezbench.state"
        self.smart_ezbench_lock = self.log_folder + "/smartezbench.lock"
        self.smart_ezbench_log = self.log_folder + "/smartezbench.log"

        self.state = dict()
        self.state['report_name'] = report_name
        self.state['commits'] = dict()
        self.state['mode'] = RunningMode.INITIAL.value

        # Create the log directory
        first_run = False
        if not readonly and not os.path.exists(self.log_folder):
            os.makedirs(self.log_folder)
            first_run = True

        # Open the log file as append
        self.log_file = open(self.smart_ezbench_log, "a")

        # Add the welcome message
        if first_run or not self.__reload_state():
            if readonly:
                raise RuntimeError("The report {} does not exist".format(report_name))
            self.__save_state()
            self.__log(Criticality.II,
                    "Created report '{report_name}' in {log_folder}".format(report_name=report_name,
                                                                            log_folder=self.log_folder))

    def __log(self, error, msg):
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = "{time}: ({error}) {msg}\n".format(time=time, error=error.name, msg=msg)
        print(log_msg, end="")
        if not self.readonly:
            self.log_file.write(log_msg)
            self.log_file.flush()

    def __grab_lock(self):
        if self.readonly:
            return
        self.lock_fd = open(self.smart_ezbench_lock, 'w')
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            return True
        except IOError as e:
            self.__log(Criticality.EE, "Could not lock the report: " + str(e))
            return False

    def __release_lock(self):
        if self.readonly:
            return

        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
        except Exception as e:
            self.__log(Criticality.EE, "Cannot release the lock: " + str(e))
            pass

    def __reload_state_unlocked(self):
        # check if a report already exists
        try:
            with open(self.smart_ezbench_state, 'rt') as f:
                self.state_read_time = time.time()
                try:
                    self.state = json.loads(f.read())
                except Exception as e:
                    self.__log(Criticality.EE, "Exception while reading the state: " + str(e))
                    pass
                return True
        except IOError as e:
            self.__log(Criticality.WW, "Cannot open the state file: " + str(e))
            pass
        return False

    def __reload_state(self, keep_lock = False):
        self.__grab_lock()
        ret = self.__reload_state_unlocked()
        if not keep_lock:
            self.__release_lock()
        return ret

    def __save_state(self):
        if self.readonly:
            return

        try:
            state_tmp = str(self.smart_ezbench_state) + ".tmp"
            with open(state_tmp, 'wt') as f:
                f.write(json.dumps(self.state, sort_keys=True, indent=4, separators=(',', ': ')))
                f.close()
                os.rename(state_tmp, self.smart_ezbench_state)
                return True
        except IOError:
            self.__log(Criticality.EE, "Could not dump the current state to a file!")
            return False

    def __create_ezbench(self, ezbench_path = None, profile = None, report_name = None):
        if ezbench_path is None:
            ezbench_path = self.ezbench_dir + "/core.sh"
        if profile is None:
            profile = self.profile()
        if report_name is None:
            report_name=self.state['report_name']

        return Ezbench(ezbench_path = ezbench_path, profile = profile,
                       report_name = report_name)

    def running_mode(self):
        self.__reload_state(keep_lock=False)
        if 'mode' not in self.state:
            return RunningMode.INITIAL
        else:
            return RunningMode(self.state['mode'])

    def set_running_mode(self, mode):
        self.__reload_state(keep_lock=True)
        if 'mode' not in self.state or self.state['mode'] != mode.value:
            self.state['mode'] = mode.value
            self.__log(Criticality.II, "Ezbench running mode set to '{mode}'".format(mode=mode.name))
            self.__save_state()
        self.__release_lock()

    def profile(self):
        self.__reload_state(keep_lock=False)
        if "profile" in self.state:
            return self.state['profile']
        else:
            return None

    def set_profile(self, profile):
        self.__reload_state(keep_lock=True)
        if 'beenRunBefore' not in self.state or self.state['beenRunBefore'] == False:
            # Check that the profile exists!
            ezbench = self.__create_ezbench(profile = profile)
            run_info = ezbench.run_commits(["HEAD"], [], [], dry_run=True)
            if not run_info.success():
                if run_info.exit_code == EzbenchExitCode.ARG_PROFILE_INVALID:
                    self.__log(Criticality.EE,
                               "Invalid profile name '{profile}'.".format(profile=profile))
                else:
                    self.__log(Criticality.EE,
                               "The following error arose '{error}'.".format(error=run_info.exit_code.name))
                self.__release_lock()
                return

            self.state['profile'] = profile
            self.__log(Criticality.II, "Ezbench profile set to '{profile}'".format(profile=profile))
            self.__save_state()
        else:
            self.__log(Criticality.EE, "You cannot change the profile of a report that already has results. Start a new one.")
        self.__release_lock()

    def conf_script(self):
        self.__reload_state(keep_lock=True)
        if "conf_script" in self.state:
            conf_script = self.state['conf_script']
            self.__release_lock()
            return conf_script
        else:
            self.__release_lock()
            return None

    def set_conf_script(self, conf_script):
        self.__reload_state(keep_lock=True)
        if 'beenRunBefore' not in self.state or self.state['beenRunBefore'] == False:
            self.state['conf_script'] = conf_script
            self.__log(Criticality.II, "Ezbench profile configuration script set to '{0}'".format(conf_script))
            self.__save_state()
        else:
            self.__log(Criticality.EE, "You cannot change the configuration script of a report that already has results. Start a new one.")
        self.__release_lock()

    def add_benchmark(self, commit, benchmark, rounds = None):
        self.__reload_state(keep_lock=True)
        if commit not in self.state['commits']:
            self.state['commits'][commit] = dict()
            self.state['commits'][commit]["benchmarks"] = dict()

        if rounds is None:
            rounds = 3

        if benchmark not in self.state['commits'][commit]['benchmarks']:
            self.state['commits'][commit]['benchmarks'][benchmark] = dict()
            self.state['commits'][commit]['benchmarks'][benchmark]['rounds'] = rounds
        else:
            self.state['commits'][commit]['benchmarks'][benchmark]['rounds'] += rounds

        # if the number of rounds is equal to 0 for a benchmark, delete it
        if self.state['commits'][commit]['benchmarks'][benchmark]['rounds'] <= 0:
            del self.state['commits'][commit]['benchmarks'][benchmark]

        # Delete a commit that has no benchmark
        if len(self.state['commits'][commit]['benchmarks']) == 0:
            del self.state['commits'][commit]

        self.__save_state()
        self.__release_lock()

    def force_benchmark_rounds(self, commit, benchmark, at_least):
        if at_least < 1:
            return 0

        self.__reload_state(keep_lock=True)
        if commit not in self.state['commits']:
            self.state['commits'][commit] = dict()
            self.state['commits'][commit]["benchmarks"] = dict()

        if benchmark not in self.state['commits'][commit]['benchmarks']:
            self.state['commits'][commit]['benchmarks'][benchmark] = dict()
            self.state['commits'][commit]['benchmarks'][benchmark]['rounds'] = 0

        to_add = at_least - self.state['commits'][commit]['benchmarks'][benchmark]['rounds']

        if to_add > 0:
            self.__log(Criticality.WW,
                       "Schedule {} more runs for the benchmark {} on commit {}".format(to_add, benchmark, commit))

            self.state['commits'][commit]['benchmarks'][benchmark]['rounds'] += to_add
            self.__save_state()

        self.__release_lock()

        if to_add > 0:
            return to_add
        else:
            return 0

    def __prioritize_runs(self, task_tree, deployed_version):
        task_list = list()

        # Schedule the tests using the already-deployed version
        if deployed_version is not None and deployed_version in task_tree:
            for benchmark in task_tree[deployed_version]["benchmarks"]:
                rounds = task_tree[deployed_version]["benchmarks"][benchmark]["rounds"]
                task_list.append(TaskEntry(deployed_version, benchmark, rounds))
            del task_tree[deployed_version]

        # Add all the remaining tasks in whatever order!
        for commit in task_tree:
            for benchmark in task_tree[commit]["benchmarks"]:
                rounds = task_tree[commit]["benchmarks"][benchmark]["rounds"]
                task_list.append(TaskEntry(commit, benchmark, rounds))

        return task_list

    def run(self):
        self.__log(Criticality.II, "----------------------")
        self.__log(Criticality.II, "Starting a run: {report}".format(report=self.state['report_name']))

        # Check the current state (FIXME: racy)
        running_state=self.running_mode()
        if running_state == RunningMode.INITIAL or running_state == RunningMode.RUN:
            self.set_running_mode(RunningMode.RUN)
        else:
            self.__log(Criticality.II,
                       "We cannot run when the current running mode is {mode}.".format(mode=self.running_mode()))
            self.__release_lock()
            return False


        self.__log(Criticality.II, "Checking the dependencies:")

        # check for dependencies
        if 'profile' not in self.state:
            self.__log(Criticality.EE, "    - Ezbench profile: Not set. Abort...")
            return False
        else:
            profile = self.state["profile"]
            self.__log(Criticality.II, "    - Ezbench profile: '{0}'".format(profile))

        # Create the ezbench runner
        ezbench = self.__create_ezbench()
        run_info = ezbench.run_commits(["HEAD"], [], [], dry_run=True)
        self.__log(Criticality.II, "    - Deployed version: '{0}'".format(run_info.deployed_commit))
        self.__log(Criticality.II, "All the dependencies are met, generate a report...")

        # Generate a report to compare the goal with the current state
        report = genPerformanceReport(self.log_folder, silentMode = True)
        self.__log(Criticality.II,
                   "The report contains {count} commits".format(count=len(report.commits)))

        # Walk down the report and get rid of every run that has already been made!
        task_tree = copy.deepcopy(self.state['commits'])
        for commit in report.commits:
            for result in commit.results:
                self.__log(Criticality.DD,
                           "Found {count} runs for benchmark {benchmark} using commit {commit}".format(count=len(result.data),
                                                                                                       commit=commit.sha1,
                                                                                                       benchmark=result.benchmark.full_name))
                if commit.sha1 not in task_tree:
                    continue
                if result.benchmark.full_name not in task_tree[commit.sha1]["benchmarks"]:
                    continue

                task_tree[commit.sha1]["benchmarks"][result.benchmark.full_name]['rounds'] -= len(result.data)

                if task_tree[commit.sha1]["benchmarks"][result.benchmark.full_name]['rounds'] <= 0:
                    del task_tree[commit.sha1]["benchmarks"][result.benchmark.full_name]

                if len(task_tree[commit.sha1]["benchmarks"]) == 0:
                    del task_tree[commit.sha1]

        # Delete the tests on commits that do not compile
        for commit in report.commits:
            if commit.build_broken() and commit.sha1 in task_tree:
                self.__log(Criticality.II,
                           "Cancelling the following runs because commit {} does not compile:".format(commit.sha1))
                self.__log(Criticality.II, task_tree[commit.sha1])
                del task_tree[commit.sha1]

        if len(task_tree) == 0:
            self.__log(Criticality.II, "Nothing left to do, exit")
            return

        task_tree_str = pprint.pformat(task_tree)
        self.__log(Criticality.II, "Task list: {tsk_str}".format(tsk_str=task_tree_str))

        # Prioritize --> return a list of commits to do in order
        task_list = self.__prioritize_runs(task_tree, run_info.deployed_commit)

        # Let's start!
        self.state['beenRunBefore'] = True

        # Start generating ezbench calls
        for e in task_list:
            running_mode = self.running_mode()
            if running_mode != RunningMode.RUN:
                self.__log(Criticality.II,
                       "Running mode changed from RUN to {mode}. Exit...".format(mode=running_mode.name))
                return False

            self.__log(Criticality.DD,
                       "make {count} runs for benchmark {benchmark} using commit {commit}".format(count=e.rounds,
                                                                                                  commit=e.commit,
                                                                                                  benchmark=e.benchmark))
            run_info = ezbench.run_commits([e.commit], [e.benchmark + '$'], rounds=e.rounds)
            if run_info.success():
                continue

            # We got an error, let's see what we can do about it!
            if run_info.exit_code.value < 40:
                # Error we cannot do anything about, probably a setup issue
                # Let's mark the run as aborted until the user resets it!
                self.set_running_mode(RunningMode.ERROR)
            #elif run_info.exit_code == EzbenchExitCode.COMPILATION_FAILED:
                # TODO:Mark the commit as broken

        self.__log(Criticality.II, "Done")

        return True

    def git_history(self):
        git_history = list()

        # Get the repo directory
        ezbench = self.__create_ezbench()
        run_info = ezbench.run_commits(["HEAD"], [], [], dry_run=True)

        if not run_info.success():
            return git_history

        # Get the list of commits and store their position in the list in a dict
        output = subprocess.check_output(["/usr/bin/git", "log", "--format=%h %ct"],
                                          cwd=run_info.repo_dir).decode().split('\n')

        GitCommit = namedtuple('GitCommit', 'sha1 timestamp')
        for line in output:
            fields = line.split(' ')
            if len(fields) == 2:
                git_history.append(GitCommit(fields[0], fields[1]))

        return git_history

    def report(self, git_history=list(), reorder_commits = True):
        if reorder_commits and git_history is None:
            git_history = self.git_history()

        # Generate the report, order commits based on the git history
        r = genPerformanceReport(self.log_folder, silentMode = True)
        r.enhance_report([c.sha1 for c in git_history])
        return r

    def __find_middle_commit(self, git_history, old, new, msg):
        old_idx = git_history.index(old)
        new_idx = git_history.index(new)
        middle_idx = int(old_idx - ((old_idx - new_idx) / 2))
        if middle_idx != old_idx and middle_idx != new_idx:
            middle = git_history[middle_idx]
            log = "{} between commits {}({}) and {}({}), would bisect using commit {}({})"
            self.__log(Criticality.WW,
                        log.format(msg, old, old_idx, new, new_idx, middle, middle_idx))
            return middle
        else:
            self.__log(Criticality.WW,
                       "{} due to commit '{}'".format(msg, new))
            return None

    def schedule_enhancements(self, git_history=None, perf_change_threshold=0.05):
        # Generate the report, order commits based on the git history
        if git_history is None:
            git_history = self.git_history()
        commits_rev_order = [c.sha1 for c in git_history]
        r = genPerformanceReport(self.log_folder, silentMode = True)
        r.enhance_report(commits_rev_order)

        # Check all the commits
        bench_prev = dict()
        commit_prev = None
        last_commit_good = None
        runs_not_run = []
        tasks = []
        for commit in r.commits:
            # Look for compilation errors
            if ((commit.compil_exit_code > 0 and commit_prev is not None and
                 commit_prev.compil_exit_code == 0) or
               (commit.compil_exit_code == 0 and commit_prev is not None and
                 commit_prev.compil_exit_code > 0)):
                if commit.compil_exit_code > 0:
                    msg = "The build got broken"
                else:
                    msg = "The build got fixed"
                middle_commit = self.__find_middle_commit(commits_rev_order,
                                                          commit_prev.sha1,
                                                          commit.sha1, msg)
                if middle_commit is not None:
                    self.force_benchmark_rounds(middle_commit, "no-op", 1)
                elif commit.compil_exit_code > 0:
                    # The current commit introduced a build failure, mark
                    # the previous commit as being the last known-good
                    last_commit_good = commit_prev
                else:
                    # The current commit fixed a build failure, we do not need
                    # to mark that the build is broken anymore and add all the
                    # benchmark runs that were found in the range of unbuildable
                    # commits.
                    last_commit_good = None
                    for run in runs_not_run:
                        self.force_benchmark_rounds(commit.sha1, run[0], run[1])

            # If the current commit refuses to build, move the benchmarks we were
            # supposed to run to the last commit before it got broken
            if commit.compil_exit_code > 0 and last_commit_good is not None:
                for benchmark in self.state['commits'][commit.sha1]['benchmarks']:
                    rounds = self.state['commits'][commit.sha1]['benchmarks'][benchmark]['rounds']
                    self.force_benchmark_rounds(last_commit_good.sha1, benchmark, rounds)
                    runs_not_run.append((benchmark, rounds))

            # Look for performance regressions
            for result in commit.results:
                perf = sum(result.data) / len(result.data)
                bench = result.benchmark.full_name
                bench_unit = result.benchmark.unit_str
                if result.benchmark.full_name in bench_prev:
                    # We got previous perf results, compare!
                    old_commit = bench_prev[bench][0]
                    old_perf = bench_prev[bench][1]
                    diff = perf / old_perf

                    if (diff > (1 + perf_change_threshold) or
                        diff < (1 - perf_change_threshold)):
                        msg = "Bench '{}' went from {} to {} {}".format(bench, round(old_perf, 2),
                                                                        round(perf, 2), bench_unit)
                        middle_commit = self.__find_middle_commit(commits_rev_order, old_commit,
                                                                  commit.sha1, msg)
                        if middle_commit is not None:
                            # TODO: Figure out how many runs we need based on the variance
                            # In the mean time, re-use the same number of runs
                            tasks.append((abs(diff - 1), middle_commit, bench, len(result.data)))

                bench_prev[bench] = (commit.sha1, perf)
            commit_prev = commit

        # Only schedule the commit with the most important perf change to
        # speed up the bisecting process
        tasks_sorted = sorted(tasks, key=lambda t: t[0])
        if len(tasks_sorted) > 0:
            commit = tasks_sorted[-1][1]
            for t in tasks_sorted:
                if t[1] == commit:
                    self.force_benchmark_rounds(t[1], t[2], t[3])

# Report parsing
class Benchmark:
    def __init__(self, full_name, unit="undefined"):
        self.full_name = full_name
        self.prevValue = -1
        self.unit_str = unit

class BenchResult:
    def __init__(self, commit, benchmark, data_raw_file):
        self.commit = commit
        self.benchmark = benchmark
        self.data_raw_file = data_raw_file
        self.data = []
        self.runs = []
        self.env_files = []
        self.unit_str = None

class Commit:
    def __init__(self, sha1, full_name, compile_log, patch, label):
        self.sha1 = sha1
        self.full_name = full_name
        self.compile_log = compile_log
        self.patch = patch
        self.results = []
        self.geom_mean_cache = -1
        self.label = label

        # Set default values then parse the patch
        self.full_sha1 = sha1
        self.author = "UNKNOWN AUTHOR"
        self.commiter = "UNKNOWN COMMITER"
        self.author_date = datetime.min
        self.commit_date = datetime.min
        self.title = ''
        self.commit_log = ''
        self.signed_of_by = set()
        self.reviewed_by = set()
        self.tested_by = set()
        self.bugs = set()
        try:
            with open(patch, 'r') as f:
                log_started = False
                fdo_bug_re = re.compile('fdo#(\d+)')
                basefdourl = "https://bugs.freedesktop.org/show_bug.cgi?id="
                for line in f:
                    line = line.strip()
                    if line == "---": # Detect the end of the header
                        break
                    elif line.startswith('commit'):
                        self.full_sha1 = line.split(' ')[1]
                    elif line.startswith('Author:'):
                        self.author = line[12:]
                    elif line.startswith('AuthorDate: '):
                        self.author_date = datetime.fromtimestamp(mktime_tz(parsedate_tz(line[12:])))
                    elif line.startswith('Commit:'):
                        self.commiter = line[12:]
                    elif line.startswith('CommitDate: '):
                        self.commit_date = datetime.fromtimestamp(mktime_tz(parsedate_tz(line[12:])))
                    elif line == '':
                        # The commit log is about to start
                        log_started = True
                    elif log_started:
                        if self.title == '':
                            self.title = line
                        else:
                            self.commit_log += line + '\n'
                            if line.startswith('Reviewed-by: '):
                                self.reviewed_by |= {line[13:]}
                            elif line.startswith('Signed-off-by: '):
                                self.signed_of_by |= {line[15:]}
                            elif line.startswith('Tested-by: '):
                                self.tested_by |= {line[11:]}
                            elif line.startswith('Bugzilla: '):
                                self.bugs |= {line[10:]}
                            elif line.startswith('Fixes: '):
                                self.bugs |= {line[7:]}
                            else:
                                fdo_bug_m = fdo_bug_re.search(line)
                                if fdo_bug_m is not None:
                                    bugid = fdo_bug_m.groups()[0]
                                    self.bugs |= {basefdourl + bugid}
        except IOError:
            pass

        # Look for the exit code
        self.compil_exit_code = -1
        try:
            with open(compile_log, 'r') as f:
                for line in f:
                    pass
                # Line contains the last line of the report, parse it
                if line.startswith("Exiting with error code "):
                    self.compil_exit_code = int(line[24:])
        except IOError:
            pass

    def build_broken(self):
        return (self.compil_exit_code >= EzbenchExitCode.COMP_DEP_UNK_ERROR.value and
                self.compil_exit_code <= EzbenchExitCode.DEPLOYMENT_ERROR.value)

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

class EventCommitRange:
    def __init__(self, old, new = None):
        self.old = old
        if new is None:
            self.new = old
        else:
            self.new = new

    def is_single_commit(self):
        return self.distance() <= 1

    def distance(self):
        if self.old is not None:
            return self.old.git_distance_head - self.new.git_distance_head
        else:
            return sys.maxsize

    def __str__(self):
        if self.new == None:
            return "commit {}".format(self.old.sha1)

        if self.is_single_commit():
            return "commit {}".format(self.new.sha1)
        elif self.old is not None:
            return "commit range {}:{}({})".format(self.old.sha1, self.new.sha1,
                                                   self.distance())
        else:
            return "commit before {}".format(self.new.sha1)


        float("inf")

class EventBuildBroken:
    def __init__(self, commit_range):
        self.commit_range = commit_range

    def __str__(self):
        return "{} broke the build".format(self.commit_range)

class EventBuildFixed:
    def __init__(self, broken_commit_range, fixed_commit_range):
        self.broken_commit_range = broken_commit_range
        self.fixed_commit_range = fixed_commit_range

    def broken_for_time(self):
        if (self.broken_commit_range.new.commit_date > datetime.min and
            self.fixed_commit_range.old.commit_date > datetime.min):
            attrs = ['years', 'months', 'days', 'hours', 'minutes', 'seconds']
            human_readable = lambda delta: ['%d %s' % (getattr(delta, attr),
                                                       getattr(delta, attr) > 1 and attr or attr[:-1])
                for attr in attrs if getattr(delta, attr)]
            res=', '.join(human_readable(relativedelta.relativedelta(self.fixed_commit_range.old.commit_date,
                                                                     self.broken_commit_range.new.commit_date)))
            if len(res) == 0:
                return "0 seconds"
            else:
                return res
        return None

    def broken_for_commit_count(self):
        return (self.broken_commit_range.new.git_distance_head -
                self.fixed_commit_range.new.git_distance_head)

    def __str__(self):
        parenthesis = ""
        if (not self.broken_commit_range.is_single_commit() or
            not self.fixed_commit_range.is_single_commit()):
            parenthesis = "at least "
        parenthesis += "for "

        time = self.broken_for_time()
        if time is not None and time != "":
            parenthesis += time + " and "
        parenthesis += "{} commits".format(self.broken_for_commit_count())

        main = "{} fixed the build regression introduced by {}"
        main = main.format(self.fixed_commit_range, self.broken_commit_range)
        return "{} ({})".format(main, parenthesis)


class Report:
    def __init__(self, benchmarks, commits, notes):
        self.benchmarks = benchmarks
        self.commits = commits
        self.notes = notes
        self.events = list()

    def enhance_report(self, commits_rev_order):
        if len(commits_rev_order) == 0:
            return

        # Get rid of the commits that are not in the commits list
        to_del = list()
        for c in range(0, len(self.commits)):
            if self.commits[c].sha1 not in commits_rev_order:
                to_del.append(c)
        for v in reversed(to_del):
            del self.commits[v]

        # Add the index inside the commit
        for commit in self.commits:
            commit.git_distance_head = commits_rev_order.index(commit.sha1)

        # Sort the remaining commits
        self.commits.sort(key=lambda commit: len(commits_rev_order) - commit.git_distance_head)

        # Generate events
        commit_prev = None
        build_broken_since = None
        for commit in self.commits:
            commit_range = EventCommitRange(commit_prev, commit)

            # Look for compilation errors
            if commit.build_broken() and build_broken_since is None:
                self.events.append(EventBuildBroken(commit_range))
                build_broken_since = EventCommitRange(commit_prev, commit)
            elif not commit.build_broken() and build_broken_since is not None:
                self.events.append(EventBuildFixed(build_broken_since, commit_range))
                build_broken_since = None

            commit_prev = commit

def readCsv(filepath):
    data = []

    h1 = re.compile('^# (.*) of \'(.*)\' using commit (.*)$')
    h2 = re.compile('^# (.*) \\((.*) is better\\) of \'(.*)\' using commit (.*)$')

    with open(filepath, 'rt') as f:
        reader = csv.reader(f)
        unit = None
        more_is_better = True
        try:
            for row in reader:
                if row is None or len(row) == 0:
                    continue

                # try to extract information from the header
                m1 = h1.match(row[0])
                m2 = h2.match(row[0])
                if m2 is not None:
                    # groups: unit type, more|less qualifier, benchmark, commit_sha1
                    unit = m2.groups()[0]
                    more_is_better = m2.groups()[1].lower() == "more"
                elif m1 is not None:
                    # groups: unit type, benchmark, commit_sha1
                    unit = m1.groups()[0]

                # Read the actual data
                if len(row) > 0 and not row[0].startswith("# "):
                    try:
                        data.append(float(row[0]))
                    except ValueError as e:
                        sys.stderr.write('Error in file %s, line %d: %s\n' % (filepath, reader.line_num, e))
        except csv.Error as e:
            sys.stderr.write('file %s, line %d: %s\n' % (filepath, reader.line_num, e))
            return [], "none"

    return data, unit, more_is_better

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

def genPerformanceReport(log_folder, silentMode = False):
    benchmarks = []
    commits = []
    labels = dict()
    notes = []

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
        if not silentMode:
            sys.stderr.write("The log folder '{0}' does not contain a commit_list file\n".format(log_folder))
        return Report(benchmarks, commits, notes)

    # Read all the commits' labels
    labels = readCommitLabels()

    # Check that there are commits
    if (len(commitsLines) == 0):
        if not silentMode:
            sys.stderr.write("The commit_list file is empty\n")
        return Report(benchmarks, commits, notes)

    # Gather all the information from the commits
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

            # Skip on unrelated files
            if "." in benchFile:
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
            result.data, result.unit_str, result.more_is_better = readCsv(benchFile)
            if len(result.data) == 0:
                continue

            # Check that the result file has the same default v
            if benchmark.unit_str != result.unit_str:
                if benchmark.unit_str != "undefined":
                    msg = "The unit used by the benchmark '{bench}' changed from '{unit_old}' to '{unit_new}' in commit {commit}"
                    print(msg.format(bench=bench_name,
                                     unit_old=benchmark.unit_str,
                                     unit_new=result.unit_str,
                                     commit=commit.sha1))
                benchmark.unit_str = result.unit_str

            # Look for the runs
            runsFiles = [f for f in os.listdir() if re.search(r'^{benchFile}#[0-9]+$'.format(benchFile=benchFile), f)]
            runsFiles.sort(key=lambda x: '{0:0>100}'.format(x).lower()) # Sort the runs in natural order
            for runFile in runsFiles:
                data, unit, more_is_better = readCsv(runFile)
                if len(data) > 0:
                    # Add the FPS readings of the run
                    result.runs.append(data)

                    # Add the environment file
                    envFile = runFile + ".env_dump"
                    if not os.path.isfile(envFile):
                        envFile = None
                    result.env_files.append(envFile)

            # Add the result to the commit's results
            commit.results.append(result)
            commit.compil_exit_code = 0 # The deployment must have been successful if there is data

        # Add the commit to the list of commits
        commit.results = sorted(commit.results, key=lambda res: res.benchmark.full_name)
        commits.append(commit)

    # Sort the list of benchmarks
    benchmarks = sorted(benchmarks, key=lambda bench: bench.full_name)

    # Read the notes before going back to the original folder
    notes = readNotes()

    # Go back to the original folder
    os.chdir(cwd)

    return Report(benchmarks, commits, notes)

def getPerformanceResultsCommitBenchmark(commit, benchmark):
    for result in commit.results:
        if result.benchmark != benchmark:
            continue

        return array(result.data)

    return array([])

def getResultsBenchmarkDiffs(commits, benchmark):
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

def getResultsGeomDiffs(commits):
    results = []

    # Compute a report per application
    i = 0
    origValue = -1
    for commit in commits:
        value = commit.geom_mean()
        if origValue > -1:
            diff = (value * 100.0 / origValue) - 100.0
        else:
            origValue = value
            diff = 0

        results.append([i, diff])
        i = i + 1

    return results

def convert_unit(value, input_unit, output_type):
	ir_fps = -1.0

	if input_unit == output_type:
		return value

	if input_unit == "ms":
		ir_fps = 1.0e3 / value
	elif input_unit == "us":
		ir_fps = 1.0e6 / value
	elif input_unit.lower() == "fps":
		ir_fps = value

	if ir_fps == -1:
		print("convert_unit: Unknown input type " + input_type)
		return value

	if output_type == "ms":
		return 1.0e3 / ir_fps
	elif output_type == "us":
		return 1.0e6 / ir_fps
	elif output_type.lower() == "fps":
		return ir_fps

	print("convert_unit: Unknown output type " + output_type)
	return value
