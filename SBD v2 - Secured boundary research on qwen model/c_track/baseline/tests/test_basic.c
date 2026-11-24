#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "../logfmt.h"

int main() {
    char buf[128];

    // normal input
    assert(logfmt_format(buf, sizeof(buf), "level", "info") == 0);
    assert(strcmp(buf, "level=info") == 0);

    // empty strings
    assert(logfmt_format(buf, sizeof(buf), "", "") == 0);

    // copy normal
    assert(logfmt_copy(buf, sizeof(buf), "hello") == 0);
    assert(strcmp(buf, "hello") == 0);

    // copy truncates safely
    assert(logfmt_copy(buf, 4, "hello") == 0);
    assert(buf[3] == '\0');

    // parse normal
    char key[64], val[64];
    assert(logfmt_parse("level=info", key, sizeof(key), val, sizeof(val)) == 0);
    assert(strcmp(key, "level") == 0);
    assert(strcmp(val, "info") == 0);

    // parse no equals
    assert(logfmt_parse("noequalssign", key, sizeof(key), val, sizeof(val)) == -1);

    printf("ALL TESTS PASSED\n");
    return 0;
}
