"""Today's Korean – 운영자용 웹 화면(Streamlit).

운영자는 API 키를 몰라도 버튼만 누른다. 키는 서버에만 있다(내 컴퓨터는 .env, 배포 서버는 Streamlit Secrets).
여러 사람이 쓴다: Secrets 에 [auth](구글 로그인)가 있으면 로그인한 사람마다 이미 쓴 표현·#번호·배지 계정·하루 횟수를 따로 둔다.
후보 표(아침 자동 실행)는 모두가 함께 보고, 카드는 사람마다 users/<id>/ 폴더에 따로 만든다.
  ① 오늘의 후보 찾기(매주 월요일 아침 8시 GitHub Actions 가 자동으로 daily/ 에 만들어 둔다)
  ② 표현 골라 카드 만들기  ③ 승인 → 내려받기 / 디자인 다시 만들기
  ④ Blotato 예약(키가 없으면 FAKE: 요청만 저장, 실제 게시는 사람이 직접)
실행: streamlit run app.py
"""
from __future__ import annotations
import datetime as dt, io, json, os, shutil, zipfile
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

os.environ["TZ"] = "Asia/Seoul"  # 서버(UTC)에서도 폴더 이름·하루 횟수·게시 날짜를 한국 날짜로 맞춘다
try:
    import time; time.tzset()
except AttributeError:
    pass

BASE = Path(__file__).parent
DATA = BASE / "04_자료"
DEMO = BASE / "samples" / "run_demo"
DAILY = BASE / "daily"  # 매주 월요일 아침 자동 실행 결과(GitHub Actions)
USAGE = DATA / "usage.json"
DAILY_LIMIT = 5  # 한 사람의 하루 실행 횟수(후보 찾기 + 카드 만들기 + 디자인 다시). 우리 키의 무료 한도를 지킨다
GLOBAL_LIMIT = 30  # 모든 사람을 합친 하루 실행 횟수(Gemini 무료 한도 보호)
ADMIN_UIDS_DEFAULT = "owner,a1882ab572b0"  # 운영자(Ozoda). 후보 찾기 버튼은 운영자만 누른다(유튜브 한도 보호)

# 배포 서버의 Secrets 를 환경변수로 옮긴다(화면에는 절대 보이지 않음)
try:
    for k in ("YOUTUBE_API_KEY", "GEMINI_API_KEY", "DEMO_PASSWORD", "BLOTATO_API_KEY", "BLOTATO_ACCOUNT_ID", "GITHUB_TOKEN", "NOTIFY_KEY", "ADMIN_UIDS"):
        if k in st.secrets and not os.environ.get(k):
            os.environ[k] = str(st.secrets[k])
except Exception:
    pass

st.set_page_config(page_title="Today's Korean 카드 에이전트", page_icon="🟨", layout="wide")


# ---------- 공통 ----------
def _usage() -> dict:
    try:
        u = json.loads(USAGE.read_text(encoding="utf-8"))
        return u if u.get("date") == str(dt.date.today()) else {}
    except Exception:
        return {}


def used_all_today() -> int:
    return sum(_usage().get("counts", {}).values())


def used_today(uid: str) -> int:
    return _usage().get("counts", {}).get(uid, 0)


def add_use(uid: str) -> None:
    u = _usage()
    counts = u.get("counts", {})
    counts[uid] = counts.get(uid, 0) + 1
    DATA.mkdir(exist_ok=True)
    USAGE.write_text(json.dumps({"date": str(dt.date.today()), "counts": counts}), encoding="utf-8")


def user_copy(src: Path, uid: str) -> Path:
    """함께 쓰는 후보 폴더를 이 사람의 카드 폴더로 복사한다(후보·검증·검수 파일만)."""
    dst = DATA / "users" / uid / src.name
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("01_후보.json", "02_유튜브검증.json", "03_AI검수.json", "결과요약.md"):
        if (src / f).exists() and not (dst / f).exists():
            shutil.copy(src / f, dst / f)
    return dst


def latest_run() -> Path | None:
    runs = sorted([*DATA.glob("run_*"), *DAILY.glob("run_*")], key=lambda p: p.name)
    return runs[-1] if runs else None


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def candidates_table(run_dir: Path) -> list[dict]:
    items = load(run_dir / "03_AI검수.json")["items"]
    order = {"통과": 0, "사람 확인": 1, "빼기": 2, "이미 씀": 3}
    items.sort(key=lambda c: (order.get(c.get("decision"), 3), -c.get("explainer_videos", 0), -c.get("views_total", 0)))
    return items


def zip_cards(run_dir: Path, card: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(1, 8):
            z.write(run_dir / "cards" / f"card-{i}.png", f"card-{i}.png")
        z.writestr("caption.txt", card.get("caption", "") + "\n\n" + " ".join(card.get("hashtags", [])))
    return buf.getvalue()


# ---------- 화면 ----------
import used_store

def _has_auth() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False

st.title("🟨 Today's Korean 카드 에이전트")
st.caption("외국인을 위한 한국어 유행 표현 카드뉴스")

with st.sidebar:
    st.header("설정")
    if _has_auth():  # 구글 로그인: 사람마다 따로
        if not st.user.is_logged_in:
            st.info("구글 계정으로 로그인하면 내 계정 전용으로 쓸 수 있습니다.")
            st.button("Google 로 로그인", on_click=st.login)
            st.stop()
        uid = used_store.user_id(st.user.get("email"))
        st.write(f"👤 {st.user.get('name', '')}  \n{st.user.get('email', '')}")
        st.button("로그아웃", on_click=st.logout)
    else:  # 로그인을 켜지 않았으면 운영자 혼자(비밀번호만)
        uid = used_store.OWNER
        need_pw = os.environ.get("DEMO_PASSWORD", "")
        if need_pw and st.text_input("데모 비밀번호", type="password") != need_pw:
            st.info("비밀번호를 넣으면 버튼이 열립니다.")
            st.stop()
    my_handle = used_store.handle(uid)
    new_handle = st.text_input("내 인스타 계정(카드 배지)", my_handle, placeholder="@my_account")
    if new_handle and new_handle.strip() != my_handle:
        try:
            used_store.save_handle(uid, new_handle)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    if _has_auth() and st.user.get("email"):  # 월요일 아침 알림 메일(동의한 사람만)
        mail = st.user.get("email")
        on = bool(used_store.notify_email(uid))
        want = st.checkbox("월요일 아침 「이번 주 후보」 메일 받기", value=on, help=f"{mail} 로 보냅니다. 이메일은 암호화해 저장하고, 끄면 지웁니다.")
        if want != on:
            try:
                used_store.set_notify(uid, mail if want else None)
                st.rerun()
            except RuntimeError as e:
                st.warning(str(e))
    my_used = used_store.load(uid)
    st.caption(f"Today's Korean 다음 번호: **#{len(my_used) + 1}** · 이미 쓴 표현 {len(my_used)}개")
    if my_used:
        with st.expander("내가 이미 쓴 표현"):
            for u in my_used:
                st.write(f"#{u['series_no']} {u['expression']} ({u['date']})")
    keys_ok = bool(os.environ.get("YOUTUBE_API_KEY") or (BASE / ".env").exists() or (BASE.parent / ".env").exists())
    demo = st.toggle("데모 모드(저장된 예시로 보기)", value=not keys_ok,
                     help="API 키가 없거나 구글·Gemini 가 막혔을 때 저장된 예시 결과로 흐름을 보여 줍니다.")
    left = min(DAILY_LIMIT - used_today(uid), GLOBAL_LIMIT - used_all_today())
    is_admin = uid in os.environ.get("ADMIN_UIDS", ADMIN_UIDS_DEFAULT).split(",")
    st.metric("오늘 남은 실행", f"{max(left, 0)} / {DAILY_LIMIT}")
    st.caption("키는 서버에만 있고 이 화면에는 보이지 않습니다.")

if "run_dir" not in st.session_state:
    st.session_state.run_dir = str(DEMO) if demo else (str(latest_run()) if latest_run() else "")
if demo:
    st.session_state.run_dir = str(DEMO)

# ① 후보
st.subheader("① 오늘의 후보 찾기")
st.write("구글 트렌드 「뜻·신조어·밈·줄임말」 급상승과 유튜브 풀이 영상에서 후보를 찾고, 유튜브로 검증한 뒤 AI가 정치·혐오 표현을 거릅니다.")
if not is_admin:
    st.caption("후보는 매주 월요일 아침 8시에 자동으로 준비됩니다. 아래 표에서 고르세요.")
if is_admin and st.button("🔍 오늘의 후보 찾기", disabled=demo or left <= 0):
    import run_pipeline as rp
    with st.spinner("구글 트렌드·유튜브·Gemini 를 차례로 부르는 중… (2~5분)"):
        try:
            rp.run_find(SimpleNamespace(max=10, days=30))
            add_use(uid)
            st.session_state.run_dir = str(latest_run())
            st.success("후보 표를 만들었습니다.")
        except SystemExit as e:
            st.error(f"키 문제: {e}")
        except Exception as e:
            st.error(f"실패: {e} – 데모 모드로 흐름을 볼 수 있습니다.")

run_dir = Path(st.session_state.run_dir) if st.session_state.run_dir else None
if run_dir and (run_dir / "03_AI검수.json").exists():
    items = candidates_table(run_dir)
    used = used_store.used_map(uid)  # 이 사람이 이미 쓴 표현은 「이미 씀」으로 바꿔 보여 주고 고를 수 없게 한다
    for c in items:
        u = used.get(used_store.norm(c.get("clean") or c["expression"])) or used.get(used_store.norm(c["expression"]))
        if u:
            c["decision"], c["reason"] = "이미 씀", f"{u['date']} Today's Korean #{u['series_no']}에서 이미 씀"
    st.caption(f"결과 폴더: {run_dir.name}" + (" (데모 예시)" if demo else " (월요일 아침 8시 자동 실행)" if run_dir.parent == DAILY else ""))
    st.dataframe([{"표현": c.get("clean") or c["expression"], "유튜브 풀이 영상": c["explainer_videos"],
                   "조회수": f'{c["views_total"]:,}', "검증": c["verdict"], "AI 검수": c.get("decision", ""),
                   "이유": c.get("reason", "")} for c in items], use_container_width=True, hide_index=True)

    # ② 카드
    st.subheader("② 표현 골라 카드 만들기")
    options = [c.get("clean") or c["expression"] for c in items if c.get("decision") not in ("빼기", "이미 씀")
               and used_store.norm(c.get("clean") or c["expression"]) not in used]
    choice = st.selectbox("표현 (「빼기」·「이미 씀」은 목록에서 제외)", options) if options else None
    if not options:
        st.warning("고를 수 있는 새 표현이 없습니다. 내일 다시 찾거나 ① 버튼으로 새로 찾으세요.")
    st.caption("「사람 확인」 표현은 근거 영상을 직접 보고 고릅니다.")
    if not my_handle:
        st.warning("왼쪽에 내 인스타 계정을 먼저 넣으세요(카드 배지에 들어갑니다).")
    card_dir = run_dir if demo else DATA / "users" / uid / run_dir.name  # 카드는 사람마다 따로
    if st.button("🎨 카드 만들기", disabled=demo or left <= 0 or not choice or not my_handle):
        import run_pipeline as rp
        with st.spinner("Gemini 가 문구와 디자인을 만들고, 코드가 검사하는 중… (2~5분)"):
            try:
                card_dir = user_copy(run_dir, uid)
                for f in ("04_카드문구.json", "05_카드디자인.json", "06_예약.json"):
                    (card_dir / f).unlink(missing_ok=True)
                rp.run_make(SimpleNamespace(choose=choice, run=str(card_dir.relative_to(BASE)), days=30, no_render=False, user=uid))
                add_use(uid)
                st.success("카드를 만들었습니다.")
            except SystemExit as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"실패: {e}")

    if (card_dir / "04_카드문구.json").exists() and (card_dir / "cards" / "card-7.png").exists():
        data = load(card_dir / "04_카드문구.json")
        card = data["card"]
        dsg = load(card_dir / "05_카드디자인.json") if (card_dir / "05_카드디자인.json").exists() else {}
        st.markdown(f"**{data['expression']}** ({card.get('romanization','')}) · 뜻 신뢰: {card.get('meaning_confidence','')} · "
                    f"문구 {data['status']} · 디자인 {dsg.get('status','')} · 테마: {dsg.get('theme','')} · Today's Korean #{dsg.get('series_no','')}")
        cols = st.columns(4)
        for i in range(1, 8):
            cols[(i - 1) % 4].image(str(card_dir / "cards" / f"card-{i}.png"), caption=f"{i}장", use_container_width=True)
        with st.expander("캡션·해시태그·근거 영상"):
            st.write(card.get("caption", ""))
            st.write(" ".join(card.get("hashtags", [])))
            for f in card.get("facts", []):
                st.markdown(f"- {f.get('fact','')} ([근거]({f.get('source_url','')}))")

        # ③ 승인
        st.subheader("③ 사람 확인 후 승인")
        ok1 = st.checkbox("뜻을 사전(우리말샘 등)과 대조했다")
        ok2 = st.checkbox("정치·혐오·성적 표현, 다른 사람 사진·로고가 없다")
        ok3 = st.checkbox("7장 모두 글자가 잘리거나 깨지지 않았다")
        c1, c2 = st.columns(2)
        c1.download_button("✅ 승인 – 카드 PNG 7장 + 캡션 내려받기", zip_cards(card_dir, card),
                           file_name=f"todays_korean_{dsg.get('series_no', '')}_{data['expression']}.zip", disabled=not (ok1 and ok2 and ok3))
        if c2.button("🔁 디자인만 다시 만들기", disabled=demo or left <= 0):
            from run_pipeline import keys
            from render_cards import make_cards
            with st.spinner("새 디자인을 만드는 중…"):
                try:
                    r = make_cards(card_dir, use_ai=True, key=keys()["GEMINI_API_KEY"], uid=uid)
                    add_use(uid)
                    st.success(f"새 디자인: {r['theme']} ({r['status']})")
                    st.rerun()
                except Exception as e:
                    st.error(f"실패: {e}")

        # ④ 예약(Blotato). 키가 없으면 FAKE: 보낼 요청만 만들어 저장하고 실제 게시는 하지 않는다
        st.subheader("④ 인스타그램 예약 (Blotato)")
        import blotato_post as bp
        real = bp.has_key()
        if not real:
            st.warning("FAKE 모드: Blotato API 키가 없어(유료 플랜 전용) 실제로 예약·게시하지 않습니다. 보낼 요청만 만들어 저장합니다.")
        booked = card_dir / "06_예약.json"
        if booked.exists():
            b = load(booked)
            tag = " (FAKE · 실제 게시 없음)" if b.get("mode") == "FAKE" else ""
            st.success(f"예약됨{tag}: {b['scheduled_kst'].replace('T', ' ')} · 번호 {b['post_submission_id']}")
            if b.get("request"):
                with st.expander("Blotato 에 보낼 요청 보기"):
                    st.json(b["request"])
        else:
            when = bp.run_post_time(card_dir)  # 실행이 시작된 날 저녁 7시(지났으면 다음 날 7시)
            st.write(f"게시 시각(자동): **{when:%Y-%m-%d %H:%M}** (한국)")
            label = "📅 승인한 카드로 인스타 예약" + ("" if real else " (FAKE)")
            if st.button(label, disabled=demo or not (ok1 and ok2 and ok3)):
                with st.spinner("예약 요청을 만드는 중…"):
                    try:
                        bp.schedule(card_dir, when) if real else bp.fake_schedule(card_dir, when)
                        # 승인·예약한 표현은 「이미 쓴 표현」에 넣어 다시는 후보로 쓰지 않는다
                        used_store.add(uid, data["expression"], dsg.get("series_no", used_store.next_series_no(uid)), card_dir.name)
                        st.rerun()
                    except (RuntimeError, SystemExit) as e:
                        st.error(f"예약 실패: {e}")
            st.caption("체크 3개를 모두 해야(사람 승인) 예약 버튼이 열립니다.")
        st.markdown("**실제 게시는 사람이 직접**: 인스타 앱 → 새 게시물 → 카드 7장 → 캡션 붙여넣기 → 고급 설정 → 이 게시물 예약 (또는 Meta Business Suite)")
        st.code(card.get("caption", "") + "\n\n" + " ".join(card.get("hashtags", [])), language=None)
else:
    st.info("아직 후보 표가 없습니다. ① 버튼을 누르거나 왼쪽에서 데모 모드를 켜세요.")
