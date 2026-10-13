"""「뜨기 전」 판정 함수. 검색량 지수(네이버 데이터랩 또는 구글 트렌드)와 블로그 발행량으로 네 단계 가운데 하나를 돌려준다.

판정 규칙(숫자의 근거는 01_제안서.md 4절과 04_자료/벤치마크_지표_비교표.md)
  search_growth = 최근 4주 검색량 지수 평균 / 직전 4주 평균 - 1       (예: 0.5 = +50%)
  blog_growth   = 최근 4주 블로그 발행 글 수 / 직전 4주 글 수 - 1
  base_ok       = 직전 4주 평균 지수가 1.0 이상 (0에 가까운 값으로 나눈 배수는 뜻이 없다. Trend-hub naver.ts BASE_MIN 과 같다)

  단계                 조건
  자료 부족            주간 자료가 8주 미만, 또는 직전 4주 평균 < 1.0 이면서 최근 4주 평균도 < 5.0
  신규 출현(new)       직전 4주 평균 < 1.0 인데 최근 4주 평균 ≥ 5.0 (검색이 없다가 생김. 배수는 계산하지 않고 따로 표시)
  뜨기 전(before)      검색 +50% 이상  AND  블로그 증가율 < 검색 증가율  AND  검색 +300% 미만
  이미 뜸(peaked)      검색 +100% 이상 AND  블로그 +100% 이상           또는 검색 +300% 이상(네이버 급등 상한·Trend-hub 3배 기준)
  오르는 중(rising)    검색 +20% 이상 +50% 미만(어느 쪽도 아님)
  평소(flat)           검색 +20% 미만(감소 포함)

단위 테스트: python3 -m pytest tests/ 또는 python3 tests/test_judge.py
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from statistics import mean

BASE_MIN = 1.0          # 직전 4주 평균 지수가 이보다 작으면 배수를 내지 않는다(Trend-hub lib/collect/naver.ts BASE_MIN=1.0)
BEFORE_MIN = 0.50       # 뜨기 전: 검색 +50% 이상(Exploding Topics 가 「Regular」와 「Exploding」을 가르는 성장률 구간, Trend-hub 「오르는 편」 1.5배)
PEAK_SEARCH = 1.00      # 이미 뜸: 검색 +100% 이상이면서
PEAK_BLOG = 1.00        #         블로그도 +100% 이상(공급이 수요를 따라잡음)
CAP_SEARCH = 3.00       # 검색 +300%(=4배) 이상은 단독으로 이미 뜸(Trend-hub 「지금 오르는」 3배, 구글 트렌드 Breakout 은 +5000%라 그보다 훨씬 낮게 둔다)
NEW_MIN = 5.0           # 신규 출현: 직전 4주가 사실상 0인데 최근 4주 평균 지수가 이 값 이상(구글 트렌드 개별 요청에서 크루키가 0→29로 나온 사례)
RISING_MIN = 0.20       # 오르는 중: +20% 이상(Trend-hub 는 1.5배 미만을 「평소」로 보지만 주간 자료는 잡음이 커서 한 단계 더 둔다)


@dataclass
class Verdict:
    keyword: str
    stage: str               # before | peaked | rising | flat | insufficient
    search_growth: float | None
    blog_growth: float | None
    recent_mean: float | None
    base_mean: float | None
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def growth(recent: list[float], base: list[float]) -> float | None:
    """(최근 평균 / 직전 평균) - 1. 직전 평균이 BASE_MIN 미만이면 None."""
    if not recent or not base:
        return None
    b = mean(base)
    if b < BASE_MIN:
        return None
    return mean(recent) / b - 1.0


def judge(keyword: str, weekly_search: list[float], blog_recent: int | None = None, blog_prev: int | None = None,
          window: int = 4) -> Verdict:
    """weekly_search: 오래된 주부터 최근 주 순서의 주간 검색량 지수(8주 이상).
    blog_recent / blog_prev: 최근 4주·직전 4주 블로그 발행 글 수(없으면 None → 블로그 축 없이 판정, 단계 이름에 표시)."""
    if len(weekly_search) < 2 * window:
        return Verdict(keyword, "insufficient", None, None, None, None, f"주간 자료가 {len(weekly_search)}주로 {2*window}주보다 적다")
    recent, base = weekly_search[-window:], weekly_search[-2 * window:-window]
    rm, bm = mean(recent), mean(base)
    sg = growth(recent, base)
    if sg is None:
        if rm >= NEW_MIN:
            return Verdict(keyword, "new", None, None, rm, bm, f"직전 {window}주 평균 {bm:.2f}로 검색이 사실상 없다가 최근 {window}주 평균 {rm:.1f}로 나타남(배수 계산 불가, 블로그 수로 확인 필요)")
        return Verdict(keyword, "insufficient", None, None, rm, bm, f"직전 {window}주 평균 지수 {bm:.2f}가 {BASE_MIN} 미만이라 배수를 낼 수 없다")
    bg = None
    if blog_recent is not None and blog_prev is not None and blog_prev > 0:
        bg = blog_recent / blog_prev - 1.0

    pct = lambda x: f"{x*100:+.0f}%"
    if sg >= CAP_SEARCH:
        return Verdict(keyword, "peaked", sg, bg, rm, bm, f"검색 {pct(sg)}로 +{CAP_SEARCH*100:.0f}% 상한을 넘어 이미 널리 퍼진 상태")
    if bg is not None and sg >= PEAK_SEARCH and bg >= PEAK_BLOG:
        return Verdict(keyword, "peaked", sg, bg, rm, bm, f"검색 {pct(sg)}·블로그 {pct(bg)} 모두 +100% 이상, 공급이 수요를 따라잡음")
    if sg >= BEFORE_MIN and (bg is None or bg < sg):
        why = f"검색 {pct(sg)}, 블로그 {pct(bg) if bg is not None else '자료 없음'}: 찾는 사람은 늘었는데 글은 그만큼 늘지 않았다"
        return Verdict(keyword, "before" if bg is not None else "before(블로그 미확인)", sg, bg, rm, bm, why)
    if sg >= BEFORE_MIN:
        return Verdict(keyword, "rising", sg, bg, rm, bm, f"검색 {pct(sg)}이지만 블로그 {pct(bg)}가 검색보다 빨라 선점 여지가 작다")
    if sg >= RISING_MIN:
        return Verdict(keyword, "rising", sg, bg, rm, bm, f"검색 {pct(sg)}로 +{BEFORE_MIN*100:.0f}% 기준에 못 미침")
    return Verdict(keyword, "flat", sg, bg, rm, bm, f"검색 {pct(sg)}, 평소 수준")


def to_weekly(pts: list[tuple[str, float]]) -> list[float]:
    """(날짜, 값) 목록이 일 단위(구글 트렌드 3개월은 일 단위로 온다)이면 마지막 날부터 거슬러 7일씩 묶어 주 평균을 만든다.
    이미 주 단위(간격 7일)이면 값만 돌려준다. 7일을 채우지 못한 맨 앞 토막은 버린다."""
    import datetime as dt
    pts = sorted(pts)
    if len(pts) < 2:
        return [v for _, v in pts]
    d0, d1 = dt.date.fromisoformat(pts[0][0]), dt.date.fromisoformat(pts[1][0])
    if (d1 - d0).days >= 7:
        return [v for _, v in pts]
    vals = [v for _, v in pts]
    weeks = []
    for end in range(len(vals), 6, -7):
        weeks.append(mean(vals[end - 7:end]))
    return list(reversed(weeks))


def judge_from_rows(rows: list[dict], blog: dict[str, tuple[int, int]] | None = None, window: int = 4) -> list[Verdict]:
    """naver_datalab.py / google_trends.py 가 저장한 CSV 행(keyword, period, ratio)을 받아 키워드마다 판정한다.
    일 단위 자료는 to_weekly 로 주 평균으로 바꾼 뒤 판정한다."""
    by: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        by.setdefault(r["keyword"], []).append((r["period"], float(r["ratio"])))
    out = []
    for k, pts in by.items():
        series = to_weekly(pts)
        br, bp = (blog or {}).get(k, (None, None))
        out.append(judge(k, series, br, bp, window))
    return out


if __name__ == "__main__":
    import argparse, csv, json, sys
    ap = argparse.ArgumentParser(description="CSV(keyword, period, ratio)를 읽어 판정 결과를 JSON 으로 출력")
    ap.add_argument("csv")
    ap.add_argument("--blog", help="블로그 발행량 CSV(keyword, recent_4w, prev_4w)", default=None)
    ap.add_argument("--window", type=int, default=4)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    blog = None
    if a.blog:
        blog = {r["keyword"]: (int(r["recent_4w"]), int(r["prev_4w"])) for r in csv.DictReader(open(a.blog, encoding="utf-8-sig"))}
    res = [v.as_dict() for v in judge_from_rows(rows, blog, a.window)]
    json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
    print()
