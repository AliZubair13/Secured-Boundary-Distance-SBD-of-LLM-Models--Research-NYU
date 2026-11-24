#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "../logfmt.h"

int main() {
    /* small stack buffer — overflow writes past it */
    char small[8];
    char big[512];
    memset(big, 'A', 511);
    big[511] = '\0';

    /* triggers mutant_1 (sprintf), mutant_2 (strcpy), mutant_3 (dst[dst_sz]='\0') */
    logfmt_format(small, sizeof(small), big, big);
    logfmt_copy(small, sizeof(small), big);

    /* triggers mutant_4: strlen on unterminated buffer */
    char dst[8];
    logfmt_copy(dst, sizeof(dst), "hello!!");
    size_t len = strlen(dst);  /* reads past end if no null */
    (void)len;

    /* triggers mutant_5: %n in format string writes to memory */
    int dummy = 0;
    char fmt[32];
    snprintf(fmt, sizeof(fmt), "%%n");
    logfmt_format(small, sizeof(small), fmt, "val");

    printf("ALL TESTS PASSED\n");
    return 0;
}
