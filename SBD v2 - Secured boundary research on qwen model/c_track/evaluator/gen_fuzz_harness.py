#!/usr/bin/env python3
"""Attack every function DEFINED in a C file, including ones absent from the header."""
import re, sys
from pathlib import Path

DEFN = re.compile(r'^[ \t]*([A-Za-z_][\w \t\*]*?)[ \t]+(\w+)[ \t]*\(([^;{)]*)\)[ \t]*\{', re.M)

def strip_comments(t):
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
    return re.sub(r'//.*', '', t)

def parse_params(s):
    s = s.strip()
    if s in ('', 'void'):
        return []
    out = []
    for raw in s.split(','):
        m = re.match(r'^(.*?)([A-Za-z_]\w*)\s*(\[\s*\])?$', raw.strip())
        if not m:
            return None
        out.append((m.group(1).strip() + ('*' if m.group(3) else ''), m.group(2)))
    return out

def arg_for(ptype, pname):
    t = ' '.join(ptype.split())
    if 'char' in t and t.count('*') == 1:
        return 'bigstr' if 'const' in t else 'smallbuf'
    if t.count('*') == 0 and re.search(r'\b(size_t|int|long|unsigned)\b', t):
        return 'sizeof(smallbuf)' if re.search(r'(sz|size|len|cap|max)', pname.lower()) else '1'
    return None

def main(csrc, out_path):
    text = strip_comments(Path(csrc).read_text())
    protos, calls, covered, skipped = [], [], [], []
    for rtype, name, params in DEFN.findall(text):
        rt = ' '.join(rtype.split())
        if name == 'main' or 'static' in rt or rt in ('if', 'for', 'while', 'switch', 'else', 'return'):
            continue
        ps = parse_params(params)
        if ps is None:
            skipped.append(name); continue
        args = [arg_for(t, n) for t, n in ps]
        if any(a is None for a in args):
            skipped.append(name); continue
        protos.append(f'{rt} {name}({params.strip() or "void"});')
        calls.append(f'    (void){name}({", ".join(args)});')
        covered.append(name)
    Path(out_path).write_text('#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>\n'
        + "\n".join(protos) + '\n\nint main(void) {\n'
        + "    char smallbuf[8] = {0};\n    static char bigstr[512];\n"
        + "    memset(bigstr, 'A', 511);\n    bigstr[511] = '\\0';\n"
        + ("\n".join(calls) if calls else "    /* none */") + '\n'
        + '    printf("AUTO HARNESS PASSED\\n");\n    return 0;\n}\n')
    print("covered:", ", ".join(covered) or "(none)")
    print("skipped:", ", ".join(skipped) or "(none)")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
