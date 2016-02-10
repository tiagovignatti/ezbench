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

#include <xf86drm.h>
#include <stdlib.h>
#include <string.h>

static char *
read_drm_sysfs(const char *node, const char *file, size_t len_max)
{
	char sysfs_path[101];

	snprintf(sysfs_path, sizeof(sysfs_path), "/sys/class/drm/%s/%s", node, file);
	return _env_dump_read_file(sysfs_path, len_max, NULL);
}

static long
read_drm_sysfs_int(const char *node, const char *file, int base)
{
	char *val = read_drm_sysfs(node, file, 20);
	long ret = -1;

	if (val) {
		ret = strtol(val, NULL, base);
		free(val);
	}

	return ret;

}

static void
_env_dump_drm_i915_dump_info(const char *node_name,
			     const char *primary_node_name, int fd)
{
	long min, max, rp0, rp1, rpn;

	min = read_drm_sysfs_int(primary_node_name, "gt_min_freq_mhz", 10);
	max = read_drm_sysfs_int(primary_node_name, "gt_max_freq_mhz", 10);
	rp0 = read_drm_sysfs_int(primary_node_name, "gt_RP0_freq_mhz", 10);
	rp1 = read_drm_sysfs_int(primary_node_name, "gt_RP1_freq_mhz", 10);
	rpn = read_drm_sysfs_int(primary_node_name, "gt_RPn_freq_mhz", 10);

	fprintf(env_file, "INTEL_DRM,%li,%li,%li,%li,%li\n", min, max, rp0, rp1, rpn);
}

void
_env_dump_drm_dump_info(const char *path, int fd)
{
	char *(*orig_drmGetPrimaryDeviceNameFromFd)(int fd);
	drmVersionPtr (*orig_drmGetLibVersion)(int fd);
	drmVersionPtr (*orig_drmGetVersion)(int fd);
	void (*orig_drmFreeVersion)(drmVersionPtr v);
	drmVersionPtr version_lib = NULL, version_drm = NULL;
	char *node_name = NULL, *primary_node = NULL, *primary_node_name = NULL;
	char *vendor = NULL, *devid = NULL;

	/* resolve symbols */
	orig_drmGetPrimaryDeviceNameFromFd = _env_dump_resolve_symbol_by_name("drmGetPrimaryDeviceNameFromFd");
	orig_drmGetVersion = _env_dump_resolve_symbol_by_name("drmGetVersion");
	orig_drmGetLibVersion = _env_dump_resolve_symbol_by_name("drmGetLibVersion");
	orig_drmFreeVersion = _env_dump_resolve_symbol_by_name("drmFreeVersion");
	if (!orig_drmGetPrimaryDeviceNameFromFd || !orig_drmGetVersion ||
		!orig_drmGetLibVersion || !orig_drmFreeVersion)
		return;

    /* Check if the path starts with /, as it should be */
    if (path[0] != '/')
        goto exit;

	/* Get the general DRM information */
	primary_node = orig_drmGetPrimaryDeviceNameFromFd(fd);
	node_name = strrchr(path, '/');
    if (!node_name || !primary_node)
		goto exit;

	primary_node_name = strrchr(primary_node, '/');
	version_lib = orig_drmGetLibVersion(fd);
	version_drm = orig_drmGetVersion(fd);
	if (!primary_node_name || !version_lib || !version_drm)
		goto exit;

	/* get rid of the '/' in the name */
	node_name++;
	primary_node_name++;

	/* fetch the BusID */
	vendor = read_drm_sysfs(node_name, "device/vendor", 16);
	devid = read_drm_sysfs(node_name, "device/device", 16);

	fprintf(env_file, "LIBDRM,%i,%i,%i\n", version_lib->version_major,
	                                       version_lib->version_minor,
	                                       version_lib->version_patchlevel);
	fprintf(env_file, "DRM,%i,%i,%i,%s,%s,%s,%s,%s\n",
		version_drm->version_major, version_drm->version_minor,
	        version_drm->version_patchlevel, version_drm->name,
	        version_drm->date, version_drm->desc, vendor, devid);

	free(vendor); free(devid);

	/* Add data, per vendor */
	if (strcmp(version_drm->name, "i915") == 0)
		_env_dump_drm_i915_dump_info(node_name, primary_node_name, fd);

exit:
	if (primary_node)
		free(primary_node);
	if (version_lib)
		orig_drmFreeVersion(version_lib);
	if (version_drm)
		orig_drmFreeVersion(version_drm);
}