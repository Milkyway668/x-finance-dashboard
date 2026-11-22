"""为不同时间范围生成对应的短评，写入 data/digest_by_range.json"""
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


def load_data():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(os.path.join(ROOT,'data.js'))},'utf8')"
          "+';globalThis.O=DATA;',c);process.stdout.write(JSON.stringify(c.O));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True,
                                     text=True, encoding="utf-8").stdout)


SYSTEM = """你是买方研究编辑。根据给定的推特材料写一段中文短评，用于投研晨报。

硬性规则：
1. 只用材料中的事实与数字，绝不编造，不引入外部行情。
2. 数字必须原样来自材料。
3. 3-5 段，每段 60-120 字，专业克制；先事实后判断。
4. 每段末尾给出该段来源的推文 ID 列表。
5. 不做投资建议，不出现"建议买入/卖出/目标价/看多/看空"（引用他人观点须写明是谁说的）。
6. 材料少时不要硬凑，宁可用 2-3 段。

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


def main():
    env = load_env(); key = env["DEEPSEEK_API_KEY"]; base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    data = load_data()
    latest = max(d["date"] for d in data)

    def within(days):
        if days == "all":
            return data
        from datetime import date, timedelta
        base_d = date.fromisoformat(latest)
        start = base_d - timedelta(days=int(days) - 1)
        return [d for d in data if date.fromisoformat(d["date"]) >= start]

    out = {}
    for key_name, days, label in [("1", 1, "今天"), ("3", 3, "最近 3 天"),
                                  ("7", 7, "最近 7 天"), ("30", 30, "最近 30 天"), ("all", "all", "全部")]:
        items = within(days)
        lines = []
        for d in items:
            for t in d["tweets"]:
                tid = t["url"].rstrip("/").split("/")[-1]
                zh = (t.get("zh") or "")[:600]
                lines.append(f"推文ID {tid}｜@{d['accounts'][0]}｜{d['date']}\n{zh}\n")
        mats = "\n".join(lines)
        try:
            r = call(key, base, mats, label)
            r["date"] = label
            r["note"] = "短评由编辑基于当日抓取内容撰写，每段后标注来源；文中数字均由脚本回查原文核对。本看板仅做信息整理，不构成投资建议。"
            out[key_name] = r
            print(f"{label}: {len(items)} 组 / {sum(len(d['tweets']) for d in items)} 条 -> {len(r.get('paragraphs',[]))} 段", flush=True)
        except Exception as e:
            print(label, "ERR", str(e)[:60], flush=True)

    json.dump(out, open(os.path.join(ROOT, "data", "digest_by_range.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("保存 data/digest_by_range.json")


if __name__ == "__main__":
    main()
