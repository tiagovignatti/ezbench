#!/usr/bin/env python3

"""
Copyright (c) 2015, Intel Corporation

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of Intel Corporation nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import subprocess
import optparse
import sys
import os

# Start by checking what the user wants to monitor!
p = optparse.OptionParser()
p.add_option('--path', '-p', action='store', type="string", default="", help="Repository path")
p.add_option('--since', '-s', action='store', type="string", default="", help="Starting point of interest")
p.add_option('--until', '-u', action='store', type="string", default="", help="Until which date")
p.add_option('--range', '-r', action='store', type="string", default="", help="Range of commits")
p.add_option('--count', '-c', action='store', type="int", default="-1", help="Select n commits in this commit range")
p.add_option('--interval', '-i', action='store', type="string", default="", help="Interval between commits")
options, arguments = p.parse_args()

if len(options.path) == 0:
    print ("You need to specify a path to the git repo using -p.")
    exit(1)

# Move to the repo's list
os.chdir(options.path)

# Generate the call to git!
range_str = ""
if len(options.range):
    range_str = options.range
elif len(options.since):
    range_str += "--since " + options.since

gitCommandLine = ["/usr/bin/git", "log", "--oneline", "--date=short"]

if len(options.range) > 0:
        gitCommandLine.extend([options.range])
if len(options.until):
    gitCommandLine.extend(["--until", options.until])

result = []
if options.count >= 0:
    if len(options.since) > 0:
        gitCommandLine.extend(["--since ", options.since])
    commitList = subprocess.check_output(gitCommandLine).decode().split(sep='\n')
    step = len(commitList) / options.count
    for i in range(0, options.count):
        result.append(commitList[int(i * step)].split()[0])
elif options.interval:
    gitCommandLine.extend(["--reverse"])
    date = options.since
    sys.stderr.write('Gathering commits: ')
    while True:
        gitCommandLineRound = list(gitCommandLine)
        gitCommandLineRound.extend(["--since", date])
        commitList = subprocess.check_output(gitCommandLineRound)
        if len(commitList) == 0:
            break
        commitList = commitList.decode().split(sep='\n')
        result.append(commitList[0].split()[0])

        sys.stderr.write('.'); sys.stderr.flush()
        date = subprocess.check_output(["date", "+%Y-%m-%d", "-d", date + " +" + options.interval]).decode().split(sep='\n')[0]

sys.stderr.write('\n'); sys.stderr.flush()
print (" ".join(result))
