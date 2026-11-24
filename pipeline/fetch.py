"""
完整性优先的 X 抓取器
用法: python fetch.py [账号1 账号2 ...]
输出: data/fetch_<时间>.json + 控制台完整性报告

关键策略：
1. 时间线只取推文 ID（时间线正文必定被截断）
2. 每条推文打开自己的详情页取全文（详情页给的是完整内容）
3. 串文：先在根推页面收集同作者后续推文 ID，再逐条打开取全文
4. 完整性校验：尾部省略号 / 长度恰为 280 / 订阅墙 / 纯图片 都要打标记
"""
import os, re, json, time, random, sys
from datetime import datetime, timezone, timedelta, date
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".browser", "profile")
OUTDIR = os.path.join(ROOT, "data")
os.makedirs(OUTDIR, exist_ok=True)

def load_accounts():
    """账号列表来自 config/accounts.json，新增账号只需改那个文件"""
    cfg = os.path.join(ROOT, "config", "accounts.json")
    try:
        return json.load(open(cfg, encoding="utf-8"))["accounts"]
    except Exception:
        return ["aleabitoreddit", "SemiAnalysis_", "Omercheema", "OrnnExchange",
                "HedgeyeTech", "RYANHINGSHING", "FredaDuan", "TMTLongShort"]

ACCOUNTS = load_accounts()

MAX_TWEETS = 7
MAX_THREAD = 8
MAX_DAYS = 7          # 只取最近 N 天内的推文（置顶旧帖会被跳过）


def log(*a):
    print(*a, flush=True)


def parse_num(s):
    if not s:
        return None
    s = s.strip().replace(",", "")
    m = re.match(r"([\d.]+)([KMB]?)", s)
    if not m:
        return None
    return int(float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])


CANON_RE = re.compile(r"^/([^/]+)/status/(\d+)$")


def canon_link(art):
    """返回 (作者, 推文ID, 时间文字)。

    X 在 2026-11 改成服务端直出 HTML：没有 data-testid，也没有 <time>。
    每条推文里唯一指向自己的规范链接是 /<user>/status/<id>（照片/analytics 链接带后缀）。
    """
    try:
        for a in art.locator("a[href*='/status/']").all():
            href = a.get_attribute("href") or ""
            m = CANON_RE.match(href)
            if m:
                return m.group(1), m.group(2), (a.inner_text() or "").strip()
    except Exception:
        pass
    return None, None, ""


def parse_time_text(txt):
    """把 X 的时间文字转成 YYYY-MM-DD：3小时 / 7分钟 / 11月20日 / 2026年11月20日 / 昨天"""
    if not txt:
        return ""
    now = datetime.now()
    t = txt.strip()
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", t)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return ""
    m = re.search(r"(\d{1,2})月(\d{1,2})日", t)
    if m:
        mo, d = map(int, m.groups())
        for y in (now.year, now.year - 1):
            try:
                dt = date(y, mo, d)
                if dt <= now.date():
                    return dt.isoformat()
            except ValueError:
                pass
        return ""
    if "昨天" in t:
        return (now.date() - timedelta(days=1)).isoformat()
    if "今天" in t or "现在" in t or "刚刚" in t:
        return now.date().isoformat()
    m = re.match(r"(\d+)\s*秒", t)
    if m:
        return (now - timedelta(seconds=int(m.group(1)))).date().isoformat()
    m = re.match(r"(\d+)\s*分钟", t)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).date().isoformat()
    m = re.match(r"(\d+)\s*小时", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).date().isoformat()
    m = re.match(r"(\d+)\s*天", t)
    if m:
        return (now.date() - timedelta(days=int(m.group(1)))).isoformat()
    return ""


def aria_numbers(art):
    """从 aria-label 里取互动数：'14 回复、10 转帖、174 点赞、32249 次观看'"""
    out = {"replies": None, "retweets": None, "likes": None}
    try:
        labels = art.locator("[aria-label]").evaluate_all("els=>els.map(e=>e.getAttribute('aria-label')||'')")
    except Exception:
        return out
    joined = " ".join(labels)
    for key, pat in (("replies", r"([\d,]+)\s*(?:条)?回复"),
                     ("retweets", r"([\d,]+)\s*(?:次)?转帖"),
                     ("likes", r"([\d,]+)\s*(?:次)?点赞")):
        m = None
        for lab in labels:
            m = re.search(pat, lab)
            if m:
                break
        if m:
            out[key] = int(m.group(1).replace(",", ""))
    return out


def collect_ids(page, user):
    page.goto(f"https://x.com/{user}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(random.randint(3500, 5500))
    rounds = max(8, (MAX_TWEETS + 3) // 4)   # 30 条需要比 7 条多滚几屏
    for _ in range(rounds):
        page.mouse.wheel(0, random.randint(800, 1400))
        page.wait_for_timeout(random.randint(1500, 3000))
    ids = []
    cutoff = (datetime.now() - timedelta(days=MAX_DAYS)).date()
    arts = page.locator("article")
    for i in range(arts.count()):
        author, tid, ttxt = canon_link(arts.nth(i))
        if not tid or (author or "").lower() != user.lower() or tid in ids:
            continue
        iso = parse_time_text(ttxt)
        if iso and date.fromisoformat(iso) < cutoff:   # 超过时间窗口（含置顶旧帖）跳过
            continue
        ids.append(tid)
        if len(ids) >= MAX_TWEETS:
            break
    return ids


def open_detail(page, tid, user):
    # 新版前端下 /i/web/status/<id> 会空白，必须用 /<账号>/status/<id>
    page.goto(f"https://x.com/{user}/status/{tid}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(random.randint(3500, 5000))


def article_for(page, tid):
    arts = page.locator("article")
    for i in range(arts.count()):
        _, aid, _ = canon_link(arts.nth(i))
        if aid == tid:
            return arts.nth(i)
    return arts.first if arts.count() else None


def read_article(art):
    d = {"text": "", "media": 0, "video": 0, "likes": None,
         "retweets": None, "replies": None, "time": "", "url": ""}
    _, tid, ttxt = canon_link(art)
    if tid:
        d["url"] = "https://x.com/i/status/" + tid
    d["time"] = parse_time_text(ttxt)
    d.update(aria_numbers(art))
    try:
        d["media"] = art.locator("img[src*='pbs.twimg.com/media']").count()
    except Exception:
        pass
    try:
        d["video"] = art.locator("video").count()
    except Exception:
        pass
    # 先尝试点开「显示更多」（X 用纯文字节点）
    try:
        art.evaluate("""el => {
          const t = ['显示更多','Show more','查看更多'];
          [...el.querySelectorAll('*')]
            .filter(e => e.children.length === 0 && t.includes(e.textContent.trim()))
            .forEach(e => { try { e.click(); } catch (_) {} });
        }""")
    except Exception:
        pass

    # 正文：新版正文是 div[dir=auto][lang]；引用推文时会有第二个
    texts = []
    try:
        loc = art.locator('div[dir="auto"][lang]')
        for i in range(min(loc.count(), 3)):
            try:
                v = loc.nth(i).inner_text(timeout=1500)
            except Exception:
                v = ""
            if v.strip():
                texts.append(v)
    except Exception:
        pass
    d["text"] = texts[0] if texts else ""
    d["quoted"] = len(texts) > 1
    return d


def thread_part_ids(page, root_id, user):
    ids = []
    arts = page.locator("article")
    for i in range(arts.count()):
        author, tid, _ = canon_link(arts.nth(i))
        if tid and (author or "").lower() == user.lower() and tid != root_id and tid not in ids:
            ids.append(tid)
    return ids[:MAX_THREAD - 1]


def completeness(tw, tombstone=False):
    f = []
    t = tw["text"].strip()
    if tombstone:
        f.append("subscriber_only")
    if not t:
        f.append("media_only" if (tw["media"] or tw["video"]) else "empty")
        return f
    if t.endswith("…") or t.endswith("..."):
        f.append("ellipsis_tail")
    if len(t) in (278, 279, 280):
        f.append("len_280")
    return f


def fetch_root(page, uid, user):
    open_detail(page, uid, user)
    body = page.inner_text("body")[:3000]
    tomb = ("Subscribers only" in body) or ("订阅者专属" in body) or ("訂閱者專屬" in body)

    part_ids = thread_part_ids(page, uid, user)
    parts = []

    art = article_for(page, uid)
    tw = read_article(art) if art else {"text": "", "media": 0, "video": 0,
                                        "likes": None, "retweets": None, "replies": None,
                                        "time": "", "url": ""}
    tw["id"] = uid
    tw["flags"] = completeness(tw, tomb)
    parts.append(tw)

    for pid in part_ids:
        open_detail(page, pid, user)
        a = article_for(page, pid)
        if not a:
            continue
        t2 = read_article(a)
        t2["id"] = pid
        t2["flags"] = completeness(t2, tomb)
        parts.append(t2)
        time.sleep(random.randint(2, 4))

    return parts


def parse_args(argv):
    """支持: python fetch.py [账号...] [--days 30] [--max 30] [--fresh]"""
    global MAX_DAYS, MAX_TWEETS, FRESH
    users, days_set, max_set = [], False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--days" and i + 1 < len(argv):
            MAX_DAYS = int(argv[i + 1]); days_set = True; i += 2
        elif a == "--max" and i + 1 < len(argv):
            MAX_TWEETS = int(argv[i + 1]); max_set = True; i += 2
        elif a == "--fresh":
            FRESH = True; i += 1
        elif a.startswith("--"):
            i += 1
        else:
            users.append(a); i += 1
    if days_set and not max_set:          # 未单独指定条数时，按天数给一个合理上限
        MAX_TWEETS = max(7, min(50, MAX_DAYS))
    return users or ACCOUNTS


ARCHIVE = os.path.join(OUTDIR, "fetch_inprogress.json")
FRESH = False


def load_resume(users):
    """读取存档：12 小时内可续跑。

    保留存档里的**全部**账号（不只是本次要抓的），避免只重试个别账号时
    把其他账号的数据从存档里挤掉。
    """
    if FRESH or not os.path.exists(ARCHIVE):
        return {}
    age = time.time() - os.path.getmtime(ARCHIVE)
    if age > 12 * 3600:
        stale = ARCHIVE.replace(".json", "_stale_%s.json" % datetime.now().strftime("%m%d_%H%M"))
        try:
            os.replace(ARCHIVE, stale)
        except Exception:
            pass
        log("存档超过 12 小时，已另存为", os.path.basename(stale))
        return {}
    try:
        d = json.load(open(ARCHIVE, encoding="utf-8"))
    except Exception:
        return {}
    done = {u: v for u, v in d.items() if v}
    skipped = [u for u in users if u in done]
    if skipped:
        log("断点续跑：已跳过", ", ".join("@" + u for u in skipped))
    return done


def main():
    users = parse_args(sys.argv[1:])
    log(f"抓取口径：最近 {MAX_DAYS} 天，每账号最多 {MAX_TWEETS} 条")
    result = load_resume(users)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            viewport={"width": 1280, "height": 1200},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for u in users:
            if result.get(u):
                log(f"\n=== @{u} 已在存档中，跳过")
                continue
            log(f"\n=== @{u}")
            try:
                ids = collect_ids(page, u)
            except Exception as e:
                log("  收集 ID 失败:", str(e)[:80]); result[u] = []; continue
            log(f"  时间线取到 {len(ids)} 条")
            items = []
            for uid in ids:
                try:
                    parts = fetch_root(page, uid, u)
                    items.append({"root_id": uid, "parts": parts})
                    bad = sum(1 for x in parts if x["flags"])
                    log(f"   - {uid}  {len(parts)} 段" + (f"  [!] {bad} 段异常" if bad else "  OK"))
                except Exception as e:
                    log(f"   - {uid}  ERROR {str(e)[:70]}")
                time.sleep(random.randint(2, 4))
            result[u] = items
            # 每完成一个账号就落盘，避免中断导致前面的抓取白费
            try:
                json.dump(result, open(ARCHIVE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                log(f"  [存档] 已保存 {len(result)} 个账号")
            except Exception as e:
                log("  存档失败:", str(e)[:60])
        ctx.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(OUTDIR, f"fetch_{stamp}.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    log("\n" + "=" * 46)
    log("完整性报告")
    log("=" * 46)
    total = ok = 0
    issues = []
    for u, items in result.items():
        for it in items:
            for pt in it["parts"]:
                total += 1
                if pt["flags"]:
                    issues.append((u, pt["id"], pt["flags"], len(pt["text"])))
                else:
                    ok += 1
    for u, tid, fl, ln in issues:
        log(f"  [!] @{u} {tid}  {','.join(fl)}  ({ln} 字)")
    log(f"\n共 {total} 段，完整 {ok} 段，异常 {total - ok} 段")
    log("保存:", path)
    if issues:
        log("\n有异常条目，需要人工确认后再翻译。")


if __name__ == "__main__":
    main()
