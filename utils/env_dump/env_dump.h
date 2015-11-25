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

#ifndef _ENV_DUMP_H_
#define _ENV_DUMP_H_

#include <GL/glx.h>
#include <stdio.h>

extern FILE *env_file;

#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)

typedef void (*fd_callback)(int fd, void *user);

void _env_dump_libs_init();
void _env_dump_libs_fini();

void _env_dump_cpu_init();
void _env_dump_cpu_fini();

void _env_dump_drm_dump_info(const char *path, int fd);

void _env_dump_fd_init();
void _env_dump_fd_fini();
void _env_dump_close_callback(int fd, fd_callback cb, void *user);

void _env_dump_gl_init();
void _env_dump_gl_fini();

void _env_dump_linux_init();
void _env_dump_linux_fini();

void _env_dump_net_init();
void _env_dump_net_fini();

void _env_dump_posix_env_init();
void _env_dump_posix_env_fini();

void _env_dump_compute_and_print_sha1(const char *full_path);
void env_var_dump_binary_information(int pid);

char *_env_dump_read_file(const char *path, size_t len_max);

/* internal pointer-tracking mechanism */
enum symbol_key_t {
	SYMB_IOCTL = 0,
	SYMB_GLXSWAPBUFFERS,
	SYMB_EGLSWAPBUFFERS,
	SYMB_GLXMAKECURRENT,
	SYMB_EGLMAKECURRENT,
	SYMB_END
}; /* do not forget to duplicate the name in libs.c's symbol_key_str */

void *_env_dump_resolve_local_symbol_by_name(const char *symbol);
void *_env_dump_resolve_symbol_by_name(const char *symbol);
void *_env_dump_resolve_symbol_by_id(enum symbol_key_t symbol);
void _env_dump_replace_symbol(const char *symbol, void *ptr);

#endif
