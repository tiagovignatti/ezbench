#!/bin/bash

dir=$(dirname $(readlink -f $0))
so_path="$dir/env_dump.so"
dump_file="$1"
shift

echo "Before, SHA1_DB = '$SHA1_DB'"

LD_PRELOAD="$so_path" ENV_DUMP_FILE="$dump_file" $@
exit $?
