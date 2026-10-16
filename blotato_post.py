"""승인한 카드 7장 + 캡션을 Blotato 로 인스타그램에 예약한다(사람 승인 뒤에만 부른다).

사용법  python3 blotato_post.py --run 04_자료/run_<시각> [--at "2026-10-17 19:00"]
  --at 을 빼면 그 실행(run_<날짜>)이 시작된 날 저녁 7시(한국 시각)로 예약한다. 이미 지났으면 다음 날 7시.
키: BLOTATO_API_KEY (.env 또는 Secrets). Blotato 유료 플랜에서 발급된다(무료 체험에는 API 가 없다).
키가 없으면 FAKE 로 돈다: 보낼 요청을 그대로 만들어 06_예약.json 에 저장하고, Blotato 는 부르지 않는다(실제 게시 없음).
흐름: ① 인스타 계정 ID 찾기 ② 카드 PNG 7장을 Blotato 저장소에 올리기(presigned upload) ③ 캐러셀 게시물 예약
결과: run 폴더의 06_예약.json (예약 번호·예약 시각·이미지 주소)
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys
from pathlib import Path

from naver_datalab import load_env

API = "https://backend.blotato.com/v2"
KST = dt.timezone(dt.timedelta(hours=9))
POST_HOUR = 19  # 저녁 7시 게시


def api_key() -> str:
    base = Path(__file__).parent
    env = load_env(base / ".env" if (base / ".env").exists() else base.parent / ".env")
    k = env.get("BLOTATO_API_KEY") or os.environ.get("BLOTATO_API_KEY", "")
    if not k:
        sys.exit("BLOTATO_API_KEY 가 없다. Blotato 유료 플랜에서 API 키를 받아 Secrets(.env)에 넣는다.")
    return k


def next_post_time(now: dt.datetime | None = None) -> dt.datetime:
    """다음 저녁 7시(KST). 이미 지났으면 내일 7시."""
    now = now or dt.datetime.now(KST)
    t = now.replace(hour=POST_HOUR, minute=0, second=0, microsecond=0)
    return t if t > now + dt.timedelta(minutes=10) else t + dt.timedelta(days=1)


def run_post_time(run_dir: Path, now: dt.datetime | None = None) -> dt.datetime:
    """실행이 시작된 날(폴더 이름 run_YYYYMMDD_HHMM)의 저녁 7시. 이미 지났으면 다음 저녁 7시."""
    now = now or dt.datetime.now(KST)
    try:
        day = dt.datetime.strptime(run_dir.name.split("_")[1], "%Y%m%d").date()
    except (IndexError, ValueError):
        return next_post_time(now)
    t = dt.datetime.combine(day, dt.time(POST_HOUR), tzinfo=KST)
    return t if t > now + dt.timedelta(minutes=10) else next_post_time(now)


def _req(method: str, path: str, key: str, **kw):
    import requests
    r = requests.request(method, API + path, headers={"blotato-api-key": key, "Content-Type": "application/json"}, timeout=30, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"Blotato {path} HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def instagram_account(key: str) -> str:
    if os.environ.get("BLOTATO_ACCOUNT_ID"):
        return os.environ["BLOTATO_ACCOUNT_ID"]
    data = _req("GET", "/users/me/accounts", key)
    items = data.get("items", data) if isinstance(data, dict) else data
    ig = [a for a in items if str(a.get("platform", "")).lower() == "instagram"]
    if not ig:
        raise RuntimeError("Blotato 에 연결된 인스타그램 계정이 없다. Blotato 화면에서 인스타 계정을 먼저 연결한다.")
    return str(ig[0]["id"])


def upload(png: Path, key: str) -> str:
    import requests
    up = _req("POST", "/media/uploads", key, json={"filename": png.name})
    r = requests.put(up["presignedUrl"], data=png.read_bytes(), headers={"Content-Type": "image/png"}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"{png.name} 올리기 실패 HTTP {r.status_code}")
    return up["publicUrl"]


def has_key() -> bool:
    base = Path(__file__).parent
    env = load_env(base / ".env" if (base / ".env").exists() else base.parent / ".env")
    return bool(env.get("BLOTATO_API_KEY") or os.environ.get("BLOTATO_API_KEY"))


def fake_schedule(run_dir: Path, when: dt.datetime) -> dict:
    """키 없이 예약 단계를 흉내 낸다. 실제로 보낼 요청 본문을 만들어 저장만 한다."""
    card = json.loads((run_dir / "04_카드문구.json").read_text(encoding="utf-8"))["card"]
    pngs = [run_dir / "cards" / f"card-{i}.png" for i in range(1, 8)]
    if not all(p.exists() for p in pngs):
        raise RuntimeError("카드 PNG 7장이 없다. 카드 만들기를 먼저 한다.")
    if when.tzinfo is None:
        when = when.replace(tzinfo=KST)
    text = card.get("caption", "").strip() + "\n\n" + " ".join(card.get("hashtags", [])[:5])
    body = {"post": {"accountId": "<인스타 계정 ID: GET /v2/users/me/accounts>",
                     "content": {"text": text, "mediaUrls": [f"<{p.name} 업로드 뒤 publicUrl>" for p in pngs], "platform": "instagram"},
                     "target": {"targetType": "instagram"}},
            "scheduledTime": when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out = {"mode": "FAKE", "note": "BLOTATO_API_KEY 가 없어 Blotato 를 부르지 않았다. 실제 게시 없음.",
           "post_submission_id": "FAKE-" + dt.datetime.now(KST).strftime("%Y%m%d%H%M%S"),
           "scheduled_kst": when.astimezone(KST).isoformat(timespec="minutes"),
           "request": {"method": "POST", "url": API + "/posts", "body": body},
           "requested_at": dt.datetime.now(KST).isoformat(timespec="minutes")}
    (run_dir / "06_예약.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def schedule(run_dir: Path, when: dt.datetime, key: str | None = None) -> dict:
    key = key or api_key()
    card = json.loads((run_dir / "04_카드문구.json").read_text(encoding="utf-8"))["card"]
    pngs = [run_dir / "cards" / f"card-{i}.png" for i in range(1, 8)]
    if not all(p.exists() for p in pngs):
        raise RuntimeError("카드 PNG 7장이 없다. 카드 만들기를 먼저 한다.")
    if when.tzinfo is None:
        when = when.replace(tzinfo=KST)
    text = card.get("caption", "").strip() + "\n\n" + " ".join(card.get("hashtags", [])[:5])
    account = instagram_account(key)
    urls = [upload(p, key) for p in pngs]
    body = {"post": {"accountId": account, "content": {"text": text, "mediaUrls": urls, "platform": "instagram"},
                     "target": {"targetType": "instagram"}},
            "scheduledTime": when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    res = _req("POST", "/posts", key, json=body)
    out = {"mode": "REAL", "post_submission_id": res.get("postSubmissionId", ""), "scheduled_kst": when.astimezone(KST).isoformat(timespec="minutes"),
           "media_urls": urls, "requested_at": dt.datetime.now(KST).isoformat(timespec="minutes")}
    (run_dir / "06_예약.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--at", help='한국 시각 "YYYY-MM-DD HH:MM". 빼면 다음 저녁 7시')
    a = ap.parse_args()
    when = dt.datetime.strptime(a.at, "%Y-%m-%d %H:%M").replace(tzinfo=KST) if a.at else run_post_time(Path(a.run))
    try:
        r = schedule(Path(a.run), when) if has_key() else fake_schedule(Path(a.run), when)
    except RuntimeError as e:
        print("예약 실패:", e, file=sys.stderr); return 1
    print(f"예약{' (FAKE, 실제 게시 없음)' if r['mode'] == 'FAKE' else ''}: {r['scheduled_kst']} (번호 {r['post_submission_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
