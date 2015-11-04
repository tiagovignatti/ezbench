CC = gcc
CFLAGS = -c -Wall -fPIC -g
LDFLAGS = -shared -g

SOURCES = env_dump.c fd.c gl.c libs.c linux.c net.c posix_env.c xorg.c
OBJECTS = $(SOURCES:.c=.o)

# Name of executable target:
EXECUTABLE = env_dump.so

# libcrypto
CFLAGS += `pkg-config --cflags libcrypto`

# libxrandr
CFLAGS += `pkg-config --cflags xrandr`

# other libs
LDFLAGS += -lpthread -ldl

all: $(SOURCES) $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	$(CC) $(OBJECTS) -o $@ $(LDFLAGS)

.c.o:
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm $(OBJECTS) $(EXECUTABLE)
