#!/bin/sh

# Copyright 2015 Intel Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
# * Neither the name of the copyright holders nor the names of their contributors
#   may be used to endorse or promote products derived from this software without
#   specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

set -eu

: ${XDG_CACHE_HOME:=$HOME/.cache}

prog_name=${0##*/}
cache_dir="$XDG_CACHE_HOME/intel-gpu-info"
cached_i965_pci_ids_h="$cache_dir/i965_pci_ids.h"
dri_dev="/sys/class/drm/card0/device/device"


print_help ()
{
cat <<EOF
USAGE
    $prog_name [-u|--update] [--] [regex]

DESCRIPTION
    Print info about all Intel GPU's whose name or pci_id match the regex. If
    no regex is given, then print info on the current machine's Intel GPU.

OPTIONS
    -u, --update
        Update the cached copy of i965_pci_ids.h.

EXAMPLES
    Query the local device.
        $ $prog_name

    Search for a specific PCI id.
        $ $prog_name 0x1616

    Search for all Broadwell GPUs.
        $ $prog_name broadwell

    Search for all GT3 GPUs.
        $ $prog_name gt3

    Search for an Intel GPU by its marketing name.
        $ $prog_name "Iris Pro 6200"
EOF
}


parse_args ()
{
    arg_regex=
    arg_update=

    for argnum in $(seq $#); do
        case "$1" in
            --)
                shift
                break
                ;;
            -h|--help)
                print_help
                exit 0
                ;;
            -u|--update)
                arg_update=1
                shift
                ;;
            -*)
                usage_error "unknown option $1"
                ;;
            *)
                break
                ;;
        esac
    done

    if [ $# -gt 0 ]; then
        arg_regex="$1"
        shift
    fi

    if [ $# -gt 0 ]; then
        usage_error "trailing args: $@"
    fi
}

usage_error ()
{
    echo >&2 "$prog_name: usage error: $@"
    exit 2
}

die ()
{
    echo >&2 "$prog_name: error: $@"
    exit 2
}

update_cache ()
{
    local src
    local dst
    mkdir -p "$cache_dir"

    if [ -r "$cached_i965_pci_ids_h" ] && [ -z "$arg_update" ]; then
        return
    fi

    src="http://cgit.freedesktop.org/mesa/mesa/tree/include/pci_ids/i965_pci_ids.h"
    dst="$cached_i965_pci_ids_h"

    if [ -z "$(which curl)" ]; then
        if [ -z "$(which wget)" ]; then
	    die "please install either 'curl' or 'wget' to fetch/update the PCI ID information"
	fi
	wget -O - "$src" > "${dst}.bak"
    else
	curl -s "$src" > "${dst}.bak"
    fi
    sed -n 's/.*CHIPSET(\(.*\))$/\1/p' <  "${dst}.bak" > "$dst"
    rm "${dst}.bak"
}

main ()
{
    local regex

    parse_args "$@"

    if [ "$arg_regex" ]; then
        regex="$arg_regex"
    elif ! regex="$(cat $dri_dev)"; then
        die "failed to read $dri_dev"
    fi

    update_cache

    grep -i -E "$regex" "$cached_i965_pci_ids_h"
    if [ $? -ne 0 ]; then
        die "failed to find '$regex' in i965_pci_ids.h"
    fi
}

main "$@"
