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

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <link.h>

void
env_var_dump_binary_information(int pid)
{
	size_t buflen = 4096, size;
	char *buf = malloc(buflen), *cur;
	char proc_path[22]; /* longest fd path is /proc/4194303/cmdline */
	FILE *cmd_file;

	if (!buf) {
		fprintf(stderr, "Error, no memory left. Exit!");
		exit(1);
	}

	if (pid == 0)
		pid = getpid();

	/* first read the url of the program */
	snprintf(proc_path, sizeof(proc_path), "/proc/%i/exe", pid);
	size = readlink(proc_path, buf, buflen);
	if (size == -1) {
		fprintf(env_file, "ERROR(%s),", strerror(errno));
	} else {
		buf[size] = '\0';
		fprintf(env_file, "%s,", buf);
	}

	/* then read the arguments */
	snprintf(proc_path, sizeof(proc_path), "/proc/%i/cmdline", pid);
	cmd_file = fopen(proc_path, "r");
	if (cmd_file) {
		size = fread(buf, 1, buflen, cmd_file);

		/* the fields are separated by \0 characters, replace them by
		 * spaces and add '' arounds them. The last field has two null
		 * characters.
		 */
		cur = buf;
		while (*cur && (cur - buf) < size) {
			if (cur == buf)
				fprintf(env_file, "'");
			else if (*(cur - 1) == '\0')
				fprintf(env_file, " '");
			fprintf(env_file, "%c", *cur);

			cur++;

			if (*cur == '\0') {
				fprintf(env_file, "'");
				cur++;
			}
		}
		fprintf(env_file, ",");

	} else
		fprintf(env_file, "ERROR,");

	snprintf(proc_path, sizeof(proc_path), "/proc/%i/exe", pid);
	_env_dump_compute_and_print_sha1(proc_path);

	free(buf);
}

static void
dump_env_vars()
{
	char **env = environ;

	while (*env) {
		fprintf(env_file, "ENV,%s\n", *env);
		env++;
	}
}

int
putenv(char *string)
{
	int(*orig_putenv)(char *);
	int ret;

	orig_putenv = _env_dump_resolve_symbol_by_name("putenv");

	ret = orig_putenv(string);
	if (!ret)
		fprintf(env_file, "ENV_UNSET,%s\n", string);

	return ret;
}

int
setenv(const char *name, const char *value, int replace)
{
	int(*orig_setenv)(const char *, const char *, int);
	int ret;

	orig_setenv = _env_dump_resolve_symbol_by_name("setenv");

	ret = orig_setenv(name, value, replace);
	if (!ret)
		fprintf(env_file, "ENV_SET,%s=%s\n", name, value);

	return ret;
}

int
unsetenv(const char *name)
{
	int(*orig_unsetenv)(const char *);
	int ret;

	orig_unsetenv = _env_dump_resolve_symbol_by_name("unsetenv");

	ret = orig_unsetenv(name);
	if (!ret)
		fprintf(env_file, "ENV_UNSET,%s\n", name);

	return ret;
}

int
clearenv(void)
{
	int(*orig_clearenv)(void);
	int ret;

	orig_clearenv = _env_dump_resolve_symbol_by_name("clearenv");

	ret = orig_clearenv();
	if (!ret)
		fprintf(env_file, "ENV_CLEAR\n");

	return ret;
}

void
_env_dump_posix_env_init()
{
	fprintf(env_file, "EXE,");
	env_var_dump_binary_information(0);
	fprintf(env_file, "\n");

	dump_env_vars();
}

void
_env_dump_posix_env_fini()
{

}
