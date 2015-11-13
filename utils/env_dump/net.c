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

#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <errno.h>
#include <link.h>

int
connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
{
	int(*orig_connect)(int, const struct sockaddr *, socklen_t);
	struct sockaddr_un *addr_unix;
	socklen_t len;
	int ret;

	orig_connect = _env_dump_resolve_symbol_by_name("connect");

	ret = orig_connect(sockfd, addr, addrlen);
	if (!ret && addr->sa_family == AF_UNIX) {
		struct ucred ucred;
		const char *filepath = NULL;

		addr_unix = (struct sockaddr_un *)addr;
		filepath = addr_unix->sun_path;
		if (filepath[0] == '\0')
			filepath++;

		len = sizeof(struct ucred);
		if(getsockopt(sockfd, SOL_SOCKET, SO_PEERCRED, &ucred, &len) < 0){
			fprintf(env_file, "SOCKET_UNIX_CONNECT,%s,,%s\n", filepath, strerror(errno));
			return ret;
		}

		/* display a lot more information about the process! */
		fprintf(env_file, "SOCKET_UNIX_CONNECT,%s,", filepath);
		env_var_dump_binary_information(ucred.pid);
		fprintf(env_file, "\n");
	}

	return ret;
}

void _env_dump_net_init()
{

}

void _env_dump_net_fini()
{

}
