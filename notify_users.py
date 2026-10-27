"""월요일 아침 자동 실행이 끝나면 「이번 주 후보」 메일을 알림에 동의한 선생님마다 보낸다(사람별 맞춤).

사용법  python3 notify_users.py <run 폴더>
- 받는 사람: 웹 앱에서 「월요일 아침 메일 받기」를 켠 사람(users/<id>/profile.json 의 암호화된 이메일).
- 사람마다: 그 사람이 이미 쓴 표현은 빼고, 다음 Today's Korean 번호를 알려 준다.
- 보내기: Gmail(SMTP). GMAIL_USER, GMAIL_APP_PASSWORD(구글 계정의 앱 비밀번호), NOTIFY_KEY 가 필요하다.
  하나라도 없으면 보내지 않고 이유만 출력한다(실행은 실패로 끝내지 않는다).
"""
from __future__ import annotations
import json, os, smtplib, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path

import used_store

APP_URL = "https://todays-korean.streamlit.app"


def personal(items: list[dict], uid: str) -> tuple[list[dict], int]:
    used = used_store.used_map(uid)
    name = lambda c: c.get("clean") or c["expression"]
    keep = [c for c in items if c.get("decision") in ("통과", "사람 확인") and used_store.norm(name(c)) not in used
            and used_store.norm(c["expression"]) not in used]
    return keep, len(used) + 1


def build(day: str, keep: list[dict], next_no: int) -> tuple[str, str, str]:
    name = lambda c: c.get("clean") or c["expression"]
    subject = f"[Today's Korean] 이번 주 후보 {len(keep)}개 – {day}"
    lines = [f"이번 주 후보가 준비됐습니다. 오늘 카드를 만들면 Today's Korean #{next_no} 입니다.", ""]
    rows = ""
    for c in keep:
        lines.append(f"- {name(c)} ({c.get('decision')}) 풀이 영상 {c.get('explainer_videos', 0)}개 · {c.get('reason', '')}")
        rows += (f"<tr><td style='padding:10px 12px;border-bottom:1px solid #eee;font-weight:700'>{escape(name(c))}</td>"
                 f"<td style='padding:10px 12px;border-bottom:1px solid #eee'>{escape(c.get('decision', ''))}</td>"
                 f"<td style='padding:10px 12px;border-bottom:1px solid #eee;color:#5E5A72'>{escape(c.get('reason', ''))}</td></tr>")
    if not keep:
        lines.append("이번 주에는 새로 고를 표현이 없습니다(이미 쓴 표현은 뺐습니다).")
        rows = "<tr><td style='padding:10px 12px'>이번 주에는 새로 고를 표현이 없습니다.</td></tr>"
    lines += ["", f"웹 앱에서 고르고 승인하기: {APP_URL}"]
    html = (f"<div style='font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;color:#17142B;max-width:640px'>"
            f"<h2 style='color:#24135F'>이번 주 후보가 준비됐습니다</h2>"
            f"<p>오늘 카드를 만들면 <b>Today's Korean #{next_no}</b> 입니다. 이미 쓴 표현은 뺐습니다.</p>"
            f"<table style='border-collapse:collapse;width:100%'>{rows}</table>"
            f"<p style='margin-top:24px'><a href='{APP_URL}' style='background:#5B3DF5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none'>웹 앱에서 고르고 승인하기</a></p>"
            f"<p style='color:#5E5A72;font-size:13px'>메일을 그만 받으려면 웹 앱 왼쪽에서 「월요일 아침 메일 받기」를 끄세요.</p></div>")
    return subject, "\n".join(lines), html


def main() -> int:
    run_dir = Path(sys.argv[1])
    user, pw = os.environ.get("GMAIL_USER", ""), os.environ.get("GMAIL_APP_PASSWORD", "")
    if not (user and pw and os.environ.get("NOTIFY_KEY")):
        print("GMAIL_USER·GMAIL_APP_PASSWORD·NOTIFY_KEY 가 없어 메일을 보내지 않았다.")
        return 0
    targets = used_store.notify_targets()
    if not targets:
        print("알림을 켠 사람이 없다.")
        return 0
    items = json.loads((run_dir / "03_AI검수.json").read_text(encoding="utf-8"))["items"]
    d = run_dir.name.split("_")[1]
    day = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    sent = 0
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw)
        for uid, email in targets:
            keep, next_no = personal(items, uid)
            subject, text, html = build(day, keep, next_no)
            m = MIMEMultipart("alternative")
            m["Subject"], m["From"], m["To"] = subject, f"Today's Korean <{user}>", email
            m.attach(MIMEText(text, "plain", "utf-8")); m.attach(MIMEText(html, "html", "utf-8"))
            try:
                s.sendmail(user, [email], m.as_string()); sent += 1
            except smtplib.SMTPException as e:
                print(f"{uid}: 보내기 실패 {e}")
    print(f"알림 메일 {sent}/{len(targets)}통 보냄")  # 이메일 주소는 기록에 남기지 않는다
    return 0


if __name__ == "__main__":
    sys.exit(main())
