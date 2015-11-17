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

#include <sys/time.h>
#include <pthread.h>
#include <EGL/egl.h>
#include <stdlib.h>
#include <GL/glx.h>
#include <stdlib.h>
#include <string.h>
#include <link.h>

static uint64_t print_period_ms = -1;

static uint64_t
get_time_us()
{
	struct timeval tv;
	gettimeofday(&tv, NULL);
	return tv.tv_sec * 1e6 + tv.tv_usec;
}

static float
fps_clamp(uint64_t frametime_us)
{
	if (frametime_us > 0)
		return 1.0e6 / ((float)frametime_us);
	else
		return 0.0;
}

void
swap_buffer_stopwatch()
{
	static uint64_t first_frame, last_update, last_print;
	static uint64_t min = -1, max, count;
	uint64_t cur_time = get_time_us();

	if (first_frame == 0)
		first_frame = cur_time;

	if (last_update > 0) {
		uint64_t diff = cur_time - last_update;
		count++;
		if (diff > max)
			max = diff;
		if (diff < min)
			min = diff;
	}

	if (last_print == 0)
		last_print = cur_time;
	else if (cur_time - last_print > print_period_ms * 1000) {
		uint64_t diff = cur_time - last_print;
		uint64_t frametime_avg = diff / count;
		fprintf(stderr, "FPS,%lu,%.3f,%.3f,%.3f\n", cur_time - first_frame,
			fps_clamp(frametime_avg), fps_clamp(max),
			fps_clamp(min));

		/* reset the state */
		last_print = cur_time;
		count = 0;
		min = -1;
		max = 0;
	}

	last_update = cur_time;
}

void
glXSwapBuffers(Display *dpy, GLXDrawable drawable)
{
	void (*orig_glXSwapBuffers)(Display *, GLXDrawable);

	orig_glXSwapBuffers = _env_dump_resolve_symbol_by_id(SYMB_GLXSWAPBUFFERS);

	if (print_period_ms != -1)
		swap_buffer_stopwatch();

	orig_glXSwapBuffers(dpy, drawable);
}

__GLXextFuncPtr glXGetProcAddressARB(const GLubyte *procName)
{
	__GLXextFuncPtr (*orig_glXGetProcAddressARB)(const GLubyte *);
	void *external, *internal;

	orig_glXGetProcAddressARB = _env_dump_resolve_symbol_by_name("glXGetProcAddressARB");

	/* First look up the right symbol */
	external = orig_glXGetProcAddressARB(procName);
	if (!external)
		return external;

	/* check if we have an internal version of it! */
	internal = _env_dump_resolve_local_symbol_by_name((const char*)procName);
	if (!internal)
		return external;

	/* add the right symbol to the list of known symbols */
	_env_dump_replace_symbol((const char*)procName, external);

	/* return the internal address */
	return internal;
}

EGLBoolean
eglSwapBuffers(EGLDisplay display, EGLSurface surface)
{
	EGLBoolean (*orig_eglSwapBuffers)(EGLDisplay, EGLSurface);

	orig_eglSwapBuffers = _env_dump_resolve_symbol_by_id(SYMB_EGLSWAPBUFFERS);

	if (print_period_ms != -1)
		swap_buffer_stopwatch();

	return orig_eglSwapBuffers(display, surface);
}

static void
dump_gl_info()
{
	GLint num_extension;

	/* give informations about the context */
	glGetIntegerv(GL_NUM_EXTENSIONS, &num_extension);
	fprintf(env_file, "GL_NEWCONTEXTUSED,%s,%s,%s,%s,%i,%s\n",
		glGetString(GL_VENDOR), glGetString(GL_RENDERER),
		glGetString(GL_VERSION),
		glGetString(GL_SHADING_LANGUAGE_VERSION), num_extension,
		glGetString(GL_EXTENSIONS));
}

Bool
glXMakeCurrent(Display *dpy, GLXDrawable drawable, GLXContext ctx)
{
	static pthread_mutex_t dumped_contexts_mp = PTHREAD_MUTEX_INITIALIZER;
	static size_t dumped_glxcontexts_count = 0;
	static GLXContext *dumped_glxcontexts;

	Bool (*orig_glXMakeCurrent)(Display *, GLXDrawable, GLXContext);
	Bool ret = False;
	int entry_count, i;

	pthread_mutex_lock(&dumped_contexts_mp);

	orig_glXMakeCurrent = _env_dump_resolve_symbol_by_id(SYMB_GLXMAKECURRENT);
	ret = orig_glXMakeCurrent(dpy, drawable, ctx);
	if (ret == False)
		goto done;

	/* check if the context is in the list */
	for(i = 0; i < dumped_glxcontexts_count; i++) {
		if (dumped_glxcontexts[i] == ctx)
			goto done;
	}

	/* we did not find it, add it to the list before dumping all the
	 * informations. Allocate 10 contexts at a time to avoid copying every
	 * time.
	 */
	entry_count = (((dumped_glxcontexts_count + 1) / 10) + 1) * 10;
	dumped_glxcontexts = realloc(dumped_glxcontexts,
				     entry_count * sizeof(GLXContext));
	dumped_glxcontexts[dumped_glxcontexts_count] = ctx;
	dumped_glxcontexts_count++;

	/* dump the egl-related informations */
	fprintf(env_file, "GLX_NEWCONTEXTUSED,%s,%s,%s\n",
		glXGetClientString(dpy, GLX_VENDOR),
		glXGetClientString(dpy, GLX_VERSION),
		glXGetClientString(dpy, GLX_EXTENSIONS));

	dump_gl_info();

done:
	pthread_mutex_unlock(&dumped_contexts_mp);
	return ret;
}

EGLBoolean
eglMakeCurrent(EGLDisplay display, EGLSurface draw, EGLSurface read,
	       EGLContext context)
{
	static pthread_mutex_t dumped_contexts_mp = PTHREAD_MUTEX_INITIALIZER;
	static size_t dumped_eglcontexts_count = 0;
	static EGLContext *dumped_eglcontexts;
	EGLBoolean (*orig_eglMakeCurrent)(Display *, EGLSurface,
					  EGLSurface, EGLContext);
	EGLBoolean ret = False;
	EGLenum api;
	int entry_count, i;

	pthread_mutex_lock(&dumped_contexts_mp);

	orig_eglMakeCurrent = _env_dump_resolve_symbol_by_id(SYMB_EGLMAKECURRENT);

	ret = orig_eglMakeCurrent(display, draw, read, context);
	if (ret == False)
		goto done;

	/* check if the context is in the list */
	for(i = 0; i < dumped_eglcontexts_count; i++) {
		if (dumped_eglcontexts[i] == context)
			goto done;
	}

	/* we did not find it, add it to the list before dumping all the
	 * informations. Allocate 10 contexts at a time to avoid copying every
	 * time.
	 */
	entry_count = (((dumped_eglcontexts_count + 1) / 10) + 1) * 10;
	dumped_eglcontexts = realloc(dumped_eglcontexts,
				     entry_count * sizeof(EGLContext));
	dumped_eglcontexts[dumped_eglcontexts_count] = context;
	dumped_eglcontexts_count++;

	/* dump the egl-related informations */
	fprintf(env_file, "EGL_NEWCONTEXTUSED,%s,%s,%s,%s\n",
		eglQueryString(display, EGL_VENDOR),
		eglQueryString(display, EGL_VERSION),
		eglQueryString(display, EGL_CLIENT_APIS),
		eglQueryString(display, EGL_EXTENSIONS));

	/* dump the gl-related informations */
	api = eglQueryAPI();
	if (api == EGL_OPENGL_API || api == EGL_OPENGL_ES_API)
		dump_gl_info();

done:
	pthread_mutex_unlock(&dumped_contexts_mp);
	return ret;
}

void
_env_dump_gl_init()
{
	const char *frametime_period = getenv("ENV_DUMP_FPS_PRINT_PERIOD_MS");
	if (frametime_period != NULL)
		print_period_ms = strtoll(frametime_period, NULL, 10);
}

void
_env_dump_gl_fini()
{

}