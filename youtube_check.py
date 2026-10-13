"""유튜브로 후보 표현을 검증하고(A), 신조어 풀이 영상을 모은다(B). YouTube Data API v3(공식, 무료 한도 하루 10,000단위)를 쓴다.

A. 검증  python3 youtube_check.py verify 좌아하게 줴줴이야 먼작귀
   표현마다 「<표현> 뜻」으로 최근 N일 영상을 검색해, 제목에 표현과 풀이어(뜻·의미·신조어·밈·줄임말)가
   함께 들어간 「풀이 영상」 수와 조회수 합계를 센다. 결과는 04_자료/유튜브_검증.csv
B. 수집  python3 youtube_check.py explainers
   「요즘 신조어 뜻」 같은 풀이 영상을 최근 N일로 모아 제목·설명·주소를 저장한다(04_자료/유튜브_풀이영상.json).
   제목의 「OO 뜻」 꼴에서 표현 후보도 뽑아 둔다. 뜻 풀이는 참고 자료이며 카드에 넣기 전 사람이 대조한다.

키: .env 의 YOUTUBE_API_KEY. 키가 없으면 요청 주소만 보여 주고 종료 코드 2로 끝난다.
할당량: search.list 1회 100단위, videos.list 1회 1단위. 표현 5개 검증 ≈ 505단위.
판정(A): 풀이 영상 5개 이상 → 사용 확인 / 1~4개 → 약함(사람 판단) / 0개 → 쓰임 없음. 기준은 돌려 보고 조정한다.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, re, sys
from pathlib import Path
from naver_datalab import load_env

SEARCH = "https://www.googleapis.com/youtube/v3/search"
VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
EXPLAIN_WORDS = ("뜻", "의미", "신조어", "밈", "줄임말", "유행어")
EXPLAINER_QUERIES = ["요즘 신조어 뜻", "MZ 신조어 뜻", "신조어 퀴즈", "유행어 뜻 정리"]
ISO_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def seconds(iso: str) -> int:
    m = ISO_DUR.fullmatch(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def search(q: str, key: str, days: int, max_results: int = 25) -> list[dict]:
    import requests
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(SEARCH, params={"part": "snippet", "q": q, "type": "video", "publishedAfter": after,
                                     "regionCode": "KR", "relevanceLanguage": "ko", "maxResults": max_results,
                                     "order": "relevance", "key": key}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"search HTTP {r.status_code}: {r.text[:200]}")
    items = r.json().get("items", [])
    ids = [it["id"]["videoId"] for it in items]
    stats = {}
    if ids:
        v = requests.get(VIDEOS, params={"part": "statistics,contentDetails", "id": ",".join(ids), "key": key}, timeout=15)
        if v.status_code != 200:
            raise RuntimeError(f"videos HTTP {v.status_code}: {v.text[:200]}")
        for it in v.json().get("items", []):
            stats[it["id"]] = (int(it.get("statistics", {}).get("viewCount", 0)), seconds(it["contentDetails"].get("duration", "")))
    out = []
    for it in items:
        vid, sn = it["id"]["videoId"], it["snippet"]
        views, secs = stats.get(vid, (0, 0))
        out.append({"video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": sn.get("title", ""),
                    "description": sn.get("description", ""), "channel": sn.get("channelTitle", ""),
                    "published": sn.get("publishedAt", "")[:10], "views": views, "seconds": secs,
                    "short": 0 < secs <= 180})
    return out


def verify(exprs: list[str], key: str, days: int, out: Path) -> None:
    rows = []
    for e in exprs:
        vids = search(f"{e} 뜻", key, days)
        hits = [v for v in vids if nospace(e) in nospace(v["title"]) and any(w in v["title"] for w in EXPLAIN_WORDS)]
        n = len(hits)
        verdict = "사용 확인" if n >= 5 else ("약함(사람 판단)" if n >= 1 else "쓰임 없음")
        top = max(hits, key=lambda v: v["views"]) if hits else None
        rows.append({"expression": e, "explainer_videos": n, "shorts": sum(v["short"] for v in hits),
                     "views_total": sum(v["views"] for v in hits), "verdict": verdict,
                     "top_title": top["title"] if top else "", "top_url": top["url"] if top else ""})
        print(f"{e:<10} 풀이 영상 {n:>2}개  조회수 {rows[-1]['views_total']:>9,}  → {verdict}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("저장:", out)


def explainers(key: str, days: int, out: Path) -> None:
    seen, cands = {}, {}
    for q in EXPLAINER_QUERIES:
        for v in search(q, key, days):
            seen.setdefault(v["video_id"], v)
    pat = re.compile(r"['‘\"“]?([가-힣A-Za-z0-9 ]{1,10}?)['’\"”]?\s*(?:뜻|의미)")
    for v in seen.values():
        for m in pat.finditer(v["title"]):
            ex = m.group(1).strip()
            if ex and ex not in ("신조어", "유행어", "요즘", "MZ", "줄임말"):
                cands.setdefault(ex, []).append(v["url"])
    data = {"fetched_at": dt.datetime.now().isoformat(timespec="minutes"), "days": days, "queries": EXPLAINER_QUERIES,
            "videos": sorted(seen.values(), key=lambda v: -v["views"]),
            "candidates_from_titles": [{"expression": k, "videos": len(u), "urls": u[:3]} for k, u in sorted(cands.items(), key=lambda x: -len(x[1]))]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"풀이 영상 {len(seen)}개, 제목에서 뽑은 후보 {len(cands)}개")
    for c in data["candidates_from_titles"][:15]:
        print(f"  {c['expression']:<10} 영상 {c['videos']}개")
    print("저장:", out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["verify", "explainers"])
    ap.add_argument("expressions", nargs="*")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    key = load_env(Path(__file__).with_name(".env") if Path(__file__).with_name(".env").exists() else Path(__file__).parent.parent / ".env").get("YOUTUBE_API_KEY", "") or ""
    if not key:
        import os
        key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        q = (a.expressions[0] + " 뜻") if a.expressions else EXPLAINER_QUERIES[0]
        print(f"YOUTUBE_API_KEY 가 .env 에 없어 호출하지 않았다. 요청 예: GET {SEARCH}?part=snippet&type=video&q={q}&publishedAfter=<{a.days}일 전>", file=sys.stderr)
        return 2
    base = Path(__file__).parent / "04_자료"
    try:
        if a.mode == "verify":
            if not a.expressions:
                print("검증할 표현을 1개 이상 넣는다", file=sys.stderr); return 1
            verify(a.expressions, key, a.days, Path(a.out) if a.out else base / "유튜브_검증.csv")
        else:
            explainers(key, a.days, Path(a.out) if a.out else base / "유튜브_풀이영상.json")
    except RuntimeError as e:
        print("유튜브 호출 실패:", e, file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
