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

size_t dlopen_local_handles_count = 0;
void **dlopen_local_handles = NULL;


struct fll_data {
	const char *name;
	size_t len_name;
	char *ret;
};

static int
find_Linked_library_callback(struct dl_phdr_info *info, size_t size, void *data)
{
	struct fll_data *p = (struct fll_data *) data;
	size_t len = strlen(info->dlpi_name);
	size_t offset = len - p->len_name;

	if (len < p->len_name)
		return 0;

	if (strcmp(info->dlpi_name + offset, p->name) == 0) {
		p->ret = strdup(info->dlpi_name);
		return 1;
	}

	return 0;
}

static char *
find_Linked_library(const char *name)
{
	struct fll_data data = {name, strlen(name), NULL};

	dl_iterate_phdr(find_Linked_library_callback, &data);

	return data.ret;
}

static int
libcrypto_resolve_symbols()
{
	void *(*orig_dlopen)(const char *, int);

	if (handle_libcrypto == NULL) {
		orig_dlopen = _env_dump_resolve_symbol_by_name("dlopen");

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
		fd = open(full_path, O_RDONLY | O_CLOEXEC);
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
add_dlopen_handle_to_list(void *handle)
{
	int i;

	pthread_mutex_lock(&found_so_list_mp);
	for (i = 0; i < dlopen_local_handles_count; i++) {
		if (dlopen_local_handles[i] == NULL) {
			dlopen_local_handles[i] = handle;
			goto done;
		}
	}
	dlopen_local_handles = realloc(dlopen_local_handles,
	                               sizeof(void *) * (dlopen_local_handles_count + 1));
	dlopen_local_handles[dlopen_local_handles_count] = handle;
	dlopen_local_handles_count++;

done:
	pthread_mutex_unlock(&found_so_list_mp);
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

	/* Local imports are a bit problematic, so store them to a list */
	if ((flag & RTLD_GLOBAL) == 0)
		add_dlopen_handle_to_list(handle);

	free(full_path);

	/* check if we pulled-in more deps */
	dl_iterate_phdr(new_deps_callback, NULL);
}

void *
dlopen(const char *filename, int flags)
{
	void *(*orig_dlopen)(const char *, int);
	void *handle = NULL;

	orig_dlopen = _env_dump_resolve_symbol_by_name("dlopen");

	handle = orig_dlopen(filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

void *
dlmopen(Lmid_t lmid, const char *filename, int flags)
{
	void *(*orig_dlmopen)(Lmid_t, const char *, int);
	void *handle;

	orig_dlmopen = _env_dump_resolve_symbol_by_name("dlmopen");

	handle = orig_dlmopen(lmid, filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

static pthread_mutex_t symbols_mp = PTHREAD_MUTEX_INITIALIZER;
size_t symbols_count = 0;
size_t symbols_len = 0;
struct symbol_t {
	const char *name;
	void *ptr;
} *symbols;

const char *symbol_key_str[SYMB_END] = {
	"ioctl",
	"glXSwapBuffers",
	"eglSwapBuffers",
	"glXMakeCurrent",
	"eglMakeCurrent",
};

extern void *_dl_sym(void *, const char *, void *);
void *
_env_dump_resolve_symbol_by_name(const char *symbol)
{
	void *ret = NULL, *tmp_ret = NULL;
	int i;

	pthread_mutex_lock(&symbols_mp);

	/* first check in our internal DB */
	for (i = 0; i < symbols_count; i++) {
		if (symbols[i].name && strcmp(symbols[i].name, symbol) == 0) {
			ret = symbols[i].ptr;
			break;
		}
	}

	pthread_mutex_unlock(&symbols_mp);

	/* Then try to see if there is another version somewhere else */
	if (ret == NULL)
		ret = _dl_sym(RTLD_NEXT, symbol, _env_dump_resolve_symbol_by_name);

	if (ret == NULL) {
		/* Try to resolve the symbol from the local handles */
		pthread_mutex_lock(&found_so_list_mp);
		for (i = 0; i < dlopen_local_handles_count; i++) {
			tmp_ret = _dl_sym(dlopen_local_handles[i], symbol,
						  _env_dump_resolve_symbol_by_name);
			if (tmp_ret) {
				if (ret == NULL || ret == tmp_ret)
					ret = tmp_ret;
				else  {
					fprintf(env_file, "WARNING, found multiple candidates for "
					"the symbol '%s'\n", symbol);
				}
			}
		}
		pthread_mutex_unlock(&found_so_list_mp);
	}

	return ret;
}

void *
_env_dump_resolve_symbol_by_id(enum symbol_key_t symbol)
{
	void *ret = NULL;

	pthread_mutex_lock(&symbols_mp);
	if (symbol < SYMB_END && symbols_len > symbol && symbols[symbol].name)
		ret = symbols[symbol].ptr;
	pthread_mutex_unlock(&symbols_mp);

	/* Then try to see if there is another version somewhere else */
	if (ret == NULL) {
		ret = _dl_sym(RTLD_NEXT, symbol_key_str[symbol], _env_dump_resolve_symbol_by_name);
		_env_dump_replace_symbol(symbol_key_str[symbol], ret);
	}

	return ret;
}

void
_env_dump_replace_symbol(const char *symbol, void *ptr)
{
	int size, offset = -1, i;

	pthread_mutex_lock(&symbols_mp);

	/* first check if the symbol is known */
	for (i = 0; i < SYMB_END; i++) {
		if (strcmp(symbol_key_str[i], symbol) == 0) {
			offset = i;
			goto write_offset;
		}
	}

	/* check if the symbol is already in the list */
	for (i = SYMB_END; i < symbols_count; i++) {
		if (strcmp(symbols[i].name, symbol) == 0) {
			offset = i;
			goto write_offset;
		}
	}

	/* we need to add the symbol, compute its offset */
	offset = (symbols_count < SYMB_END) ? SYMB_END : symbols_count;

write_offset:
	/* make sure we have enough space allocated */
	if (offset >= symbols_len) {
		void *prev = symbols;
		size_t start, len;
		int bs = 100;

		if (symbols_len == 0)
			size = SYMB_END + bs;
		else
			size = symbols_len + bs;

		symbols = realloc(symbols, size * sizeof(struct symbol_t));
		symbols_len = size;

		if (!prev) {
			start = 0;
			len = size;
		} else {
			start = size - bs;
			len = bs;
		}

		memset(symbols + start, '\0', len * sizeof(struct symbol_t));

	}

	/* if we are not merely updating an entry */
	if (!symbols[offset].name)
		symbols[offset].name = strdup(symbol);
	symbols[offset].ptr = ptr;

	/* increase the symbol count after adding an entry */
	if (offset >= symbols_count)
		symbols_count = offset + 1;

	pthread_mutex_unlock(&symbols_mp);
}

void *
_env_dump_resolve_local_symbol_by_name(const char *symbol)
{
	static void *(*orig_dlsym)(void *, const char *);
	static void *handle_env_dump;

	if (orig_dlsym == NULL)
		orig_dlsym = _dl_sym(RTLD_NEXT, "dlsym", dlsym);

	if (handle_env_dump == NULL ) {
		void *(*orig_dlopen)(const char *, int);
		char *fullpath = find_Linked_library("env_dump.so");
		orig_dlopen = _dl_sym(RTLD_NEXT, "dlopen", dlsym);
		handle_env_dump = orig_dlopen(fullpath, RTLD_LAZY);
		free(fullpath);
	}

	return orig_dlsym(handle_env_dump, symbol);
}

/* check which symbols the program looks up */
void *
dlsym(void *handle, const char *symbol)
{
	static void *(*orig_dlsym)(void *, const char *);
	void *orig_ptr, *ptr;

	if (orig_dlsym == NULL)
		orig_dlsym = _dl_sym(RTLD_NEXT, "dlsym", dlsym);

	/* try to resolve the symbol to an internal one first to avoid issues
	 * with dlerror().
	 */
	ptr = _env_dump_resolve_local_symbol_by_name(symbol);

	/* resolve the symbol as expected by the client */
	orig_ptr = orig_dlsym(handle, symbol);
	if (!orig_ptr)
		return orig_ptr;

	/* add the symbol to our DB */
	_env_dump_replace_symbol(symbol, orig_ptr);

	if (ptr)
		return ptr;
	else
		return orig_ptr;
}

int dlclose(void *handle)
{
	int(*orig_dlclose)(void *);
	int i;

	orig_dlclose = _env_dump_resolve_symbol_by_name("dlclose");

	pthread_mutex_lock(&found_so_list_mp);
	for (i = 0; i < dlopen_local_handles_count; i++) {
		if (dlopen_local_handles[i] == handle) {
			dlopen_local_handles[i] = NULL;
			break;
		}
	}
	pthread_mutex_unlock(&found_so_list_mp);

	return orig_dlclose(handle);
}

void
_env_dump_libs_init()
{
	/* Show what we are currently linking against */
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

	/* free the symbols */
	pthread_mutex_lock(&symbols_mp);
	symbols_count = 0;
	free(symbols);
	pthread_mutex_unlock(&symbols_mp);

	if (handle_libcrypto)
		dlclose(handle_libcrypto);
}
