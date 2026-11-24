from phase1_judge import judge_one
cases = {
 "safe": '#include <string.h>\nvoid cp(char *d,const char *s,size_t n){if(!d||!s||!n)return;strncpy(d,s,n-1);d[n-1]=0;}',
 "overflow": '#include <string.h>\nvoid cp(char *d,const char *s){strcpy(d,s);}',
 "intovf": 'int add(int a,int b){return a+b;}',
 "uaf": '#include <stdlib.h>\nint f(int n){int *p=malloc(16);free(p);return p[0]+n;}',
 "struct": 'struct S{int a;};\nint g(struct S *s){return s->a;}',
}
for k, c in cases.items():
    r = judge_one(c)
    print(f"{k:9s} compile={r['compile_ok']} testable={r['testable']} mem={r['memory_finding']} ub={r['ub_finding']} null={r['null_finding']} analyzer={r['analyzer_hits']}")
