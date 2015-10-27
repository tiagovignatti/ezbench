#!/bin/bash

$@ >&2 &
echo "$!"

sleep .1
