CC = gcc
CFLAGS = -c -Wall -fPIC -g -O2
LDFLAGS = -shared -g

SHA1_DB ?= ../../SHA1_DB

SOURCES = env_dump.c cpu.c drm.c fd.c gl.c libs.c linux.c net.c posix_env.c xorg.c
OBJECTS = $(SOURCES:.c=.o)

# Name of executable target:
EXECUTABLE = env_dump.so

# libcrypto
CFLAGS += `pkg-config --cflags libcrypto`

# libxrandr
CFLAGS += `pkg-config --cflags xrandr`

# libxcb
CFLAGS += `pkg-config --cflags xcb-dri2 xcb-dri3`

# libxrandr
CFLAGS += `pkg-config --cflags libdrm`

# other libs
LDFLAGS += -lpthread -ldl

all: $(SOURCES) $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	$(CC) $(OBJECTS) -o $@ $(LDFLAGS)
	@if [ -e "${SHA1_DB}/sha1_db" ]; then \
		${SHA1_DB}/sha1_db ${SHA1_DB} - add_git . $(EXECUTABLE); \
	else \
		echo "Warning: SHA1_DB is not defined, cannot add the version to the SHA1_DB."; \
	fi

.c.o:
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm $(OBJECTS) $(EXECUTABLE)
