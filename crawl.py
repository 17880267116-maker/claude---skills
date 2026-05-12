"""
social-crawler — 小红书博主定向数据爬取

筛选维度：
  --days 30        最近 N 天
  --max 10         最多 N 条
  --min-likes 100  最低点赞数
  --type video     笔记类型 (video/normal/all)

输出：CSV（Excel 可开），含标题/文案/点赞/评论/收藏/转发/时间/链接

依赖：blogger-distiller 项目中的 TikHubClient
"""

import sys, os, json, time, argparse, csv
from datetime import datetime, timedelta

# 找到 blogger-distiller 的 scripts 目录
_BASE = os.path.dirname(os.path.abspath(__file__))
_BLOGGER_DISTILLER = os.path.join(os.path.expanduser("~"), "blogger-distiller", "scripts")
sys.path.insert(0, _BLOGGER_DISTILLER)

from utils.tikhub_client import TikHubClient, TikHubError
from utils.common import parse_count, safe_filename


# ────────────────────────────── 时间解析 ──────────────────────────────

def parse_note_time(note_obj):
    raw = (
        note_obj.get("time") or note_obj.get("timestamp")
        or note_obj.get("createTime") or note_obj.get("create_time")
        or note_obj.get("publishTime") or note_obj.get("publish_time")
        or note_obj.get("uploadTime") or note_obj.get("upload_time")
    )
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if raw > 1e12:
            raw /= 1000
        try:
            return datetime.fromtimestamp(raw)
        except (ValueError, OSError):
            pass
    if isinstance(raw, str):
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                     "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"]:
            try:
                return datetime.strptime(raw.strip(), fmt)
            except ValueError:
                continue
    return None


# ────────────────────────────── 搜索博主 ──────────────────────────────

def find_blogger(client, keyword):
    """通过搜索用户接口定位博主，返回 (user_id, nickname)"""
    from crawl_blogger import find_blogger as _fb
    uid, nick, _ = _fb(client, keyword)
    return uid, nick


# ────────────────────────────── 主页笔记列表 ──────────────────────────────

def fetch_notes_list(client, user_id, max_pages=5):
    """拉取主页笔记列表（不含详情），分页获取"""
    notes = {}
    cursor = ""
    page = 0

    while page < max_pages:
        try:
            raw = client.fetch_user_notes(user_id, cursor=cursor)
        except TikHubError as e:
            print(f"  ⚠️ 第{page+1}页失败: {e}")
            break

        data = raw.get("data", raw)
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        items = data.get("notes") or data.get("items") or data.get("feeds") or []
        last_cursor = ""

        for item in items:
            nid = item.get("id") or item.get("note_id") or item.get("noteId") or ""
            if not nid or nid in notes:
                continue

            interact = item.get("interactInfo") or item.get("interact_info") or {}
            notes[nid] = {
                "id": nid,
                "title": item.get("display_title") or item.get("displayTitle") or item.get("title") or "",
                "type": item.get("type") or "",
                "likedCount": parse_count(interact.get("likedCount") or interact.get("liked_count") or 0),
                "xsecToken": item.get("xsec_token") or item.get("xsecToken") or "",
                "time": parse_note_time(item),
            }
            c = item.get("cursor") or ""
            if c:
                last_cursor = c

        has_more = data.get("has_more") or data.get("hasMore") or False
        next_cursor = last_cursor or data.get("cursor") or data.get("lastCursor") or ""
        print(f"  第{page+1}页: +{len(items)} 条 (累计 {len(notes)} 条)")

        if not has_more or not next_cursor or not items:
            break
        cursor = next_cursor
        page += 1
        time.sleep(0.5)

    return list(notes.values())


# ────────────────────────────── 逐条详情 ──────────────────────────────

def fetch_details(client, notes, days=30, min_likes=0):
    """
    逐条获取笔记详情 → 时间过滤 → 互动阈值过滤。
    返回 [{title, desc, likes, comments, collects, shares, time, note_id, url}, ...]
    """
    cutoff = datetime.now() - timedelta(days=days) if days > 0 else None
    results = []

    print(f"\n📖 获取详情...")
    for i, note in enumerate(notes):
        nid = note["id"]
        title_short = (note.get("title") or "无标题")[:30]
        print(f"  [{i+1:3d}/{len(notes)}] {title_short}...", end="", flush=True)

        try:
            raw = client.fetch_note_detail(nid, xsec_token=note.get("xsecToken", ""),
                                           note_type=note.get("type", ""))

            detail = raw.get("data", raw)
            if isinstance(detail, dict) and "data" in detail:
                detail = detail["data"]
            if isinstance(detail, list):
                detail = detail[0] if detail else {}

            note_obj = {}
            items_raw = detail.get("items") or []
            if isinstance(items_raw, list) and items_raw:
                note_obj = items_raw[0].get("noteCard") or items_raw[0].get("note") or {}
            if not note_obj:
                nl = detail.get("note_list") or []
                note_obj = (nl[0] if nl else {})
            if not note_obj:
                note_obj = detail.get("note") or detail.get("noteData") or {}
            if not note_obj and (detail.get("noteId") or detail.get("desc")):
                note_obj = detail

            if not note_obj:
                print(f" ⚠️ 空")
                continue

            # ── 时间 ──
            t = parse_note_time(note_obj) or note.get("time")
            if cutoff and t and t < cutoff:
                print(f" ⏭️ 过旧 ({t.strftime('%m-%d')})")
                continue

            # ── 互动 ──
            interact = note_obj.get("interactInfo") or note_obj.get("interact_info") or {}
            likes = parse_count(
                note_obj.get("likedCount") or note_obj.get("liked_count")
                or interact.get("likedCount") or interact.get("liked_count") or 0
            )
            comments = parse_count(
                interact.get("commentCount") or interact.get("comment_count")
                or note_obj.get("commentCount") or note_obj.get("comment_count") or 0
            )
            collects = parse_count(
                note_obj.get("collectedCount") or note_obj.get("collected_count")
                or interact.get("collectedCount") or interact.get("collected_count") or 0
            )
            shares = parse_count(
                interact.get("shareCount") or interact.get("share_count")
                or note_obj.get("shareCount") or note_obj.get("share_count") or 0
            )

            if likes < min_likes:
                print(f" ⏭️ 赞不足 ({likes}<{min_likes})")
                continue

            # ── 标题/文案 ──
            title = (
                note_obj.get("displayTitle") or note_obj.get("display_title")
                or note_obj.get("title") or note.get("title", "")
            )
            desc = note_obj.get("desc") or note_obj.get("description") or note_obj.get("content") or ""

            results.append({
                "title": title,
                "desc": desc,
                "likes": likes,
                "comments": comments,
                "collects": collects,
                "shares": shares,
                "time": t.strftime("%Y-%m-%d %H:%M") if t else "未知",
                "note_id": nid,
                "url": f"https://www.xiaohongshu.com/explore/{nid}",
            })

            print(f" ✅ L:{likes} C:{comments} S:{collects}")

        except Exception as e:
            print(f" ❌ {str(e)[:40]}")

        time.sleep(0.3)

    return results


# ────────────────────────────── 主入口 ──────────────────────────────

def crawl(blogger, days=30, max_count=0, min_likes=0, note_type="video", output_dir="."):
    client = TikHubClient()

    # 1. 定位博主
    user_id, nickname = find_blogger(client, blogger)
    safe_name = safe_filename(nickname)

    # 2. 拉主页
    all_notes = fetch_notes_list(client, user_id)

    # 3. 类型预过滤（减少详情调用）
    if note_type != "all":
        all_notes = [n for n in all_notes if n["type"] == note_type]
        print(f"🔍 类型过滤({note_type}): {len(all_notes)} 条")

    # 4. 详情 + 时间 + 互动阈值过滤
    results = fetch_details(client, all_notes, days=days, min_likes=min_likes)

    # 5. 条数截断
    if max_count and len(results) > max_count:
        results = results[:max_count]
        print(f"📐 截取前 {max_count} 条")

    # 6. 输出 CSV
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, f"{safe_name}_crawl.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "title", "desc", "likes", "comments", "collects", "shares",
            "time", "note_id", "url"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'='*60}")
    print(f"💾 {csv_path}")
    print(f"   {len(results)} 条 | 博主: {nickname} | 时间: {results[-1]['time'] if results else '—'} ~ {results[0]['time'] if results else '—'}")

    if results:
        print(f"   点赞: {min(r['likes'] for r in results)} ~ {max(r['likes'] for r in results)}")

    # JSON 备份
    json_path = csv_path.replace(".csv", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书博主定向数据爬取")
    parser.add_argument("blogger", help="博主名")
    parser.add_argument("--days", type=int, default=30, help="最近N天 (默认30)")
    parser.add_argument("--max", type=int, default=0, help="最多N条 (0=不限)")
    parser.add_argument("--min-likes", type=int, default=0, help="最低点赞数")
    parser.add_argument("--type", choices=["video", "normal", "all"], default="video", help="笔记类型")
    parser.add_argument("--output", "-o", default="./data", help="输出目录")
    args = parser.parse_args()

    print(f"\n🎯 {args.blogger} | {args.days}天内 | 类型:{args.type} | "
          f"条数:{args.max if args.max else '不限'} | 最低赞:{args.min_likes}")
    print(f"{'='*60}")

    crawl(args.blogger, days=args.days, max_count=args.max,
          min_likes=args.min_likes, note_type=args.type, output_dir=args.output)
