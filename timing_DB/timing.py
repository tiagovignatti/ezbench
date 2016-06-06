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

import statistics
import argparse
import fcntl
import json
import sys
import os

class TimingsDB:
    def __init__(self, base_folder):
        self.db_file_name = base_folder + '/db.json'
        try:
            with open(self.db_file_name) as data_file:
                fcntl.flock(data_file, fcntl.LOCK_EX)
                self.db = json.load(data_file)
                fcntl.flock(data_file, fcntl.LOCK_UN)
        except:
            self.db = dict()
            self.db["version"] = 1
            self.db["timings"] = dict()
            pass

    def add(self, namespace, key, value):
        if "timings" not in self.db:
            self.db["timings"] = dict()
        if namespace not in self.db["timings"]:
            self.db["timings"][namespace] = dict()
        if key not in self.db["timings"][namespace]:
            self.db["timings"][namespace][key] = list()

        value_list = self.db["timings"][namespace][key]
        value_list.append(float(value))
        value_list = value_list[-10:]

        with open(self.db_file_name, mode='w') as data_file:
            fcntl.flock(data_file, fcntl.LOCK_EX)
            json.dump(self.db, data_file, sort_keys=True, indent=4, separators=(',', ': '))
            fcntl.flock(data_file, fcntl.LOCK_UN)

    def data(self, namespace, key):
        if "timings" not in self.db:
            return []
        if namespace not in self.db["timings"]:
            return []
        if key not in self.db["timings"][namespace]:
            return []

        return list(map(float, self.db["timings"][namespace][key]))


if __name__ == "__main__":
    # parse the options
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", dest='namespace', help="Namespace for the key",
                        action="store", default="default")
    parser.add_argument("-k", dest='key', help="Key for the data you want to access",
                        action="store")
    parser.add_argument("-a", dest='add_value', help="Add a timing information for a benchmark or profile",
                        action="store")
    parser.add_argument("-r", dest="read_command", help="Read the average time of a benchmark or profile",
                    choices=('mean', 'median', 'minimum', 'maximum'))
    args = parser.parse_args()

    script_dir = os.path.abspath(sys.path[0])
    timingsdb = TimingsDB(script_dir)

    if args.add_value:
        timingsdb.add(args.namespace, args.key, args.add_value)
    elif args.read_command is not None:
        value_list = timingsdb.data(args.namespace, args.key)
        if len(value_list) == 0:
            print("-1")
        elif args.read_command == "mean":
            print(statistics.mean(value_list))
        elif args.read_command == "median":
            print(statistics.median(value_list))
        elif args.read_command == "minimum":
            print(min(value_list))
        elif args.read_command == "maximum":
            print(max(value_list))
