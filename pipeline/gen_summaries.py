"""为「主题 × 时间范围」「账号 × 时间范围」各生成一段专题短评"""
import os, json, subprocess, sys, urllib.request
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"C:\Users\27243\Desktop\twitter 看板"


def load_env():
    env = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def load_data():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(os.path.join(ROOT,'data.js'))},'utf8')"
          "+';globalThis.O=DATA;',c);process.stdout.write(JSON.stringify(c.O));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True,
                                     text=True, encoding="utf-8").stdout)


SYSTEM = """你是买方研究编辑。给定一组推特材料，写一段“专题短评”：

1. 只用材料中的事实与数字，绝不编造。
2. 数字必须原样来自材料。
3. 2-3 段，每段 60-120 字，中文，专业克制。
4. 每段末尾给出该段来源的推文 ID 列表。
5. 不做投资建议；引用他人观点须写明是谁说的。
6. 材料很少时不要硬凑，可以只写 1-2 段。

输出严格 JSON：{"intro":"一句话导语","paragraphs":[{"text":"段落","refs":["推文ID"]}]}"""


def call(key, base, materials, label):
    body = {"model": "deepseek-chat",
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"以下是「{label}」范围内的材料：\n\n{materials}\n\n请写这段短评。"}],
            "temperature": 0.3, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"])


def materials_for(items):
    lines = []
    for d in items:
        for t in d["tweets"]:
            tid = t["url"].rstrip("/").split("/")[-1]
            zh = (t.get("zh") or "").strip()
            if len(zh) > 600:
                zh = zh[:600] + "…"
            lines.append(f"推文ID {tid}｜@{d['accounts'][0]}｜{d['date']}\n{zh}\n")
    return "\n".join(lines)


def main():
    env = load_env(); key = env["DEEPSEEK_API_KEY"]; base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    data = load_data()
    latest = date.fromisoformat(max(d["date"] for d in data))

    def within(items, days):
        if days == "all":
            return items
        start = latest - timedelta(days=int(days) - 1)
        return [d for d in items if date.fromisoformat(d["date"]) >= start]

    bases = {}
    for t in ["宏观", "行业", "公司"]:
        bases[t] = [d for d in data if t in d["themes"]]
    for a in sorted({a for d in data for a in d["accounts"]}):
        bases["@" + a] = [d for d in data if a in d["accounts"]]

    out = {}
    total = 0
    for name, items in bases.items():
        for rk, days, rlabel in [("1", 1, "今天"), ("3", 3, "最近 3 天"),
                                 ("7", 7, "最近 7 天"), ("all", "all", "全部")]:
            sub = within(items, days)
            if not sub:
                continue
            total += 1
            try:
                r = call(key, base, materials_for(sub), f"{name} · {rlabel}")
                r["count"] = sum(len(d["tweets"]) for d in sub)
                r["range"] = rlabel
                out[f"{name}|{rk}"] = r
                print(f"{name}|{rk}: {len(sub)} 组 / {r['count']} 条", flush=True)
            except Exception as e:
                print(name, rk, "ERR", str(e)[:50], flush=True)

    json.dump(out, open(os.path.join(ROOT, "data", "summaries.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"完成 {total} 个组合")


if __name__ == "__main__":
    main()
