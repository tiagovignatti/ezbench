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

#include "env_dump.h"

#include <sys/stat.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>

FILE *env_file = NULL;

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
		fd = open(base_path, O_EXCL | O_CREAT | O_WRONLY, 0777);
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

	fprintf(env_file, "-- Env dump loaded successfully! --\n");

	_env_dump_posix_env_init();
	_env_dump_fd_init();
	_env_dump_gl_init();
	_env_dump_libs_init();
	_env_dump_net_init();
}

__attribute__((destructor))
static void fini() {
	_env_dump_net_fini();
	_env_dump_libs_fini();
	_env_dump_gl_fini();
	_env_dump_fd_init();
	_env_dump_posix_env_fini();

	fprintf(env_file, "-- Env dump fini, closing the file! --\n");
	fclose(env_file);
}
