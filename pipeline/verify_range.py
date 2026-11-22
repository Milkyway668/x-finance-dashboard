import os, re, json, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"C:\Users\27243\Desktop\twitter 看板"


def load_data():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(os.path.join(ROOT,'data.js'))},'utf8')"
          "+';globalThis.O=DATA;',c);process.stdout.write(JSON.stringify(c.O));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True,
                                     text=True, encoding="utf-8").stdout)


data = load_data()
index = {}
for d in data:
    for t in d["tweets"]:
        tid = t["url"].rstrip("/").split("/")[-1]
        index[tid] = (t.get("zh", "") + " " + t.get("en", "") + " " + d["date"])

f = os.path.join(ROOT, "data", "digest_by_range.json")
if not os.path.exists(f):
    print("未找到 digest_by_range.json，跳过")
    sys.exit(0)

d = json.load(open(f, encoding="utf-8"))
bad = 0
for key, s in d.items():
    for i, p in enumerate(s.get("paragraphs", []), 1):
        refs = p.get("refs", [])
        src = " ".join(index.get(r if isinstance(r, str) else r[1], "") for r in refs)
        for tok in set(re.findall(r"\d+(?:\.\d+)?%?", p["text"])):
            if tok not in src:
                print(f"[!] 范围 {key} 第{i}段：数字「{tok}」在来源中找不到")
                bad += 1
print("范围短评校验完成，问题数:", bad)
sys.exit(1 if bad else 0)
