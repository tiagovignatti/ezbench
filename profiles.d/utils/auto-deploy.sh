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

function profile_repo_deployment_version_dir() {
    echo "$PROFILE_DEPLOY_BASE_DIR/$version"
}

function auto_deploy_make_and_deploy() {
    # Return error codes:
    # 71: Compilation error
    # 72: Deployment error

    # First, check if we already have the
    dep_version_dir=$(profile_repo_deployment_version_dir)
    depl_version=$(LD_LIBRARY_PATH=$dep_version_dir/lib:$LD_LIBRARY_PATH \
                   PATH=$dep_version_dir/bin:$PATH \
                   profile_repo_deployed_version)

    if [[ "$depl_version" != "$version" ]]
    then
        echo "$(date +"%m-%d-%Y-%T"): Start compiling version $version"
        local compile_start=$(date +%s)

        profile_repo_compile_start $version
        local exit_code=$?
        [ $exit_code -ne 0 ] && return $exit_code

        # Call the user-defined pre-compile hook
        callIfDefined compile_pre_hook

        repo_compile_version
        compile_error=$?

        # Call the user-defined post-compile hook
        callIfDefined compile_post_hook

        profile_repo_compile_stop
        local exit_code=$?
        [ $exit_code -ne 0 ] && return $exit_code

        # compute the compilation time
        local compile_end=$(date +%s)
        local build_time=$(($compile_end-$compile_start))
        echo "$(date +"%m-%d-%Y-%T"): Done compiling version $version. Build time = $build_time."

        # Update our build time estimator
        local avgBuildTime=$(profile_repo_compilation_time)
        local avgBuildTime=$(bc <<< "0.75*$avgBuildTime + 0.25*$build_time")
        profile_repo_set_compilation_time $avgBuildTime
    else
        echo "$(date +"%m-%d-%Y-%T"): Found a cached version of the compilation, re-use it!"
    fi

    rm $PROFILE_DEPLOY_DIR 2> /dev/null

    # TODO: Allow profiles to override this function with their own deployment function
    ln -s $dep_version_dir $PROFILE_DEPLOY_DIR || return 72

    return $compile_error
}

# TODO: Add a function that says how long it would take to test

makeAndDeployCmd="auto_deploy_make_and_deploy"
