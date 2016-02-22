function make_install_sha1_dump() {
    # First, install to the right folder
    make install-strip || exit 72

    [ -z "$SHA1_DB" ] && echo "Error: No SHA1_DB specified" && return 0

    # make a temporary folder to install our SW in
    root=$(mktemp -d)

    # install the deps
    make DESTDIR=$root install 2> /dev/null
    if [ $? -ne 0 ]
    then
        rm -rf $root
        exit 72
    fi

    # list all the binaries installed and add them to the SHA1_DB
    for binary in $(find $root -type f -executable)
    do
        [[ ${binary: -3} == ".la" ]] && continue

        binary=${binary#$root}

        $SHA1_DB/sha1_db $SHA1_DB - add_git . $binary
    done

    rm -rf $root
    return 0
}
