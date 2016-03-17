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
OF THIS
"""

import collections
import re

class EnvDumpReport:
    csv_layout_v1 = [
        ['BIOS', 'vendor', 'version', 'date'],
        ['BOOTLINK', 'fullpath', 'SHA1', 'provider'],
        ['CPU_FREQ', 'cpu count', 'cpu#0 min', 'cpu#0 max', 'cpu#1 min', 'cpu#1 max', 'cpu#2 min', 'cpu#2 max', 'cpu#3 min', 'cpu#3 max', 'cpu#4 min', 'cpu#4 max', 'cpu#5 min', 'cpu#5 max', 'cpu#6 min', 'cpu#6 max', 'cpu#7 min', 'cpu#7 max', 'cpu#8 min', 'cpu#8 max', 'cpu#9 min', 'cpu#9 max', 'cpu#10 min', 'cpu#10 max', 'cpu#11 min', 'cpu#11 max'],
        ['DATE', 'day', 'time', 'timezone'],
        ['DRM', 'major', 'minor', 'patchlevel', 'driver', 'description', 'vendor', 'vendorid', 'devid', 'codename', 'name'],
        ['DYNLINK', 'fullpath', 'SHA1', 'provider'],
        ['EGL_NEWCONTEXTUSED', 'vendor', 'version', 'client APIs', 'extensions'],
        ['ENV', 'key', 'value'],
        ['ENV_SET', 'key', 'value'],
        ['ENV_UNSET', 'value'],
        ['ENV_CLEAR', 'value'],
        ['EXE', 'fullpath', 'cmdline', 'SHA1', 'provider'],
        ['EXIT', 'status'],
        ['EXIT_CODE', 'exit code'],
        ['EXIT_SIGNAL', 'signal'],
        ['GL_NEWCONTEXTUSED', 'vendor', 'renderer', 'version', 'GL version', 'GLSL version', 'extension count', 'extensions'],
        ['GLX_NEWCONTEXTUSED', 'vendor', 'version', 'extensions'],
        ['INTEL_DRM', 'freq min (MHz)', 'freq max (MHz)', 'freq RP0 (MHz)', 'freq RP1 (MHz)', 'freq RPn (MHz)'],
        ['INTEL_PSTATE', 'pstate count', 'turbo pstate (%)', 'turbo disabled', 'min (%)', 'max (%)'],
        ['IOCTL', 'fullpath'],
        ['KERNEL', 'name', 'nodename', 'release', 'version', 'archicture', 'domain name'],
        ['LIBDRM', 'major', 'minor', 'patchlevel'],
        ['MOTHERBOARD', 'manufacturer', 'product name', 'version'],
        ['PROCESSOR', 'index', 'manufacturer', 'id', 'version', 'core count', 'thread count', 'L1 size', 'L2 size', 'L3 size', 'max clock', 'virtualization enabled'],
        ['RAM_STICK', 'index', 'type', 'manufacturer', 'part number', 'serial', 'size', 'actual clock', 'location'],
        ['SCHED', 'policy', 'cpu installed', 'cpu active', 'affinity', 'priority'],
        ['SOCKET_UNIX_CONNECT', 'fullpath', 'pid', 'server fullpath', 'server cmdline', 'SHA1', 'provider'],
        ['THROTTLING', 'cpu count', 'package', 'cpu list', 'cpu0', 'cpu1', 'cpu2', 'cpu3', 'cpu4', 'cpu5', 'cpu6', 'cpu7', 'cpu8', 'cpu9', 'cpu10', 'cpu11'],
        ['XCB_CONNECTION', 'DRI version', 'driver name'],
        ['XORG_CLOSE', 'display'],
        ['XORG_DDX', 'X\'s pid', 'fullpath', 'SHA1', 'provider'],
        ['XORG_DISPLAY', 'screen id', 'compositor', 'width', 'height', 'depth'],
        ['XORG_SESSION_OPENED', 'display name', 'vendor name', 'version'],
        ['XORG_WINDOW_CREATE', 'parent window id', 'window id', 'width', 'height', 'depth'],
        ['XORG_WINDOW_RESIZE', 'window id', 'width', 'height'],
    ]

    keys = [
        ['BOOTLINK', 'fullpath', '([^/]*)$'],
        ['DYNLINK', 'fullpath', '([^/]*)$'],
        ['ENV', 'key', ''],
        ['PROCESSOR', 'index', ''],
        ['RAM_STICK', 'index', ''],
    ]

    # format: LINE_HEADER, Key template, value template
    human_v1 = [
        ['BIOS', 'HW: BIOS', '${vendor} ${version} ${date}'],
        ['BOOTLINK', 'SW: Link (boot): ${fullpath}', '${provider}'],
        ['CPU_FREQ', 'OS: CPU governor', 'freq. ranges (kHz): [${cpu#0 min}, ${cpu#0 max}], [${cpu#1 min}, ${cpu#1 max}], [${cpu#2 min}, ${cpu#2 max}], [${cpu#3 min}, ${cpu#3 max}], [${cpu#4 min}, ${cpu#4 max}], [${cpu#5 min}, ${cpu#5 max}], [${cpu#6 min}, ${cpu#6 max}], [${cpu#7 min}, ${cpu#7 max}], [${cpu#8 min}, ${cpu#8 max}], [${cpu#9 min}, ${cpu#9 max}], [${cpu#10 min}, ${cpu#10 max}], [${cpu#11 min}, ${cpu#11 max}]'],
        ['DATE', 'OS: Date', '${day} ${time} ${timezone}'],
        ['DRM', 'HW: DRM GPU', '${vendor} ${vendorid}:${devid} (${name} AKA ${codename}), driver ${driver}(${major}.${minor}.${patchlevel})'],
        ['DYNLINK', 'SW: Link (dynamic): ${fullpath}', '${provider}'],
        ['EGL_NEWCONTEXTUSED', 'SW: EGL context', '${vendor}, version ${version}, APIs \'${client APIs}\', extensions: ${extensions}'],
        ['ENV', 'OS: Env (startup): ${key}', '${value}'],
        ['ENV_SET', 'OS: Env set: ${key}', '${value}'],
        ['ENV_UNSET', 'OS: Env unset: ${value}', ''],
        ['ENV_CLEAR', 'OS: Env clear', ''],
        ['EXE', 'OS: Binary cmdline (${fullpath})', '${cmdline} (${provider})'],
        ['EXIT', 'OS: Killed by exit()', '${status}'],
        ['EXIT_CODE', 'OS: Exit code', '${exit code}'],
        ['EXIT_SIGNAL', 'OS: Killed by signal', '${signal}'],
        ['GL_NEWCONTEXTUSED', 'SW: GL context ${version} GLSL ${GLSL version}', '${vendor}, ${renderer}, ${GL version}, extensions: ${extensions}'],
        ['GLX_NEWCONTEXTUSED', 'SW: GLX context', '${vendor}, version ${version}, extensions: ${extensions}'],
        ['INTEL_DRM', 'OS: GPU governor', 'freq. range (MHz) = [${freq min (MHz)}, ${freq max (MHz)}], RP0 = ${freq RP0 (MHz)}, RP1 = ${freq RP1 (MHz)}, RPn = ${freq RPn (MHz)}'],
        ['INTEL_PSTATE', 'OS: CPU governor pstate', 'range = [${min (%)}%, ${max (%)}%], turbo disabled? ${turbo disabled}'],
        ['IOCTL', 'HW: Device node', '${fullpath}'],
        ['KERNEL', 'OS: Kernel', '${name}, ${nodename}, ${release}, ${version}, ${achitecture}, ${domain name}'],
        ['LIBDRM', 'SW: Libdrm', 'ABI version ${major}.${minor}.${patchlevel}'],
        ['MOTHERBOARD', 'HW: Motherboard', '${manufacturer} ${product name} ${version}'],
        ['PROCESSOR', 'HW: Processor${index}', '${manufacturer} ${version} (${id}), max freq. ${max clock}, ${core count} cores ${thread count} threads, L1=${L1 size}, L2=${L2 size}, L3=${L3 size}, virt? ${virtualization enabled}'],
        ['RAM_STICK', 'HW: RAM${index}', '${type} ${size} @ ${actual clock} installed in ${location}'],
        ['SCHED', 'OS: CPU sched.', '${policy}, CPUs=(installed=${cpu installed}, active=${cpu active}), affinity=${affinity} nice=${priority}'],
        ['SOCKET_UNIX_CONNECT', 'OS: UNIX service ${fullpath}', 'exe_path=${server fullpath}, cmd=${server cmdline}, pid=${pid}, version=${provider}'],
        ['THROTTLING', 'HW: Throttling events', 'package=${package}, CPUs=[${cpu0}, ${cpu1}, ${cpu2}, ${cpu3}, ${cpu4}, ${cpu5}, ${cpu6}, ${cpu7}, ${cpu8}, ${cpu9}, ${cpu10}, ${cpu11}]'],
        ['XCB_CONNECTION', 'OS: XCB connection', '${DRI version}: driver name \'${driver name}\''],
        ['XORG_CLOSE', 'OS: X display closed', '${display}'],
        ['XORG_DDX', 'OS: X drivers: ${fullpath}', '${provider}'],
        ['XORG_DISPLAY', 'OS: X display', 'Screen id ${screen id} (${width}x${height}x${depth}) with compositor ${compositor}'],
        ['XORG_SESSION_OPENED', 'OS: X display opened', '${display name}, vendor=\'${vendor name}\', version=${version}'],
        ['XORG_WINDOW_CREATE', 'OS: X window created', '${width}x${height}x${depth}, id=${window id} (parent=${parent window id})'],
        ['XORG_WINDOW_RESIZE', 'OS: X window resized', 'id=${window id} to ${width}x${height}'],
    ]

    def __createkey__(self, category, vals):
        # Try to find a key
        for key in self.keys:
            if key[0] == category:
                m = re.search(key[2], vals[key[1]])
                if m is not None and len(m.groups()) > 0:
                    return m.groups()[0]
                else:
                    return vals[key[1]]

        # We failed, use a number instead
        return "{0}".format(len(self.values[category]))

    def __patternresolve__(self, pattern, fields):
        out = pattern
        for key in fields:
            if key == "extensions":
                value = ' '.join(str(e) for e in fields[key])
            else:
                value = fields[key]
            out = out.replace("${" + key + "}", value)
        out = re.sub('\$\{[^}]*\}', '', out)
        return out

    def __humanoutput__(self, category, fields):
        # look for a human entry for those fields
        for human_line in self.human_v1:
            if human_line[0] == category:
                key = self.__patternresolve__(human_line[1], fields)
                values = self.__patternresolve__(human_line[2], fields)
                if key in self.values:
                    index=1
                    while "{}#{}".format(key, index) in self.values:
                        index = index + 1
                    key =  "{}#{}".format(key, index)
                self.values[key] = values
                return True
        return False

    def __init__(self, report_path, human=False):
        try:
            f = open(report_path)
        except Exception as e:
            print("Cannot open the file {0}: {1}".format(report_path, str(e)))
            return

        # Create the report
        self.version = -1
        self.complete = False
        self.values = dict()
        head_re = re.compile('^-- Env dump start \(version (\d+)\) --$')
        for line in f:
            raw_fields = line.rstrip('\n').split(',')

            # Detect when a coma was found between two '', useful for the EXE line
            fields = []
            total_count = 0
            for field in raw_fields:
                if raw_fields[0] == 'EXE' and (total_count % 2) == 1:
                    fields[-1] = fields[-1] + ',' + field
                else:
                    fields.append(field)
                total_count += field.count('\'')

            # Parse the header and footer
            if len(fields) == 1:
                head_m = head_re.match(fields[0])
                if head_m is not None:
                    self.version = int(head_m.groups()[0])
                elif fields[0] == '-- Env dump end --':
                    self.complete = True

            # Look for the right line in the csv layout
            for layout_line in self.csv_layout_v1:
                if layout_line[0] == fields[0]:
                    # Copy each entry
                    vals = dict()
                    for f in range(1, len(layout_line)):
                        if len(fields) > f:
                            if layout_line[f] == 'extensions':
                                vals[layout_line[f]] = set(fields[f].strip().split(' '))
                            else:
                                vals[layout_line[f]] = fields[f]

                    # create the entry
                    cat = layout_line[0]
                    if human:
                        self.__humanoutput__(cat, vals)
                    else:
                        if cat not in self.values:
                            self.values[cat] = vals
                        else:
                            if type(self.values[cat]) is dict:
                                orig = self.values[cat]
                                self.values[cat] = collections.OrderedDict()
                                entry_key = self.__createkey__(cat, orig)
                                self.values[cat][entry_key] = orig
                            entry_key = self.__createkey__(cat, vals)
                            self.values[cat][entry_key] = vals

    def __to_set__(self, head, key, ignore_list):
        if type(head) is str:
            return set([(key, head)])

        out = set()
        for entry in head:
            if len(key) > 0:
                entrykey = key + "." + entry
            else:
                entrykey = entry

            ignore = False
            for ignoreentry in ignore_list:
                if ignoreentry.search(entrykey) is not None:
                    ignore = True
            if ignore == True:
                continue

            if type(head) is not set:
                out.update(self.__to_set__(head[entry], entrykey, ignore_list))
            else:
                out.update(set([(entrykey, True)]))
        return out

    def to_set(self, ignore_list=[]):
        ignore_list_re = []
        # pre-compile the ignore_list
        for ignoreentry in ignore_list:
            ignore_list_re.append(re.compile(ignoreentry))

        return self.__to_set__(self.values, "", ignore_list_re)
