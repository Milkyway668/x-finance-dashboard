"""把 data.js 裁剪为最近 N 天（默认 7 天）

- 以数据集中最新一条推文的日期为基准，保留 [最新日期 - (N-1) 天, 最新日期]
- 同时清理 DIGEST / DIGEST_BY_RANGE / SUMMARIES 中指向已删除推文的引用，
  避免页面出现死链接、也避免 verify_*.py 因来源缺失误报
用法: python prune_days.py [天数]
"""
import json, os, re, subprocess, sys
from datetime import date, timedelta, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DP = os.path.join(ROOT, "data.js")


def load_all():
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


def tid_of(ref):
    if isinstance(ref, (list, tuple)) and len(ref) >= 2:
        return str(ref[1])
    return str(ref).rstrip("/").split("/")[-1]


def clean_summary(s, keep):
    """删掉指向不存在推文的 refs；悬空引用是页面死链的来源"""
    if not isinstance(s, dict):
        return s
    for p in s.get("paragraphs", []):
        if "refs" in p:
            p["refs"] = [r for r in p["refs"] if tid_of(r) in keep]
    return s


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    obj = load_all()
    data = obj["DATA"]
    if not data:
        raise SystemExit("DATA 为空，无法裁剪")

    def iso10(s):
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s or "")
        if not m:
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    def tweet_date(d, t):
        """兼容三种写法：t='MM-DD' / t='YYYY-MM-DDTHH:MM...' / 组 date 兜底"""
        ti = (t.get("t") or "").strip()
        dt = iso10(ti)
        if dt:
            return dt
        base = iso10(d.get("date") or "")
        if not re.match(r"^\d{2}-\d{2}$", ti):
            return base
        year = base.year if base else datetime.now().year
        try:
            dt = date(year, int(ti[:2]), int(ti[3:]))
            if base and int(ti[:2]) - base.month > 6:
                dt = dt.replace(year=dt.year - 1)
            elif base and base.month - int(ti[:2]) > 6:
                dt = dt.replace(year=dt.year + 1)
            elif not base and dt > datetime.now().date() + timedelta(days=1):
                dt = dt.replace(year=dt.year - 1)
            return dt
        except ValueError:
            return None

    all_dates = [x for d in data for t in d.get("tweets", []) if (x := tweet_date(d, t))]
    if not all_dates:
        raise SystemExit("无法解析任何推文日期，已中止")
    latest = max(all_dates)
    cutoff = latest - timedelta(days=days - 1)

    # 以组内每一条推文的日期为准裁剪，并按推文 ID 全局去重；
    # 根推文可能很早或没有日期，不能因此丢掉整个串文组。
    kept, seen = [], set()
    for d in data:
        tw = []
        for t in d.get("tweets", []):
            tid = t.get("url", "").rstrip("/").split("/")[-1]
            dt = tweet_date(d, t)
            if dt is None or dt < cutoff:   # 无法确定日期或超过窗口的条目剔除
                continue
            if tid in seen:
                continue
            seen.add(tid)
            t["t"] = dt.strftime("%m-%d")   # 统一成 MM-DD，兼容旧格式
            tw.append(t)
        if not tw:
            continue
        d["tweets"] = tw
        dates = sorted(x for t in tw if (x := tweet_date(d, t)))
        if dates:
            d["date"] = dates[-1].isoformat()
            d["time"] = d["date"][5:]
        kept.append(d)

    removed = len(data) - len(kept)
    keep_ids = seen

    obj["DATA"] = kept
    obj["DIGEST"] = clean_summary(obj["DIGEST"], keep_ids)
    for k in list(obj["DIGEST_BY_RANGE"].keys()):
        obj["DIGEST_BY_RANGE"][k] = clean_summary(obj["DIGEST_BY_RANGE"][k], keep_ids)
    for k in list(obj["SUMMARIES"].keys()):
        obj["SUMMARIES"][k] = clean_summary(obj["SUMMARIES"][k], keep_ids)

    out = ("const ACC_NAMES=" + json.dumps(obj["ACC_NAMES"], ensure_ascii=False) + ";\n"
           "const DIGEST=" + json.dumps(obj["DIGEST"], ensure_ascii=False) + ";\n"
           "const DIGEST_BY_RANGE=" + json.dumps(obj["DIGEST_BY_RANGE"], ensure_ascii=False) + ";\n"
           "const SUMMARIES=" + json.dumps(obj["SUMMARIES"], ensure_ascii=False) + ";\n"
           "const DATA=" + json.dumps(obj["DATA"], ensure_ascii=False) + ";\n")
    open(DP, "w", encoding="utf-8").write(out)
    print(f"裁剪为近 {days} 天（{cutoff} ~ {latest}）："
          f"保留 {len(kept)} 组 / {len(keep_ids)} 条推文，移除 {removed} 组")


if __name__ == "__main__":
    main()
