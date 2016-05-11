#!/bin/bash

if [ $# -eq 0 ]
then
	echo "Usage: $0 env_dump_file binary param1 param2 ..."
fi

dir=$(dirname $(readlink -f $0))
so_path="$dir/env_dump.so"
dump_file="$1.env_dump"
metrics_file="$1.metrics_envdump"
shift

# Add the exit code
if [[ "$dump_file" != "stderr" ]]
then
	LD_PRELOAD="$so_path" ENV_DUMP_FILE="$dump_file" ENV_DUMP_METRIC_FILE="$metrics_file" "$@"
	exit_code=$?

	# Do not add the EXIT_CODE line if it already exists. It means the file
	# existed before we ran the tool. Just warn about this issue and do nothing.
	if [ -z "$(grep EXIT_CODE "$dump_file")" ];
	then
		line="EXIT_CODE,$exit_code\n"
		sed -i "s\`^-- Env dump end --\`${line}-- Env dump end --\`g" $dump_file
	else
		echo "ENV_DUMP: The file '$dump_file' already contains the EXIT_CODE, ignore..." >&2
	fi
else
	LD_PRELOAD="$so_path" ENV_DUMP_FILE="stderr" "$@"
	exit_code=$?
fi

exit $exit_code
