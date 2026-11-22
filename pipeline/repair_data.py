# -*- coding: utf-8 -*-
"""修复 data.js 中重复的常量声明：每个常量保留内容最完整的一份"""
import json, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = r"C:\Users\27243\Desktop\twitter 看板\data.js"
src = open(P, encoding="utf-8").read()

NAMES = ["ACC_NAMES", "DIGEST_BY_RANGE", "SUMMARIES", "DIGEST", "DATA"]


def extract(name):
    """找出 const NAME=<json>; 的全部出现，返回 JSON 值列表"""
    vals = []
    for m in re.finditer(r"const\s+" + name + r"\s*=\s*", src):
        i = m.end()
        if i >= len(src) or src[i] not in "{[":
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < len(src):
            c = src[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c in "{[":
                    depth += 1
                elif c in "}]":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        raw = src[i:j + 1]
        try:
            vals.append(json.loads(raw))
        except Exception:
            pass
    return vals


out = []
for name in NAMES:
    vals = extract(name)
    if not vals:
        print("未找到", name)
        continue
    # 取内容最多的那份
    best = max(vals, key=lambda v: len(json.dumps(v, ensure_ascii=False)))
    print(f"{name}: 发现 {len(vals)} 份，保留最大的一份")
    out.append(f"const {name}=" + json.dumps(best, ensure_ascii=False) + ";")

open(P, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("已重写 data.js")
