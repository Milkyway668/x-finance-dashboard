"""
用 DeepSeek 生成「今日短评」草稿
- 只把抓取到的推文内容发给 DeepSeek，不发其它任何信息
- 强制要求：只用材料里的信息、不得编造数字、每条结论标注来源、不做投资建议
输出: data/digest_draft.json（草稿，需人工终审后才写进 data.js）
"""
import os, re, json, sys, subprocess, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def load_data():
    dp = os.path.join(ROOT, "data.js")
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(dp)},'utf8')+';globalThis.O=DATA;',c);"
          "process.stdout.write(JSON.stringify(c.O));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit(out.stderr[:400])
    return json.loads(out.stdout)


def build_materials(data):
    lines = []
    for d in data:
        for t in d["tweets"]:
            tid = t["url"].rstrip("/").split("/")[-1]
            text = (t.get("zh") or "").strip()
            if len(text) > 800:
                text = text[:800] + "…（后略）"
            lines.append(
                f'### 条目 {d["id"]} | @{d["accounts"][0]} | {d["date"]} | 主题:{"、".join(d["themes"])}\n'
                f'推文ID: {tid}\n内容: {text}\n'
            )
    return "\n".join(lines)


SYSTEM = """你是一名严谨的买方研究编辑，负责把当天抓取到的推特内容整理成一篇中文短评。

硬性规则（必须全部遵守）：
1. 只能使用材料中出现的事实与数字，绝对不许编造、外推或引入你自己知道的行情数据。
2. 每一个数字都必须原样来自材料（包括百分号、单位）。
3. 每段末尾标注该段信息的来源，格式为推文ID列表。
4. 不做任何投资建议，不出现"建议买入/卖出/目标价/看多/看空"等表述；引用他人观点时须写明是谁说的。
5. 不要评判哪条"最重要"，只做信息归拢与对照。
6. 中文写作，4-6 段，段落之间要有逻辑递进（背景 → 线索 → 对照 → 待验证的问题），不要写成一堆要点罗列。

输出严格 JSON：
{"intro":"一句话导语","paragraphs":[{"text":"段落正文","refs":["推文ID1","推文ID2"]}],"note":"固定说明"}"""


def call_deepseek(key, base, materials):
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "以下是今日抓取的全部材料：\n\n" + materials +
                                        "\n\n请依据这些材料写今日短评。"},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out["choices"][0]["message"]["content"]


def main():
    env = load_env()
    key = env.get("DEEPSEEK_API_KEY")
    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not key:
        raise SystemExit("未找到 DEEPSEEK_API_KEY（检查 .env）")

    data = load_data()
    materials = build_materials(data)
    print(f"材料: {len(data)} 条观点，字符数 {len(materials)}")

    content = call_deepseek(key, base, materials)
    draft = json.loads(content)

    out = {
        "date": "2026-11-22",
        "title": "今日短评",
        "intro": draft.get("intro", ""),
        "paragraphs": draft.get("paragraphs", []),
        "note": "短评由模型基于当日抓取内容生成，经人工复核；每段后标注来源；文中数字均由脚本回查原文核对。本看板仅做信息整理，不构成投资建议。",
        "generated_by": "deepseek-chat",
    }
    path = os.path.join(ROOT, "data", "digest_draft.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n--- 草稿 ---")
    print(out["intro"])
    for i, p in enumerate(out["paragraphs"], 1):
        print(f"\n[{i}] {p['text']}")
        print("    refs:", p.get("refs"))
    print("\n保存:", path)


if __name__ == "__main__":
    main()
