#!/bin/bash

if [ $# -eq 0 ]
then
	echo "Usage: $0 env_dump_file binary param1 param2 ..."
fi

dir=$(dirname $(readlink -f $0))
so_path="$dir/env_dump.so"
dump_file="$1"
shift

LD_PRELOAD="$so_path" ENV_DUMP_FILE="$dump_file" "$@"
exit $?
