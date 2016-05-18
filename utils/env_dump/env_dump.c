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

#include <sys/stat.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <time.h>
#include <link.h>

FILE *env_file = NULL;
int _env_debug = 0;
int _env_ignored = 0;

static void fini();

/* Yes, the program may call _exit() and in this case, the fini() function will
 * never be called. Fix this!
 */
void
_exit(int status)
{
	void (*__attribute__((noreturn)) const orig__exit)(int) = _env_dump_resolve_symbol_by_name("_exit");
	fprintf(env_file, "EXIT,%i\n", status);

	/* call fini() now, as no other interaction may happen after our call to
	 * _exit().
	 */
	fini();
	orig__exit(status);
}

void
exit(int status)
{
	void (*__attribute__((noreturn)) const orig_exit)(int) = _env_dump_resolve_symbol_by_name("exit");
	fprintf(env_file, "EXIT,%i\n", status);
	/* do not call fini() now as we may miss some precious interactions */
	orig_exit(status);
}

/* handle exit signals to run the fini() functions */
static void
sig_handler(int sig, siginfo_t *siginfo, void *context)
{
	void (*const orig__exit)(int) = _env_dump_resolve_symbol_by_name("_exit");
	fprintf(env_file, "EXIT_SIGNAL,%i (%s)\n", sig, strsignal(sig));
	fini();
	orig__exit(-1);
}

static void
register_signal_handler(int signal)
{
	struct sigaction act;
	memset (&act, '\0', sizeof(act));
	act.sa_sigaction = &sig_handler;
	act.sa_flags = SA_SIGINFO;
	if (sigaction(signal, &act, NULL) < 0) {
		perror ("sigaction");
	}
}

static void
print_date_and_time()
{
	struct tm* tm_info;
	time_t timer;
	char buf[51];

	time(&timer);
	tm_info = localtime(&timer);

	strftime(buf, sizeof(buf), "%Y:%m:%d,%H:%M:%S,%Z(%z)", tm_info);

	fprintf(env_file, "DATE,%s\n", buf);
}

static int
check_restrictions()
{
	char *full_path, *cmdline, *restrict_binary, *restrict_cmdline;
	int ret = 0;

	full_path = _env_dump_binary_fullpath(getpid());
	cmdline = _env_dump_binary_cmdline(getpid());
	restrict_binary = getenv("ENV_DUMP_RESTRICT_TO_BINARY");
	restrict_cmdline = getenv("ENV_DUMP_REQUIRE_ARGUMENT");

	if (full_path!= NULL && restrict_binary != NULL &&
		strcmp(full_path, restrict_binary) != 0) {
		if (_env_debug)
			fprintf(stderr, "Env_dump: binary '%s', ignore...\n", full_path);
		ret = 1;
	}

	if (cmdline!= NULL && restrict_cmdline != NULL) {
		/* Read the entire cmdline */
		const char *p = cmdline;
		int not_found = 1;
		while (*p) {
			if (strcmp(p, restrict_cmdline) == 0) {
				not_found = 0;
				break;
			}
			while (*p++);
		}
		if (not_found && _env_debug)
			fprintf(stderr, "Env_dump: cmdline does not contain '%s', ignore...\n", restrict_cmdline);
		ret |= not_found;
	}
	free(cmdline);
	free(full_path);

	return ret;
}

FILE *
_env_dump_create_file(const char *base_path)
{
	FILE *file;
	char *path;
	int fd;

	if (check_restrictions())
		return NULL;

	/* if the file asked by the user already exists, append the pid to the
	* name. Otherwise, just use the name.
	*/
	fd = open(base_path, O_EXCL | O_CREAT | O_WRONLY | O_CLOEXEC, 0666);
	if (fd >= 0) {
		fprintf(stderr, "pid %i: opened file %s\n", getpid(), base_path);
		file = fdopen(fd, "w");
	} else {
		path = malloc(strlen(base_path) + 1 + 10 + 1); /* log(2^32) = 10 */
		if (!path)
			exit(1);
		sprintf(path, "%s.%i", base_path, getpid());
		fd = open(path, O_EXCL | O_CREAT | O_WRONLY | O_CLOEXEC, 0666);
		fprintf(stderr, "pid %i: file %s -> fd = %i\n", getpid(), path, fd);
		if (fd >= 0)
			file = fopen(path, "w");
		else
			file = NULL;

		free(path);
	}
	/* do not buffer this stream */
	if (file)
		setvbuf(file, (char *)NULL, _IONBF, 0);

	return file;
}

__attribute__((constructor)) static void
init()
{
	const char *base_path = getenv("ENV_DUMP_FILE");
	if (base_path == NULL)
		base_path = "/tmp/env_dump";

	_env_debug = getenv("ENV_DUMP_DEBUG") ? 1 : 0;

	if (strcmp(base_path, "stderr") != 0) {
		env_file = _env_dump_create_file(base_path);
	} else if (!check_restrictions()){
		env_file = stderr;
	}

	if (!env_file) {
		_env_ignored = 1;
		env_file = fopen("/dev/null", "w");
	} else {
		/* handle some signals that would normally result in an exit without
		* calling the fini functions. This will hopefully be done before any
		* other library does it. It is however OK if the program replaces the
		* handler as long as it calls exit() or _exit().
		*/
		register_signal_handler(SIGHUP);
		register_signal_handler(SIGINT);
		register_signal_handler(SIGPIPE);
		register_signal_handler(SIGTERM);
		register_signal_handler(SIGSEGV);

		fprintf(env_file, "-- Env dump start (version 1) --\n");

		print_date_and_time();

		_env_dump_posix_env_init();
		_env_dump_fd_init();
		_env_dump_gl_init();
		_env_dump_linux_init();
		_env_dump_cpu_init();
		_env_dump_libs_init();
		_env_dump_net_init();
		_env_dump_metrics_init();
	}
}

__attribute__((destructor))
static void fini() {
	if (!_env_ignored) {
		_env_dump_metrics_fini();
		_env_dump_net_fini();
		_env_dump_libs_fini();
		_env_dump_cpu_fini();
		_env_dump_linux_fini();
		_env_dump_gl_fini();
		_env_dump_fd_init();
		_env_dump_posix_env_fini();

		fprintf(env_file, "-- Env dump end --\n");
		fclose(env_file);
	}
}
