#!/bin/bash
set -e
SRC=$1
gcc -fsanitize=address,undefined -g -Wall -o /tmp/logfmt_test \
    $SRC c_track/baseline/tests/test_basic.c 2>&1 | grep -i "error" && exit 1

# oversized input test
python3 -c "
import subprocess, sys
r = subprocess.run(['/tmp/logfmt_test'], capture_output=True)
if r.returncode != 0:
    sys.exit(1)
"
