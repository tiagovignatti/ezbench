#!/bin/bash

# Thanks to stack overflow for writing most of this script! It has been tested
# with bash and zsh only!
# Author: Martin Peres <martin.peres@free.fr>

#set -o xtrace

shopt -s globstar || {
    echo "ERROR: ezbench requires bash 4.0+ or zsh with globstat support."
    exit 1
}

#Default values
rounds=3
avgBuildTime=30
makeCommand="make -j8 install"
lastNCommits=
uptoCommit="HEAD"
gitRepoDir=''
ezBenchDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# Default user options
for conf in $ezBenchDir/conf.d/**/*.conf; do source $conf; done
source "$ezBenchDir/test_options.sh" # Allow test_options.sh to override all

# initial cleanup
mkdir $ezBenchDir/logs/ 2> /dev/null

# parse the options
function show_help {
    echo "    ezbench.sh -p <path_git_repo> -n <last n commits>"
    echo ""
    echo "    Optional arguments:"
    echo "        -r <benchmarking rounds> (default: 3)"
    echo "        -b benchmark1 benchmark2 ..."
    echo "        -H <git-commit-id> benchmark the commits preceeding this one"
    echo "        -m <make command> (default: 'make -j8 install', '' to skip the compilation)"
    echo "        -N <log folder's name> (default: current date and time)"
    echo ""
    echo "    Other actions:"
    echo "        -h/?: Show this help message"
    echo "        -l: List the available tests"
}
function available_tests {
    # Generate the list of available tests
    echo -n "Available tests: "
    for test_file in $ezBenchDir/tests.d/**/*.test
    do
        unset test_name
        unset test_exec_time

        source $test_file || continue
        [ -z "$test_name" ] && continue
        [ -z "$test_exec_time" ] && continue
        for t in $test_name; do
            echo -n "$t "
        done
    done
    echo
    
}
function callIfDefined() {
    if [ "`type -t $1`" == 'function' ]; then
        local funcName=$1
        shift
        $funcName $@
    else
        return 1
    fi
}

no_compile=
while getopts "h?p:n:N:H:r:b:m:l" opt; do
    case "$opt" in
    h|\?)
        show_help 
        exit 0
        ;;
    p)  gitRepoDir=$OPTARG
        ;;
    n)  lastNCommits=$OPTARG
        ;;
    N)  name=$OPTARG
        ;;
    H)  uptoCommit=$OPTARG
        ;;
    r)  rounds=$OPTARG
        ;;
    b)  testsList="$testsList $OPTARG"
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
shift $((OPTIND-1))

commitList=
for id in "$@"; do
    if [[ $id =~ \.\. ]]; then
        commitList+=$(git rev-list --abbrev-commit --reverse $id)
    else
        commitList+=$(git rev-list --abbrev-commit -n 1 `git rev-parse $id`)
    fi
    commitList+=" "
done

# Set the average compilation time to 0 when we are not compiling
if [ -z "$makeCommand" ]
then
    avgBuildTime=0
fi

# redirect the output to both a log file and stdout
logsFolder="$ezBenchDir/logs/${name:-$(date +"%Y-%m-%d-%T")}"
[ -d $logsFolder ] || mkdir -p $logsFolder || exit 1
exec > >(tee -a $logsFolder/results)
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

# Execute the user-defined pre hook
callIfDefined ezbench_pre_hook

# Seed the results with the last round?
commitListLog="$logsFolder/commit_list"
last_commit=$(tail -1 $commitListLog 2>/dev/null | cut -f 1 -d ' ')

# Generate the actual list of tests
typeset -A testNames
typeset -A testPrevFps
typeset -A testFilter
total_tests=0
total_round_time=0
testPrevFps[-1]=-1
echo -n "Tests that will be run: "
for test_file in $ezBenchDir/tests.d/**/*.test
do
    unset test_name
    unset test_exec_time

    source $test_file || continue

    for t in $test_name; do
        # Check that the user wants this test or not
        if [ -n "$testsList" ]; then
            found=0
            for filter in $testsList; do
                if [[ $t =~ $filter ]]; then
                    testFilter[$filter]=1
                    found=1
                    break
                fi
            done
            [ $found -eq 0 ] && continue
        fi

        testNames[$total_tests]=$t

        last_result="$logsFolder/${last_commit}_result_${t}"
	if [ -e "$logsFolder/${last_commit}_result_${t}" ]; then
            testPrevFps[$total_tests]=$(cat $last_result)
	else
            testPrevFps[$total_tests]=-1
	fi
        unset last_result

        echo -n "${testNames[$total_tests]} "

        total_round_time=$(( $total_round_time + $test_exec_time ))
        total_tests=$(( $total_tests + 1))
    done
done
echo
unset last_commit

[ -z "$total_tests" ] && exit 1

missing_tests=
for t in $testsList; do
    [ -z ${testFilter[$t]} ] && missing_tests+="$t "
done
if [ -n "$missing_tests" ]; then
    echo "The tests \"${missing_tests:0:-1}\" do not exist"
    available_tests
    exit 1
fi

# Estimate the execution time
if [ -z "$commitList" ]; then
    commitList=$(git rev-list --abbrev-commit --reverse -n ${lastNCommits} ${uptoCommit})
    [ "${uptoCommit}" == "HEAD" ] && commitList="${commitList} ${stash}"
fi
num_commits=$(wc -w <<< $commitList)
secs=$(( ($total_round_time * $rounds + $avgBuildTime) * $num_commits))
finishDate=$(date +"%y-%m-%d - %T" --date="$secs seconds")
printf "Testing %d commits, estimated finish date: $finishDate (%02dh:%02dm:%02ds)\n\n" ${num_commits} $(($secs/3600)) $(($secs%3600/60)) $(($secs%60))
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
    [ -z "$makeCommand" ] && return

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

}

# Iterate through the commits
for commit in $commitList
do
    # save the commit in the commit_list

    # Make sure we are in the right folder
    cd $gitRepoDir

    # Select the commit of interest
    if [ $commit == "$stash" ]
    then
        git reset --hard $commit_head > /dev/null
        git stash apply $stash > /dev/null
        echo -e "${c_bright_yellow}WIP${c_reset}"
        echo "$commit" >> $commitListLog
    else
        git reset --hard $commit > /dev/null
        git show --format="%Cblue%h%Creset %Cgreen%s%Creset" -s
        git show --format="%h %s" -s >> $commitListLog
    fi

    compile

    # Iterate through the tests
    fpsALL=""
    for (( t=0; t<${#testNames[@]}; t++ ));
    do
        # Generate the logs file names
        fps_logs=$logsFolder/${commit}_bench_${testNames[$t]}
        error_logs=${fps_logs}.errors

        # Run the benchmark
        echo "FPS of '${testNames[$t]}' using commit ${commit}" > $fps_logs
        printf "%28s: " ${testNames[$t]}

        runFuncName=${testNames[$t]}_run
        preHookFuncName=${testNames[$t]}_run_pre_hook
        postHookFuncName=${testNames[$t]}_run_post_hook
        processHookFuncName=${testNames[$t]}_process

	unset ERROR
        callIfDefined $preHookFuncName
        output=$($runFuncName $rounds $fps_logs 2>$error_logs || ERROR=1)
        callIfDefined $postHookFuncName

        if [ -n "$ERROR" -o -z "$output" ]; then
            echo -e "${c_red}failed${c_reset}"
            continue
        fi

        # delete the error file if it is empty
        if [ ! -s $error_logs ] ; then
            rm $error_logs
        fi

        echo "$output" >> $fps_logs

        # Process the data ourselves
        statistics=
        result=$(callIfDefined $processHookFuncName "$output") || {
            statistics=$(echo "$output" | $ezBenchDir/fps_stats.awk)
            result=$(echo "$statistics" | cut -d ' ' -f 1)
            statistics=$(echo "$statistics" | cut -d ' ' -f 2-)
        }
        echo $result > $logsFolder/${commit}_result_${testNames[$t]}
        if (( $(echo "${testPrevFps[$t]} == -1" | bc -l) ))
        then
            testPrevFps[$t]=$result
        fi
        fpsDiff=$(echo "scale=3;($result * 100.0 / ${testPrevFps[$t]}) - 100" | bc 2>/dev/null)
        [ $? -eq 0 ] && testPrevFps[$t]=$result
        if (( $(bc -l <<< "$fpsDiff < -1.5" 2>/dev/null || echo 0) )); then
            color=$bad_color
        elif (( $(bc -l <<< "$fpsDiff > 1.5" 2>/dev/null || echo 0) )); then
            color=$good_color
        else
            color="$meh_color"
        fi
        printf "%9.2f ($color%+.2f%%$c_reset): %s\n" $result $fpsDiff "$statistics"
        [ -z "$result" ] || fpsALL="$fpsALL $result"
    done

    # finish with the geometric mean (when we have multiple tests)
    if [ $t -gt 1 ]; then
        fpsALL=$(echo $fpsALL | awk '{ for (i=1; i <= NF; i++) { sum += 1/$i; n += 1 } } END { print n / sum }')
        if (( $(echo "${testPrevFps[-1]} == -1" | bc -l) ))
        then
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
                $fpsALL \
                $fpsDiff
    fi
    echo
done

endTime=`date +%s`
runtime=$((endTime-startTime))
printf "Actual run time: %02dh:%02dm:%02ds\n\n" $(($runtime/3600)) $(($runtime%3600/60)) $(($runtime%60))
