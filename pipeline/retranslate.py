"""把翻译不完整的条目重新逐句翻译，并回写 data.js"""
import os, json, subprocess, sys, urllib.request

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


def dump_all():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(os.path.join(ROOT,'data.js'))},'utf8')"
          "+';globalThis.O={DATA,SUMMARIES,DIGEST,ACC_NAMES};',c);"
          "process.stdout.write(JSON.stringify(c.O));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


SYSTEM = """你是严谨的财经翻译。把给定的英文推特**逐句完整翻译成中文**。

硬性要求：
1. 必须逐句翻译，不允许概括、省略、合并段落。
2. 保留所有数字、单位、公司名、股票代码、专有名词。
3. 保留原文的换行与段落结构。
4. 语气平实，不要加评论、不要加"这显示出"之类的解读。
5. 只输出译文本身，不要任何前言或解释。"""


def translate(key, base, text):
    body = {"model": "deepseek-chat",
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": text}],
            "temperature": 0.1}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()


def main():
    env = load_env(); key = env["DEEPSEEK_API_KEY"]; base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    obj = dump_all()
    data = obj["DATA"]

    targets = []
    for d in data:
        for t in d["tweets"]:
            en, zh = t.get("en", ""), t.get("zh", "")
            if len(en) > 300 and len(zh) < len(en) * 0.3:
                targets.append((d, t))
    print("待重译:", len(targets), flush=True)

    done = 0
    for d, t in targets:
        try:
            new = translate(key, base, t["en"])
            if len(new) > len(t.get("zh", "")):
                t["zh"] = new
                done += 1
                print(f"  @{d['accounts'][0]} {t['url'].split('/')[-1]} {len(t['en'])}→{len(new)}", flush=True)
        except Exception as e:
            print("  ERR", str(e)[:60], flush=True)

    # 回写：DATA 用 JSON 重写，其余常量原样
    path = os.path.join(ROOT, "data.js")
    s = open(path, encoding="utf-8").read()
    head = s[:s.index("const DATA=[")] if "const DATA=[" in s else ""
    s2 = head + "const DATA=" + json.dumps(data, ensure_ascii=False) + ";\n" \
         + "const SUMMARIES=" + json.dumps(obj["SUMMARIES"], ensure_ascii=False) + ";\n" \
         + "const DIGEST=" + json.dumps(obj["DIGEST"], ensure_ascii=False) + ";\n"
    open(path, "w", encoding="utf-8").write(s2)
    print("重译完成:", done, "回写 data.js")


if __name__ == "__main__":
    main()
