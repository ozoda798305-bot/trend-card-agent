"""이미 쓴 표현 목록(used_expressions.json). 한 번 승인·예약한 표현은 다시 쓰지 않는다(영원히 금지).

- 저장 위치: 저장소 맨 위 used_expressions.json. GitHub Actions(매일 후보 찾기)는 이 파일을 그대로 읽는다.
- 웹 앱(Streamlit)은 서버 파일이 재시작 때 지워지므로, GITHUB_TOKEN 이 있으면 GitHub 의 파일을 직접 읽고 고친다.
  토큰은 이 저장소 하나만, Contents 읽기·쓰기 권한만 준 fine-grained token. 없으면 서버 파일만 고친다.
- 「Today's Korean #N」 번호 = 이미 쓴 표현 개수 + 1.
"""
from __future__ import annotations
import base64, datetime as dt, json, os, re
from pathlib import Path

BASE = Path(__file__).parent
FILE = BASE / "used_expressions.json"
REPO = os.environ.get("GITHUB_REPO", "ozoda798305-bot/trend-card-agent")
API = f"https://api.github.com/repos/{REPO}/contents/used_expressions.json"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _token() -> str:
    return os.environ.get("GITHUB_TOKEN", "")


def _remote() -> tuple[list[dict], str] | None:
    """GitHub 의 최신 목록과 sha. 토큰이 없거나 실패하면 None."""
    if not _token():
        return None
    import requests
    r = requests.get(API, headers={"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"}, timeout=15)
    if r.status_code == 404:
        return [], ""
    if r.status_code != 200:
        return None
    j = r.json()
    return json.loads(base64.b64decode(j["content"]).decode("utf-8")).get("items", []), j["sha"]


def load() -> list[dict]:
    remote = _remote()
    if remote is not None:
        return remote[0]
    try:
        return json.loads(FILE.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        return []


def used_map(items: list[dict] | None = None) -> dict[str, dict]:
    return {norm(i["expression"]): i for i in (load() if items is None else items)}


def next_series_no() -> int:
    return len(load()) + 1


def add(expression: str, series_no: int, run: str) -> dict:
    """승인·예약한 표현을 목록에 더한다. 이미 있으면 그대로 둔다. 반환: {"saved_to": "GitHub" | "서버 파일"}"""
    remote = _remote()
    items, sha = remote if remote is not None else (load(), "")
    if norm(expression) in used_map(items):
        return {"saved_to": "이미 있음"}
    items.append({"expression": expression, "series_no": series_no, "date": str(dt.date.today()), "run": run})
    body = json.dumps({"note": "이미 쓴 표현. 다시 쓰지 않는다(영원히 금지).", "items": items}, ensure_ascii=False, indent=1) + "\n"
    FILE.write_text(body, encoding="utf-8")
    if remote is None:
        return {"saved_to": "서버 파일"}
    import requests
    payload = {"message": f"이미 쓴 표현 추가: {expression} (#{series_no})",
               "content": base64.b64encode(body.encode("utf-8")).decode("ascii")}
    if sha:
        payload["sha"] = sha
    r = requests.put(API, headers={"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"}, json=payload, timeout=15)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub 에 기록 실패 HTTP {r.status_code}: {r.text[:150]}")
    return {"saved_to": "GitHub"}
