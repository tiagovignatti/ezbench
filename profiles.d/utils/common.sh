source "$ezBenchDir/profiles.d/utils/sha1_db.sh"

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

# Change VT
function vt_switch_start() {
    has_automatic_sudo_rights || return 1
    has_binary chvt || return 1
    has_binary fgconsole || return 1

    export EZBENCH_VT_ORIG=$(sudo -n fgconsole)
    sudo -n chvt 5
    sleep 1 # Wait for the potential x-server running to release MASTER
}
function vt_switch_stop() {
    has_automatic_sudo_rights || return 1
    has_binary chvt || return 1
    has_binary sleep || return 1

    [[ -z "$EZBENCH_VT_ORIG" ]] && return 1

    sudo -n chvt $EZBENCH_VT_ORIG
    unset EZBENCH_VT_ORIG
    sleep 1
}

# Requires xset, chvt,X,sudo rights without passwords
function xserver_setup_start() {
    [[ $dry_run -eq 1 ]] && return 1

    # Check for dependencies
    has_automatic_sudo_rights || return 1
    has_binary Xorg || return 1
    has_binary xset || return 1
    has_binary sleep || return 1
    has_binary kill || return 1 # Need by stop()

    vt_switch_start || return 1

    x_pid=$(sudo -n $ezBenchDir/profiles.d/utils/_launch_background.sh Xorg -nolisten tcp -noreset :42 vt5 -auth /tmp/ezbench_XAuth 2> /dev/null) # TODO: Save the xorg logs
    export EZBENCH_X_PID=$x_pid

    export DISPLAY=:42
    export XAUTHORITY=/tmp/ezbench_XAuth

    # disable DPMS. The X-Server may not have started yet, so try multiple times (up to 5 seconds)
    for i in {0..50}
    do
        xset s off -dpms 2> /dev/null
        [ $? -eq 0 ] && return 0
        sleep 0.1
    done

    echo "ERROR: The X-Server still has not started after 5 seconds. Abort..." >&2
    xserver_setup_stop
    return 1
}

function xserver_setup_stop() {
    [[ $dry_run -eq 1 ]] && return

    kill_random_pid $EZBENCH_X_PID
    unset EZBENCH_X_PID

    vt_switch_stop
}

# Requires xrandr
function xserver_reset() {
    [[ $dry_run -eq 1 ]] && return 1

    # Check for dependencies
    has_binary xrandr || return 1

    xrandr --auto

    return 0
}

function gui_start() {
    [[ $dry_run -eq 1 ]] && return 1

    # Start X or not?
    if [[ "$EZBENCH_CONF_X11" != "0" ]]; then
        xserver_setup_start || return 1
    fi

    # Start the compositor
    if [ -n "$EZBENCH_CONF_COMPOSITOR" ]; then
        has_binary "${EZBENCH_CONF_COMPOSITOR}" || return 1
        eval "${EZBENCH_CONF_COMPOSITOR} $EZBENCH_CONF_COMPOSITOR_ARGS&" 2> /dev/null > /dev/null
        sleep 0.25
    fi

    return 0
}

function gui_stop() {
    [[ $dry_run -eq 1 ]] && return

    # Stop our X server
    xserver_setup_stop

    # Nothing else to do until we have support for Wayland

    return 0
}

function gui_reset() {
    [[ $dry_run -eq 1 ]] && return

    if [[ "$EZBENCH_CONF_X11" != "0" ]]; then
        xserver_reset || return 1
    fi
}

function x_show_debug_info_start() {
    [[ $dry_run -eq 1 ]] && return

    # Check for dependencies
    [ -z $DISPLAY ] && { echo "WARNING: Cannot display the debug information without X running"; return; }
    has_binary twm || return 1
    has_binary xterm || return 1
    has_binary tail || return 1
    has_binary kill || return 1 # Needed for stop()

    export EZBENCH_COMPILATION_LOGS=$compile_logs
    export EZBENCH_COMMIT_SHA1=$commit

    $ezBenchDir/profiles.d/utils/_show_debug_info.sh&
    export EZBENCH_DEBUG_SESSION_PID=$!

    unset EZBENCH_COMMIT_SHA1
    unset EZBENCH_COMPILATION_LOGS
}

function x_show_debug_info_stop() {
    [[ $dry_run -eq 1 ]] && return

    # Check for dependencies
    [ -z "$EZBENCH_DEBUG_SESSION_PID" ] && return
    has_binary ps || return 1

    # Kill all the processes under the script
    # FIXME: Would be better with a session id of a pid namespace
    kill $(ps -o pid= --ppid $EZBENCH_DEBUG_SESSION_PID) $EZBENCH_DEBUG_SESSION_PID 2> /dev/null
    unset EZBENCH_DEBUG_SESSION_PID
}

function cpu_id_max_get() {
    # Check for dependencies
    has_binary grep || return 1
    has_binary tail || return 1
    has_binary rev || return 1
    has_binary cut || return 1

    grep "processor" /proc/cpuinfo | tail -n 1 | rev | cut -f 1 -d ' '
}

function cpu_reclocking_disable_start() {
    # Check for dependencies
    has_automatic_sudo_rights || return

    # Disable turbo (TODO: Fix it for other cpu schedulers)
    sudo -n sh -c "echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo"

    # Set the frequency to a fixed one
    [ -z "$WANTED_CPU_FREQ_kHZ" ] && return
    cpu_id_max=$(cpu_id_max_get)
    for (( i=0; i<=${cpu_id_max}; i++ )); do
        # Since the kernel makes sure that min <= max and min may be > $WANTED_CPU_FREQ_kHZ,
        # the first write to max may fail. The second is guaranteed to succeed though!
        sudo -n sh -c "echo $WANTED_CPU_FREQ_kHZ > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_max_freq"
        sudo -n sh -c "echo $WANTED_CPU_FREQ_kHZ > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_min_freq"
        sudo -n sh -c "echo $WANTED_CPU_FREQ_kHZ > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_max_freq"
    done
    export EZBENCH_CPU_RECLOCKED=1
}

function cpu_reclocking_disable_stop() {
    # Check for dependencies
    has_automatic_sudo_rights || return

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
    # Check for dependencies
    has_automatic_sudo_rights || return

    sudo -n sh -c "echo 0 > /proc/sys/kernel/randomize_va_space"
}

function aslr_disable_stop() {
    # Check for dependencies
    has_automatic_sudo_rights || return

    sudo -n sh -c "echo 1 > /proc/sys/kernel/randomize_va_space"
}

function thp_disable_start() {
    # Check for dependencies
    has_automatic_sudo_rights || return

    sudo -n sh -c "echo never > /sys/kernel/mm/transparent_hugepage/enabled"
    sudo -n sh -c "echo never > /sys/kernel/mm/transparent_hugepage/defrag"
}

function thp_disable_stop() {
    # Check for dependencies
    has_automatic_sudo_rights || return

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

function kill_random_pid() {
    loop_watchdog=500 # 5 seconds

    # Send a term signal
    sudo -n kill $1

    # This is generally unsafe, but better than waiting a random amount of time
    ps -p $1 > /dev/null 2> /dev/null
    while [[ ${?} == 0 && $loop_watchdog > 0 ]]
    do
        loop_watchdog=$((loop_watchdog - 1))
        sleep .01
        ps -p $1 > /dev/null 2> /dev/null
    done

    # Stop waiting, just kill it!
    sudo -n kill -9 $1
}
