"""把 new_items.json 合并进 data.js（结构化读写，不依赖文本位置）"""
import json, os, sys, subprocess, re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"C:\Users\27243\Desktop\twitter 看板"
DP = os.path.join(ROOT, "data.js")

NOISE = ["寿司郎", "经济学人", "天气", "共和党", "选举", "峰会将在", "停更", "民调",
         "黎曼", "预测共和党"]


def dump_all():
    js = ("const fs=require('fs');const vm=require('vm');const c={};vm.createContext(c);"
          f"vm.runInContext(fs.readFileSync({json.dumps(DP)},'utf8')"
          "+';globalThis.O={DATA:(typeof DATA!==\"undefined\"?DATA:[]),"
          "SUMMARIES:(typeof SUMMARIES!==\"undefined\"?SUMMARIES:{}),"
          "DIGEST:(typeof DIGEST!==\"undefined\"?DIGEST:{}),"
          "DIGEST_BY_RANGE:(typeof DIGEST_BY_RANGE!==\"undefined\"?DIGEST_BY_RANGE:{}),"
          "ACC_NAMES:(typeof ACC_NAMES!==\"undefined\"?ACC_NAMES:{})};',c);"
          "process.stdout.write(JSON.stringify(c.O));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("读取 data.js 失败:\n" + out.stderr[:400])
    return json.loads(out.stdout)


def main():
    obj = dump_all()
    data = obj["DATA"]
    have = set()
    for d in data:
        for t in d["tweets"]:
            have.add(t["url"].rstrip("/").split("/")[-1])

    items = json.load(open(os.path.join(ROOT, "data", "new_items.json"), encoding="utf-8"))
    seen, keep = set(), []
    for it in items:
        title = it.get("title", "")
        if any(k in title for k in NOISE) or not it.get("themes"):
            continue
        key = title[:12]
        if key in seen:
            continue
        seen.add(key)
        keep.append(it)
    print("保留", len(keep), "条（原始", len(items), "）")

    n = 0
    for it in keep:
        parts, seen_now = [], set()
        for p in it["parts"]:
            pid = p.get("id")
            if not pid or not p.get("zh") or pid in have or pid in seen_now:
                continue
            seen_now.add(pid)
            parts.append(p)
        if not parts:
            continue
        have.update(seen_now)   # 防止同一条推文被后面的串文重复合并
        n += 1
        # 串文组的日期取组内最新一条，而不是根推文（根推文可能很早或没有日期）
        dates = [p.get("time") for p in parts if p.get("time")]
        date = max(dates) if dates else (parts[0].get("time") or "")[:10]
        mmdd = date[5:]
        data.append({
            "id": "n%d" % (len(data) + 1),
            "themes": it["themes"][:2],
            "date": date, "time": mmdd,
            "tickers": it.get("tickers", [])[:4],
            "accounts": [it["account"]],
            "tweets": [{
                "u": it["account"], "t": mmdd, "l": p.get("likes"), "r": p.get("retweets"),
                "url": p.get("url") or f"https://x.com/i/status/{p['id']}",
                "en": p["text"], "zh": p["zh"],
            } for p in parts],
        })
    print("新增条目", n)

    out = ("const ACC_NAMES=" + json.dumps(obj["ACC_NAMES"], ensure_ascii=False) + ";\n"
           "const DIGEST=" + json.dumps(obj["DIGEST"], ensure_ascii=False) + ";\n"
           "const DIGEST_BY_RANGE=" + json.dumps(obj["DIGEST_BY_RANGE"], ensure_ascii=False) + ";\n"
           "const SUMMARIES=" + json.dumps(obj["SUMMARIES"], ensure_ascii=False) + ";\n"
           "const DATA=" + json.dumps(data, ensure_ascii=False) + ";\n")
    open(DP, "w", encoding="utf-8").write(out)
    print("已写入 data.js，共", len(data), "组")


if __name__ == "__main__":
    main()
