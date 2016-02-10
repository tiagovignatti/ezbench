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

static void fini();

/* Yes, the program may call _exit() and in this case, the fini() function will
 * never be called. Fix this!
 */
void _exit(int status)
{
	void (*const orig__exit)(int) = _env_dump_resolve_symbol_by_name("_exit");
	fini();
	orig__exit(status);
}

/* handle exit signals to run the fini() functions */
static void
sig_handler(int sig, siginfo_t *siginfo, void *context)
{
	/* this will also call fini! */
	_exit(-1);
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

__attribute__((constructor))
static void init() {
	const char *base_path = getenv("ENV_DUMP_FILE");
	char *path;
	int fd;

	if (base_path == NULL)
		base_path = "/tmp/env_dump";

	if (strcmp(base_path, "stderr") != 0) {
		/* if the file asked by the user already exists, append the pid to the
		* name. Otherwise, just use the name.
		*/
		fd = open(base_path, O_EXCL | O_CREAT | O_WRONLY | O_CLOEXEC, 0666);
		if (fd >= 0) {
			env_file = fdopen(fd, "w");
			fprintf(stderr, "path = %s\n", base_path);
		} else {
			path = malloc(strlen(base_path) + 1 + 10 + 1); /* log(2^32) = 10 */
			if (!path)
				exit(1);
			sprintf(path, "%s.%i", base_path, getpid());
			fprintf(stderr, "path = %s.%i\n", base_path, getpid());
			env_file = fopen(path, "w");
			free(path);
		}
		/* do not buffer this stream */
		setvbuf(env_file, (char *)NULL, _IONBF, 0);
	} else {
		env_file = stderr;
	}

	/* handle some signals that would normally result in an exit without
	 * calling the fini functions. This will hopefully be done before any
	 * other library does it. It is however OK if the program replaces the
	 * handler as long as it calls exit() or _exit().
	 */
	register_signal_handler(SIGHUP);
	register_signal_handler(SIGINT);
	register_signal_handler(SIGPIPE);
	register_signal_handler(SIGTERM);

	fprintf(env_file, "-- Env dump start (version 1) --\n");

	print_date_and_time();

	_env_dump_posix_env_init();
	_env_dump_fd_init();
	_env_dump_gl_init();
	_env_dump_linux_init();
	_env_dump_cpu_init();
	_env_dump_libs_init();
	_env_dump_net_init();
}

__attribute__((destructor))
static void fini() {
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
