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

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/extensions/Xrandr.h>
#include <stdlib.h>
#include <string.h>
#include <link.h>

/* XLib functions, should only be called if the libxcb or libX11 is loaded */
static char *
_env_dump_xlib_compositor(Display *dpy, int screen)
{
	Atom wmCheckAtom, wmName,stringType, typeRet;
	unsigned long nitems, after;
	unsigned char *name = 0;
	Window root, *wm_window;
	char *result = NULL;
	int format;

	/* Retrieve the pointers to x-related functions */
	Atom (*orig_xinternatom)(Display *, char *, Bool);
	int (*orig_xgetwindowproperty)(Display *, Window, Atom, long, long, Bool,
				       Atom, Atom *, int *, unsigned long *,
				       unsigned long *, unsigned char **);
	int (*orig_xfree)(void *);
	orig_xinternatom = _env_dump_resolve_symbol_by_name("XInternAtom");
	orig_xgetwindowproperty = _env_dump_resolve_symbol_by_name("XGetWindowProperty");
	orig_xfree = _env_dump_resolve_symbol_by_name("XFree");

	wmCheckAtom = orig_xinternatom(dpy, "_NET_SUPPORTING_WM_CHECK", True);
	wmName = orig_xinternatom(dpy, "_NET_WM_NAME", True);
	stringType = orig_xinternatom(dpy, "UTF8_STRING", True);

	if (wmCheckAtom == None || wmName == None || stringType == None)
		return strdup("UNKOWN");

	root = RootWindow(dpy, screen);
	if (!(orig_xgetwindowproperty(dpy, root, wmCheckAtom, 0, 1024, False,
		XA_WINDOW, &typeRet, &format, &nitems, &after,
		(unsigned char **) &wm_window)))
	{
		if (!(orig_xgetwindowproperty(dpy, *wm_window, wmName, 0, 1024,
			False, stringType, &typeRet, &format, &nitems, &after,
			(unsigned char **) &name)))
		{
			result = strdup((char *)name);
			orig_xfree(name);
		}
	}

	return result;
}

Display *
XOpenDisplay(const char *display_name)
{
	Display *(*orig_xopendisplay)(const char *);
	Display *dpy;
	int i;

	orig_xopendisplay = _env_dump_resolve_symbol_by_name("XOpenDisplay");
	dpy = orig_xopendisplay(display_name);
	if (dpy) {
		fprintf(env_file, "XORG_SESSION_OPENED,%s\n", display_name);
		for (i = 0; i < ScreenCount(dpy); i++) {
			char *wm = _env_dump_xlib_compositor(dpy, i);

			fprintf(env_file, "XORG_DISPLAY,%i,%s,%i,%i,%i\n", i,
				wm, DisplayWidth(dpy, i), DisplayHeight(dpy, i),
				DefaultDepth(dpy, i));

			free(wm);
		}
	}

	return dpy;
}

int
XCloseDisplay(Display *display)
{
	int (*orig_xclosedisplay)(Display *);
	int ret;

	orig_xclosedisplay = _env_dump_resolve_symbol_by_name("XCloseDisplay");

	fprintf(env_file, "XORG_CLOSE,%s\n", DisplayString(display));
	ret = orig_xclosedisplay(display);

	return ret;
}

Window
XCreateSimpleWindow(Display* display, Window parent, int x, int y,
		    unsigned int width, unsigned int height,
		    unsigned int border_width, unsigned long border,
		    unsigned long background)
{
	int (*orig_xcreatesimplewindow)(Display *, Window, int, int,
					       unsigned int, unsigned int,
					       unsigned int, unsigned long,
					       unsigned long);
	Window ret;

	orig_xcreatesimplewindow = _env_dump_resolve_symbol_by_name("XCreateSimpleWindow");

	ret = orig_xcreatesimplewindow(display, parent, x, y, width, height,
				       border_width, border, background);
	fprintf(env_file, "XORG_WINDOW_CREATE,%lu,%lu,%i,%i,-1\n", parent, ret,
		width, height);

	return ret;
}

Window
XCreateWindow(Display* display, Window parent, int x, int y,
	      unsigned int width, unsigned int height,
	      unsigned int border_width, int depth, unsigned int class,
	      Visual* visual, unsigned long valuemask,
	      XSetWindowAttributes *attributes)
{
	int (*orig_xcreatewindow)(Display *, Window, int, int,
					 unsigned int, unsigned int,
					 unsigned int, int, unsigned int,
					 Visual *, unsigned long,
					 XSetWindowAttributes *);
	Window ret;

	orig_xcreatewindow = _env_dump_resolve_symbol_by_name("XCreateWindow");

	ret = orig_xcreatewindow(display, parent, x, y, width, height,
				 border_width, depth, class, visual,
				 valuemask, attributes);
	fprintf(env_file, "XORG_WINDOW_CREATE,%lu,%lu,%i,%i,%i\n", parent, ret,
		width, height, depth);

	return ret;
}

int
XMoveResizeWindow(Display *display, Window w, int x, int y, unsigned int width,
		  unsigned int height)
{
	int (*orig_xmoveresizewindow)(Display *, Window, int, int,
					     unsigned int, unsigned int);
	int ret;

	orig_xmoveresizewindow = _env_dump_resolve_symbol_by_name("XMoveResizeWindow");

	ret = orig_xmoveresizewindow(display, w, x, y, width, height);
	fprintf(env_file, "XORG_WINDOW_RESIZE,%lu,%i,%i\n", w, width, height);

	return ret;
}

int
XResizeWindow(Display *display, Window w, unsigned int width, unsigned int height)
{
	int (*orig_xresizewindow)(Display *, Window, unsigned int,
					 unsigned int);
	int ret;

	orig_xresizewindow = _env_dump_resolve_symbol_by_name("XResizeWindow");

	ret = orig_xresizewindow(display, w, width, height);
	fprintf(env_file, "XORG_WINDOW_RESIZE,%lu,%i,%i\n", w, width, height);

	return ret;
}


/* libxcb */

/* WARNING: No need to hook the connect close and createwindow functions because
 * the libxcb calls the original xlib functions which are already hook!
 */
