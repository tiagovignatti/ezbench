#!/bin/bash

# Start a compositor
twm&

# Start xterm to follow the compilation logs
xterm -geometry 80x66+0+0 -e "tail -f $EZBENCH_COMPILATION_LOGS"&

# Start xterm to follow the compilation logs
exec xterm -geometry 80x50+494+51