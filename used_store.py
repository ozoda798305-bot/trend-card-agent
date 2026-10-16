"""사용자별 저장소: 이미 쓴 표현 목록(영원히 금지)·Today's Korean 번호·배지 계정 이름.

- 사용자 = 구글 로그인 이메일. 폴더 이름은 이메일을 그대로 쓰지 않고 해시 12자리(users/<id>/)로 한다.
  로그인을 켜지 않았으면(혼자 쓸 때) 사용자 id 는 "owner".
- users/<id>/used.json    : 이 사람이 승인·예약한 표현. 다음 후보·카드에서 이 사람에게만 뺀다.
- users/<id>/profile.json : 배지에 쓸 인스타 계정 이름(@...).
- 「Today's Korean #N」 = 이 사람이 이미 쓴 표현 개수 + 1.
- 웹 서버(Streamlit)의 파일은 재시작 때 지워지므로, GITHUB_TOKEN 이 있으면 GitHub 저장소의 파일을 직접 읽고 고친다.
  토큰은 이 저장소 하나만, Contents 읽기·쓰기 권한만 준 fine-grained token. 없으면 서버 파일만 쓴다.
"""
from __future__ import annotations
import base64, datetime as dt, hashlib, json, os, re
from pathlib import Path

BASE = Path(__file__).parent
REPO = os.environ.get("GITHUB_REPO", "ozoda798305-bot/trend-card-agent")
OWNER = "owner"
OWNER_HANDLE = "@ozoda_korean"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def user_id(email: str | None) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12] if email else OWNER


# ---------- 파일 읽기·쓰기(GitHub 우선, 없으면 서버 파일) ----------
def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}


def _get(rel: str) -> tuple[dict | None, str]:
    """(내용, sha). 파일이 없으면 (None, "")."""
    if os.environ.get("GITHUB_TOKEN"):
        import requests
        r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{rel}", headers=_headers(), timeout=15)
        if r.status_code == 200:
            j = r.json()
            return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j["sha"]
        if r.status_code == 404:
            return None, ""
    p = BASE / rel
    return (json.loads(p.read_text(encoding="utf-8")) if p.exists() else None), ""


def _put(rel: str, obj: dict, message: str, sha: str = "") -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    if not os.environ.get("GITHUB_TOKEN"):
        return "서버 파일"
    import requests
    payload = {"message": message, "content": base64.b64encode(body.encode("utf-8")).decode("ascii")}
    if sha:
        payload["sha"] = sha
    r = requests.put(f"https://api.github.com/repos/{REPO}/contents/{rel}", headers=_headers(), json=payload, timeout=15)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub 에 기록 실패 HTTP {r.status_code}: {r.text[:150]}")
    return "GitHub"


# ---------- 이미 쓴 표현 ----------
def load(uid: str = OWNER) -> list[dict]:
    obj, _ = _get(f"users/{uid}/used.json")
    return (obj or {}).get("items", [])


def used_map(uid: str = OWNER, items: list[dict] | None = None) -> dict[str, dict]:
    return {norm(i["expression"]): i for i in (load(uid) if items is None else items)}


def next_series_no(uid: str = OWNER) -> int:
    return len(load(uid)) + 1


def add(uid: str, expression: str, series_no: int, run: str) -> str:
    """승인·예약한 표현을 이 사람의 목록에 더한다. 반환: 저장한 곳(GitHub / 서버 파일 / 이미 있음)."""
    rel = f"users/{uid}/used.json"
    obj, sha = _get(rel)
    items = (obj or {}).get("items", [])
    if norm(expression) in used_map(uid, items):
        return "이미 있음"
    items.append({"expression": expression, "series_no": series_no, "date": str(dt.date.today()), "run": run})
    return _put(rel, {"note": "이 사람이 이미 쓴 표현. 다시 쓰지 않는다(영원히 금지).", "items": items},
                f"이미 쓴 표현 추가({uid}): {expression} #{series_no}", sha)


# ---------- 배지 계정 이름 ----------
def handle(uid: str = OWNER) -> str:
    obj, _ = _get(f"users/{uid}/profile.json")
    h = (obj or {}).get("handle", "")
    return h or (OWNER_HANDLE if uid == OWNER else "")


def save_handle(uid: str, h: str) -> str:
    h = "@" + h.strip().lstrip("@")
    if not re.fullmatch(r"@[A-Za-z0-9._]{1,30}", h):
        raise ValueError("인스타 계정 이름은 영문·숫자·밑줄(_)·점(.)으로 30자 이내입니다.")
    obj, sha = _get(f"users/{uid}/profile.json")
    return _put(f"users/{uid}/profile.json", {**(obj or {}), "handle": h}, f"배지 계정 이름({uid})", sha)
