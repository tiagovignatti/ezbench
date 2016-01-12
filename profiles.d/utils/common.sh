source "$ezBenchDir/profiles.d/utils/sha1_db.sh"

# Requires xset, chvt,X
function xserver_setup_start() {
    [[ $dry_run -eq 1 ]] && return

    export EZBENCH_VT_ORIG=$(sudo -n fgconsole)

    sudo -n chvt 5
    sleep 1 # Wait for the potential x-server running to release MASTER
    x_pid=$(sudo -n $ezBenchDir/profiles.d/utils/_launch_background.sh Xorg -nolisten tcp -noreset :42 vt5 -auth /tmp/ezbench_XAuth 2> /dev/null) # TODO: Save the xorg logs
    export EZBENCH_X_PID=$x_pid

    export DISPLAY=:42
    export XAUTHORITY=/tmp/ezbench_XAuth

    # disable DPMS
    xset s off -dpms
}

function xserver_setup_stop() {
    [[ $dry_run -eq 1 ]] && return

    sudo -n kill $EZBENCH_X_PID
    wait_random_pid $EZBENCH_X_PID
    unset EZBENCH_X_PID

    sudo -n chvt $EZBENCH_VT_ORIG
    unset EZBENCH_VT_ORIG
    sleep 1
}

# Requires xrandr
function xserver_reset() {
    [[ $dry_run -eq 1 ]] && return

    xrandr --auto
}

function x_show_debug_info_start() {
    [[ $dry_run -eq 1 ]] && return
    [ -z $DISPLAY ] && return

    export EZBENCH_COMPILATION_LOGS=$compile_logs
    export EZBENCH_COMMIT_SHA1=$commit

    $ezBenchDir/profiles.d/utils/_show_debug_info.sh&
    export EZBENCH_DEBUG_SESSION_PID=$!

    unset EZBENCH_COMMIT_SHA1
    unset EZBENCH_COMPILATION_LOGS
}

function x_show_debug_info_stop() {
    [[ $dry_run -eq 1 ]] && return
    [ -z "$DISPLAY" ] && return
    [ -z "$EZBENCH_DEBUG_SESSION_PID" ] && return

    # Kill all the processes under the script
    # FIXME: Would be better with a session id of a pid namespace
    kill $(ps -o pid= --ppid $EZBENCH_DEBUG_SESSION_PID)
    unset EZBENCH_DEBUG_SESSION_PID
}

function cpu_id_max_get() {
    grep "processor" /proc/cpuinfo | tail -n 1 | rev | cut -f 1 -d ' '
}

function cpu_reclocking_disable_start() {
    # Disable turbo (TODO: Fix it for other cpu schedulers)
    sudo -n sh -c "echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo"

    # Set the frequency to a fixed one
    [ -z "$WANTED_CPU_FREQ_kHZ" ] && return
    cpu_id_max=$(cpu_id_max_get)
    for (( i=0; i<=${cpu_id_max}; i++ )); do
        sudo -n sh -c "echo $WANTED_CPU_FREQ_kHZ > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_max_freq"
        sudo -n sh -c "echo $WANTED_CPU_FREQ_kHZ > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_min_freq"
    done
    export EZBENCH_CPU_RECLOCKED=1
}

function cpu_reclocking_disable_stop() {
    # Re-enable turbo (TODO: Fix it for other cpu schedulers)
    sudo -n sh -c "echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo"

    # Reset the scaling to the original values
    [ -z "EZBENCH_CPU_RECLOCKED" ] && return
    cpu_id_max=$(cpu_id_max_get)
    cwd=$(pwd)
    for (( i=0; i<=${cpu_id_max}; i++ )); do
        cd "/sys/devices/system/cpu/cpu${i}/cpufreq/"
        sudo -n sh -c "cat cpuinfo_min_freq > scaling_min_freq"
        sudo -n sh -c "cat cpuinfo_max_freq > scaling_max_freq"
    done
    cd $cwd
    unset EZBENCH_CPU_RECLOCKED
}

function aslr_disable_start() {
    sudo -n sh -c "echo 0 > /proc/sys/kernel/randomize_va_space"
}

function aslr_disable_stop() {
    sudo -n sh -c "echo 1 > /proc/sys/kernel/randomize_va_space"
}

function thp_disable_start() {
    sudo -n sh -c "echo never > /sys/kernel/mm/transparent_hugepage/enabled"
    sudo -n sh -c "echo never > /sys/kernel/mm/transparent_hugepage/defrag"
}

function thp_disable_stop() {
    sudo -n sh -c "echo always > /sys/kernel/mm/transparent_hugepage/enabled"
    sudo -n sh -c "echo always > /sys/kernel/mm/transparent_hugepage/defrag"
}

# function irq_remap_start() {
#     cpu_id_max=$(cpu_id_max_get)
#     for d in /proc/irq/*/ ; do
#         sudo sh -c "echo $cpu_id_max > $d/smp_affinity"
#     done
# }
#
# function irq_remap_stop() {
#     for d in /proc/irq/*/ ; do
#         sudo sh -c "echo 0 > $d/smp_affinity"
#     done
# }

function wait_random_pid() {
    # This is generally unsafe, but better than waiting a random amount of time

    ps -p $1 > /dev/null 2> /dev/null
    while [[ ${?} == 0 ]]
    do
        sleep .01
        ps -p $1 > /dev/null 2> /dev/null
    done
}
