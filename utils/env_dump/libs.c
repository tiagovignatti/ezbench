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

#include <openssl/sha.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <link.h>

static pthread_mutex_t found_so_list_mp = PTHREAD_MUTEX_INITIALIZER;
size_t shared_object_count = 0;
struct shared_object {
	char *full_path;
	/* more here? */
} *found_so_list = NULL;

void *handle_libcrypto = NULL;
unsigned char *(*SHA1_local)(const unsigned char *d, size_t n, unsigned char *md);

static int
libcrypto_resolve_symbols()
{
	static void *(*orig_dlopen)(const char *, int);

	if (handle_libcrypto == NULL) {
		if (orig_dlopen == NULL)
			orig_dlopen = dlsym(RTLD_NEXT, "dlopen");

		/* Open a local version of the libcrypto */
		handle_libcrypto = orig_dlopen("libcrypto.so",
					       RTLD_LOCAL | RTLD_LAZY);
		if (handle_libcrypto)
			SHA1_local = dlsym(handle_libcrypto, "SHA1");
	}

	return !handle_libcrypto && !SHA1_local;
}

void
_env_dump_compute_and_print_sha1(const char *full_path)
{
	unsigned char hash[SHA_DIGEST_LENGTH];
	unsigned char *data;
	off_t size;
	int fd, i;

	/* this function can be called before init(), so let's check if the
	 * libcrypto has been loaded or not yet.
	 */
	if (libcrypto_resolve_symbols()) {
		fprintf(env_file, "ERR_MISSING_LIBCRYPTO");
	} else {
		fd = open(full_path, O_RDONLY);
		size = lseek(fd, 0, SEEK_END);
		data = mmap (0, size, PROT_READ, MAP_PRIVATE, fd, 0);
		if (data == MAP_FAILED) {
			fprintf(env_file, "UNK");
			return;
		}

		SHA1_local(data, size, hash);

		for (i = 0; i < 20; i++) {
			fprintf(env_file, "%02x", hash[i]);
		}

		munmap(data, size);
		close(fd);
	}
}

static int
add_so_to_found_list(const char *full_path, const char *when)
{
	int ret = 0, i;

	pthread_mutex_lock(&found_so_list_mp);
	found_so_list = realloc(found_so_list,
				sizeof(struct shared_object) * (shared_object_count + 1));
	if (found_so_list) {
		/* look for already-existing entries */
		for (i = 0; i < shared_object_count; i++) {
			if (strcmp(found_so_list[i].full_path, full_path) == 0) {
				ret = -1;
				goto done;
			}
		}

		/* we could not find an already-existing entry, add a new one */
		found_so_list[shared_object_count].full_path = strdup(full_path);
		shared_object_count++;

		/* report the finding */
		fprintf(env_file, "%s,%s,", when, full_path);
		_env_dump_compute_and_print_sha1(full_path);
		fprintf(env_file, "\n");
	} else
		fprintf(env_file, "ERROR,add_so_to_found_list,realloc\n");

done:
	pthread_mutex_unlock(&found_so_list_mp);
	return ret;
}

static int
ldd_callback(struct dl_phdr_info *info, size_t size, void *data)
{
	if (strlen(info->dlpi_name) == 0)
		return 0;

	add_so_to_found_list(info->dlpi_name, "BOOTLINK");

	return 0;
}

static int
new_deps_callback(struct dl_phdr_info *info, size_t size, void *data)
{
	if (strlen(info->dlpi_name) == 0)
		return 0;

	add_so_to_found_list(info->dlpi_name, "DYNLINK");

	return 0;
}

static void
_dlopen_check_result(void *handle, const char *filename, int flag)
{
	char *full_path;
	struct link_map *lm;

	if (!handle || !filename)
		return;

	dlinfo(handle, RTLD_DI_LINKMAP, &lm);
	full_path = realpath(lm->l_name, NULL);

	add_so_to_found_list(full_path, "DYNLINK");

	free(full_path);

	/* check if we pulled-in more deps */
	dl_iterate_phdr(new_deps_callback, NULL);
}

void *
dlopen(const char *filename, int flags)
{
	static void *(*orig_dlopen)(const char *, int);
	void *handle = NULL;

	if (orig_dlopen == NULL)
		orig_dlopen = dlsym(RTLD_NEXT, "dlopen");

	handle = orig_dlopen(filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

void *
dlmopen (Lmid_t lmid, const char *filename, int flags)
{
	static void *(*orig_dlmopen)(Lmid_t, const char *, int);
	void *handle;

	if (orig_dlmopen == NULL)
		orig_dlmopen = dlsym(RTLD_NEXT, "dlmopen");

	handle = orig_dlmopen(lmid, filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

/*int dlclose(void *handle)
{
	static int(*orig_dlclose)(void *);
	if (orig_dlclose == NULL)
		orig_dlclose = dlsym(RTLD_NEXT, "dlclose");

	return orig_dlclose(handle);
}*/

void
_env_dump_libs_init()
{
	/* Show what we are currently linking with */
	dl_iterate_phdr(ldd_callback, NULL);
}

void
_env_dump_libs_fini()
{
	size_t i;

	/* free the memory we do not need anymore */
	pthread_mutex_lock(&found_so_list_mp);
	for (i = 0; i < shared_object_count; i++)
		free(found_so_list[i].full_path);
	shared_object_count = 0;
	free(found_so_list);
	pthread_mutex_unlock(&found_so_list_mp);

	if (handle_libcrypto)
		dlclose(handle_libcrypto);
}
