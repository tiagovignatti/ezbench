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
#       - 14: Missing repository directory
#
#   OS:
#       - 30: The shell does not support globstat
#       - 31: Cannot create the log folder
#       - 32: Cannot move to the repo directory
#
#   Git:
#       - 50: Invalid version ID
#
#   Environment:
#       - 60: Failed to deploy the environment
#
#   Compilation & deployment:
#       - 70: Compilation or deployment failed
#       - 71: Compilation failed
#       - 72: Deployment failed
#       - 73: The deployed version does not match the wanted version
#       - 74: A reboot is necessary
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
        run_log_file_env_dump="$run_log_file"
        env_dump_launch="$ezBenchDir/utils/env_dump/env_dump.sh"
        cmd="$cmd $env_dump_launch "$run_log_file" $@"
    else
        cmd="$cmd $@"
    fi

    run_log_file_stdout="$run_log_file.stdout"
    run_log_file_stderr="$run_log_file.stderr"

    callIfDefined run_bench_pre_hook
    local time_before=$(date +%s.%N)
    eval $cmd > "$run_log_file_stdout" 2> "$run_log_file_stderr"
    local exit_code=$?
    local time_after=$(date +%s.%N)
    local test_exec_time=$(echo "$time_after - $time_before" | bc -l)
    callIfDefined run_bench_post_hook

    if [ -f "$env_dump_path" ]; then
        $ezBenchDir/utils/env_dump/env_dump_extend.sh "$SHA1_DB" "$run_log_file.env_dump"
    fi

    # delete the log files if they are empty
    if [ ! -s "$run_log_file_stdout" ] ; then
        rm "$run_log_file_stdout"
    else
        cat "$run_log_file_stdout"
    fi
    if [ ! -s "$run_log_file_stderr" ] ; then
        rm "$run_log_file_stderr"
    else
        cat "$run_log_file_stderr" >&2
    fi

    echo "EZBENCH:test_exec_time:$test_exec_time"
    return $exit_code
}

function display_repo_info() {
    local type=$(profile_repo_type)
    local vh=$(profile_repo_version)
    local dv=$(profile_repo_deployed_version)
    echo "Repo type = $type, directory = $repoDir, version = $vh, deployed version = $dv"
}

function available_tests {
    # Generate the list of available tests
    echo -n "Available tests: "
    for (( t=0; t<${#availTestNames[@]}; t++ )); do
        echo -n "${availTestNames[$t]} "
    done
    echo
}
function callIfDefined() {
    if [ "$(type -t "$1")" == 'function' ]; then
        local funcName=$1
        shift
        $funcName "$@"
        return 0
    else
        return 1
    fi
}

function show_help {
    echo "    core.sh [list of SHA1]"
    echo ""
    echo "    Optional arguments:"
    echo "        -P <profile name>"
    echo "        -p <path_repo>"
    echo "        -r <benchmarking rounds> (default: 3)"
    echo "        -b <benchmark regexp> include these benchmarks to run"
    echo "        -B <benchmark regexp> exclude these benchamrks from running"
    echo "        -m <make and deploy command> (default: 'make -j8 install', '' to skip the compilation)"
    echo "        -N <log folder's name> (default: current date and time)"
    echo "        -T <path> source the test definitions from this folder"
    echo "        -k dry run, do not compile any version or execute any benchmark"
    echo "        -c configuration shell script to be run after user_parameters.sh"
    echo ""
    echo "    Other actions:"
    echo "        -h/?: Show this help message"
    echo "        -l: List the available tests"
    echo "        -L: List the already-built versions (requires -P)"
}

# Read the user parameters
source "$ezBenchDir/user_parameters.sh"

# First find the profile, if it is set
optString="h?P:p:n:N:H:r:b:B:m:T:lLkc:"
profile="default"
list_built_versions=0
while getopts "$optString" opt; do
    case "$opt" in
    P)  profile=$OPTARG
        ;;
    L)  list_built_versions=1
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

# The profile name is valid, set some environment variables
PROFILE_TMP_BUILD_DIR="$DEPLOY_BASE_DIR/$profile/tmp"
PROFILE_DEPLOY_BASE_DIR="$DEPLOY_BASE_DIR/$profile/builds"
PROFILE_DEPLOY_DIR="$DEPLOY_BASE_DIR/$profile/cur"

# Default user options
for conf in $profileDir/conf.d/**/*.conf; do
    [ "$conf" = "$profileDir/conf.d/**/*.conf" ] && continue
    source "$conf"
done
source "$profileDir/profile"

if [ "$list_built_versions" -eq 1 ]; then
    display_repo_info
    echo -n "Available versions: "
    profile_get_built_versions
    echo ""
    exit 0
fi

# Parse the list of tests
typeset -A availTestNames
typeset -A availTestUnits
typeset -A availTestTypes
typeset -A availTestIsInvert
typeset -A availTestExecTime
for test_dir in ${testsDir:-$ezBenchDir/tests.d}; do
    for test_file in $test_dir/**/*.test; do
        unset test_name
        unset test_unit
        unset test_type
        unset test_invert
        unset test_exec_time

        source "$test_file" || continue

        # Sanity checks on the file
        [ -z "$test_name" ] && continue
        [ -z "$test_exec_time" ] && continue

        # Set the default unit to FPS
        [ -z "$test_unit" ] && test_unit="FPS"

        # Set the default type to bench
        [ -z "$test_type" ] && test_type="bench"

        for test in $test_name; do
            # TODO: Check that the run function exists

            idx=${#availTestNames[@]}
            availTestNames[$idx]=$test
            availTestUnits[$idx]=$test_unit
            availTestTypes[$idx]=$test_type
            availTestIsInvert[$idx]=$test_invert
            availTestExecTime[$idx]=$test_exec_time
        done
    done
done
unset test_name
unset test_unit
unset test_type
unset test_invert
unset test_exec_time

# Start again the argument parsing, this time with every option
unset OPTIND
typeset -A testsList
typeset -A testExcludeList
conf_scripts=""
while getopts "$optString" opt; do
    case "$opt" in
    h|\?)
        show_help
        exit 0
        ;;
    p)  repoDir=$OPTARG
        ;;
    N)  reportName=$OPTARG
        ;;
    r)  rounds=$OPTARG
        ;;
    b)  if [ "$OPTARG" != "-" ]; then
            idx=${#testsList[@]}
            testsList[$idx]="$OPTARG"
        else
            while read test; do
                idx=${#testsList[@]}
                testsList[$idx]="$test"
            done
        fi
        ;;
    B)  idx=${#testExcludeList[$@]}
        testExcludeList[$idx]="$OPTARG"
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
        conf_scripts="$conf_scripts $OPTARG"
        ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 13
      ;;
    esac
done
shift $((OPTIND-1))

# Show the configuration scripts used
echo "Configuration scripts used: $conf_scripts"

# Check the repo and display information about it
profile_repo_check
display_repo_info

# redirect the output to both a log file and stdout
if [ -z "$dry_run" ]
then
    logsFolder="$ezBenchDir/logs/${reportName:-$(date +"%Y-%m-%d-%T")}"
    [ -d $logsFolder ] || mkdir -p $logsFolder || exit 30
    exec > >(tee -a $logsFolder/results)
    exec 2>&1

    # generate the early-exit filename
    abortFile="$logsFolder/requestExit"
fi

# functions to call on exit
function __ezbench_finish__ {
    exitcode=$?
    action=$1

    # Execute the user-defined post hook
    callIfDefined ezbench_post_hook

    if [ "$action" == "reboot" ]
    then
        printf "Rebooting with error code 74\n"
        sudo reboot
    else
        printf "Exiting with error code $exitcode\n"
        exit $exitcode
    fi
}
trap __ezbench_finish__ EXIT
trap __ezbench_finish__ INT # Needed for zsh

# Execute the user-defined pre hook
callIfDefined ezbench_pre_hook

versionList=$(profile_get_version_list $@)
if [ $? -ne 0 ]; then
    echo $versionList
    exit 50
fi

# Get the list of commits that will need to be recompiled
compilations_needed=0
avail_versions=$(profile_get_built_versions)
for version in $versionList; do
    found=0
    for avail_version in $avail_versions; do
        if [ "$version" == "$avail_version" ]; then
            found=1
            break
        fi
    done

    if [ $found -eq "0" ]; then
        compilations_needed=$(($compilations_needed + 1))
    fi
done

# Seed the results with the last round?
versionListLog="$logsFolder/commit_list"
last_version=$(tail -1 "$versionListLog" 2>/dev/null | cut -f 1 -d ' ')

# Generate the actual list of tests
typeset -A testNames
typeset -A testSubTests
typeset -A testInvert
typeset -A testUnit
typeset -A testType
typeset -A testPrevFps
typeset -A testMissing
total_round_time=0
for (( t=0; t<${#testsList[@]}; t++ )); do
    test=${testsList[$t]}
    basetest=$(echo "$test" | cut -d [ -f 1)
    subtests=$(echo $test | cut -s -d '[' -f 2- | rev | cut -d ']' -f 2- | rev)

    # Try to find the test in the list of available tests
    found=0
    for (( a=0; a<${#availTestNames[@]}; a++ )); do
        if [[ ${availTestNames[$a]} =~ $basetest ]]; then
            found=1

            # We do not accept running subtests on non-complete matches of names
            [[ $basetest != ${availTestNames[$a]} && -n $subtests ]] && continue

            # Try to find the test in the list of blacklisted tests
            blacklisted=0
            for (( b=0; b<${#testExcludeList[@]}; b++ )); do
                if [[ "${availTestNames[$a]}" =~ "${testExcludeList[$b]}" ]]; then
                    blacklisted=1
                    break
                fi
            done
            [ $blacklisted -eq 1 ] && continue

            # TODO: Check that the test is not already scheduled

            # Add the test!
            total_tests=${#testNames[@]}
            testNames[$total_tests]="${availTestNames[$a]}"
            testSubTests[$total_tests]="$subtests"
            testUnit[$total_tests]="${availTestUnits[$a]}"
            testType[$total_tests]="${availTestTypes[$a]}"
            testInvert[$total_tests]="${availTestIsInvert[$a]}"

            last_result="$logsFolder/${last_version}_result_${basetest}"
            if [ -e "$last_result" ]; then
                testPrevFps[$total_tests]=$(cat "$last_result")
            fi
            unset last_result

            total_round_time=$(dc <<<"$total_round_time ${availTestExecTime[$a]} +p")
        fi
    done
    if [ $found -eq 0 ]; then
        idx=${#testMissing[@]}
        testMissing[$idx]=$basetest
    fi
done
total_round_time=$(printf '%.0f' "$total_round_time")
unset last_version

# Check if there are any tests that were not found
if [[ ${#testMissing[@]} > 0 ]]; then
    echo -n "The following tests are not available:"
    for (( t=0; t<${#testMissing[@]}; t++ )); do
        echo -n " ${testMissing[$t]}"
    done
    echo

    exit 100
fi

# Print the tests that will be executed
echo -n "Tests that will be run:"
for (( t=0; t<${#testNames[@]}; t++ )); do
    echo -n " ${testNames[$t]}"
    [ -n "${testSubTests[$t]}" ] && echo -n "[${testSubTests[$t]}]"
done
echo

# Set the average compilation time to 0 when we are not compiling
if [ -z "$makeAndDeployCmd" ]
then
    avgBuildTime=0

    # Since we cannot deploy a new version, we need to use the version that is
    # currently deployed
    if [ -n "$deployedVersion" ]
    then
        printf "WARNING: Cannot deploy new versions, forcing the version list to $deployedVersion\n"
        versionList=$deployedVersion
    fi
else
    avgBuildTime=$(profile_repo_compilation_time)
fi

# finish computing the list of versions
num_versions=$(wc -w <<< $versionList)
printf "Testing %d versions: %s\n" $num_versions "$(echo "$versionList" | tr '\n' ' ')"

# Estimate the execution time
secs=$(( ($total_round_time * $rounds) * $num_versions + $compilations_needed * $avgBuildTime))

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

function compile_and_deploy {
    # Accessible variables
    # $version     [RO]: SHA1 id of the current version
    # $versionName [RO]: Name of the version

    # early exit if the deployed version is the wanted version
    deployed_version=$(profile_repo_deployed_version)

    # Select the version of interest
    human_name=$(profile_repo_version_to_human "$version")
    if [ -z "$(grep ^"$version" "$versionListLog" 2> /dev/null)" ]
    then
        echo "$human_name" >> "$versionListLog"
    fi
    echo "$human_name"
    [ $? -eq 0 ] && [[ "$deployed_version" =~ "$version" ]] && return 0

    compile_logs=$logsFolder/${version}_compile_log

    profile_repo_get_patch $version > "$logsFolder/$1.patch"

    # Compile the version and check for failure. If it failed, go to the next version.
    export REPO_COMPILE_AND_DEPLOY_VERSION=$version
    eval "$makeAndDeployCmd" >> "$compile_logs" 2>&1
    local exit_code=$?
    unset REPO_COMPILE_AND_DEPLOY_VERSION

    # The exit code 74 actually means everything is fine but we need to reboot
    if [ $exit_code -eq 74 ]
    then
        printf "Exiting with error code 0\n" >> "$compile_logs"
    else
        printf "Exiting with error code $exit_code\n" >> "$compile_logs"
    fi

    # Check for compilation errors
    if [ "$exit_code" -ne '0' ]; then
        # Forward the error code from $makeAndDeployCmd if it is a valid error code
        if [ $exit_code -eq 71 ]; then
            component="Compilation"
        elif [ $exit_code -eq 72 ]; then
            component="Deployment"
        elif [ $exit_code -eq 74 ]; then
            __ezbench_finish__ "reboot"
        else
            exit_code=70
        fi

        printf "    ${c_bright_red}ERROR${c_reset}: $component failed, log saved in $compile_logs\n"
        exit $exit_code
    fi

    # Check that the deployed image is the right one
    deployed_version=$(profile_repo_deployed_version)
    if [ $? -eq 0 ] && [[ ! "$deployed_version" =~ "$version" ]]
    then
        printf "    ${c_bright_red}ERROR${c_reset}: The deployed version ($deployed_version) does not match the wanted one($version)\n"
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

# Execute the user-defined environment deployment hook
callIfDefined ezbench_env_deploy_hook

# Iterate through the versions
for version in $versionList
do
    # Exit if asked to
    [ -e "$abortFile" ] && continue

    # compile and deploy the version
    compile_and_deploy $version

    # Iterate through the tests
    fpsALL=""
    for (( t=0; t<${#testNames[@]}; t++ ));
    do
        benchName=${testNames[$t]}

        # Generate the logs file names
        fps_logs=$logsFolder/${version}_${testType[$t]}_${testNames[$t]}
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
            echo "# ${testUnit[$t]} ($direction) of '${testNames[$t]}' using version ${version}" > "$fps_logs"
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
            # Exit if asked to
            [ -e "$abortFile" ] && continue

            run_log_file="${fps_logs}#$c"
            IFS='|' read -a run_sub_tests <<< "${testSubTests[$t]}"

            callIfDefined "$preHookFuncName"
            callIfDefined benchmark_run_pre_hook

            # This function will return multiple fps readings
            "$runFuncName" > "$run_log_file" 2> /dev/null

            callIfDefined benchmark_run_post_hook
            callIfDefined "$postHookFuncName"

            if [ -s "$run_log_file" ]; then
                if [ ${testType[$t]} == "bench" ]; then
                    # Add the reported values before adding the result to the average values for
                    # the run.
                    run_avg=$(awk '{sum=sum+$1} END {print sum/NR}' $run_log_file)
                elif [ ${testType[$t]} == "unit" ]; then
                    run_avg=$(head -n 1 $run_log_file)
                fi
                echo "$run_avg" >> "$fps_logs"
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
        echo $result > $logsFolder/${version}_result_${testNames[$t]}
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
        printf "%9.2f ${testUnit[$t]} ($color%+.2f%%$c_reset): %s\n" "$result" "$fpsDiff" "$statistics"
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

rm $abortFile 2> /dev/null
if [ $? -eq 0 ]; then
	echo "Early exit requested"
fi

endTime=$(date +%s)
runtime=$((endTime-startTime))
printf "Actual run time: %02dh:%02dm:%02ds\n\n" $((runtime/3600)) $((runtime%3600/60)) $((runtime%60))
