#!/bin/bash

# Thanks to stack overflow for writing most of this script! It has been tested with bash and zsh only!
# Author: Martin Peres <martin.peres@free.fr>

#set -o xtrace

#Default values
rounds=3
avgBuildTime=30
makeCommand="make -j8 install"
lastNCommits=
gitRepoDir=''
ezBenchDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# Default user options
source "$ezBenchDir/test_options.sh"

# initial cleanup
mkdir $ezBenchDir/logs/ 2> /dev/null

# Generate the list of available tests
typeset -A availTests
i=0
for test_file in $ezBenchDir/tests.d/*.test
do
    unset test_name
    unset test_exec_time

    source $test_file || continue
    if [ -z "$test_name" ]; then continue; fi
    if [ -z "$test_exec_time" ]; then continue; fi
    availTests[$i]=$test_name
    i=$(($i+1))
done

# parse the options
function show_help {
    echo "    ezbench.sh -p <path_git_repo> -n <last n commits>"
    echo ""
    echo "    Optional arguments:"
    echo "        -r <benchmarking rounds> (default: 3)"
    echo "        -b benchmark1 benchmark2 ..."
    echo "        -m <make command> (default: 'make -j8 install')"
    echo ""
    echo "    Other actions:"
    echo "        -h/?: Show this help message"
    echo "        -l: List the available tests"
}
function available_tests {
    echo -n "Available tests: "
    for (( t=0; t<${#availTests[@]}; t++ ));
    do
        echo -n "${availTests[$t]} "
    done
    echo
    
}
while getopts "h?p:n:r:b:m:l" opt; do
    case "$opt" in
    h|\?)
        show_help 
        exit 0
        ;;
    p)  gitRepoDir=$OPTARG
        ;;
    n)  lastNCommits=$OPTARG
        ;;
    r)  rounds=$OPTARG
        ;;
    b)  testsList=$OPTARG
        ;;
    m)  makeCommand=$OPTARG
        ;;
    l)
        available_tests
        exit 0
        ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
    esac
done

# Check that the list of wanted benchmarks is OK
testsListOK=1
for test in $testsList
do
    if [[ ! " ${availTests[@]} " =~ " ${test} " ]]; then
        echo "The test '$test' does not exist."
        testsListOK=0
    fi
done
if [[ $testsListOK == 0 ]]; then
    available_tests
    exit 1
fi

# redirect the output to both a log file and stdout
logsFolder="$ezBenchDir/logs/$(date +"%y-%m-%d-%T")"
mkdir $logsFolder || exit 1
exec > >(tee $logsFolder/results)
exec 2>&1

# Check the git repo, saving then displaying the HEAD commit
cd $gitRepoDir
commit_head=$(git rev-parse HEAD 2>/dev/null)
if [ $? -ne 0 ]
then
    echo "ERROR: The path '$gitRepoDir' does not contain a valid git repository. Aborting..."
    exit 1
fi
echo "Original commit = $commit_head"

# Preserve any local modifications
stash=`git stash create`
if [ $? -ne 0 ]
then
    echo "ERROR: Unable to preserve dirty state in '$gitRepoDir'. Aborting..."
    exit 1
fi
[ -n "$stash" ] && echo "Preserving work-in-progress"

# function to call on exit
function finish {
    # to be executed on exit, possibly twice!
    git reset --hard $commit_head 2> /dev/null
    [ -n "$stash" ] && git stash apply $stash > /dev/null

    # Execute the user-defined post hook
    callIfDefined ezbench_post_hook
}
trap finish EXIT
trap finish INT # Needed for zsh

# Generate the actual list of tests
typeset -A testNames
typeset -A testPrevFps
i=0
total_round_time=0
echo -n "Tests that will be run: "
for test_file in $ezBenchDir/tests.d/*.test
do
    unset test_name
    unset test_exec_time

    source $test_file || continue
    
    # Check that the user wants this test or not
    if [ -n "$testsList" ]; then
        if [[ "$testsList" != *"$test_name"* ]]; then
            continue
        fi
    fi
    
    testNames[$i]=$test_name 
    testPrevFps[$i]=-1
    
    echo -n "${testNames[$i]} "
    
    total_round_time=$(( $total_round_time + $test_exec_time ))
    i=$(($i+1))
done
echo

# Estimate the execution time
num_commits=$lastNCommits
[ -n "$stash" ] && num_commits=$(($num_commits + 1))
secs=$(( ($total_round_time * $rounds + $avgBuildTime) * $num_commits))
printf "Estimated run time: %02dh:%02dm:%02ds\n\n" $(($secs/3600)) $(($secs%3600/60)) $(($secs%60))
startTime=`date +%s`

# Execute the user-defined pre hook
function callIfDefined() {
    if [ "`type -t $1`" == 'function' ]; then
        local funcName=$1
        shift
        $funcName $@
    fi
}
callIfDefined ezbench_pre_hook

# ANSI colors
c_bright_red='\e[1;31m'
c_bright_green='\e[1;32m'
c_bright_yellow='\e[1;33m'
c_reset='\e[0m'

bad_color=$c_bright_red
good_color=$c_bright_green
meh_color=$c_bright_yellow


# Iterate through the commits
for commit in $(git rev-list --abbrev-commit --reverse -n ${lastNCommits} HEAD) $stash
do
    # Make sure we are in the right folder
    cd $gitRepoDir

    # Select the commit of interest
    if [ $commit == "$stash" ]
    then
	    git reset --hard $commit_head > /dev/null
	    git stash apply $stash > /dev/null
            echo -e "${c_bright_yellow}WIP${c_reset}"
    else
	    git reset --hard $commit > /dev/null
	    git show --format="%Cblue%h%Creset %Cgreen%s%Creset" -s
    fi

    # Call the user-defined pre-compile hook
    callIfDefined compile_pre_hook

    # Compile the commit and check for failure. If it failed, go to the next commit.
    compile_logs=$logsFolder/${commit}_compile_log
    eval $makeCommand > $compile_logs 2>&1
    if [ $? -ne 0 ]
    then
        echo "    ERROR: Compilation failed, log saved in $compile_logs"
        echo
        git reset --hard HEAD~ > /dev/null 2> /dev/null
        continue
    fi

    # Call the user-defined post-compile hook
    callIfDefined compile_post_hook

    # Iterate through the tests
    for (( t=0; t<${#testNames[@]}; t++ ));
    do
        # Generate the logs file names
        fps_logs=$logsFolder/${commit}_bench_${testNames[$t]}
        error_logs=${fps_logs}.errors

        # Run the benchmark
        printf "%28s: " ${testNames[$t]}
        runFuncName=${testNames[$t]}_run
        preHookFuncName=${testNames[$t]}_run_pre_hook
        postHookFuncName=${testNames[$t]}_run_post_hook
        callIfDefined $preHookFuncName
        fpsTest=$($runFuncName $rounds 2> $error_logs)
        callIfDefined $postHookFuncName

        # delete the error file if it is empty
        if [ ! -s $error_logs ] ; then
            rm $error_logs
        fi

        # Save the raw data
        echo "FPS of '${testNames[$t]}' using commit ${commit}" > $fps_logs
        echo "$fpsTest" >> $fps_logs

        # Process the data ourselves
        statsTest=$(echo "$fpsTest" | $ezBenchDir/fps_stats.awk)
        fpsTest=$(echo $statsTest | cut -d ' ' -f 1)
        remStatsTest=$(echo $statsTest | cut -d ' ' -f 2-)
        if (( $(echo "${testPrevFps[$t]} == -1" | bc -l) ))
        then
                testPrevFps[$t]=$fpsTest
        fi
        fpsDiff=$(echo "scale=3;($fpsTest * 100.0 / ${testPrevFps[$t]}) - 100" | bc)
        testPrevFps[$t]=$fpsTest
        if (( $(bc -l <<< "$fpsDiff < -1.5") == 1 )); then
            color=$bad_color
        elif (( $(bc -l <<< "$fpsDiff > 1.5") == 1 )); then
            color=$good_color
        else
            color="$meh_color"
        fi
        printf "%9.2f ($color%+.2f%%$c_reset): %s\n" $fpsTest $fpsDiff "$remStatsTest"
    done
    echo
done

endTime=`date +%s`
runtime=$((endTime-startTime))
printf "Actual run time: %02dh:%02dm:%02ds\n\n" $(($runtime/3600)) $(($runtime%3600/60)) $(($runtime%60))
