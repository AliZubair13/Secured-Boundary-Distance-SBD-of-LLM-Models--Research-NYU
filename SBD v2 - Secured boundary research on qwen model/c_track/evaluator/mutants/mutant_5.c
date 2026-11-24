#include "logfmt.h"
#include <stdio.h>
#include <string.h>

int logfmt_format(char *out, size_t out_sz, const char *key, const char *val) {
    /* format string injection: key controls the format */
    int n = snprintf(out, out_sz, key, val);
    return (n > 0 && (size_t)n < out_sz) ? 0 : -1;
}

int logfmt_copy(char *dst, size_t dst_sz, const char *src) {
    if (dst_sz == 0) return -1;
    strncpy(dst, src, dst_sz - 1);
    dst[dst_sz - 1] = '\0';
    return 0;
}

int logfmt_parse(const char *in, char *key_out, size_t k_sz, char *val_out, size_t v_sz) {
    const char *eq = strchr(in, '=');
    if (!eq) return -1;
    size_t klen = (size_t)(eq - in);
    if (klen >= k_sz) klen = k_sz - 1;
    strncpy(key_out, in, klen);
    key_out[klen] = '\0';
    strncpy(val_out, eq + 1, v_sz - 1);
    val_out[v_sz - 1] = '\0';
    return 0;
}
