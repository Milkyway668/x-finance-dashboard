import os, re, json, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"C:\Users\27243\Desktop\twitter 看板"


def load_data():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(os.path.join(ROOT,'data.js'))},'utf8')"
          "+';globalThis.O=DATA;',c);process.stdout.write(JSON.stringify(c.O));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


def tokens(t):
    return re.findall(r"\d+(?:\.\d+)?%?", t)


data = load_data()
sums = json.load(open(os.path.join(ROOT, "data", "summaries.json"), encoding="utf-8"))

index = {}
for d in data:
    for t in d["tweets"]:
        tid = t["url"].rstrip("/").split("/")[-1]
        index[tid] = (t.get("zh", "") + " " + t.get("en", "") + " " + d["date"])

problems = 0
for name, s in sums.items():
    for i, p in enumerate(s.get("paragraphs", []), 1):
        refs = p.get("refs", [])
        if not refs:
            if tokens(p["text"]):
                print(f"[!] {name} 第{i}段：无来源但有数字")
                problems += 1
            continue
        src = " ".join(index.get(r, "") for r in refs)
        for tok in set(tokens(p["text"])):
            if tok not in src:
                print(f"[!] {name} 第{i}段：数字「{tok}」在来源中找不到")
                problems += 1

print("检查完成，问题数:", problems)
