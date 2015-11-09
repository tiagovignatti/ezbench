#!/bin/bash

SHA1_DB="$1"
dump_file="$2"

function get_binary_version() {
	filename=$1
	sha1=$2

	if [ -d "$SHA1_DB/$sha1" ]; then
		cat "$SHA1_DB/$sha1/version"
		return 0
	else
		# We did not find the file, add it to the sha1 DB. First check if it was
		# provided by the distro
		pkg=$(pkcon search file $filename 2> /dev/null | grep Installed | xargs | cut -d ' ' -f 2)
		[ -z "$pkg" ] && echo "UNKNOWN_VERSION" && return 1

		# Now check that the SHA1 still matches the one used by the benchmark
		if [ "$sha1" == $(sha1sum $filename | cut -d ' ' -f 1) ]
		then
			version=$distro-$pkg

			mkdir -p $SHA1_DB/$sha1/
			echo $version > $SHA1_DB/$sha1/version
			echo $filename > $SHA1_DB/$sha1/filepath

			echo $version
			return 0
		fi
	fi
}

function resolve_SHA1() {
	SHA1_DB="$1"
	dump_file="$2"

	[ -z "$SHA1_DB" ] && return 0

	# Try to get the name of the distro from lsb-release, revert to pkcon if not
	# available
	distro=$(grep DISTRIB_ID /etc/lsb-release 2> /dev/null | cut -d '=' -f2)
	if [ -z "$distro" ];
	then
		distro=$(pkcon backend-details 2> /dev/null | grep Name | xargs | cut -d ' ' -f 2)
		[ -z "$distro" ] && distro="UNK_DISTRO"
	fi

	# resolve the SHA1 of the EXE
	exe_line=$(grep -e '^EXE,' $dump_file)
	filename=$(echo "$exe_line" | cut -d ',' -f 2)
	sha1=$(echo "$exe_line" | cut -d ',' -f 4)
	version=$(get_binary_version $filename $sha1)
	sed -i "s~$exe_line~$exe_line,$version~g" $dump_file

	# resolve the SHA1 of the libraries
	for line in $(grep -e '^BOOTLINK\|^DYNLINK,' $dump_file)
	do
		filename=$(echo "$line" | cut -d ',' -f 2)
		sha1=$(echo "$line" | cut -d ',' -f 3)
		version=$(get_binary_version $filename $sha1)
		sed -i "s~$line~$line,$version~g" $dump_file
	done

	# resolve the SHA1 of the binary on the other side of a unix socket
	grep -e '^SOCKET_UNIX_CONNECT,' $dump_file | while read line
	do
		filename=$(echo "$line" | cut -d ',' -f 3)
		sha1=$(echo "$line" | cut -d ',' -f 5)
		version=$(get_binary_version $filename $sha1)
		sed -i "s~$line~$line,$version~g" $dump_file
	done

	return 0
}

resolve_SHA1 "$SHA1_DB" "$dump_file"

# TODO: add dmidecode-related information here

exit 0
