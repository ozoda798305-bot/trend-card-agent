"""네이버 데이터랩 「검색어 트렌드」 API를 불러 키워드의 주간 검색량 지수를 받는다.

사용법
  python3 naver_datalab.py 두바이초콜릿 말차 크루키 요아정 탕후루 --weeks 12 --out ../04_자료/naver_datalab_sample.csv
  (.env 에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 이 있어야 실제로 호출한다.
   키가 없으면 요청 본문만 조립해 보여 주고 종료 코드 2로 끝난다.)

API 설명: https://developers.naver.com/docs/serviceapi/datalab/search/search.md
 - POST https://openapi.naver.com/v1/datalab/search
 - 헤더: X-Naver-Client-Id, X-Naver-Client-Secret, Content-Type: application/json
 - 본문: startDate, endDate, timeUnit(date|week|month), keywordGroups(최대 5개 그룹, 그룹당 키워드 최대 20개)
 - 응답: results[].data[] 의 period(그 주 시작일)·ratio(요청 구간 안 최대값을 100으로 둔 상대 지수)
 - 한도: 하루 1,000회(무료)

주의: ratio 는 요청 구간 안에서 정규화된 상대 지수다. 같은 요청에 넣은 키워드끼리만 비교할 수 있고,
      다른 요청에서 받은 값과 섞어 비교하면 틀린다. 그래서 5개 키워드를 한 요청에 넣는다.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, datetime as dt
from pathlib import Path

API_URL = "https://openapi.naver.com/v1/datalab/search"


def load_env(path: Path) -> dict:
    """.env 파일을 읽어 dict 로 돌려준다(없으면 빈 dict). 외부 패키지 없이 처리한다."""
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def build_request(keywords: list[str], weeks: int, end: dt.date | None = None) -> dict:
    """API 요청 본문을 만든다. 키워드 5개까지, 주 단위, 최근 weeks 주."""
    if not 1 <= len(keywords) <= 5:
        raise ValueError("키워드는 1개 이상 5개 이하로 넣는다(데이터랩 한 요청의 그룹 한도)")
    end = end or dt.date.today()
    start = end - dt.timedelta(weeks=weeks)
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "week",
        "keywordGroups": [{"groupName": k, "keywords": [k]} for k in keywords],
    }


def parse_response(payload: dict) -> list[dict]:
    """응답 JSON을 행 목록(keyword, period, ratio)으로 편다."""
    rows = []
    for g in payload.get("results", []):
        name = g.get("title") or (g.get("keywords") or [""])[0]
        for p in g.get("data", []):
            rows.append({"keyword": name, "period": p["period"], "ratio": float(p["ratio"])})
    return rows


def call_api(body: dict, client_id: str, client_secret: str, timeout: int = 15) -> dict:
    import requests  # 키가 있을 때만 필요하므로 여기서 불러온다
    r = requests.post(
        API_URL,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
        },
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"네이버 데이터랩 HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["keyword", "period", "ratio"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keywords", nargs="+", help="키워드 1~5개")
    ap.add_argument("--weeks", type=int, default=12, help="최근 몇 주를 받을지(기본 12)")
    ap.add_argument("--out", default="../04_자료/naver_datalab_sample.csv")
    ap.add_argument("--dry-run", action="store_true", help="요청 본문만 출력")
    a = ap.parse_args()

    body = build_request(a.keywords, a.weeks)
    env = load_env(Path(__file__).with_name(".env"))
    cid, csec = env.get("NAVER_CLIENT_ID", ""), env.get("NAVER_CLIENT_SECRET", "")
    if a.dry_run or not (cid and csec):
        print("[요청 본문] POST", API_URL)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if not a.dry_run:
            print("\nNAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 .env 에 없어 호출하지 않았다. "
                  ".env.example 을 보고 키를 넣으면 같은 명령으로 실제 자료가 저장된다.", file=sys.stderr)
            return 2
        return 0
    payload = call_api(body, cid, csec)
    rows = parse_response(payload)
    out = Path(__file__).parent / a.out
    write_csv(rows, out)
    print(f"저장: {out} ({len(rows)}행, 키워드 {len(a.keywords)}개, {a.weeks}주)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
