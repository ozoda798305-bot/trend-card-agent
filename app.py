"""Today's Korean – 운영자용 웹 화면(Streamlit).

운영자는 API 키를 몰라도 버튼만 누른다. 키는 서버에만 있다(내 컴퓨터는 .env, 배포 서버는 Streamlit Secrets).
  ① 오늘의 후보 찾기  ② 표현 골라 카드 만들기  ③ 승인(내려받기) / 디자인 다시 만들기
실행: streamlit run app.py
"""
from __future__ import annotations
import datetime as dt, io, json, os, zipfile
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

BASE = Path(__file__).parent
DATA = BASE / "04_자료"
DEMO = BASE / "samples" / "run_demo"
USAGE = DATA / "usage.json"
DAILY_LIMIT = 5  # 하루 실행 횟수(후보 찾기 + 카드 만들기). 우리 키의 무료 한도를 지킨다

# 배포 서버의 Secrets 를 환경변수로 옮긴다(화면에는 절대 보이지 않음)
try:
    for k in ("YOUTUBE_API_KEY", "GEMINI_API_KEY", "DEMO_PASSWORD"):
        if k in st.secrets and not os.environ.get(k):
            os.environ[k] = str(st.secrets[k])
except Exception:
    pass

st.set_page_config(page_title="Today's Korean 카드 에이전트", page_icon="🟨", layout="wide")


# ---------- 공통 ----------
def used_today() -> int:
    try:
        u = json.loads(USAGE.read_text(encoding="utf-8"))
        return u["count"] if u.get("date") == str(dt.date.today()) else 0
    except Exception:
        return 0


def add_use() -> None:
    DATA.mkdir(exist_ok=True)
    USAGE.write_text(json.dumps({"date": str(dt.date.today()), "count": used_today() + 1}), encoding="utf-8")


def latest_run() -> Path | None:
    runs = sorted(DATA.glob("run_*"))
    return runs[-1] if runs else None


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def candidates_table(run_dir: Path) -> list[dict]:
    items = load(run_dir / "03_AI검수.json")["items"]
    order = {"통과": 0, "사람 확인": 1, "빼기": 2}
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
st.title("🟨 Today's Korean 카드 에이전트")
st.caption("외국인을 위한 한국어 유행 표현 카드뉴스 · @ozoda_korean")

with st.sidebar:
    st.header("설정")
    need_pw = os.environ.get("DEMO_PASSWORD", "")
    if need_pw:
        if st.text_input("데모 비밀번호", type="password") != need_pw:
            st.info("비밀번호를 넣으면 버튼이 열립니다.")
            st.stop()
    keys_ok = bool(os.environ.get("YOUTUBE_API_KEY") or (BASE / ".env").exists() or (BASE.parent / ".env").exists())
    demo = st.toggle("데모 모드(저장된 예시로 보기)", value=not keys_ok,
                     help="API 키가 없거나 구글·Gemini 가 막혔을 때 저장된 예시 결과로 흐름을 보여 줍니다.")
    left = DAILY_LIMIT - used_today()
    st.metric("오늘 남은 실행", f"{max(left, 0)} / {DAILY_LIMIT}")
    st.caption("키는 서버에만 있고 이 화면에는 보이지 않습니다.")

if "run_dir" not in st.session_state:
    st.session_state.run_dir = str(DEMO) if demo else (str(latest_run()) if latest_run() else "")
if demo:
    st.session_state.run_dir = str(DEMO)

# ① 후보
st.subheader("① 오늘의 후보 찾기")
st.write("구글 트렌드 「뜻·신조어·밈·줄임말」 급상승과 유튜브 풀이 영상에서 후보를 찾고, 유튜브로 검증한 뒤 AI가 정치·혐오 표현을 거릅니다.")
if st.button("🔍 오늘의 후보 찾기", disabled=demo or left <= 0):
    import run_pipeline as rp
    with st.spinner("구글 트렌드·유튜브·Gemini 를 차례로 부르는 중… (2~5분)"):
        try:
            rp.run_find(SimpleNamespace(max=10, days=30))
            add_use()
            st.session_state.run_dir = str(latest_run())
            st.success("후보 표를 만들었습니다.")
        except SystemExit as e:
            st.error(f"키 문제: {e}")
        except Exception as e:
            st.error(f"실패: {e} – 데모 모드로 흐름을 볼 수 있습니다.")

run_dir = Path(st.session_state.run_dir) if st.session_state.run_dir else None
if run_dir and (run_dir / "03_AI검수.json").exists():
    items = candidates_table(run_dir)
    st.caption(f"결과 폴더: {run_dir.name}" + (" (데모 예시)" if demo else ""))
    st.dataframe([{"표현": c.get("clean") or c["expression"], "유튜브 풀이 영상": c["explainer_videos"],
                   "조회수": f'{c["views_total"]:,}', "검증": c["verdict"], "AI 검수": c.get("decision", ""),
                   "이유": c.get("reason", "")} for c in items], use_container_width=True, hide_index=True)

    # ② 카드
    st.subheader("② 표현 골라 카드 만들기")
    options = [c.get("clean") or c["expression"] for c in items if c.get("decision") != "빼기"]
    choice = st.selectbox("표현 (「빼기」는 목록에서 제외)", options) if options else None
    st.caption("「사람 확인」 표현은 근거 영상을 직접 보고 고릅니다.")
    if st.button("🎨 카드 만들기", disabled=demo or left <= 0 or not choice):
        import run_pipeline as rp
        with st.spinner("Gemini 가 문구와 디자인을 만들고, 코드가 검사하는 중… (2~5분)"):
            try:
                rp.run_make(SimpleNamespace(choose=choice, run=str(run_dir.relative_to(BASE)) if run_dir.is_relative_to(BASE) else str(run_dir),
                                            days=30, no_render=False))
                add_use()
                st.success("카드를 만들었습니다.")
            except SystemExit as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"실패: {e}")

    if (run_dir / "04_카드문구.json").exists() and (run_dir / "cards" / "card-7.png").exists():
        data = load(run_dir / "04_카드문구.json")
        card = data["card"]
        dsg = load(run_dir / "05_카드디자인.json") if (run_dir / "05_카드디자인.json").exists() else {}
        st.markdown(f"**{data['expression']}** ({card.get('romanization','')}) · 뜻 신뢰: {card.get('meaning_confidence','')} · "
                    f"문구 {data['status']} · 디자인 {dsg.get('status','')} · 테마: {dsg.get('theme','')} · Today's Korean #{dsg.get('series_no','')}")
        cols = st.columns(4)
        for i in range(1, 8):
            cols[(i - 1) % 4].image(str(run_dir / "cards" / f"card-{i}.png"), caption=f"{i}장", use_container_width=True)
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
        c1.download_button("✅ 승인 – 카드 PNG 7장 + 캡션 내려받기", zip_cards(run_dir, card),
                           file_name=f"todays_korean_{data['expression']}.zip", disabled=not (ok1 and ok2 and ok3))
        if c2.button("🔁 디자인만 다시 만들기", disabled=demo or left <= 0):
            from run_pipeline import keys
            from render_cards import make_cards
            with st.spinner("새 디자인을 만드는 중…"):
                try:
                    r = make_cards(run_dir, use_ai=True, key=keys()["GEMINI_API_KEY"])
                    add_use()
                    st.success(f"새 디자인: {r['theme']} ({r['status']})")
                    st.rerun()
                except Exception as e:
                    st.error(f"실패: {e}")
        st.caption("승인한 카드는 Blotato 에서 인스타그램에 예약합니다(게시 자동 연결은 다음 단계).")
else:
    st.info("아직 후보 표가 없습니다. ① 버튼을 누르거나 왼쪽에서 데모 모드를 켜세요.")
