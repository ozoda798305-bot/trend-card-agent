"""카드 문구(04_카드문구.json)로 카드 PNG 7장을 만든다. 디자인은 매번 AI가 새로 짜고, 선생님 시그니처는 코드가 고정으로 넣는다.

사용법
  python3 render_cards.py 04_자료/run_<시각>            # 04_카드문구.json → cards/card-1~7.png
  python3 render_cards.py 04_자료/run_<시각> --default  # AI 디자인 없이 기본 디자인으로

시그니처(코드가 고정, AI가 바꾸지 못함)
  ② 위쪽 왼쪽 계정 배지 @ozoda_korean   ③ 위쪽 오른쪽 「Today's Korean #번호」
  ④ 한글 표현은 굵은 Pretendard 로 크게, 로마자는 둥근 알약   ⑤ 시그니처 노란색(#FFD43B) 밑줄
  ⑥ 마지막 장(7장)은 항상 같은 「Save & Follow」 디자인
AI가 바꾸는 것: 1~6장의 배치·배경·색·장식(SVG·도형·이모지). 글자는 AI가 쓰지 않고 자리표시({{TEXT}} 등)만 두며,
실제 문구는 코드가 넣는다(카드 문구가 확정본과 한 글자도 다르지 않게).

검사(코드): 7장인지, 바탕이 통째로 검은색 계열인지(어두운 픽셀이 면적 50% 초과면 실패, 일부·흐린 어두움은 허용), 글자가 칸이나 카드 밖으로 넘치는지, 글자·배경 대비(4.5:1, 단색 배경일 때),
시그니처가 보이고 가려지지 않았는지, 한글 폰트가 로드됐는지. 걸리면 AI에게 다시 디자인하게 하고(최대 2번),
그래도 안 되면 기본 디자인으로 만든다.
"""
from __future__ import annotations
import argparse, html, json, re, sys
from pathlib import Path

ACCOUNT = "@ozoda_korean"
SERIES = "Today's Korean"
YELLOW = "#FFD43B"
W, H = 1080, 1350
BASE = Path(__file__).parent
COUNTER = BASE / "04_자료" / "series_counter.json"
FONT_CSS = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"

SIGNATURE_CSS = f"""
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #222; font-family: Pretendard, 'Apple SD Gothic Neo', sans-serif; }}
.card {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; margin: 0 0 20px 0; }}
.design {{ position: absolute; inset: 0; }}
.sig-badge {{ position: absolute !important; top: 44px !important; left: 48px !important; z-index: 50 !important;
  font: 700 30px/1 Pretendard, sans-serif !important; color: #111 !important; background: #fff !important;
  padding: 14px 24px !important; border-radius: 999px !important; border: 4px solid {YELLOW} !important; }}
.sig-series {{ position: absolute !important; top: 44px !important; right: 48px !important; z-index: 50 !important;
  font: 800 30px/1 Pretendard, sans-serif !important; color: #111 !important; background: {YELLOW} !important;
  padding: 14px 24px !important; border-radius: 12px !important; }}
.sig-expr {{ font-family: Pretendard, sans-serif !important; font-weight: 900 !important; display: inline-block;
  text-decoration: underline !important; text-decoration-color: {YELLOW} !important; text-decoration-thickness: 14px !important;
  text-underline-offset: 10px !important; }}
.sig-roman {{ display: inline-block !important; font: 700 34px/1 Pretendard, sans-serif !important; color: #111 !important;
  background: {YELLOW} !important; padding: 12px 28px !important; border-radius: 999px !important; margin-top: 20px !important; }}
.last {{ background: #FFFDF5; color: #111; display: flex; flex-direction: column; justify-content: center; align-items: center;
  text-align: center; padding: 160px 100px; gap: 44px; }}
.last .cta {{ font: 900 96px/1.1 Pretendard, sans-serif; color: #111; background: linear-gradient(transparent 62%, {YELLOW} 62%); padding: 0 12px; }}
.last .txt {{ font: 600 44px/1.45 Pretendard, sans-serif; color: #222; }}
.last .acc {{ font: 800 52px/1 Pretendard, sans-serif; color: #111; background: {YELLOW}; padding: 22px 44px; border-radius: 999px; }}
"""

DEFAULT_DESIGN = {
    "theme": "기본",
    "css": """.d { position:absolute; inset:0; padding:180px 96px 120px; display:flex; flex-direction:column; justify-content:center; gap:40px; }
.d1 { background: linear-gradient(160deg,#1d2b64,#3a4fa0); color:#fff; }
.d2 { background:#f5f3ee; color:#111; }
.d .big { font-size:110px; line-height:1.15; }
.d .t { font: 800 70px/1.25 Pretendard, sans-serif; }
.d .b { font: 600 52px/1.45 Pretendard, sans-serif; }
.d .no { font: 900 140px/1 Pretendard, sans-serif; color:#FFD43B; }""",
    "cards": [
        '<div class="d d1"><div class="big">{{EXPR}}</div><div>{{ROMAN}}</div><div class="t">{{TEXT}}</div></div>',
        '<div class="d d2"><div class="no">01</div><div class="b">{{TEXT}}</div></div>',
        '<div class="d d2"><div class="no">02</div><div class="b">{{TEXT}}</div></div>',
        '<div class="d d2"><div class="no">03</div><div class="b">{{TEXT}}</div></div>',
        '<div class="d d2"><div class="no">04</div><div class="b">{{TEXT}}</div></div>',
        '<div class="d d2"><div class="no">05</div><div class="b">{{TEXT}}</div></div>',
    ],
}

DESIGN_PROMPT = """역할: 당신은 인스타그램 카드뉴스 디자이너입니다. 외국인에게 한국어 유행 표현을 가르치는 계정의 카드 6장을 디자인합니다.

들어오는 것 1(표현과 뜻): {expr} ({roman}) – {meaning}
들어오는 것 2(장별 글의 길이): {lengths}
들어오는 것 3(지난번 테마, 겹치지 않게): {last_theme}

하는 일: 이 표현의 분위기에 맞는 새 디자인(HTML 조각 6개 + CSS)을 만들어 주세요. 매번 다른 배치·배경·색·장식을 씁니다.

지킬 규칙:
- 각 카드는 1080×1350 px 상자(class="design") 안에 들어간다. 조각의 맨 바깥 요소는 position:absolute; inset:0 으로 상자를 채운다.
- 글자는 직접 쓰지 않는다. 자리표시만 둔다: 1장은 {{{{EXPR}}}}, {{{{ROMAN}}}}, {{{{TEXT}}}}를 모두 넣고, 2~6장은 {{{{TEXT}}}}만 한 번 넣는다. 장식용 글자·숫자·영어 단어도 쓰지 않는다(이모지는 장식으로 1~3개 가능).
- 자리표시는 각각 다른 블록 요소(div) 안에 단독으로 넣는다. 그 div 에 글자 크기를 준다: 1장 {{{{EXPR}}}} 120~160px, {{{{TEXT}}}} 60~72px / 2~6장 {{{{TEXT}}}} 48~60px. 글자색과 바로 뒤 배경색은 대비가 충분해야 한다(어두운 배경엔 밝은 글자). 글자를 담은 div 에는 단색 배경색(background-color)을 직접 주거나, 카드 바탕을 단색으로 둔다.
- 위쪽 170px 와 아래쪽 90px 는 비운다(시그니처 배지 자리). 좌우 여백은 80px 이상.
- 노란색(#FFD43B)과 비슷한 노랑은 쓰지 않는다(계정 시그니처 색).
- 카드 바탕 전체를 검은색·짙은 남색·짙은 보라처럼 어두운 색으로 채우지 않는다. 바탕은 밝거나 선명한 색으로 하고, 어두운 색은 일부 도형·띠·흐린 그림자·반투명 겹침으로만 쓴다(코드가 카드 면적의 절반 이상이 어두우면 실패로 본다).
- 외부 이미지·폰트·스크립트는 쓰지 않는다. CSS 그라디언트, 도형, 인라인 SVG, 이모지만 쓴다. font-family 는 지정하지 않는다.
- CSS 클래스 이름은 모두 "x-" 로 시작한다. position:fixed, transform 으로 상자 밖에 놓기, overflow 숨기기 꼼수는 쓰지 않는다.
- 6장은 하나의 세트로 어울리되 장마다 배치를 조금씩 바꾼다.

나가는 것의 형식: JSON 객체 {{"theme": "테마 이름 한 줄", "css": "CSS 문자열", "cards": ["1장 HTML", "2장 HTML", "3장 HTML", "4장 HTML", "5장 HTML", "6장 HTML"]}}"""

CHECK_JS = r"""
() => {
  const out = [];
  const lum = c => { const m = c.match(/\d+(\.\d+)?/g); if (!m) return null; const [r,g,b,a] = m.map(Number);
    if (a !== undefined && a < 0.95) return null;
    const f = v => { v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const L = lum(s.backgroundColor); if (L !== null) return L; } return null; };
  document.querySelectorAll('.card').forEach((card, i) => {
    card.scrollIntoView({block: 'start'});  // 화면 안에 있어야 elementFromPoint 로 가려짐을 볼 수 있다
    const n = i + 1, cr = card.getBoundingClientRect();
    card.querySelectorAll('[data-slot]').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 5 || r.height < 5) out.push(`${n}장 ${el.dataset.slot} 글자가 보이지 않음`);
      if (r.left < cr.left-1 || r.right > cr.right+1 || r.top < cr.top-1 || r.bottom > cr.bottom+1) out.push(`${n}장 ${el.dataset.slot} 글자가 카드 밖으로 넘침`);
      if (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2) out.push(`${n}장 ${el.dataset.slot} 글자가 칸에서 잘림`);
      const fs = parseFloat(getComputedStyle(el).fontSize); if (fs < 40) out.push(`${n}장 ${el.dataset.slot} 글자 ${fs}px(40px 미만)`);
      const fg = lum(getComputedStyle(el).color), bg = bgOf(el);
      if (fg !== null && bg !== null) { const c = (Math.max(fg,bg)+0.05)/(Math.min(fg,bg)+0.05);
        if (c < 4.5) out.push(`${n}장 ${el.dataset.slot} 대비 ${c.toFixed(1)}:1(4.5 미만)`); }
    });
    ['.sig-badge','.sig-series'].forEach(sel => { const s = card.querySelector(sel); if (!s) { out.push(`${n}장 시그니처 ${sel} 없음`); return; }
      const r = s.getBoundingClientRect(); const top = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
      if (!s.contains(top)) out.push(`${n}장 시그니처 ${sel} 가려짐`); });
  });
  if (document.querySelectorAll('.card').length !== 7) out.push(`카드 ${document.querySelectorAll('.card').length}장(7장 아님)`);
  if (![...document.fonts].some(f => f.family.replace(/["']/g,'') === 'Pretendard' && f.status === 'loaded')) out.push('한글 폰트(Pretendard) 로드 실패');
  return out;
}
"""


def esc(s: str) -> str:
    return html.escape(s or "")


def next_series_no() -> int:
    try:
        return json.loads(COUNTER.read_text(encoding="utf-8")).get("next", 1)
    except Exception:
        return 1


def build_html(card: dict, expr: str, design: dict, no: int) -> str:
    roman = card.get("romanization", "")
    texts = [card.get("title", "")] + card.get("quotes", [])[:6]
    slots = {"EXPR": f'<span class="sig-expr">{esc(expr)}</span>', "ROMAN": f'<span class="sig-roman">{esc(roman)}</span>'}
    pages = []
    for i in range(6):
        frag = design["cards"][i]
        frag = frag.replace("{{EXPR}}", f'<span data-slot="표현">{slots["EXPR"]}</span>')
        frag = frag.replace("{{ROMAN}}", slots["ROMAN"])
        frag = frag.replace("{{TEXT}}", f'<span data-slot="본문" style="display:block">{esc(texts[i])}</span>')
        pages.append(frag)
    sig = f'<div class="sig-badge">{esc(ACCOUNT)}</div><div class="sig-series">{esc(SERIES)} #{no}</div>'
    body = "".join(f'<section class="card"><div class="design">{p}</div>{sig}</section>' for p in pages)
    body += (f'<section class="card"><div class="design last"><div class="cta">Save &amp; Follow</div>'
             f'<div class="txt" data-slot="본문">{esc(texts[6] if len(texts) > 6 else "")}</div>'
             f'<div class="acc">{esc(ACCOUNT)}</div></div>{sig}</section>')
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><link rel="stylesheet" href="{FONT_CSS}">'
            f'<style>{design["css"]}\n{SIGNATURE_CSS}</style></head><body>{body}</body></html>')


def render(page_html: str, out_dir: Path) -> list[str]:
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cards.html").write_text(page_html, encoding="utf-8")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")  # 내 컴퓨터: 설치된 Chrome
        except Exception:
            b = p.chromium.launch()  # 서버: playwright 가 받은 Chromium
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(page_html, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(800)
        problems = pg.evaluate(CHECK_JS)
        for i, el in enumerate(pg.query_selector_all(".card"), 1):
            el.screenshot(path=str(out_dir / f"card-{i}.png"))
        b.close()
    for i in range(1, 8):  # 바탕이 통째로 검은색 계열인지(부분·흐린 어두움은 허용)
        r = dark_ratio(out_dir / f"card-{i}.png")
        if r > DARK_MAX:
            problems.append(f"{i}장 배경이 통째로 어두움(어두운 면적 {r*100:.0f}%, 기준 {DARK_MAX*100:.0f}% 이하)")
    return problems


DARK_MAX = 0.50   # 카드 면적에서 어두운 픽셀이 이 비율을 넘으면 「통째로 검은 배경」으로 본다
DARK_LEVEL = 70   # RGB 중 가장 밝은 값이 이보다 작으면 어두운 픽셀(검정·짙은 남색·짙은 보라)


def dark_ratio(png: Path) -> float:
    from PIL import Image
    im = Image.open(png).convert("RGB").resize((216, 270))  # 1/5로 줄여 센다
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    return sum(1 for p in px if max(p) < DARK_LEVEL) / len(px)


def ai_design(card: dict, expr: str, last_theme: str, key: str) -> dict:
    from run_pipeline import gemini
    texts = [card.get("title", "")] + card.get("quotes", [])[:5]
    d, _ = gemini(DESIGN_PROMPT.format(expr=expr, roman=card.get("romanization", ""), meaning=card.get("meaning_en", ""),
                                       lengths=", ".join(f"{i+1}장 {len(t)}자" for i, t in enumerate(texts)), last_theme=last_theme), key)
    if not (isinstance(d, dict) and isinstance(d.get("cards"), list) and len(d["cards"]) == 6 and isinstance(d.get("css"), str)):
        raise RuntimeError("AI 디자인 형식이 맞지 않음")
    if any("{{TEXT}}" not in c for c in d["cards"]) or "{{EXPR}}" not in d["cards"][0]:
        raise RuntimeError("AI 디자인에 자리표시가 빠짐")
    d["css"] = re.sub(r"@import[^;]*;", "", d["css"])  # 외부 자원 차단
    return d


def make_cards(run_dir: Path, use_ai: bool = True, key: str = "") -> dict:
    data = json.loads((run_dir / "04_카드문구.json").read_text(encoding="utf-8"))
    card, expr = data["card"], data["expression"]
    no = next_series_no()
    last_theme = ""
    try:
        last_theme = json.loads(COUNTER.read_text(encoding="utf-8")).get("last_theme", "")
    except Exception:
        pass
    attempts = []
    design = None
    if use_ai:
        for i in range(3):  # 첫 디자인 + 다시 디자인 최대 2번
            try:
                design = ai_design(card, expr, last_theme, key)
            except Exception as e:
                attempts.append({"try": i, "theme": "", "problems": [f"디자인 생성 실패: {e}"]}); design = None; continue
            probs = render(build_html(card, expr, design, no), run_dir / "cards")
            attempts.append({"try": i, "theme": design.get("theme", ""), "problems": probs})
            if not probs:
                break
            design = None
    if design is None:
        design = DEFAULT_DESIGN
        probs = render(build_html(card, expr, design, no), run_dir / "cards")
        attempts.append({"try": "기본 디자인", "theme": "기본", "problems": probs})
    result = {"series_no": no, "theme": design.get("theme", ""), "design": design, "attempts": attempts,
              "status": "검사 통과" if not attempts[-1]["problems"] else "확인 필요", "files": [f"cards/card-{i}.png" for i in range(1, 8)]}
    (run_dir / "05_카드디자인.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(json.dumps({"next": no + 1, "last_theme": result["theme"]}, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir"); ap.add_argument("--default", action="store_true")
    a = ap.parse_args()
    run_dir = Path(a.run_dir) if Path(a.run_dir).is_absolute() else BASE / a.run_dir
    key = ""
    if not a.default:
        from run_pipeline import keys
        key = keys()["GEMINI_API_KEY"]
    r = make_cards(run_dir, use_ai=not a.default, key=key)
    print(f"[{r['status']}] {SERIES} #{r['series_no']} – 테마: {r['theme']}")
    for t in r["attempts"]:
        print(f"  시도 {t['try']} ({t['theme']}): {t['problems'] or '통과'}")
    print("저장:", run_dir / "cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
