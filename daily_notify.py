"""아침 자동 실행이 끝나면 「오늘의 후보」 알림을 만든다(GitHub 이슈 → GitHub 가 운영자 이메일로 보낸다).

사용법  python3 daily_notify.py <run 폴더> <제목 파일> <본문 파일>
알림에는 후보 표와 웹 앱 링크만 넣는다. 확인·승인은 카드 7장을 보고 웹 앱에서 한다(메일로 승인하지 않는다).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

APP_URL = "https://todays-korean.streamlit.app"
OWNER = "@ozoda798305-bot"  # 멘션하면 GitHub 가 이메일 알림을 확실히 보낸다


def main() -> int:
    run_dir, title_out, body_out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    items = json.loads((run_dir / "03_AI검수.json").read_text(encoding="utf-8"))["items"]
    order = {"통과": 0, "사람 확인": 1, "빼기": 2}
    items.sort(key=lambda c: (order.get(c.get("decision"), 3), -c.get("explainer_videos", 0), -c.get("views_total", 0)))
    ok = [c for c in items if c.get("decision") == "통과"]
    check = [c for c in items if c.get("decision") == "사람 확인"]
    name = lambda c: c.get("clean") or c["expression"]
    day = run_dir.name.split("_")[1]
    day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    head = f"통과 {len(ok)}개" + (f" · 1위 {name(ok[0])}" if ok else "") + (f" · 사람 확인 {len(check)}개" if check else "")
    title_out.write_text(f"🟨 오늘의 후보 {day} – {head}", encoding="utf-8")
    rows = ["| 표현 | 유튜브 풀이 영상 | 조회수 | 검증 | AI 검수 | 이유 |", "|---|---|---|---|---|---|"]
    for c in items:
        if c.get("decision") == "빼기":
            continue
        rows.append(f"| {name(c)} | {c.get('explainer_videos', 0)} | {c.get('views_total', 0):,} | {c.get('verdict', '')} | {c.get('decision', '')} | {c.get('reason', '')} |")
    dropped = [name(c) for c in items if c.get("decision") == "빼기"]
    body = [f"{OWNER} 오늘 아침 자동 실행이 끝났습니다.", "",
            f"## 👉 [웹 앱에서 확인·승인하기]({APP_URL})",
            "구글로 로그인 → 표현 고르기 → 카드 만들기 → 카드 7장 확인 → 체크 3개(승인) → 예약", "",
            "### 고를 수 있는 후보", *rows, "",
            f"AI가 뺀 표현 {len(dropped)}개: " + (", ".join(dropped) if dropped else "없음"), "",
            "이미 쓴 표현은 웹 앱에서 사람마다 「이미 씀」으로 바뀌어 고를 수 없습니다.",
            f"결과 폴더: `daily/{run_dir.name}`"]
    body_out.write_text("\n".join(body) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
