"""
把 fetch 抓到的原文批量翻译成中文，并给出主题初判（供人工校对）
输出 data/new_items.json
"""
import os, re, json, subprocess, sys, urllib.request, glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def existing_ids():
    dp = os.path.join(ROOT, "data.js")
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(dp)},'utf8')+';globalThis.O=DATA;',c);"
          "process.stdout.write(JSON.stringify(c.O));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    ids = set()
    if out.returncode == 0:
        for d in json.loads(out.stdout):
            for t in d["tweets"]:
                ids.add(t["url"].rstrip("/").split("/")[-1])
    return ids


SYSTEM = """你是金融翻译与编辑。给定一条（或一组）英文推特原文，完成三件事，输出严格 JSON：

{
 "title": "中文标题，12-20 字，陈述这条推文的核心事实",
 "zh": ["逐条对应的中文翻译，忠实原意，不增不减，保留数字与专有名词"],
 "themes": ["宏观" 或 "产业·半导体" 或 "产业·AI算力" 或 "公司"，可多选],
 "tickers": ["$XXX 形式的标的名，没有就空数组"]
}

规则：
1. 翻译必须准确，数字、公司名、百分比原样保留；不要润色成评论。
2. 主题判定按顺序：讲政策/地缘/关税→宏观；讲芯片本身（设计/制造/设备/存储/份额）→产业·半导体；
   讲数据中心/算力/GPU租用/折旧/capex→产业·AI算力；讲某家公司的战略/产品/融资/IPO/财报→公司。
3. 不确定就少选，不要硬套。
4. 不要输出任何解释，只输出 JSON。"""


def call(key, base, texts):
    user = "推特原文（按顺序，共 %d 条）：\n\n" % len(texts)
    for i, t in enumerate(texts, 1):
        user += f"[{i}] {t}\n\n"
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read().decode("utf-8"))
    return json.loads(out["choices"][0]["message"]["content"])


def main():
    env = load_env()
    key = env["DEEPSEEK_API_KEY"]; base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    cands = glob.glob(os.path.join(ROOT, "data", "fetch_*.json")) +         glob.glob(os.path.join(ROOT, "data", "fetch_inprogress.json"))
    src = max(cands, key=os.path.getmtime)
    data = json.load(open(src, encoding="utf-8"))
    done = existing_ids()

    results = []
    for user, items in data.items():
        for it in items:
            root = it["root_id"]
            if root in done:
                continue
            parts = [p for p in it["parts"] if p.get("text", "").strip()]
            if not parts:
                continue
            texts = [p["text"] for p in parts]
            try:
                r = call(key, base, texts)
            except Exception as e:
                print("ERR", user, root, str(e)[:60], flush=True)
                continue
            zh = r.get("zh") or []
            results.append({
                "account": user,
                "root_id": root,
                "title": r.get("title", ""),
                "themes": r.get("themes", []),
                "tickers": [t.lstrip("$") for t in r.get("tickers", [])],
                "parts": [
                    {
                        "id": p["id"], "text": p["text"],
                        "zh": zh[i] if i < len(zh) else "",
                        "time": p.get("time", ""), "likes": p.get("likes"),
                        "retweets": p.get("retweets"), "url": p.get("url", ""),
                        "media": p.get("media", 0), "flags": p.get("flags", []),
                    } for i, p in enumerate(parts)
                ],
            })
            print(f"{user} {root} -> {r.get('title','')[:24]}", flush=True)

    out = os.path.join(ROOT, "data", "new_items.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("新增条目:", len(results), "保存:", out)


if __name__ == "__main__":
    main()
