# Copyright (c) 2015, Intel Corporation
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Intel Corporation nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# MANDATORY: Check that the repo given by the user is valid
# Inputs:
#   - $repoDir
# Output:
#   - Exit if the check fails with the right exit code
#   - return 0 otherwise
function profile_repo_check() {
    if [ -z "$repoDir" ]
    then
        echo "ERROR: You did not specify a git repository path (-p). Aborting..."
        exit 14
    fi

    GIT_DIR="$repoDir/.git" git status 2>/dev/null > /dev/null
    if [ $? -ne 0 ]
    then
        echo "ERROR: The path '$repoDir' does not contain a valid git repository. Aborting..."
        exit 1
    fi

    return 0
}

# MANDATORY: Print the version pointed by the tip of the repo (HEAD for git for example)
# Inputs:
#   - $repoDir
function profile_repo_version() {
    version=$(GIT_DIR="$repoDir/.git" git rev-list -n 1 --abbrev-commit HEAD 2>/dev/null)
    if [ $? -eq 0 ]
    then
        echo "$version"
    fi
}

# MANDATORY: Print the repo type
# Inputs: None
function profile_repo_type() {
    echo "git"
}

# MANDATORY: Print the version pointed by the tip of the repo (HEAD for git for example)
# Inputs:
#   - $repoDir
function profile_repo_version_to_human() {
   GIT_DIR="$repoDir/.git" git show --format="%h %s" -s "$1"
}

# Print on stdout the patch for the version id given as a parameter
# Inputs:
#   - $repoDir
#   - $1 = version to get the patch for
function profile_repo_get_patch() {
    [ -z "$1" ] && { echo "ERROR: No version specified"; return 71; }
    GIT_DIR="$repoDir/.git" git show $1 --format=fuller
}

# MANDATORY: Check the list of versions to test as provided by the user and
# return a list of acceptable individual versions
# Inputs:
#   - $repoDir
#   - $@ = versions the user wants to test
# Output:
#   - exit 51 if any versoin is invalid
#   - print the list of versions to test
function profile_get_version_list() {
    cwd=$(pwd)
    cd "$repoDir"
    versionList=
    for id in "$@"; do
        if [[ $id =~ \.\. ]]; then
            versionList+=$(git rev-list --abbrev-commit --reverse "$id" 2> /dev/null)
        else
            versionList+=$(git rev-list --abbrev-commit -n 1 "$(git rev-parse "$id" 2> /dev/null)" 2> /dev/null)
        fi
        [ $? -ne 0 ] && printf "ERROR: Invalid git commit ID '$id'\n" && exit 51
        versionList+=" "
    done
    cd $cwd
    echo $versionList
}

# MANDATORY: List all the versions we previously compiled
# Outputs:
#   - Space-separated list of versions
function profile_get_built_versions() {
    pushd  $PROFILE_DEPLOY_BASE_DIR > /dev/null || return 1
    for file in *; do
        echo -n "$file "
    done
    popd > /dev/null

    return 0
}

# MANDATORY: Print the average compilation time
# Inputs:
#   - $repoDir
function profile_repo_compilation_time() {
    GIT_DIR="$repoDir/.git" git config --get ezbench.average-build-time 2>/dev/null || echo 30
}

# MANDATORY: Set the average compilation time
# Inputs:
#   - $repoDir
#   - $1: time to be set
function profile_repo_set_compilation_time() {
    GIT_DIR="$repoDir/.git" git config --replace-all ezbench.average-build-time "$(printf "%.0f" "$1")"
}

# Set up the repo so as we can start compiling $version
# Only mandatory if your repo supports compiling/deploying versions
# Inputs:
#   - $repoDir
#   - $1 = version that needs to be prepared for compilation
function profile_repo_compile_start() {
    [ -z "$1" ] && { echo "ERROR: No version specified"; return 71; }
    [ ! -d "$DEPLOY_BASE_DIR" ] && { echo "ERROR: DEPLOY_BASE_DIR($DEPLOY_BASE_DIR) is not a folder"; return 71; }

    # Get information about the upstream
    cd "$repoDir" || return 71
    tracked_branch=$(git branch -vv --no-color | grep --color=never "^*" | cut -d '[' -f 2 | cut -d ']' -f 1 | cut -d : -f 1)
    remote=$(echo "$tracked_branch" | cut -d '/' -f 1)
    branch=$(echo "$tracked_branch" | cut -d '/' -f 2)
    if [ -n "$(echo "$branch" | grep " ")" ]
    then
        # Local branch detected
        fetch_url="$USER@$(hostname):$(pwd)"
        branch=$(git rev-parse --abbrev-ref HEAD)
    else
        fetch_url=$(git remote show -n origin | grep "Fetch URL:" | cut -d ':' -f 2- | cut -d ' ' -f 2-)
    fi

    # Clone the repo in a different directory
    mkdir -p $PROFILE_TMP_BUILD_DIR 2> /dev/null
    rm -rf $PROFILE_TMP_BUILD_DIR 2> /dev/null
    git clone "$repoDir" "$PROFILE_TMP_BUILD_DIR" || return 71

     # Use the new repo
    export PROFILE_REPO_OLDPWD=$(pwd)
    cd "$PROFILE_TMP_BUILD_DIR" || return 71
    git reset --hard "$1"

    # Display information about the git tree
    git_sha1=$(git rev-parse --short HEAD)
    echo "BUILD_INFO, Repo type: git"
    echo "BUILD_INFO, Local tree: $repoDir"
    echo "BUILD_INFO, Fetch URL: $fetch_url"
    echo "BUILD_INFO, Branch: $branch"
    echo "BUILD_INFO, Commit: $git_sha1"
}

# Tear-down the environment set by the last profile_repo_compile_start call
# Only mandatory if your repo supports compiling/deploying versions
# Inputs:
#   - $repoDir
function profile_repo_compile_stop() {
    cd $PROFILE_REPO_OLDPWD
    rm -rf $PROFILE_TMP_BUILD_DIR
    unset PROFILE_REPO_OLDPWD
}
