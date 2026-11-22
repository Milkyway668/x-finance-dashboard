"""把 data/summaries.json 与 data/digest_by_range.json 注入 data.js

原脚本名为 _range_ui.py，被 .gitignore 的 **/_*.py 规则漏掉，仓库里一直缺失。
现在改为 range_ui.py 并纳入版本管理。
"""
import json, os, subprocess, sys

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


def main():
    obj = load_all()

    p = os.path.join(ROOT, "data", "summaries.json")
    if os.path.exists(p):
        obj["SUMMARIES"] = json.load(open(p, encoding="utf-8"))
        print("SUMMARIES:", len(obj["SUMMARIES"]), "组")
    else:
        print("未找到 summaries.json，保留原 SUMMARIES")

    p = os.path.join(ROOT, "data", "digest_by_range.json")
    if os.path.exists(p):
        obj["DIGEST_BY_RANGE"] = json.load(open(p, encoding="utf-8"))
        print("DIGEST_BY_RANGE:", list(obj["DIGEST_BY_RANGE"].keys()))
    else:
        print("未找到 digest_by_range.json，保留原 DIGEST_BY_RANGE")

    out = ("const ACC_NAMES=" + json.dumps(obj["ACC_NAMES"], ensure_ascii=False) + ";\n"
           "const DIGEST=" + json.dumps(obj["DIGEST"], ensure_ascii=False) + ";\n"
           "const DIGEST_BY_RANGE=" + json.dumps(obj["DIGEST_BY_RANGE"], ensure_ascii=False) + ";\n"
           "const SUMMARIES=" + json.dumps(obj["SUMMARIES"], ensure_ascii=False) + ";\n"
           "const DATA=" + json.dumps(obj["DATA"], ensure_ascii=False) + ";\n")
    open(DP, "w", encoding="utf-8").write(out)
    print("已写回 data.js：", len(obj["DATA"]), "组")


if __name__ == "__main__":
    main()
