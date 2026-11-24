#ifndef LOGFMT_H
#define LOGFMT_H
#include <stddef.h>
int logfmt_format(char *out, size_t out_sz, const char *key, const char *val);
int logfmt_copy(char *dst, size_t dst_sz, const char *src);
int logfmt_parse(const char *in, char *key_out, size_t k_sz, char *val_out, size_t v_sz);
#endif
