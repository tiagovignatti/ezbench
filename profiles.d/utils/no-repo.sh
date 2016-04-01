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
    return 0
}

# MANDATORY: Print the version pointed by the tip of the repo (HEAD for git for example)
# Inputs:
#   - $repoDir
function profile_repo_version() {
    echo ""
}

# MANDATORY: Print the repo type
# Inputs: None
function profile_repo_type() {
    echo "none"
}

# MANDATORY: Print the version pointed by the tip of the repo (HEAD for git for example)
# Inputs:
#   - $repoDir
function profile_repo_version_to_human() {
   echo "$1"
}

# Print the version pointed by the tip of the repo (HEAD for git for example)
# Only mandatory if your repo supports compiling/deploying versions
# Inputs:
#   - $repoDir
#   - $1 = version to get the patch for
function profile_repo_get_patch() {
    echo ""
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
    echo $(profile_repo_deployed_version)
}

# MANDATORY: Print the average compilation time
# Inputs:
#   - $repoDir
function profile_repo_compilation_time() {
    echo 0
}

# MANDATORY: Set the average compilation time
# Inputs:
#   - $repoDir
#   - $1: time to be set
function profile_repo_set_compilation_time() {
    return 0
}

makeAndDeployCmd=""
repoDir=""
