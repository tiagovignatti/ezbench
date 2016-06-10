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

#include <pthread.h>
#include <dirent.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct metric_t {
	char *name;
	char *path;
	float factor;
	float offset;
	float (*process)(struct metric_t *metric, double timestamp_ms,
	                 float calibrated_value);

	double prev_timestamp_ms;
	float prev_value;
};

/* Not protected by a mutex because it is not changed after the initial
 * startup which is not multithreaded.
 */
pthread_t pthread_polling;
struct metric_t *metrics;
uint32_t metrics_count = 0;
FILE *output_file;

static void
metric_add(char *name, char *path, float factor, float offset,
		   float (*process)(struct metric_t *metric, double, float))
{
	metrics = realloc(metrics, sizeof(struct metric_t) * (metrics_count + 1));
	metrics[metrics_count].name = name;
	metrics[metrics_count].path = path;
	metrics[metrics_count].factor = factor;
	metrics[metrics_count].offset = offset;
	metrics[metrics_count].process = process;

	metrics[metrics_count].prev_timestamp_ms = 0;
	metrics[metrics_count].prev_value = 0.0;
	metrics_count++;
}

static void
add_hwmon_device(const char *hwmon_dir)
{
	const char *files[] = { "fan", "pwm", "temp", "power", "energy" };
	const char *suffix[] = { "_input", "", "_input", "_input", "_input" };
	const char *unit[] = { "RPM", "%", "°C", "W", "J" };
	float factor[] = { 0, 100.0/255, 1e-3,  1e-6, 1e-6};
	char *path, *driver_name, *label, *input_file, *metric_name;
	long long val;
	int f, i;

	path = malloc(4096 * sizeof(char));

	sprintf(path, "%s/name", hwmon_dir);
	driver_name = _env_dump_read_file(path, 100, NULL);

	for (f = 0; f < sizeof(files) / sizeof(const char *); f++) {
		for (i = 1; i < 20; i++) {
			snprintf(path, 4096, "%s/%s%i%s", hwmon_dir, files[f], i, suffix[f]);
			val = _env_dump_read_file_intll(path, 10);
			if (val == -1)
				break;

			input_file = strdup(path);

			snprintf(path, 4096, "%s/%s%i_label", hwmon_dir, files[f], i);
			label = _env_dump_read_file(path, 100, NULL);
			if (label == NULL) {
				metric_name = malloc(strlen(driver_name) + 1 + strlen(files[f]) + 3 + strlen(unit[f]) + 1);
				sprintf(metric_name, "%s.%s%i (%s)", driver_name, files[f], i, unit[f]);
			} else {
				metric_name = malloc(strlen(driver_name) + 1 + strlen(label) + 3 + strlen(unit[f]) + 1);
				sprintf(metric_name, "%s.%s (%s)", driver_name, label, unit[f]);
				free(label);
			}

			metric_add(metric_name, input_file, factor[f], 0, NULL);
		}
	}

	free(driver_name);
	free(path);
}

static void
add_hwmon()
{
	DIR *dir;
	struct dirent *dp;

	dir = opendir("/sys/class/hwmon/");
	if (dir == NULL)
		return;

	while ((dp = readdir(dir)) != NULL) {
		if (!strncmp(dp->d_name, "hwmon", 5)) {
			char *path = malloc((17 + strlen(dp->d_name) + 1) * sizeof(char));
			sprintf(path, "/sys/class/hwmon/%s", dp->d_name);
			add_hwmon_device(path);
			free(path);
		}
	}
	closedir(dir);
}

static float
rapl_process_value(struct metric_t *metric, double timestamp_ms,
                   float calibrated_value)
{
	if (metric->prev_timestamp_ms == 0) {
		return 0;
	} else {
		double time_diff_ms = timestamp_ms - metric->prev_timestamp_ms;
		float val_diff = calibrated_value - metric->prev_value;

		fprintf(stderr, "%s: %f J in %f ms\n", metric->name, val_diff, time_diff_ms);

		return val_diff * 1000 / time_diff_ms;
	}
}

static int
add_rapl_device(const char *rapl_dir, int dev_id, const char *parent_base_name)
{
	char *path, *block_name, *base_name, *metric_name;
	long long val;
	int i;

	path = malloc(4096 * sizeof(char));

	/* bail out if the device is not enabled */
	snprintf(path, 4096, "%s/enabled", rapl_dir);
	if (_env_dump_read_file_intll("/sys/class/powercap/intel-rapl/enabled",
		                          10) != 1)
		return 1;

	snprintf(path, 4096, "%s/name", rapl_dir);
	block_name = _env_dump_read_file(path, 100, NULL);
	if (!block_name)
		return 1;

	if (parent_base_name == NULL) {
		base_name = malloc(8 + strlen(block_name) + 1);
		sprintf(base_name, "rapl%i.%s", dev_id, block_name);
	} else {
		base_name = malloc(strlen(parent_base_name) + 1 + strlen(block_name) + 1);
		sprintf(base_name, "%s.%s", parent_base_name, block_name);
	}
	metric_name = malloc(strlen(base_name) + 4 + 1);
	sprintf(metric_name, "%s (W)", base_name);

	free(block_name);

	/* Find all the constraints */
	for (i = 0; i < 20; i++) {
		const char *name;
		long long time_window, max_power, power_limit;

		snprintf(path, 4096, "%s/constraint_%i_name", rapl_dir, i);
		name = _env_dump_read_file(path, 50, NULL);
		if (name == NULL)
			break;

		snprintf(path, 4096, "%s/constraint_%i_time_window_us", rapl_dir, i);
		time_window = _env_dump_read_file_intll(path, 10);

		snprintf(path, 4096, "%s/constraint_%i_max_power_uw", rapl_dir, i);
		max_power = _env_dump_read_file_intll(path, 10);

		snprintf(path, 4096, "%s/constraint_%i_power_limit_uw", rapl_dir, i);
		power_limit = _env_dump_read_file_intll(path, 10);

		fprintf(env_file, "RAPL_CONSTRAINT,%s,%s,%llu,%.1f,%.1f\n",
				base_name, name, time_window, max_power / 1.0e6,
				power_limit / 1.0e6);
	}

	/* Add the metric */
	snprintf(path, 4096, "%s/energy_uj", rapl_dir);
	val = _env_dump_read_file_intll(path, 10);
	metric_add(metric_name, strdup(path), 1e-6, val, rapl_process_value);

	/* Find all the subdevices */
	if (parent_base_name == NULL) {
		for (i = 0; i < 20; i++) {
			snprintf(path, 4096, "%s/intel-rapl:%i:%i", rapl_dir, dev_id, i);
			if (add_rapl_device(path, dev_id, base_name))
				break;
		}
	}

	free(base_name);
	free(path);

	return 0;
}

static void
add_rapl()
{
	char *path;
	int i;

	if (_env_dump_read_file_intll("/sys/class/powercap/intel-rapl/enabled",
		                          10) != 1)
		return;

	path = malloc(4096);
	for (i = 0; i < 100; i++) {
		snprintf(path, 4096, "/sys/class/powercap/intel-rapl/intel-rapl:%i", i);
		if (add_rapl_device(path, i, NULL))
			break;
	}
	free(path);
}

static float
poll_metric(struct metric_t *metric, double timestamp_ms)
{
	long long val = _env_dump_read_file_intll(metric->path, 10);
	float calib_val, final_val;

	if (val == -1)
		return 0;

	calib_val = (val - metric->offset) * metric->factor;
	if (metric->process)
		final_val = metric->process(metric, timestamp_ms, calib_val);
	else
		final_val = calib_val;
	metric->prev_timestamp_ms = timestamp_ms;
	metric->prev_value = calib_val;

	return final_val;
}

static void *
polling_thread(void *arg)
{
	FILE *file = (FILE *)arg;
	struct timespec ts;
	int i;

	/* Do not allow to cancel the thread immediatly */
	pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, NULL);

	/* print the header */
	fprintf(file, "time (ms)");
	for (i = 0; i < metrics_count; i++)
		fprintf(file, ",%s", metrics[i].name);
	fprintf(file, "\n");

	/* poll all the metrics */
	while (1) {
		double timestamp_ms;

		clock_gettime(CLOCK_REALTIME, &ts);
		timestamp_ms = difftime(ts.tv_sec, 0) * 1000 + ts.tv_nsec / 1e6;

		fprintf(file, "%.0f", timestamp_ms);
		for (i = 0; i < metrics_count; i++)
			fprintf(file, ",%.2f", poll_metric(&metrics[i], timestamp_ms));
		fprintf(file, "\n");

		/* wait a 100ms and make the thread cancellable during this wait  */
		pthread_setcancelstate(PTHREAD_CANCEL_ENABLE, NULL);
		usleep(100000);
		pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, NULL);
	}

	return NULL;
}

void
_env_dump_metrics_init()
{
	int err;

	output_file = _env_dump_create_file(getenv("ENV_DUMP_METRIC_FILE"));
	if (output_file == NULL)
		return;

	add_hwmon();
	add_rapl();

	if (metrics_count > 0) {
		err = pthread_create(&pthread_polling, NULL, polling_thread, output_file);
		if(err) {
			fprintf(stderr,
					"env_dump: failed to create a thread for metrics (%i)\n", err);
		}
	}
}

void
_env_dump_metrics_fini()
{
	struct timespec ts;
	int i;

	if (metrics_count > 0) {
		/* ask the thread to terminate */
		pthread_cancel(pthread_polling);

		/* wait for the thread to be done */
		clock_gettime(CLOCK_REALTIME, &ts);
		ts.tv_sec += 1;
		pthread_timedjoin_np(pthread_polling, NULL, &ts);

		/* destroy the resources */
		for (i = 0; i < metrics_count; i++) {
			free(metrics[i].name);
			free(metrics[i].path);
		}
		free(metrics);
	}

	if (output_file)
		fclose(output_file);
}
