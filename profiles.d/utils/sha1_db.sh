function make_install_sha1_dump() {
    # First, install to the right folder
    make install || exit 72

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

        git_sha1=$(git rev-parse --short HEAD)
        tracked_branch=$(git branch -vv --no-color | grep --color=never "^*" | cut -d '[' -f 2 | cut -d ']' -f 1)
        remote=$(echo "$tracked_branch" | cut -d '/' -f 1)
        branch=$(echo "$tracked_branch" | cut -d '/' -f 2)
        fetch_url=$(git remote show -n origin | grep "Fetch URL:" | cut -d ':' -f 2- | cut -d ' ' -f 2-)
        sha1=$(sha1sum $binary | cut -d ' ' -f 1)

        echo "SHA1_DB: $binary ($sha1) added with git SHA1 $git_sha1"
        $SHA1_DB/sha1_db $SHA1_DB $sha1 add $git_sha1 $binary "$fetch_url/$branch"
    done

    rm -rf $root
    return 0
}
