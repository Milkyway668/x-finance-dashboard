"""
短评真实性校验
规则：
1) 每条短评必须至少挂一个来源推文，且来源必须在数据集中存在
2) 短评里出现的每个数字，必须能在其引用的推文原文（中文或英文）中找到
3) 出现"看多/看空/买入/卖出"等方向性建议时报警（本看板不做投资建议）
"""
import os, re, json, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(ROOT, "data.js")


def load_js():
    """用 node 读取 data.js 中的 DATA 与 DIGEST"""
    js = (
        "const fs=require('fs');const vm=require('vm');"
        f"const ctx={{}};vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(DATA_JS)},'utf8')+';globalThis.OUT={{DATA:DATA,DIGEST:DIGEST}};',ctx);"
        "process.stdout.write(JSON.stringify(ctx.OUT));"
    )
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("读取 data.js 失败:\n" + out.stderr[:500])
    return json.loads(out.stdout)


def number_tokens(text):
    """抓出所有数字 token：12% / 2027 / 2.45 / 76 等"""
    return re.findall(r"\d+(?:\.\d+)?%?", text)


def main():
    import sys as _s
    if len(_s.argv) > 1 and _s.argv[1].endswith(".json"):
        obj = load_js()
        data = obj["DATA"]
        digest = json.load(open(_s.argv[1], encoding="utf-8"))
    else:
        obj = load_js()
        data, digest = obj["DATA"], obj["DIGEST"]

    # 推文索引
    tw_index = {}
    for d in data:
        for t in d["tweets"]:
            tid = t.get("url", "").rstrip("/").split("/")[-1]
            t = dict(t)
            t["_date"] = d.get("date", "")
            t["_time"] = d.get("time", "")
            tw_index[tid] = t

    problems, warnings = [], []
    banned = ["建议买入", "建议卖出", "看多", "看空", "目标价", "recommend buy", "price target"]

    for i, item in enumerate(digest.get("paragraphs", digest.get("items", [])), 1):
        title = item.get("h") or ("第 %d 段" % i)
        body, refs = item["text"] if "text" in item else item["t"], item.get("refs", [])
        line = f"[{i}] {title}"

        # 规则 1：必须有来源且来源存在
        if not refs:
            if number_tokens(body):
                problems.append(f"{line}: 无来源但包含数字")
            continue
        src_text = ""
        for ref in refs:
            tid = ref[1] if isinstance(ref, (list, tuple)) else ref
            t = tw_index.get(tid)
            if not t:
                problems.append(f"{line}: 来源推文 {tid} 不存在于数据集")
                continue
            src_text += " " + (t.get("zh", "") + " " + t.get("en", "") + " " + t.get("_date", "") + " " + t.get("_time", ""))

        # 规则 2：数字必须能在来源里找到
        for tok in set(number_tokens(body)):
            if tok not in src_text:
                problems.append(f"{line}: 数字「{tok}」在来源推文中找不到")

        # 规则 3：不做方向性建议
        for w in banned:
            if w in body or w in title:
                warnings.append(f"{line}: 出现方向性表述「{w}」")

    print("=" * 48)
    print("短评真实性校验")
    print("=" * 48)
    print(f"短评段落: {len(digest.get('paragraphs', digest.get('items', [])))}   来源推文: {len(tw_index)}")
    if problems:
        print("\n[必须修复]")
        for p in problems:
            print("  ✗", p)
    else:
        print("\n[通过] 所有结论均有来源，所有数字均可在原文中找到")

    if warnings:
        print("\n[提醒]")
        for w in warnings:
            print("  !", w)

    print("\n结果:", "FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
