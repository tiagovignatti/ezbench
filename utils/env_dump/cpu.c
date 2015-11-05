/* Copyright (c) 2015, Intel Corporation
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *     * Redistributions of source code must retain the above copyright notice,
 *       this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in the
 *       documentation and/or other materials provided with the distribution.
 *     * Neither the name of Intel Corporation nor the names of its contributors
 *       may be used to endorse or promote products derived from this software
 *       without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#define _GNU_SOURCE

#include "env_dump.h"

#include <sys/resource.h>
#include <sys/sysinfo.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <malloc.h>
#include <stdint.h>
#include <sched.h>


static char *
read_file(const char *path, size_t len_max)
{
	size_t len;
	char *buf;

	FILE *file = fopen(path, "r");
	if (!file)
		return NULL;

	buf = calloc(len_max, sizeof(char));
	if (!buf) {
		fclose(file);
		return buf;
	}

	len = fread(buf, 1, len_max, file);

	/* get rid of the final \n */
	if (len > 0 && buf[len - 1] == '\n')
		buf[len - 1] = '\0';

	return buf;
}

static void
dump_cpu_common()
{
	char *path = malloc(255);
	int i;

	fprintf(env_file, "CPU_FREQ,%i", get_nprocs_conf());
	for (i = 0; i < get_nprocs_conf(); i++) {
		char *min, *max;
		snprintf(path, 255,
			 "/sys/devices/system/cpu/cpu%i/cpufreq/scaling_min_freq",
			 i);
		min = read_file(path, 20);

		snprintf(path, 255,
			 "/sys/devices/system/cpu/cpu%i/cpufreq/scaling_max_freq",
			 i);
		max = read_file(path, 20);

		fprintf(env_file, ",%s,%s", min, max);
		free(min);
		free(max);
	}
	fprintf(env_file, "\n");

	free(path);
}

static void
dump_shed_common()
{
	uint64_t affinity = 0;
	const char *sched_str;
	int prio, sched, i;
	cpu_set_t cpu_set;

	/* FIXME: This does not work when having more than 64 CPUs */
	sched_getaffinity(0, sizeof(cpu_set), &cpu_set);
	for (i = 0; i < 64; i++) {
		affinity |= (CPU_ISSET(i, &cpu_set) != 0) << i;
	}

	sched = sched_getscheduler(0);
	switch (sched) {
	case SCHED_OTHER:
		sched_str = "SCHED_OTHER";
		break;
	case SCHED_BATCH:
		sched_str = "SCHED_BATCH";
		break;
	case SCHED_IDLE:
		sched_str = "SCHED_IDLE";
		break;
	case SCHED_FIFO:
		sched_str = "SCHED_FIFO";
		break;
	case SCHED_RR:
		sched_str = "SCHED_RR";
		break;
	case -1:
		sched_str = "ERROR";
		break;
	default:
		sched_str = "UNKNOWN";
		break;
	}

	prio = getpriority(PRIO_PROCESS, 0);

	fprintf(env_file, "SCHED,%s,%i,%i,%lu,%i\n", sched_str,
		get_nprocs_conf(), get_nprocs(), affinity, prio);
}

static void
dump_throttling_common()
{
	char *package, *path = malloc(255);
	int i;

	package = read_file("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count", 20);

	fprintf(env_file, "THROTTLING,%i,%s", get_nprocs_conf(), package);
	for (i = 0; i < get_nprocs_conf(); i++) {
		char *core;
		snprintf(path, 255,
			 "/sys/devices/system/cpu/cpu%i/thermal_throttle/core_throttle_count",
			 i);
		core = read_file(path, 20);
		fprintf(env_file, ",%s", core);
		free(core);
	}
	fprintf(env_file, "\n");

	free(path);
}

static void
dump_intel_pstate()
{
	struct stat pstate_dir;
	char *num_pstates, *turbo_pct, *min, *max, *turbo;

	/* check that the intel pstate governor is being used */
	if (stat("/sys/devices/system/cpu/intel_pstate/", &pstate_dir))
		return;

	/* read the different values */
	num_pstates = read_file("/sys/devices/system/cpu/intel_pstate/num_pstates", 10);
	turbo_pct = read_file("/sys/devices/system/cpu/intel_pstate/turbo_pct", 10);
	min = read_file("/sys/devices/system/cpu/intel_pstate/min_perf_pct", 4);
	max = read_file("/sys/devices/system/cpu/intel_pstate/max_perf_pct", 4);
	turbo = read_file("/sys/devices/system/cpu/intel_pstate/no_turbo", 2);

	fprintf(env_file, "INTEL_PSTATE,%s,%s,%s,%s,%s\n", num_pstates,
		turbo_pct, turbo, min, max);

	free(num_pstates); free(turbo_pct); free(min); free(max); free(turbo);
}

void
_env_dump_cpu_init()
{
	dump_shed_common();
	dump_cpu_common();
	dump_throttling_common();
	dump_intel_pstate();
}

void
_env_dump_cpu_fini()
{
	dump_throttling_common();
}