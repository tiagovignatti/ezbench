#!/bin/bash

# Copyright (c) 2015, Intel Corporation
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Intel Corporation nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The script is known to work with recent versions of bash.
# Authors:
# - Martin Peres <martin.peres@intel.com>
# - Chris Wilson <chris@chris-wilson.co.uk>

# Error codes:
#   Argument parsing:
#       - 11: Need a profile name after the -P option
#       - 12: The profile does not exist
#       - 13: Missing optarg after a parameter
#       - 14: Missing git repository directory
#
#   OS:
#       - 30: The shell does not support globstat
#       - 31: Cannot create the log folder
#       - 32: Cannot move to the git repo directory
#
#   Git:
#       - 50: Unable to preserve dirty state of the repository
#       - 51: Invalid commit ID
#
#   Compilation & deployment:
#       - 70: Compilation or deployment failed
#       - 71: Compilation failed
#       - 72: Deployment failed
#       - 73: The deployed version does not match the wanted version
#
#   Tests:
#       - 100: At least one test does not exist
#

# Uncomment the following to track all the executed commands
#set -o xtrace

shopt -s globstar || {
    echo "ERROR: ezbench requires bash 4.0+ or zsh with globstat support."
    exit 30
}

# Printf complains about floating point numbers having , as a delimiter otherwise
LC_NUMERIC="C"

ezBenchDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# initial cleanup
mkdir "$ezBenchDir/logs" 2> /dev/null

# set the default run_bench function which can be overriden by the profiles:
# Bash variables: $run_log_file : filename of the log report of the current run
# Arguments: $1 : timeout (set to 0 for infinite wait)
#            $2+: command line executing the test AND NOTHING ELSE!
function run_bench {
    timeout=$1
    shift
    cmd="LIBGL_DEBUG=verbose vblank_mode=0 stdbuf -oL timeout $timeout"
    bench_binary=$(echo "$1" | rev | cut -d '/' -f 1 | rev)

    env_dump_path="$ezBenchDir/utils/env_dump/env_dump.so"
    if [ -f "$env_dump_path" ]; then
        run_log_file_env_dump="$run_log_file.env_dump"
        env_dump_launch="$ezBenchDir/utils/env_dump/env_dump.sh"
        cmd="$cmd $env_dump_launch $run_log_file_env_dump $@"
    else
        cmd="$cmd $@"
    fi

    run_log_file_stdout="$run_log_file.stdout"
    run_log_file_stderr="$run_log_file.stderr"
    if [ ! -z "$run_log_file" ]; then
        cmd="$cmd > >(tee $run_log_file_stdout) 2> >(tee $run_log_file_stderr >&2)"
    fi

    callIfDefined run_bench_pre_hook
    eval $cmd
    callIfDefined run_bench_post_hook

    if [ -f "$env_dump_path" ]; then
        $ezBenchDir/utils/env_dump/env_dump_extend.sh "$SHA1_DB" "$run_log_file_env_dump"
    fi

    # delete the log files if they are empty
    if [ ! -s "$run_log_file_stdout" ] ; then
        rm "$run_log_file_stdout"
    fi
    if [ ! -s "$run_log_file_stderr" ] ; then
        rm "$run_log_file_stderr"
    fi
}

# parse the options
function available_tests {
    # Generate the list of available tests
    echo -n "Available tests: "
    for test_dir in ${testsDir:-$ezBenchDir/tests.d}; do
        for test_file in $test_dir/**/*.test; do
            unset test_name
            unset test_exec_time

            source "$test_file" || continue
            [ -z "$test_name" ] && continue
            [ -z "$test_exec_time" ] && continue
            for t in $test_name; do
                echo -n "$t "
            done
        done
    done
    echo
}
function callIfDefined() {
    if [ "$(type -t "$1")" == 'function' ]; then
        local funcName=$1
        shift
        $funcName "$@"
    else
        return 1
    fi
}

function show_help {
    echo "    core.sh [list of SHA1]"
    echo ""
    echo "    Optional arguments:"
    echo "        -P <profile name>"
    echo "        -p <path_git_repo>"
    echo "        -r <benchmarking rounds> (default: 3)"
    echo "        -b <benchmark regexp> include these benchmarks to run"
    echo "        -B <benchmark regexp> exclude these benchamrks from running"
    echo "        -H <git-commit-id> benchmark the commits preceeding this one"
    echo "        -n <last n commits>"
    echo "        -m <make and deploy command> (default: 'make -j8 install', '' to skip the compilation)"
    echo "        -N <log folder's name> (default: current date and time)"
    echo "        -T <path> source the test definitions from this folder"
    echo "        -k dry run, do not compile any commit or execute any benchmark"
    echo "        -c configuration shell script to be run after user_parameters.sh"
    echo ""
    echo "    Other actions:"
    echo "        -h/?: Show this help message"
    echo "        -l: List the available tests"
}

# Read the user parameters
source "$ezBenchDir/user_parameters.sh"

# First find the profile, if it is set
optString="h?P:p:n:N:H:r:b:B:m:T:lkc:"
profile="default"
while getopts "$optString" opt; do
    case "$opt" in
    P)  profile=$OPTARG
        ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 11
      ;;
    esac
done

# Check if the profile exists
profileDir="$ezBenchDir/profiles.d/$profile"
if [ ! -d "$profileDir" ]; then
    echo "Profile '$profile' does not exist." >&2
    exit 12
fi

# Default user options
for conf in $profileDir/conf.d/**/*.conf; do
    [ "$conf" = "$ezBenchDir/conf.d/**/*.conf" ] && continue
    source "$conf"
done
source "$profileDir/profile"

# Start again the argument parsing, this time with every option
unset OPTIND
while getopts "$optString" opt; do
    case "$opt" in
    h|\?)
        show_help
        exit 0
        ;;
    p)  gitRepoDir=$OPTARG
        ;;
    n)  lastNCommits=$OPTARG
        ;;
    N)  reportName=$OPTARG
        ;;
    H)  uptoCommit=$OPTARG
        ;;
    r)  rounds=$OPTARG
        ;;
    b)  testsList="$testsList $OPTARG"
        ;;
    B)  testExcludeList="$testExcludeList $OPTARG"
        ;;
    m)  makeAndDeployCmd=$OPTARG
        ;;
    T)  testsDir="$testsDir $OPTARG"
        ;;
    l)
        available_tests
        exit 0
        ;;
    k)
        dry_run=1
        ;;
    c)
        source "$OPTARG"
        ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 13
      ;;
    esac
done
shift $((OPTIND-1))

# redirect the output to both a log file and stdout
if [ -z "$dry_run" ]
then
    logsFolder="$ezBenchDir/logs/${reportName:-$(date +"%Y-%m-%d-%T")}"
    [ -d $logsFolder ] || mkdir -p $logsFolder || exit 30
    exec > >(tee -a $logsFolder/results)
    exec 2>&1
fi

function read_git_version_deployed() {
    if [ -n "$gitVersionDeployedCmd" ]
    then
        eval "$gitVersionDeployedCmd"
        return $?
    fi
    return 1
}

# Check the git repo, saving then displaying the HEAD commit
if [ -z "$gitRepoDir" ]
then
    echo "ERROR: You did not specify a git repository path (-p). Aborting..."
    exit 14
fi
cd "$gitRepoDir" || exit 1
commit_head=$(git rev-parse HEAD 2>/dev/null)
if [ $? -ne 0 ]
then
    echo "ERROR: The path '$gitRepoDir' does not contain a valid git repository. Aborting..."
    exit 1
fi
printf "Original commit = $commit_head"

deployedVersion=$(read_git_version_deployed)
[ $? -eq 0 ] && printf ", deployed version = $deployedVersion"
echo

# Preserve any local modifications
stash=$(git stash create)
if [ $? -ne 0 ]
then
    echo "ERROR: Unable to preserve dirty state in '$gitRepoDir'. Aborting..."
    exit 50
fi
[ -n "$stash" ] && echo "Preserving work-in-progress"

commitList=
for id in "$@"; do
    if [[ $id =~ \.\. ]]; then
        commitList+=$(git rev-list --abbrev-commit --reverse "$id" 2> /dev/null)
    else
        commitList+=$(git rev-list --abbrev-commit -n 1 "$(git rev-parse "$id" 2> /dev/null)" 2> /dev/null)
    fi
    [ $? -ne 0 ] && printf "ERROR: Invalid commit ID '$id'\n" && exit 51
    commitList+=" "
done

# function to call on exit
function finish {
    # to be executed on exit, possibly twice!
    git reset --hard "$commit_head" 2> /dev/null
    [ -n "$stash" ] && git stash apply "$stash" > /dev/null

    # Execute the user-defined post hook
    callIfDefined ezbench_post_hook
}
trap finish EXIT
trap finish INT # Needed for zsh

# Execute the user-defined pre hook
callIfDefined ezbench_pre_hook

# Seed the results with the last round?
commitListLog="$logsFolder/commit_list"
last_commit=$(tail -1 "$commitListLog" 2>/dev/null | cut -f 1 -d ' ')

# Generate the actual list of tests
typeset -A testNames
typeset -A testInvert
typeset -A testPrevFps
typeset -A testFilter
total_tests=0
total_round_time=0
echo -n "Tests that will be run: "
for test_dir in ${testsDir:-$ezBenchDir/tests.d}; do
    for test_file in $test_dir/**/*.test; do
        unset test_name
        unset test_unit
        unset test_invert
        unset test_exec_time

        source "$test_file" || continue

        for t in $test_name; do
            # Check that the user wants this test or not
            found=1
            if [ -n "$testsList" ]; then
                found=0
                for filter in $testsList; do
                    if [[ $t =~ $filter ]]; then
                        testFilter[$filter]=1
                        found=1
                        break
                    fi
                done
            fi
            if [ -n "$testExcludeList" ]; then
                for filter in $testExcludeList; do
                    if [[ $t =~ $filter ]]; then
                        testFilter[$filter]=-1
                        found=0
                        break
                    fi
                done
            fi
            [ $found -eq 0 ] && continue

            # Set the default unit to FPS
            [ -z "$test_unit" ] && test_unit="FPS"

            testNames[$total_tests]=$t
            testUnit[$total_tests]=$test_unit
            testInvert[$total_tests]=$test_invert

            last_result="$logsFolder/${last_commit}_result_${t}"
            if [ -e "$logsFolder/${last_commit}_result_${t}" ]; then
                testPrevFps[$total_tests]=$(cat "$last_result")
            fi
            unset last_result

            echo -n "${testNames[$total_tests]} "

            total_round_time=$(dc <<<"$total_round_time $test_exec_time + p")
            total_tests=$(( total_tests + 1))
        done
    done
done
total_round_time=${total_round_time%.*}
echo
unset last_commit

missing_tests=
for t in $testsList; do
    [ -z ${testFilter[$t]} ] && missing_tests+="$t "
done
if [ -n "$missing_tests" ]; then
    echo "The tests \"${missing_tests:0:-1}\" do not exist"
    available_tests
    exit 101
fi

# Set the average compilation time to 0 when we are not compiling
if [ -z "$makeAndDeployCmd" ]
then
    avgBuildTime=0
else
    avgBuildTime=$(git config --get ezbench.average-build-time 2>/dev/null || echo 30)
fi

# finish computing the list of commits
if [ -z "$commitList" ]; then
    commitList=$(git rev-list --abbrev-commit --reverse -n "${lastNCommits}" "${uptoCommit}")
    [ "${uptoCommit}" == "HEAD" ] && commitList="${commitList} ${stash}"
fi
num_commits=$(wc -w <<< $commitList)
printf "Testing %d commits: %s\n" $num_commits "$(echo "$commitList" | tr '\n' ' ')"

# Estimate the execution time
secs=$(( ($total_round_time * $rounds + $avgBuildTime) * $num_commits))
finishDate=$(date +"%y-%m-%d - %T" --date="$secs seconds")
printf "Estimated finish date: $finishDate (%02dh:%02dm:%02ds)\n\n" $(($secs/3600)) $(($secs%3600/60)) $(($secs%60))
startTime=`date +%s`

# ANSI colors
c_red='\e[31m'
c_bright_red='\e[1;31m'
c_bright_green='\e[1;32m'
c_bright_yellow='\e[1;33m'
c_bright_white='\e[1;37m'
c_reset='\e[0m'

bad_color=$c_bright_red
good_color=$c_bright_green
meh_color=$c_bright_yellow

function compile {
    # Accessible variables
    # $commit     [RO]: SHA1 id of the current commit
    # $commitName [RO]: Name of the commit

    [ -z "$makeAndDeployCmd" ] && return 0

    # early exit if the deployed version is the wanted commit
    version=$(read_git_version_deployed)
    [ $? -eq 0 ] && [[ "$version" =~ "$commit" ]] && return 0

    # Call the user-defined pre-compile hook
    callIfDefined compile_pre_hook

    # Compile the commit and check for failure. If it failed, go to the next commit.
    compile_logs=$logsFolder/${commit}_compile_log
    compile_start=$(date +%s)
    eval "$makeAndDeployCmd" > "$compile_logs" 2>&1
    local exit_code=$?
    compile_end=$(date +%s)
    if [ "$exit_code" -ne '0' ]; then
        git reset --hard HEAD~ > /dev/null 2> /dev/null

        # Forward the error code from $makeAndDeployCmd if it is a valid error code
        if [ $exit_code -eq 71 ]; then
            component="Compilation"
        elif [ $exit_code -eq 72 ]; then
            component="Deployment"
        else
            exit_code=70
        fi

        printf "    ${c_bright_red}ERROR${c_reset}: $component failed, log saved in $compile_logs\n"
        exit $exit_code
    fi

    # Update our build time estimator
    avgBuildTime=$(bc <<< "0.75*$avgBuildTime + 0.25*($compile_end - $compile_start)")
    git config --replace-all ezbench.average-build-time "$(printf "%.0f" "$avgBuildTime")"

    # Call the user-defined post-compile hook
    callIfDefined compile_post_hook

    # Check that the deployed image is the right one
    version=$(read_git_version_deployed)
    if [ $? -eq 0 ] && [[ ! "$version" =~ "$commit" ]]
    then
        printf "    ${c_bright_red}ERROR${c_reset}: The deployed version ($version) does not match the wanted one($commit)\n"
        exit 73
    fi

}

if [ $rounds -eq 0 ]
then
    echo "Nothing to do (rounds == 0), exit."
    exit 0
fi

if [ -n "$dry_run" ]
then
    echo "Dry-run mode, exit."
    exit 0
fi

# Iterate through the commits
for commit in $commitList
do
    # save the commit in the commit_list

    # Make sure we are in the right folder
    cd "$gitRepoDir" || exit 31

    # Select the commit of interest
    if [ "$commit" == "$stash" ]
    then
        git reset --hard "$commit_head" > /dev/null
        git stash apply "$stash" > /dev/null
        echo -e "${c_bright_yellow}WIP${c_reset}"
        echo "$commit" >> "$commitListLog"
        git diff > "$logsFolder/${commit}.patch"
    else
        git reset --hard "$commit" > /dev/null
        git show --format="%Cblue%h%Creset %Cgreen%s%Creset" -s
        if [ -z "$(grep ^"$commit" "$commitListLog" 2> /dev/null)" ]
        then
            git show --format="%h %s" -s >> "$commitListLog"
        fi
        git format-patch HEAD~ --format=fuller --stdout > "$logsFolder/${commit}.patch"
    fi

    compile

    # Iterate through the tests
    fpsALL=""
    for (( t=0; t<${#testNames[@]}; t++ ));
    do
        benchName=${testNames[$t]}

        # Generate the logs file names
        fps_logs=$logsFolder/${commit}_bench_${testNames[$t]}
        error_logs=${fps_logs}.errors

        # Find the first run id available
        if [ -f "$fps_logs" ]; then
            # The logs file exist, look for the number of runs
            run=0
            while [ -f "${fps_logs}#${run}" ]
            do
                run=$((run+1))
            done
        else
            if [ -z "${testInvert[$t]}" ]; then
                direction="more is better"
            else
                direction="less is better"
            fi
            echo "# ${testUnit[$t]} ($direction) of '${testNames[$t]}' using commit ${commit}" > "$fps_logs"
            run=0
        fi

        # display the run name
        printf "%28s: " "${testNames[$t]}"

        # compute the different hook names
        runFuncName=${testNames[$t]}_run
        preHookFuncName=${testNames[$t]}_run_pre_hook
        postHookFuncName=${testNames[$t]}_run_post_hook
        processHookFuncName=${testNames[$t]}_process

        # Run the benchmark
        for (( c=$run; c<$run+$rounds; c++ ))
        do
            run_log_file="${fps_logs}#$c"

            callIfDefined "$preHookFuncName"
            callIfDefined benchmark_run_pre_hook

            # This function will return multiple fps readings
            "$runFuncName" > "$run_log_file" 2> /dev/null

            callIfDefined benchmark_run_post_hook
            callIfDefined "$postHookFuncName"

            if [ -s "$run_log_file" ]; then
                # Add the fps values before adding the result to the average fps for
                # the run.
                fps_avg=$(awk '{sum=sum+$1} END {print sum/NR}' $run_log_file)
                echo "$fps_avg" >> "$fps_logs"
            else
                echo "0" >> "$run_log_file"
                echo "0" >> "$fps_logs"
            fi
        done

        # Process the data ourselves
        output=$(tail -n +2 "$fps_logs") # Read back the data, minus the header
        statistics=
        result=$(callIfDefined "$processHookFuncName" "$output") || {
            statistics=$(echo "$output" | "$ezBenchDir/fps_stats.awk")
            result=$(echo "$statistics" | cut -d ' ' -f 1)
            statistics=$(echo "$statistics" | cut -d ' ' -f 2-)
        }
        echo $result > $logsFolder/${commit}_result_${testNames[$t]}
        if [ -z "${testPrevFps[$t]}" ]; then
            testPrevFps[$t]=$result
        fi
        if [ -z "${testInvert[$t]}" ]; then
            fpsDiff=$(echo "scale=3;($result * 100.0 / ${testPrevFps[$t]}) - 100" | bc 2>/dev/null)
        else
            fpsDiff=$(echo "scale=3;(100.0 * ${testPrevFps[$t]} / $result) - 100" | bc 2>/dev/null)
        fi
        [ $? -eq 0 ] && testPrevFps[$t]=$result
        if (( $(bc -l <<< "$fpsDiff < -1.5" 2>/dev/null || echo 0) )); then
            color=$bad_color
        elif (( $(bc -l <<< "$fpsDiff > 1.5" 2>/dev/null || echo 0) )); then
            color=$good_color
        else
            color="$meh_color"
        fi
        printf "%9.2f ($color%+.2f%%$c_reset): %s\n" "$result" "$fpsDiff" "$statistics"
        [ -z "$result" ] || fpsALL="$fpsALL $result"
    done

    # finish with the geometric mean (when we have multiple tests)
    if [ $t -gt 1 ]; then
        fpsALL=$(awk '{r=0; for(i=1; i<=NF; i++) { r += log($i) } print exp(r / NF) }' <<< $fpsALL)
        if [ -z "${testPrevFps[-1]}" ]; then
            testPrevFps[-1]=$fpsALL
        fi
        fpsDiff=$(echo "scale=3;($fpsALL * 100.0 / ${testPrevFps[-1]}) - 100" | bc 2>/dev/null)
        [ $? -eq 0 ] && testPrevFps[-1]=$fpsALL
        if (( $(bc -l <<< "$fpsDiff < -1.5" 2>/dev/null || echo 0) )); then
                color=$bad_color
        elif (( $(bc -l <<< "$fpsDiff > 1.5" 2>/dev/null || echo 0) )); then
                color=$good_color
        else
                color="$meh_color"
        fi
        printf "$c_bright_white%28s: %9.2f ($color%+.2f%%$c_bright_white)$c_reset\n"  \
                "geometric mean" \
                "$fpsALL" \
                "$fpsDiff"
    fi
    echo
done

endTime=$(date +%s)
runtime=$((endTime-startTime))
printf "Actual run time: %02dh:%02dm:%02ds\n\n" $((runtime/3600)) $((runtime%3600/60)) $((runtime%60))
