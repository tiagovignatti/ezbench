#!/bin/bash

Xorg -nolisten tcp -noreset :42 vt5 -auth /tmp/ezbench_XAuth&
echo "$!" > /tmp/ezbench_x.pid

sleep .1
