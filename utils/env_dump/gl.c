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

#include <pthread.h>
#include <EGL/egl.h>
#include <GL/glx.h>
#include <stdlib.h>
#include <link.h>

#if 0
void
glXSwapBuffers(Display *dpy, GLXDrawable drawable)
{
	static void (*orig_glXSwapBuffers)(Display *, GLXDrawable);
	if (orig_glXSwapBuffers == NULL)
		orig_glXSwapBuffers = dlsym(RTLD_NEXT, "glXSwapBuffers");

	fprintf(stderr, "glXSwapBuffers'\n");

	orig_glXSwapBuffers(dpy, drawable);
}*/

EGLBoolean *
eglSwapBuffers(EGLDisplay display, EGLSurface surface)
{
	static EGLBoolean (*orig_eglSwapBuffers)(EGLDisplay, EGLSurface);
	if (orig_eglSwapBuffers == NULL)
		orig_eglSwapBuffers = dlsym(RTLD_NEXT, "eglSwapBuffers");

	//fprintf(stderr, "eglSwapBuffers'\n");

	return orig_eglSwapBuffers(display, surface);
}
#endif

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

	static Bool (*orig_glXMakeCurrent)(Display *, GLXDrawable, GLXContext);
	Bool ret = False;
	int entry_count, i;

	pthread_mutex_lock(&dumped_contexts_mp);

	if (orig_glXMakeCurrent == NULL)
		orig_glXMakeCurrent = dlsym(RTLD_NEXT, "glXMakeCurrent");

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

	/* dump the gl-related informations */
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
	static EGLBoolean (*orig_eglMakeCurrent)(Display *, EGLSurface,
						 EGLSurface, EGLContext);
	EGLBoolean ret = False;
	EGLenum api;
	int entry_count, i;

	pthread_mutex_lock(&dumped_contexts_mp);

	if (orig_eglMakeCurrent == NULL)
		orig_eglMakeCurrent = dlsym(RTLD_NEXT, "eglMakeCurrent");

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

}

void
_env_dump_gl_fini()
{

}