"""구글 트렌드 「관련 검색어 → 급상승」에서 요즘 뜨는 표현 후보를 찾는다.

씨앗 검색어(기본: 뜻, 신조어, 밈, 줄임말)마다 대한민국·지난 30일의 급상승 관련 검색어를 받아,
끝의 "뜻", "의미", "밈" 같은 말을 떼고 표현만 남긴 뒤 CSV 로 저장한다.
이 CSV 의 표현을 사람이(또는 AI가) 걸러 naver_datalab.py → naver_blog_count.py → judge.py 로 넘긴다.

사용법
  python3 find_candidates.py
  python3 find_candidates.py 뜻 신조어 --timeframe "today 1-m" --out 04_자료/후보_구글트렌드.csv

주의
 - pytrends 는 구글이 공식으로 지원하지 않는 라이브러리다. 429(요청이 너무 많음)로 막히면 종료 코드 3으로 끝난다.
   몇 분 뒤 다시 하거나 하루 한 번만 돌린다.
 - 결과에는 일반 단어·외국어·사람 이름·혐오 표현이 섞인다. 자동 걸러내기는 형태만 보고, 뜻은 사람이 판단한다.
"""
from __future__ import annotations
import argparse, csv, re, sys, time, datetime as dt
from pathlib import Path

TAIL = re.compile(r"\s*(뜻|의미|밈|meaning|뜻은|무슨\s*뜻|이란|이 뭐야|가 뭐야)\s*$")
HANGUL = re.compile(r"[가-힣]")


def clean(query: str, seed: str) -> str:
    """'부캉 이 뜻' -> '부캉 이'. 씨앗 검색어 자체와 꼬리말을 뗀다."""
    q = query.strip()
    for _ in range(2):
        q = TAIL.sub("", q).strip()
    if q.startswith(seed + " "):
        q = q[len(seed) + 1:].strip()
    if q.endswith(" " + seed):
        q = q[: -len(seed) - 1].strip()
    return q


def shape_ok(expr: str) -> tuple[bool, str]:
    """모양만 보는 1차 거르기. 뜻이 맞는지는 판단하지 않는다."""
    if not expr:
        return False, "빈 값"
    if not HANGUL.search(expr):
        return False, "한글 없음(외국어·숫자)"
    if len(expr.replace(" ", "")) > 12:
        return False, "12자 초과(문장·질문)"
    if any(w in expr for w in ("사용", "문제점", "이유", "모음", "사전", "테스트", "그래프")):
        return False, "분야 설명어(표현 아님)"
    return True, ""


def fetch(seeds: list[str], timeframe: str, geo: str = "KR") -> list[dict]:
    from pytrends.request import TrendReq
    tr = TrendReq(hl="ko-KR", tz=540, timeout=(10, 30))  # retries 를 쓰면 urllib3 2.x 와 충돌한다
    rows = []
    for i, seed in enumerate(seeds):
        if i:
            time.sleep(15)  # 연속 요청으로 막히지 않게 쉰다
        try:
            tr.build_payload([seed], timeframe=timeframe, geo=geo)
            rq = tr.related_queries().get(seed, {}) or {}
        except Exception as e:  # 한 씨앗이 막혀도 받은 것까지는 저장한다
            print(f"  [{seed}] 실패: {str(e)[:120]}", file=sys.stderr)
            if not rows and i == len(seeds) - 1:
                raise
            continue
        rising = rq.get("rising")
        if rising is not None:
            for _, r in rising.iterrows():
                rows.append({"seed": seed, "query": str(r["query"]), "value": r["value"]})
    if not rows:
        raise RuntimeError("모든 씨앗 검색어에서 결과를 받지 못했다")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seeds", nargs="*", default=["뜻", "신조어", "밈", "줄임말"])
    ap.add_argument("--timeframe", default="today 1-m", help='"now 7-d", "today 1-m", "today 3-m" 등')
    ap.add_argument("--geo", default="KR")
    ap.add_argument("--out", default="04_자료/후보_구글트렌드.csv")
    a = ap.parse_args()
    try:
        rows = fetch(a.seeds, a.timeframe, a.geo)
    except Exception as e:
        msg = str(e)
        print(f"구글 트렌드 호출 실패: {msg[:300]}", file=sys.stderr)
        return 3 if "429" in msg or "Too Many" in msg else 1

    seen: dict[str, dict] = {}
    for r in rows:
        expr = clean(r["query"], r["seed"])
        ok, why = shape_ok(expr)
        key = expr.replace(" ", "")
        v = r["value"]
        num = 10**9 if str(v).lower() in ("breakout",) else (int(v) if str(v).isdigit() else 0)
        prev = seen.get(key)
        if prev is None or num > prev["_num"]:
            seen[key] = {"expression": expr, "original_query": r["query"], "seed": r["seed"],
                         "rising": "급등" if num == 10**9 else f"+{num}%", "keep": "Y" if ok else "N",
                         "drop_reason": why, "_num": num}
    out_rows = sorted(seen.values(), key=lambda x: (x["keep"] != "Y", -x["_num"]))
    out = Path(__file__).parent / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["expression", "original_query", "seed", "rising", "keep", "drop_reason"]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(out_rows)
    kept = [r for r in out_rows if r["keep"] == "Y"]
    print(f"받은 시각 {dt.datetime.now():%Y-%m-%d %H:%M}, 급상승 {len(rows)}건 → 표현 {len(out_rows)}개 (1차 통과 {len(kept)}개)")
    for r in kept[:15]:
        print(f"  {r['expression']:<12} {r['rising']:>8}  ({r['seed']}: {r['original_query']})")
    print("저장:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
