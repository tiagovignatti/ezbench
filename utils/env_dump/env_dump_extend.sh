#!/bin/bash

# Requires pkcon from packagekit and the file /etc/lsb-release

if [[ $# -ne 2 ]]
then
	echo "Usage: $0 SHA1_DB env_dump_file"
fi

SHA1_DB="$1"
dump_file="$2"

function get_binary_version() {
	filename=$1
	sha1=$2

	upstream=$($SHA1_DB/sha1_db $SHA1_DB $sha1 read_attr upstream 2> /dev/null)
	version=$($SHA1_DB/sha1_db $SHA1_DB $sha1 read_attr version 2> /dev/null)

	if [ -n "$upstream" ] && [ -n "$version" ]; then
		echo $upstream-$version
		return 0
	else
		# We did not find the file, add it to the sha1 DB. First check if it was
		# provided by the distro
		pkg=$(pkcon search file $filename 2> /dev/null | grep Installed | xargs | cut -d ' ' -f 2)
		[ -z "$pkg" ] && echo "UNKNOWN_VERSION" && return 1

		# Now check that the SHA1 still matches the one used by the benchmark
		if [ "$sha1" == $(sha1sum $filename | cut -d ' ' -f 1) ]
		then
			$SHA1_DB/sha1_db $SHA1_DB $sha1 add $pkg $filename $distro
			echo $distro-$pkg
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
	sed -i "s\`$exe_line\`$exe_line,$version\`g" $dump_file

	# resolve the SHA1 of the libraries
	for line in $(grep -e '^BOOTLINK\|^DYNLINK,' $dump_file)
	do
		filename=$(echo "$line" | cut -d ',' -f 2)
		sha1=$(echo "$line" | cut -d ',' -f 3)
		version=$(get_binary_version $filename $sha1)
		sed -i "s\`$line\`$line,$version\`g" $dump_file
	done

	# resolve the SHA1 of the binary on the other side of a unix socket
	grep -e '^SOCKET_UNIX_CONNECT,' $dump_file | while read line
	do
		filename=$(echo "$line" | cut -d ',' -f 3)
		sha1=$(echo "$line" | cut -d ',' -f 5)
		version=$(get_binary_version $filename $sha1)
		sed -i "s\`$line\`$line,$version\`g" $dump_file
	done

	return 0
}

function add_dmidecode_info() {
	dimdecode=$(sudo -n dmidecode 2> /dev/null)

	# test if dmidecode ran properly
	[ $? -ne 0 ] && echo "WARNING; dmidecode is not present or not working..." && return 0

	# Motherboard information
	mobo_info=$(echo "$dimdecode" | grep -A 3 "Base Board Information")
	manufacturer=$(echo "$mobo_info" | grep "Manufacturer:" | cut -d ':' -f 2- | xargs)
	product_name=$(echo "$mobo_info" | grep "Product Name:" | cut -d ':' -f 2- | xargs)
	version=$(echo "$mobo_info" | grep "Version:" | cut -d ':' -f 2- | xargs)
	mobo_info=$(echo "MOTHERBOARD,$manufacturer,$product_name,$version\n")

	# BIOS information
	bios_info=$(echo "$dimdecode" | grep -A 6 "BIOS Information")
	vendor=$(echo "$bios_info" | grep "Vendor:" | cut -d ':' -f 2- | xargs)
	version=$(echo "$bios_info" | grep "Version:" | cut -d ':' -f 2- | xargs)
	date=$(echo "$bios_info" | grep "Release Date:" | cut -d ':' -f 2- | xargs)
	bios_info=$(echo "BIOS,$vendor,$version,$date\n")

	# CPU information
	cpu_count=$(echo "$dimdecode" | grep "Processor Information" | wc -l)
	cpu_info=""
	for i in $(seq 1 $cpu_count)
	do
		manufacturer=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "Manufacturer:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		id=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "ID:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		version=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "Version:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		max_speed=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "Max Speed:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		core_count=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "Core Count" | tail -n 1 | cut -d ':' -f 2- | xargs)
		thread_count=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "Thread Count:" | tail -n 1 | cut -d ':' -f 2- | xargs)

		l1_handle=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "L1 Cache Handle:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		l2_handle=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "L2 Cache Handle:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		l3_handle=$(echo "$dimdecode" | grep -m $i -A 24 "Processor Information$" | grep "L3 Cache Handle:" | tail -n 1 | cut -d ':' -f 2- | xargs)

		l1_size=$(echo "$dimdecode" | grep -A 15 "Handle $l1_handle" | grep "Installed Size:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		l2_size=$(echo "$dimdecode" | grep -A 15 "Handle $l2_handle" | grep "Installed Size:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		l3_size=$(echo "$dimdecode" | grep -A 15 "Handle $l3_handle" | grep "Installed Size:" | tail -n 1 | cut -d ':' -f 2- | xargs)

		cpu_info=$(echo "${cpu_info}PROCESSOR,$i,$manufacturer,$id,$version,$core_count,$thread_count,$l1_size,$l2_size,$l3_size,$max_speed\n")
	done

	# RAM information
	stick_count=$(echo "$dimdecode" | grep "Memory Device$" | wc -l)
	ram_info=""
	for i in $(seq 1 $stick_count)
	do
		manufacturer=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Manufacturer:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		part_number=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Part Number:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		serial=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Serial Number:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		type=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Type:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		size=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Size:" | tail -n 1 | cut -d ':' -f 2- | xargs)
		clock=$(echo "$dimdecode" | grep -m $i -A 21 "Memory Device$" | grep "Configured Clock Speed:" | tail -n 1 | cut -d ':' -f 2- | xargs)

		ram_info=$(echo "${ram_info}RAM_STICK,$i,$type,$manufacturer,$part_number,$serial,$size,$clock\n")
	done

	sed -i "s\`^EXE,\`${mobo_info}${bios_info}${cpu_info}${ram_info}EXE,\`g" $dump_file
}

resolve_SHA1 "$SHA1_DB" "$dump_file"
add_dmidecode_info "$dump_file"

exit 0
