"""
一键更新：抓取 → 翻译 → 归类 → 生成短评 → 校验 → 写回 data.js
用法：
  python update_all.py            # 全流程（含抓取）
  python update_all.py --no-fetch # 跳过抓取，用已有数据重跑翻译与短评
任何一步校验失败，脚本会停下并报错，不会把错误内容写进页面。
"""
import os, subprocess, sys, glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"C:\Users\27243\Desktop\twitter 看板"
PY = sys.executable
PIPE = os.path.join(ROOT, "pipeline")


def run(script, *args):
    cmd = [PY, "-I", os.path.join(PIPE, script)] + list(args)
    print(f"\n>>> {script} {' '.join(args)}", flush=True)
    r = subprocess.run(cmd, cwd=PIPE)
    if r.returncode != 0:
        raise SystemExit(f"[失败] {script} 返回 {r.returncode}，已中止，页面数据未被破坏")
    return r.returncode


def main():
    skip_fetch = "--no-fetch" in sys.argv

    if not skip_fetch:
        run("fetch.py")
    else:
        print("跳过抓取")

    run("translate_new.py")      # 只翻新增（已存在的会跳过）
    run("merge_new.py")          # 合并进 data.js
    run("retranslate.py")        # 修补“摘要冒充翻译”的条目
    run("repair_data.py")        # 去重常量声明，保证 data.js 结构干净
    run("gen_summaries.py")      # 每个分类/账号的专题短评
    run("gen_range_digest.py")   # 每个时间范围的短评

    # 校验闸门
    print("\n=== 真实性校验 ===", flush=True)
    ok = True
    try:
        run("verify_digest.py")
    except SystemExit as e:
        print(e); ok = False
    try:
        run("verify_summaries.py")
    except SystemExit as e:
        print(e); ok = False
    try:
        run("verify_range.py")
    except SystemExit as e:
        print(e); ok = False

    if not ok:
        raise SystemExit("\n[中止] 有结论未能溯源，请人工检查后再发布")

    # 把范围数据注入 data.js，并再次清理
    run("_range_ui.py")
    run("repair_data.py")

    print("\n完成。刷新页面即可看到新内容。")


if __name__ == "__main__":
    main()
