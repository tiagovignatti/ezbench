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
#include <unistd.h>

static void
dump_binary_information()
{
	size_t buflen = 4096, size;
	char *buf = malloc(buflen), *cur;
	FILE *cmd_file;

	if (!buf) {
		fprintf(stderr, "Error, no memory left. Exit!");
		exit(1);
	}

	fprintf(env_file, "EXE,");

	/* first read the url of the program */
	size = readlink("/proc/self/exe", buf, buflen);
	buf[size] = '\0';
	fprintf(env_file, "%s,", buf);

	/* then read the arguments */
	cmd_file = fopen("/proc/self/cmdline", "r");
	if (cmd_file) {
		size = fread(buf, 1, buflen, cmd_file);

		/* the fields are separated by \0 characters, replace them by
		 * spaces and add '' arounds them. The last field has two null
		 * characters.
		 */
		cur = buf;
		while (*cur && (cur - buf) < size) {
			if (cur == buf || *(cur - 1) == '\0')
				fprintf(env_file, "'");
			fprintf(env_file, "%c", *cur);

			cur++;

			if (*cur == '\0') {
				fprintf(env_file, "' ");
				cur++;
			}
		}
		fprintf(env_file, ",");

	} else
		fprintf(env_file, "ERROR,");

	_env_dump_compute_and_print_sha1("/proc/self/exe");

	fprintf(env_file, "\n");
	free(buf);
}

void
_env_dump_posix_env_init()
{
	/* Start by showing the binary, command line and sha1 */
	dump_binary_information();
}

void
_env_dump_posix_env_fini()
{

}
