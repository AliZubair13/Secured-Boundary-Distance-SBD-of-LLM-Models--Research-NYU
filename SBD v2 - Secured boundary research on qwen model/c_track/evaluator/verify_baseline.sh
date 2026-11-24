#!/bin/bash
cd "$(dirname "$0")/../.."
gcc -fsanitize=address,undefined -g -Wall \
    -o /tmp/baseline_test \
    c_track/baseline/logfmt.c \
    c_track/baseline/tests/test_basic.c 2>&1

/tmp/baseline_test
if [ $? -eq 0 ]; then
    echo "PASS: baseline is clean"
else
    echo "FAIL: baseline has errors"
    exit 1
fi
