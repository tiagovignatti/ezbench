#define _GNU_SOURCE

#include <openssl/sha.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <pthread.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdarg.h>
#include <string.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <dlfcn.h>
#include <link.h>

/*#include <GL/glx.h>
#include <EGL/egl.h>*/

// gcc -Wall -fPIC -shared -o env_dump.so env_dump.c -ldl -lpthread -lcrypto

#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)

FILE *env_file = NULL;

static pthread_mutex_t found_so_list_mp = PTHREAD_MUTEX_INITIALIZER;
size_t shared_object_count = 0;
struct shared_object {
	char *full_path;
	/* more here? */
} *found_so_list = NULL;

static void compute_and_print_sha1(const char *full_path)
{
	unsigned char hash[SHA_DIGEST_LENGTH];
	unsigned char *data;
	off_t size;
	int fd, i;

	fd = open(full_path, O_RDONLY);
	size = lseek(fd, 0, SEEK_END);
	data = mmap (0, size, PROT_READ, MAP_PRIVATE, fd, 0);
	if (data == MAP_FAILED) {
		fprintf(env_file, "UNK");
		return;
	}

	SHA1(data, size, hash);

	for (i = 0; i < 20; i++) {
		fprintf(env_file, "%02x", hash[i]);
	}

	munmap(data, size);
	close(fd);
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
		compute_and_print_sha1(full_path);
		fprintf(env_file, "\n");
	} else
		fprintf(env_file, "ERROR,add_so_to_found_list,realloc\n");

done:
	pthread_mutex_unlock(&found_so_list_mp);
	return ret;
}

static int ldd_callback(struct dl_phdr_info *info, size_t size, void *data)
{
	if (strlen(info->dlpi_name) == 0)
		return 0;

	add_so_to_found_list(info->dlpi_name, "BOOTLINK");

	return 0;
}

static void dump_binary_information()
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

	compute_and_print_sha1("/proc/self/exe");

	fprintf(env_file, "\n");
	free(buf);
}

__attribute__((constructor))
static void init() {
	const char *base_path = getenv("ENV_DUMP_FILE");
	char *path;
	int fd;

	if (base_path == NULL)
		base_path = "/tmp/env_dump";

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

	fprintf(env_file, "-- Env dump loaded successfully! --\n");

	/* Start by showing the binary, command line and sha1 */
	dump_binary_information();

	/* Show what are currently linking with */
	dl_iterate_phdr(ldd_callback, NULL);
}

/* Have a small DB of booleans that will store if we already accounted the
 * fd (1) or not yet (0). This DB can hold up to 2048, which is twice the usual
 * limit found on Linux.
 */
static pthread_mutex_t fd_mp = PTHREAD_MUTEX_INITIALIZER;
static unsigned long fds[64] = { 0 };

static inline int bit_read(int bit)
{
	int val;

	/* If we go out of the expected range, just give up and say it has been
	 * reported already!
	 */
	if (unlikely(bit > sizeof(fds) * 8))
		return 1;

	val = (fds[bit >> 5] >> (bit & 0x1f)) & 1;

	return val;
}

static inline void bit_write(int bit, int value)
{
	int idxh, idxl;

	if (unlikely(bit > sizeof(fds) * 8))
		return;

	idxh = bit >> 5;
	idxl = bit & 0x1f;
	fds[idxh] = (fds[idxh] & ~(1 << idxl)) | (value << idxl);
}

static ssize_t get_path_from_fd(int fd, char *buf, size_t bufsiz)
{
	/* longest fd path is /proc/4194303/fd/1024 --> 21 chars */
	char proc_path[22];
	sprintf(proc_path, "/proc/%u/fd/%u", getpid(), fd);

	return readlink(proc_path, buf, bufsiz);
}

int ioctl(int fd, unsigned long int request, ...)
{
	static int (*orig_ioctl)(int, unsigned long int, ...);
	void *arg;
	va_list ap;

	if (orig_ioctl == NULL)
		orig_ioctl = dlsym(RTLD_NEXT,"ioctl");

	va_start(ap, request);
	arg = va_arg(ap, void *);

	/* If it is the first time we see an ioctl on this fd */
	pthread_mutex_lock(&fd_mp);
	if (!bit_read(fd)) {
		char path[101];
		size_t len = get_path_from_fd(fd, path, sizeof(path));
		path[len] = '\0';
		fprintf(env_file, "IOCTL,%i,%s\n", fd, path);
		bit_write(fd, 1);
	}
	pthread_mutex_unlock(&fd_mp);

	return orig_ioctl(fd, request, arg);
}

int close(int fd)
{
	static int (*orig_close)(int);
	if (orig_close == NULL)
		orig_close = dlsym(RTLD_NEXT, "close");

	pthread_mutex_lock(&fd_mp);
	bit_write(fd, 0);
	pthread_mutex_unlock(&fd_mp);

	return orig_close(fd);
}

static int new_deps_callback(struct dl_phdr_info *info, size_t size, void *data)
{
	if (strlen(info->dlpi_name) == 0)
		return 0;

	add_so_to_found_list(info->dlpi_name, "DYNLINK");

	return 0;
}

static void _dlopen_check_result(void *handle, const char *filename, int flag)
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

void *dlopen(const char *filename, int flags)
{
	static void *(*orig_dlopen)(const char *, int);
	void *handle = NULL;

	if (orig_dlopen == NULL)
		orig_dlopen = dlsym(RTLD_NEXT, "dlopen");

	handle = orig_dlopen(filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

void *dlmopen (Lmid_t lmid, const char *filename, int flags)
{
	static void *(*orig_dlmopen)(Lmid_t, const char *, int);
	void *handle;

	if (orig_dlmopen == NULL)
		orig_dlmopen = dlsym(RTLD_NEXT, "dlmopen");

	handle = orig_dlmopen(lmid, filename, flags);
	_dlopen_check_result(handle, filename, flags);

	return handle;
}

__attribute__((destructor))
static void fini() {
	size_t i;

	/* free the memory we do not need anymore */
	pthread_mutex_lock(&found_so_list_mp);
	for (i = 0; i < shared_object_count; i++)
		free(found_so_list[i].full_path);
	shared_object_count = 0;
	free(found_so_list);
	pthread_mutex_unlock(&found_so_list_mp);

	fprintf(env_file, "-- Env dump fini, closing the file! --\n");
	fclose(env_file);
}

/*int dlclose(void *handle)
{
	static int(*orig_dlclose)(void *);
	if (orig_dlclose == NULL)
		orig_dlclose = dlsym(RTLD_NEXT, "dlclose");

	return orig_dlclose(handle);
}*/

/*void glXSwapBuffers(Display *dpy, GLXDrawable drawable)
{
	static void (*orig_glXSwapBuffers)(Display *, GLXDrawable);
	if (orig_glXSwapBuffers == NULL)
		orig_glXSwapBuffers = dlsym(RTLD_NEXT, "glXSwapBuffers");

	fprintf(stderr, "glXSwapBuffers'\n");

	orig_glXSwapBuffers(dpy, drawable);
}*/

/*EGLBoolean eglSwapBuffers(EGLDisplay display, EGLSurface surface)
{
	static EGLBoolean (*orig_eglSwapBuffers)(EGLDisplay, EGLSurface);
	if (orig_eglSwapBuffers == NULL)
		orig_eglSwapBuffers = dlsym(RTLD_NEXT, "eglSwapBuffers");

	//fprintf(stderr, "eglSwapBuffers'\n");

	return orig_eglSwapBuffers(display, surface);
}*/
