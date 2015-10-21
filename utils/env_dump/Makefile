CC = gcc
CFLAGS = -c -Wall -fPIC
LDFLAGS = -shared

SOURCES = env_dump.c fd.c gl.c libs.c posix_env.c
OBJECTS = $(SOURCES:.c=.o)

# Name of executable target:
EXECUTABLE = env_dump.so

# libcrypto
CFLAGS += `pkg-config --cflags libcrypto`
LDFLAGS += `pkg-config --libs libcrypto`

# other libs
LDFLAGS += -lpthread -ldl

all: $(SOURCES) $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	$(CC) $(OBJECTS) -o $@ $(LDFLAGS)

.c.o:
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm $(OBJECTS) $(EXECUTABLE)
