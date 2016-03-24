#!/bin/bash

function has_automatic_sudo_rights() {
    sudo -n /bin/true > /dev/null 2>&1
    if [ $? != 0 ];
    then
        echo "WARNING: automatic sudo rights are missing for function '${FUNCNAME[1]}'"
        return 1
    fi
    return 0
}

function has_binary() {
    command -v $1 >/dev/null 2>&1
    if [ $? != 0 ];
    then
        echo "WARNING: function '${FUNCNAME[1]}' requires the binary '$1'"
        return 1
    fi
    return 0
}

function setup_cgroup() {
    has_automatic_sudo_rights || return 1
    has_binary cgcreate || return 2
    has_binary cgexec || return 3

    sudo -n cgcreate -a $(id -gn):$(id -un) -t $(id -gn):$(id -un) -g freezer:ezbench || return 4
    cgset -r freezer.state=THAWED ezbench || return 5
}

# Start the cgroup
setup_cgroup || exec $@

# Run the command
cgexec -g freezer:ezbench $@

# Freeze all the processes, before killing them one by one
cgset -r freezer.state=FROZEN ezbench
for pid in $(cat /sys/fs/cgroup/freezer/ezbench/tasks); do
    echo "cgroup_run: killing remaining pid $pid ($(cat /proc/$pid/cmdline))"
    sudo -n kill -9 $pid
done

sudo -n cgdelete -g freezer:ezbench
