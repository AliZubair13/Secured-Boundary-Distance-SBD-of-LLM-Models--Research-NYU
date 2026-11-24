#!/bin/bash
cd "$(dirname "$0")/../.."
PASS=0
FAIL=0

check_mutant() {
    local name=$1
    local file=$2
    local expect_fail=$3
    local testfile=$4

    gcc -fsanitize=address,undefined -g -Wall \
        -o /tmp/cal_test \
        $file $testfile -I c_track/baseline 2>/tmp/cal_err

    if [ $? -ne 0 ]; then
        if [ "$expect_fail" = "1" ]; then
            echo "PASS: $name (compile error caught)"
            PASS=$((PASS+1))
        else
            echo "FAIL: $name (unexpected compile error)"
            FAIL=$((FAIL+1))
        fi
        return
    fi

    /tmp/cal_test 2>/tmp/cal_run
    rc=$?

    if [ "$expect_fail" = "1" ] && [ $rc -ne 0 ]; then
        echo "PASS: $name (flaw caught)"
        PASS=$((PASS+1))
    elif [ "$expect_fail" = "0" ] && [ $rc -eq 0 ]; then
        echo "PASS: $name (clean confirmed)"
        PASS=$((PASS+1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL+1))
    fi
}

OVERFLOW="c_track/baseline/tests/test_overflow.c"
BASIC="c_track/baseline/tests/test_basic.c"

check_mutant "mutant_1" "c_track/evaluator/mutants/mutant_1.c" "1" "$OVERFLOW"
check_mutant "mutant_2" "c_track/evaluator/mutants/mutant_2.c" "1" "$OVERFLOW"
check_mutant "mutant_3" "c_track/evaluator/mutants/mutant_3.c" "1" "$OVERFLOW"
check_mutant "mutant_4" "c_track/evaluator/mutants/mutant_4.c" "1" "$OVERFLOW"
check_mutant "mutant_5" "c_track/evaluator/mutants/mutant_5.c" "1" "$OVERFLOW"
check_mutant "clean_1"  "c_track/evaluator/mutants/clean_1.c"  "0" "$BASIC"
check_mutant "clean_2"  "c_track/evaluator/mutants/clean_2.c"  "0" "$BASIC"
check_mutant "clean_3"  "c_track/evaluator/mutants/clean_3.c"  "0" "$BASIC"

echo ""
echo "Result: $PASS passed, $FAIL failed"
