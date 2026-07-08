# -*- coding: utf-8 -*-
"""
לוח בקרת קטלוג — דשבורד ניהול ממצאים
דף חי לניהול מעגל-הבקרה המלא: קליטת ריצות (בגרירה), מעקב למי נשלח,
קבלת מענה, בטיפול, טיפול וסגירה. עיצוב כהה עם נורות ירוק/כתום/אדום.
הרצה:  py -m streamlit run app.py
"""
import os
import json
import datetime as dt

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

import core

st.set_page_config(page_title="לוח בקרת קטלוג", page_icon="🎛️", layout="wide")

# ---------------------------------------------------------------- עיצוב (כהה + RTL)

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&display=swap');
  :root{
    --bg:#0a0d14; --surface:#151b28; --surface2:#1c2331; --elev:#242c3d;
    --border:#2c3543; --border-hi:#414d61;
    --text:#eef1f6; --text2:#98a1b2; --text3:#6b7484;
    --accent:#6d78ec; --accent-hi:#8791f2; --accent-dim:rgba(109,120,236,.20);
    --green:#4cc38a; --amber:#e8b04b; --red:#f16a6a; --blue:#5aaefc; --gray:#6b7484; --indigo:#8b83f0;
    --shadow:0 4px 16px rgba(0,0,0,.35);
  }
  /* ---------- בסיס: רקע עמוק ועשיר עם שתי הילות עדינות (עומק) ---------- */
  html, body, .stApp, p, span, label, li, input, textarea, button, select, td, th,
  h1,h2,h3,h4, .stMarkdown, div[data-testid="stExpander"] summary, div[data-baseweb="tab"]{
     font-family:'Inter','Segoe UI',-apple-system,Roboto,Arial,sans-serif; }
  .stApp { direction:rtl; background:
     radial-gradient(1000px 520px at 85% -8%, #1d2949 0%, rgba(29,41,73,0) 52%),
     radial-gradient(760px 420px at 2% 3%, #161c33 0%, rgba(22,28,51,0) 46%),
     linear-gradient(180deg, #0f1422 0%, #0a0d14 48%) !important; background-attachment:fixed !important; }
  [data-testid="stAppViewContainer"], [data-testid="stMain"], .main { background:transparent !important; }
  [data-testid="stHeader"] { background:rgba(13,15,21,.5) !important; backdrop-filter:blur(8px); }
  .block-container { padding-top:2.2rem !important; padding-bottom:3rem !important; }
  ::selection { background:var(--accent-dim); }
  ::-webkit-scrollbar { width:11px; height:11px; }
  ::-webkit-scrollbar-track { background:transparent; }
  ::-webkit-scrollbar-thumb { background:#2f3542; border-radius:6px; border:2px solid #0d0f15; }
  ::-webkit-scrollbar-thumb:hover { background:#404859; }
  /* ---------- טיפוגרפיה ---------- */
  .stApp, p, span, label { color:var(--text); }
  h1 { font-size:23px !important; font-weight:600 !important; letter-spacing:-0.6px; color:var(--text); }
  h2 { font-size:19px !important; font-weight:600 !important; letter-spacing:-0.3px; }
  h3 { font-size:16px !important; font-weight:600 !important; letter-spacing:-0.2px; color:var(--text); }
  .note { color:var(--text2); font-size:12.5px; line-height:1.6; }
  a { color:var(--accent-hi); text-decoration:none; } a:hover { text-decoration:underline; }
  /* ---------- סרגל צד ---------- */
  section[data-testid="stSidebar"] { direction:rtl; border-left:1px solid var(--border);
     background:linear-gradient(180deg,#101320,#0c0e14) !important; }
  /* ---------- כפתורים — מסגרת ברורה + עומק לכל כפתור ---------- */
  .stButton>button, .stDownloadButton>button, div[data-testid="stPopover"]>button {
     background:linear-gradient(180deg,#242835,#1b1f29) !important;
     border:1px solid #343b49 !important; color:var(--text) !important; border-radius:10px !important;
     font-weight:500 !important; font-size:13.5px !important; padding:.46rem 1rem !important;
     box-shadow:inset 0 1px 0 rgba(255,255,255,.045), 0 1px 2px rgba(0,0,0,.3) !important;
     transition:background .15s, border-color .15s, box-shadow .15s, transform .06s !important; }
  .stButton>button:hover, .stDownloadButton>button:hover, div[data-testid="stPopover"]>button:hover {
     background:linear-gradient(180deg,#2c3140,#242934) !important; border-color:#49515f !important;
     box-shadow:inset 0 1px 0 rgba(255,255,255,.06), 0 4px 12px rgba(0,0,0,.35) !important; }
  .stButton>button:active { transform:translateY(1px); }
  button[kind="primary"], button[data-testid="baseButton-primary"] {
     background:linear-gradient(180deg,#7681ee,#626dde) !important; border:1px solid #6b76e8 !important;
     color:#fff !important; box-shadow:0 2px 10px rgba(107,118,232,.35) !important; }
  button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
     background:linear-gradient(180deg,#838df2,#6f79e8) !important;
     box-shadow:0 4px 16px rgba(107,118,232,.5) !important; }
  /* ---------- שדות קלט / בחירה ---------- */
  .stTextInput input, .stNumberInput input, .stDateInput input,
  div[data-baseweb="select"]>div, div[data-baseweb="input"]>div, div[data-baseweb="base-input"] {
     background:#141722 !important; border-color:var(--border) !important;
     border-radius:9px !important; color:var(--text) !important; }
  .stTextInput input:focus, .stNumberInput input:focus,
  div[data-baseweb="select"]>div:focus-within {
     border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--accent-dim) !important; }
  /* ---------- טאבים — ניווט מקוטע ---------- */
  .stTabs [data-baseweb="tab-list"] { gap:3px; background:#12141d; border:1px solid var(--border);
     border-radius:12px; padding:4px; }
  .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none !important; }
  .stTabs [data-baseweb="tab"] { font-size:13.5px !important; color:var(--text2) !important;
     border-radius:9px; padding:6px 14px !important; transition:.15s; }
  .stTabs [data-baseweb="tab"]:hover { color:var(--text) !important; background:#1c2029; }
  .stTabs [aria-selected="true"] { color:#fff !important;
     background:linear-gradient(180deg,#7681ee,#626dde) !important;
     box-shadow:0 2px 8px rgba(107,118,232,.3) !important; }
  /* ---------- קוביות KPI ---------- */
  .kpi { background:linear-gradient(180deg,var(--surface2),var(--surface));
     border:1px solid var(--border); border-radius:14px; padding:17px 18px; text-align:center;
     box-shadow:var(--shadow); transition:border-color .15s, transform .12s, box-shadow .15s; }
  .kpi:hover { border-color:var(--border-hi); transform:translateY(-2px);
     box-shadow:0 10px 30px rgba(0,0,0,.45); }
  .kpi .v { font-size:31px; font-weight:650; line-height:1.05; letter-spacing:-1.2px; }
  .kpi .t { font-size:12px; color:var(--text2); margin-top:6px; font-weight:450; }
  .kpi.red .v{color:var(--red)} .kpi.orange .v{color:var(--amber)} .kpi.green .v{color:var(--green)}
  .kpi.blue .v{color:var(--blue)} .kpi.gray .v{color:var(--text2)}
  .kpi.red{border-top:2px solid var(--red)} .kpi.orange{border-top:2px solid var(--amber)}
  .kpi.green{border-top:2px solid var(--green)} .kpi.blue{border-top:2px solid var(--blue)}
  .kpi.gray{border-top:2px solid var(--gray)}
  .chip { display:inline-block; background:#1c2029; border:1px solid var(--border);
     border-radius:9px; padding:5px 13px; margin:0 4px 6px 0; font-size:12.5px; color:var(--text2); }
  .chip b { color:var(--text); font-weight:600; }
  /* ---------- כרטיסים מתקפלים ---------- */
  div[data-testid="stExpander"] { border:1px solid var(--border) !important; border-radius:13px !important;
     background:linear-gradient(180deg,var(--surface),#121824) !important; margin-bottom:9px;
     box-shadow:var(--shadow); transition:border-color .15s, box-shadow .15s; }
  div[data-testid="stExpander"]:hover { border-color:var(--border-hi) !important;
     box-shadow:0 8px 22px rgba(0,0,0,.4); }
  div[data-testid="stExpander"] summary { font-size:13.5px !important; padding:12px 16px !important;
     font-weight:500; }
  div[data-testid="stExpander"] summary:hover { color:var(--accent-hi) !important; }
  /* ---------- טבלאות / מדדים / העלאה ---------- */
  div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { direction:ltr;
     border:1px solid var(--border) !important; border-radius:12px; overflow:hidden; }
  div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--border);
     border-radius:12px; padding:15px 17px; }
  div[data-testid="stFileUploader"] { border:1.5px dashed var(--border-hi); border-radius:12px;
     padding:10px; background:var(--surface); }
  hr { border-color:var(--border); margin:16px 0; }
  /* ---------- כותרת-על (hero) ---------- */
  .hero { position:relative; overflow:hidden; display:flex; align-items:center;
     justify-content:space-between; gap:24px; flex-wrap:wrap;
     background:linear-gradient(120deg,#1c2340 0%,#151b2c 55%,#121722 100%);
     border:1px solid #313c5a; border-radius:18px; padding:22px 28px; margin:2px 0 20px;
     box-shadow:0 12px 34px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.045); }
  .hero:before { content:''; position:absolute; inset:0; pointer-events:none;
     background:radial-gradient(460px 220px at 90% -40%, rgba(109,120,236,.42), transparent 68%); }
  .hero-l { position:relative; }
  .hero-title { font-size:26px; font-weight:700; letter-spacing:-0.8px; color:#fff; }
  .hero-sub { font-size:13px; color:#aab3c6; margin-top:5px; }
  .hero-stats { position:relative; display:flex; gap:14px; }
  .hstat { min-width:96px; text-align:center; padding:10px 16px; border-radius:13px;
     background:rgba(12,16,26,.5); border:1px solid rgba(255,255,255,.07); }
  .hstat .hv { display:block; font-size:28px; font-weight:700; letter-spacing:-1px; line-height:1; }
  .hstat .hl { display:block; font-size:11.5px; color:#aab3c6; margin-top:6px; }
  .hstat.open .hv{color:#f2f4f8} .hstat.done .hv{color:var(--green)} .hstat.late .hv{color:var(--red)}
  [data-testid="stAppViewContainer"] > .main { background:transparent !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
PLOTLY_DARK = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
STATUS_BADGE = {"נשלח": "🟡 נשלח", "בטיפול": "🔵 בטיפול",
                "טופל": "🟢 טופל", "לא רלוונטי": "⚪ לא רלוונטי"}


def rtl_title(text: str) -> dict:
    """כותרת-גרף מיושרת לימין — התאמה לכיוון קריאה בעברית (Plotly לא יורש RTL מהעמוד)."""
    return dict(text=text, x=0.98, xanchor="right", font=dict(size=15))


CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_cfg() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ledger_path": "", "reminder_days": 7}


def save_cfg(cfg: dict):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- מצב אחסון: ענן / מקומי

def _sheets_secrets():
    try:
        if "gcp_service_account" in st.secrets and st.secrets.get("GOOGLE_SHEET_ID"):
            return st.secrets
    except Exception:
        pass
    return None


SEC = _sheets_secrets()
MODE = "sheets" if SEC else "local"


@st.cache_resource
def get_sheet():
    return core.gs_open(SEC)


def persist() -> bool:
    """שומר את המאגר למקור-האמת הפעיל (ענן/קובץ). מחזיר האם נשמר בפועל."""
    try:
        if MODE == "sheets":
            core.gs_save_ledger(st.session_state.led, get_sheet())
            return True
        src = st.session_state.get("led_src", "")
        if src and not src.startswith(("הועלה", "Google")):
            core.save_ledger(st.session_state.led, src)
            return True
    except Exception as e:
        st.session_state.led_err = f"שמירה נכשלה: {e}"
    return False


def update_findings(edits: dict, note: str) -> int:
    """מעדכן שדות בממצאים לפי מזהה. edits: {מזהה: {עמודה: ערך}}. מחזיר כמות שדות ששונו."""
    f = led["findings"].set_index("מזהה")
    changed = 0
    for fid, fields in edits.items():
        if fid not in f.index or isinstance(f.loc[fid], pd.DataFrame):
            continue
        for c, v in fields.items():
            if str(f.at[fid, c]) != str(v or ""):
                f.at[fid, c] = str(v or "")
                changed += 1
        if fields:
            f.at[fid, "עדכון אחרון"] = core.now_str()
    led["findings"] = f.reset_index()
    return changed


# ---------------------------------------------------------------- טעינת מצב

if "cfg" not in st.session_state:
    st.session_state.cfg = load_cfg()
cfg = st.session_state.cfg

if "led" not in st.session_state:
    st.session_state.led = None
    if MODE == "sheets":
        try:
            st.session_state.led = core.gs_load_ledger(get_sheet())
            st.session_state.led_src = "Google Sheets ☁️"
        except Exception as e:
            st.session_state.led_err = str(e)
    else:
        p = cfg.get("ledger_path", "")
        if p and os.path.exists(p):
            try:
                st.session_state.led = core.load_ledger(p)
                st.session_state.led_src = p
            except Exception as e:
                st.session_state.led_err = str(e)
if st.session_state.get("led") is None:
    st.session_state.led = core.empty_ledger()
    st.session_state.setdefault("led_src", "")

led = st.session_state.led
REM = int(cfg.get("reminder_days", 7) or 7)

# הודעת-הבזק ששורדת רענון (rerun מוחק st.success רגיל)
if st.session_state.get("flash"):
    st.toast(st.session_state.pop("flash"), icon="✅")
if st.session_state.get("flash_logs"):
    with st.expander("📥 תוצאות הקליטה האחרונה", expanded=True):
        for l in st.session_state.pop("flash_logs"):
            st.write(l)

# ---------------------------------------------------------------- סרגל צד

with st.sidebar:
    st.markdown("## 🎛️ לוח בקרת קטלוג")
    st.markdown("<div style='display:inline-block;background:#5e6ad2;color:#fff;font-size:11px;"
                "font-weight:600;padding:2px 10px;border-radius:6px;margin:2px 0 6px'>"
                "עיצוב Linear · גרסה 26</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='note'>מאגר: {st.session_state.led_src or 'חדש (לא נשמר עדיין)'}</div>",
                unsafe_allow_html=True)
    if st.session_state.get("led_err"):
        st.error(f"⚠️ טעינת המאגר מהנתיב נכשלה: {st.session_state.led_err}")
    st.markdown("---")

    if MODE == "sheets":
        st.markdown("**☁️ מקור האמת: Google Sheets** — כל שינוי נשמר אוטומטית לענן")
        st.markdown(f"<div class='note'><a href='https://docs.google.com/spreadsheets/d/"
                    f"{SEC.get('GOOGLE_SHEET_ID')}' target='_blank'>פתח את הגיליון בדפדפן ↗</a></div>",
                    unsafe_allow_html=True)
        if st.button("🔄 טען מחדש מהענן", use_container_width=True):
            st.session_state.led = core.gs_load_ledger(get_sheet())
            st.session_state.led_src = "Google Sheets ☁️"
            st.session_state.flash = "נטען מהענן"
            st.rerun()
    else:
        path_in = st.text_input("נתיב המאגר (תיקייה שיתופית)", value=cfg.get("ledger_path", ""),
                                placeholder=r"\\שרת\תיקיה\מאגר בקרות.xlsx")
        c1, c2 = st.columns(2)
        if c1.button("📂 טען", use_container_width=True):
            if path_in and os.path.exists(path_in):
                try:
                    st.session_state.led = core.load_ledger(path_in)
                    st.session_state.led_src = path_in
                    st.session_state.pop("led_err", None)
                    cfg["ledger_path"] = path_in
                    save_cfg(cfg)
                    st.session_state.flash = "המאגר נטען"
                    st.rerun()
                except Exception as e:
                    st.error(f"טעינה נכשלה: {e}")
            else:
                st.error("הקובץ לא נמצא בנתיב")
        # הגנה: אם קיים מאגר בנתיב אבל הוא לא זה שבזיכרון — לא דורסים בלי אישור
        overwrite_risk = bool(path_in and os.path.exists(path_in)
                              and st.session_state.led_src != path_in)
        confirm_ow = st.checkbox("אני מאשר דריסה של הקובץ הקיים בנתיב", value=False) if overwrite_risk else True
        if c2.button("💾 שמור", type="primary", use_container_width=True):
            target = path_in or cfg.get("ledger_path", "")
            if not target:
                st.error("הזן נתיב לשמירה")
            elif not confirm_ow:
                st.error("בנתיב יש מאגר שלא נטען לכאן — אשר דריסה או טען אותו קודם")
            else:
                core.save_ledger(led, target)
                st.session_state.led_src = target
                cfg["ledger_path"] = target
                save_cfg(cfg)
                st.success("נשמר (כולל גיבוי מתוארך)")

    with st.expander("גיבוי / עבודה בענן"):
        up_led = st.file_uploader("טען מאגר בהעלאה", type=["xlsx"], key="led_up")
        if up_led is not None and st.button("טען מהקובץ שהועלה", use_container_width=True):
            st.session_state.led = core.load_ledger(up_led)
            st.session_state.led_src = f"הועלה: {up_led.name}"
            st.rerun()
        st.download_button("⬇️ הורד עותק של המאגר", data=core.save_ledger(led),
                           file_name="מאגר בקרות.xlsx", use_container_width=True)
    st.markdown("---")
    REM = st.number_input("תזכורת אחרי (ימים)", 1, 60, REM)
    if REM != cfg.get("reminder_days"):
        cfg["reminder_days"] = int(REM)
        save_cfg(cfg)

f_all = core.with_derived(led["findings"], REM)

# ---------------------------------------------------------------- כותרת-על (hero) עם סיכום חי
_act_all = f_all[~f_all["סוג ממצא"].isin(core.SIDE_TYPES)] if not f_all.empty else f_all
_h_open = int((~_act_all["סטטוס"].isin(core.CLOSED_STATUSES)).sum()) if not _act_all.empty else 0
_h_done = int(_act_all["סטטוס"].isin(core.CLOSED_STATUSES).sum()) if not _act_all.empty else 0
_h_late = int(_act_all["באיחור"].sum()) if (not _act_all.empty and "באיחור" in _act_all) else 0
st.markdown(
    "<div class='hero'>"
    "<div class='hero-l'><div class='hero-title'>🎛️ לוח בקרת קטלוג</div>"
    "<div class='hero-sub'>ניהול מעגל-הבקרה המלא — מריצה, דרך מייל-לאנליסט, ועד סגירה</div></div>"
    "<div class='hero-stats'>"
    f"<div class='hstat open'><span class='hv'>{_h_open}</span><span class='hl'>ממצאים פתוחים</span></div>"
    f"<div class='hstat done'><span class='hv'>{_h_done}</span><span class='hl'>טופלו</span></div>"
    f"<div class='hstat late'><span class='hv'>{_h_late}</span><span class='hl'>באיחור</span></div>"
    "</div></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- טאבים
# 'לפי תקופה' ראשון — זו מסך העבודה היומיומי; 'סקירה' (תמונת-על כוללת) משנית.

tab_period, tab_over, tab_manage, tab_ingest, tab_ship, tab_prod = st.tabs(
    ["📄 לפי תקופה", "📊 סקירה", "📋 ניהול ממצאים (הכל)", "📥 קליטה בגרירה",
     "📩 תשובות ומשלוחים", "📈 תפוקה"])

# ---------- לפי תקופה — מסך הניהול הראשי, בנוי לפי שלבי התהליך ----------
# התהליך: פריקת קובץ → מייל נשלח (אוטומטית) → ממתין → בטיפול (מעקב/בעבודה) → טופל.
# יחידת הניהול = אנליסט (כל מייל = חבילת ממצאים לאנליסט אחד) — לכן כרטיס לכל אנליסט.
with tab_period:
    if f_all.empty:
        st.info("המאגר ריק — גרור ריצה ראשונה בטאב 'קליטה בגרירה'.")
    else:
        periods = sorted(f_all["תקופת בקרה"].unique(), reverse=True)
        sel = st.selectbox("תקופת בקרה", periods)
        g = f_all[f_all["תקופת בקרה"] == sel]
        side = g[g["סוג ממצא"].isin(core.SIDE_TYPES)]
        act = g[~g["סוג ממצא"].isin(core.SIDE_TYPES)]   # ממצאים לטיפול בפועל

        # --- שלב 1: איפה התהליך עומד — פס-התקדמות לפי שלבי התהליך ---
        n_wait = int((act["סטטוס"] == "נשלח").sum())
        n_prog = int((act["סטטוס"] == "בטיפול").sum())
        n_done = int((act["סטטוס"] == "טופל").sum())
        n_irr = int((act["סטטוס"] == "לא רלוונטי").sum())   # נדחה — לא ממצא אמיתי (נפרד מ'טופל')
        n_late = int(act["באיחור"].sum())
        sent_dates = sorted({d for d in act["נשלח בתאריך"] if d})

        st.markdown(f"<div class='note' style='margin:2px 0 10px'>קובץ <b>{sel}</b> · "
                    f"{len(act)} ממצאים · המיילים נשלחו {sent_dates[0] if sent_dates else '—'} · "
                    f"{act['אנליסט'].nunique()} אנליסטים</div>", unsafe_allow_html=True)

        # שלבי-התהליך העיקריים (זורמים מימין לשמאל), ואז קופסאות-קצה נפרדות
        stages = [(n_wait, "ממתין", "#e8b04b"), (n_prog, "בטיפול", "#5aaefc"),
                  (n_done, "טופל", "#4cc38a")]

        def _box(v, t, c, txt="#98a1b2"):
            dim = "opacity:.45;" if v == 0 else ""
            return (f"<div style='background:linear-gradient(180deg,#1c2331,#151b28);"
                    f"border:1px solid #2c3543;border-top:3px solid {c};"
                    f"border-radius:14px;padding:12px 22px;text-align:center;min-width:118px;"
                    f"box-shadow:0 4px 14px rgba(0,0,0,.3);{dim}'>"
                    f"<div style='font-size:30px;font-weight:700;letter-spacing:-1px;color:{c}'>{v}</div>"
                    f"<div style='font-size:12px;color:{txt};margin-top:3px'>{t}</div></div>")

        arrow = "<div style='color:#414d61;font-size:22px;align-self:center'>◄</div>"
        html = "<div style='display:flex;gap:10px;flex-wrap:wrap'>"
        html += arrow.join(_box(v, t, c) for v, t, c in stages)
        extras = ""
        if n_irr:
            extras += "<div style='width:14px'></div>" + _box(n_irr, "לא רלוונטי (נדחה)", "#6b7484")
        if n_late:
            extras += "<div style='width:6px'></div>" + _box(n_late, "🔴 באיחור", "#f16a6a", "#f0a3a3")
        html += extras + "</div>"
        st.markdown(html, unsafe_allow_html=True)

        tc = act["סוג ממצא"].value_counts()
        if not tc.empty:
            chips = "".join(f"<span class='chip'><b>{n}</b> {t}</span>" for t, n in tc.items())
            st.markdown(f"<div style='margin:10px 0 2px'>{chips}</div>", unsafe_allow_html=True)

        st.markdown("---")

        # --- שלב 2: ניהול לפי אנליסט — כרטיס לכל מי שקיבל מייל ---
        st.markdown("#### 👤 ניהול לפי אנליסט — כל כרטיס = מייל אחד שנשלח")
        st.markdown("<div class='note'>לכל פריט אפשר לשלוח מייל-מעקב עם נוסח קבוע ('האם טופל?'). "
                    "מומלץ <b>📧 טיוטת Outlook</b> — נפתחת ישירות בחלון-כתיבה של Outlook (הורד את הקובץ ופתח אותו). "
                    "כשמאשרים לך — סמן 'טופל' בעמודת הסטטוס ושמור.</div>", unsafe_allow_html=True)

        SHOW = ["סטטוס", "תגובה", "סוג ממצא", "מספר בקשה", "שורה", "מקט", "תיאור",
                "נמצא", "צפוי", "הערה", "מזהה"]

        def _reply_cell(r):
            """חיווי-תגובה לצד כל פריט: האם התקבלה תשובה / ממתין / דורש אימות."""
            note = str(r.get("הערה") or "")
            src = str(r.get("מקור חיווי") or "")
            replied = ("תשובה:" in note) or (src in ("מייל", "מייל (אוטומטי)"))
            if "דרוש אימות" in note:
                return "⚠ לאימות"
            if replied:
                return "📩 נענה"
            if r["סטטוס"] == "נשלח":
                return "⏳ ממתין"
            return "—"

        order = (act.assign(_open=~act["סטטוס"].isin(core.CLOSED_STATUSES))
                 .groupby("אנליסט")["_open"].sum().sort_values(ascending=False))
        for an in order.index:
            sub = act[act["אנליסט"] == an].copy()
            sub["תגובה"] = sub.apply(_reply_cell, axis=1)
            total, closed = len(sub), int(sub["סטטוס"].isin(core.CLOSED_STATUSES).sum())
            late_an = int(sub["באיחור"].sum())
            replied = int((sub["מקור חיווי"].astype(str).isin(["מייל", "מייל (אוטומטי)"])
                           | sub["הערה"].astype(str).str.contains("תשובה:", na=False)).sum())
            review_an = int(sub["הערה"].astype(str).str.contains("דרוש אימות", na=False).sum())
            if review_an:
                icon, state = "⚠", f"{review_an} לאימות"
            elif closed == total:
                icon, state = "✅", "הושלם"
            elif late_an:
                icon, state = "🔴", f"{late_an} באיחור"
            elif replied:
                icon, state = "🔵", "בטיפול"
            else:
                icon, state = "🟡", "ממתין"
            if replied:
                rp = f" · 📩 נענו {replied}/{total}"
            elif (sub["סטטוס"] == "נשלח").any():
                rp = " · ⏳ ממתין לתגובה"
            else:
                rp = ""
            label = f"{icon} {an or '(ללא שם)'} · {total} ממצאים · נסגרו {closed}/{total}{rp} · {state}"
            with st.expander(label, expanded=bool(late_an or review_an)):
                ed = st.data_editor(
                    sub[SHOW].sort_values("סטטוס"),
                    hide_index=True, use_container_width=True,
                    disabled=[c for c in SHOW if c not in ("סטטוס", "הערה")],
                    column_config={
                        "סטטוס": st.column_config.SelectboxColumn("סטטוס", options=core.STATUSES,
                                                                   width="small"),
                        "תגובה": st.column_config.TextColumn("תגובה", width="small",
                                                             help="📩 נענה · ⏳ ממתין · ⚠ דרוש אימות"),
                        "הערה": st.column_config.TextColumn("הערה", width="medium"),
                        "מזהה": None,
                    }, key=f"an_ed_{sel}_{an}")
                open_sub = sub[~sub["סטטוס"].isin(core.CLOSED_STATUSES)]
                to_addr = sub["נמען"].iloc[0] if len(sub) else ""

                # --- שליחת מיילים: כפתור ראשי אחד לכל הפריטים + אופציה קטנה לפריט בודד ---
                if len(open_sub):
                    n_open = len(open_sub)
                    if n_open == 1:
                        prow = open_sub.iloc[0].to_dict()
                        st.download_button("📧 שלח מייל-מעקב לפריט", core.followup_eml(prow),
                                           file_name=f"followup_{prow['מספר בקשה']}_{prow['שורה']}.eml",
                                           mime="message/rfc822", key=f"dl1_{sel}_{an}",
                                           use_container_width=True, type="primary")
                    else:
                        mc1, mc2 = st.columns([3, 1])
                        mc1.download_button(f"📧 מייל-מעקב לכל {n_open} הפריטים של {an}",
                                            core.followup_eml_bulk(open_sub, to_addr),
                                            file_name=f"followup_{an}.eml", mime="message/rfc822",
                                            key=f"dlall_{sel}_{an}", use_container_width=True,
                                            type="primary")
                        with mc2.popover("📧 פריט בודד", use_container_width=True):
                            labels = {}
                            for _, r in open_sub.iterrows():
                                mk = "🔵 נענה · " if r["סטטוס"] == "בטיפול" else ""
                                labels[f"{mk}בקשה {r['מספר בקשה']}/{r['שורה']} — {str(r['תיאור'])[:28]}"] = r["מזהה"]
                            pk = st.selectbox("בחר פריט", list(labels), key=f"pk_{sel}_{an}",
                                              label_visibility="collapsed")
                            prow = open_sub[open_sub["מזהה"] == labels[pk]].iloc[0].to_dict()
                            st.download_button("📧 הורד טיוטה לפריט", core.followup_eml(prow),
                                               file_name=f"followup_{prow['מספר בקשה']}_{prow['שורה']}.eml",
                                               mime="message/rfc822", key=f"dl1_{sel}_{an}",
                                               use_container_width=True)

                b2, b3 = st.columns(2)
                if b2.button("✅ הכל טופל", use_container_width=True, key=f"done_{sel}_{an}",
                             help="כל הממצאים הפתוחים של האנליסט יסומנו 'טופל'"):
                    edits = {}
                    for _, r in open_sub.iterrows():
                        e = {"סטטוס": "טופל"}
                        if not r["חיווי בתאריך"]:
                            e.update({"חיווי בתאריך": core.today_str(), "מקור חיווי": "ידני"})
                        edits[r["מזהה"]] = e
                    update_findings(edits, "all-done")
                    persist()
                    st.session_state.flash = f"סומנו {len(edits)} ממצאים של {an} כטופלו"
                    st.rerun()
                if b3.button("💾 שמור", type="primary", use_container_width=True, key=f"sv_{sel}_{an}"):
                    edits = {}
                    for _, r in ed.iterrows():
                        e = {"סטטוס": r["סטטוס"], "הערה": r["הערה"]}
                        # מעבר ידני ל'בטיפול'/'טופל' בלי חיווי — משלים תאריך אוטומטית
                        old = sub.loc[sub["מזהה"] == r["מזהה"], "חיווי בתאריך"]
                        if r["סטטוס"] in ("בטיפול", "טופל") and not (len(old) and old.iloc[0]):
                            e.update({"חיווי בתאריך": core.today_str(), "מקור חיווי": "ידני"})
                        edits[r["מזהה"]] = e
                    changed = update_findings(edits, "edit")
                    saved = persist()
                    st.session_state.flash = (f"עודכנו {changed} שדות של {an}"
                                              + ("" if saved else " — בזיכרון בלבד!"))
                    st.rerun()

        # --- מסומנים בצד (PROD וכו') — לתצוגה בלבד, מחוץ לזרימת הניהול ---
        if len(side):
            with st.expander(f"⚪ מסומנים בצד — {len(side)} פערי-מיפוי בסוגי חומר מחוץ ל-Z001-Z004 (ללא מייל)"):
                st.dataframe(side[["סוג ממצא", "מספר בקשה", "מקט", "תיאור", "נמצא", "אנליסט"]],
                             use_container_width=True, hide_index=True)

# ---------- סקירה — תמונת-על כוללת (כל התקופות ביחד) ----------
with tab_over:
    if f_all.empty:
        st.info("המאגר ריק — גרור לכאן ריצה ראשונה בטאב 'קליטה בגרירה'.")
    else:
        open_df = f_all[~f_all["סטטוס"].isin(core.CLOSED_STATUSES)]
        late_n = int(f_all["באיחור"].sum())
        done_n = int((f_all["סטטוס"] == "טופל").sum())

        k = st.columns(3)
        kpis = [
            (f"{len(open_df)}", "ממצאים פתוחים — כל התקופות", "red" if len(open_df) else "green"),
            (f"{late_n}", f"באיחור ≥ {REM} ימים", "red" if late_n else "green"),
            (f"{done_n}", "טופלו — כל התקופות", "green"),
        ]
        for col, (v, t, c) in zip(k, kpis):
            col.markdown(f"<div class='kpi {c}'><div class='v'>{v}</div><div class='t'>{t}</div></div>",
                         unsafe_allow_html=True)
        st.markdown("")

        c1, c2 = st.columns([1, 1.4])
        with c1:
            vc = f_all["סטטוס"].value_counts()
            fig = go.Figure(go.Pie(labels=vc.index, values=vc.values, hole=0.55,
                                   marker=dict(colors=[core.STATUS_COLORS.get(s, "#888") for s in vc.index])))
            fig.update_layout(title=rtl_title("ממצאים לפי סטטוס"), height=330, **PLOTLY_DARK)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            g = f_all.groupby(["אנליסט", "סטטוס"]).size().reset_index(name="n")
            fig = px.bar(g, x="אנליסט", y="n", color="סטטוס", color_discrete_map=core.STATUS_COLORS)
            fig.update_layout(title=rtl_title("ממצאים לפי אנליסט"), height=330, **PLOTLY_DARK)
            st.plotly_chart(fig, use_container_width=True)

        g2 = f_all.groupby(["תקופת בקרה", "סוג ממצא"]).size().reset_index(name="n")
        fig = px.bar(g2, x="תקופת בקרה", y="n", color="סוג ממצא", barmode="group",
                     color_discrete_map=core.TYPE_COLORS)
        fig.update_layout(title=rtl_title("ממצאים לפי תקופת בקרה"), height=300, **PLOTLY_DARK)
        st.plotly_chart(fig, use_container_width=True)

        # מעקב ניהולי לפי אנליסט — מי סגר, מי תקוע (אדום רק אם יש בפועל איחור בפועל, לא סתם % נמוך)
        st.markdown("### 👥 מעקב לפי אנליסט")
        ap = core.analyst_progress(f_all)
        if not ap.empty:
            for _, r in ap.iterrows():
                pct = int(r["אחוז סגירה"])
                if r["באיחור"]:
                    bar_color = "#eb5757"
                elif pct >= 80:
                    bar_color = "#4cb782"
                elif pct >= 40:
                    bar_color = "#dba13a"
                else:
                    bar_color = "#4ea7fc"
                late_badge = (f"<span style='color:#eb5757;font-weight:700'> 🔴 {r['באיחור']} באיחור</span>"
                              if r["באיחור"] else "")
                st.markdown(
                    f"<div style='background:#16171a;border:1px solid #26282d;border-radius:10px;"
                    f"padding:10px 14px;margin:6px 0'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:14px'>"
                    f"<span><b>{r['אנליסט']}</b>{late_badge}</span>"
                    f"<span class='note'>נשלחו {r['נשלחו']} · נצפו/בטיפול {r['נצפו/בטיפול']} · "
                    f"טופלו {r['טופלו']} מתוך {r['סהכ']}</span></div>"
                    f"<div style='background:#26282d;border-radius:6px;height:10px;margin-top:8px'>"
                    f"<div style='background:{bar_color};width:{pct}%;height:10px;border-radius:6px'></div></div>"
                    f"</div>", unsafe_allow_html=True)

        if late_n:
            st.markdown(f"### 🔴 דורשים תזכורת ({late_n})")
            lt = f_all[f_all["באיחור"]][["נורה", "תקופת בקרה", "מספר בקשה", "שורה", "סוג ממצא",
                                          "תיאור", "אנליסט", "נשלח בתאריך", "ימים פתוח", "סטטוס"]]
            st.dataframe(lt.sort_values("ימים פתוח", ascending=False),
                         use_container_width=True, hide_index=True)

# ---------- ניהול ממצאים (הכל) — סינון וחיפוש חוצה-תקופות ----------
with tab_manage:
    if f_all.empty:
        st.info("אין ממצאים במאגר עדיין.")
    else:
        fc1, fc2, fc3, fc4 = st.columns(4)
        f_status = fc1.multiselect("סטטוס", core.STATUSES, default=[])
        f_analyst = fc2.multiselect("אנליסט", sorted(f_all["אנליסט"].unique()), default=[])
        f_period = fc3.multiselect("תקופה", sorted(f_all["תקופת בקרה"].unique()), default=[])
        f_late = fc4.checkbox("רק באיחור 🔴")

        view = f_all.copy()
        if f_status:
            view = view[view["סטטוס"].isin(f_status)]
        if f_analyst:
            view = view[view["אנליסט"].isin(f_analyst)]
        if f_period:
            view = view[view["תקופת בקרה"].isin(f_period)]
        if f_late:
            view = view[view["באיחור"]]

        ed_state = st.session_state.get("editor", {})
        if isinstance(ed_state, dict) and ed_state.get("edited_rows"):
            st.warning("⚠️ יש שינויים שלא נשמרו בטבלה — לחץ 'שמור שינויים' לפני שינוי סינון (אחרת יאבדו)")

        show_cols = ["נורה", "מזהה", "תקופת בקרה", "סוג ממצא", "מספר בקשה", "שורה", "מקט",
                     "תיאור", "נמצא", "צפוי", "אנליסט", "נשלח בתאריך", "חיווי בתאריך",
                     "ימים פתוח", "סטטוס", "הערה"]
        edited = st.data_editor(
            view[show_cols], hide_index=True, use_container_width=True, height=480,
            disabled=[c for c in show_cols if c not in ("סטטוס", "הערה", "חיווי בתאריך", "נשלח בתאריך")],
            column_config={
                "סטטוס": st.column_config.SelectboxColumn("סטטוס", options=core.STATUSES, width="small"),
                "הערה": st.column_config.TextColumn("הערה", width="medium"),
                "נורה": st.column_config.TextColumn("", width="small"),
            }, key="editor")

        if st.button("💾 שמור שינויים בטבלה", type="primary"):
            edits = {r["מזהה"]: {"סטטוס": r["סטטוס"], "הערה": r["הערה"],
                                  "חיווי בתאריך": r["חיווי בתאריך"], "נשלח בתאריך": r["נשלח בתאריך"]}
                     for _, r in edited.iterrows()}
            changed = update_findings(edits, "edit")
            saved = persist()
            st.session_state.flash = (f"עודכנו {changed} שדות" +
                                      (" — נשמר למאגר" if saved else " — בזיכרון בלבד, שמור מהסרגל!"))
            st.rerun()

# ---------- קליטה בגרירה ----------
with tab_ingest:
    st.markdown("### גרור לכאן כל דבר מהריצה — הזיהוי אוטומטי")
    st.markdown("<div class='note'>תור מיילים (mail_queue.txt) · קובץ בקרה (xlsx) · דוח תפוקה (xlsx) · "
                "מייל שנשלח או מענה (msg / eml)</div>", unsafe_allow_html=True)
    up_key = f"ingest_up_{st.session_state.get('up_gen', 0)}"
    ups = st.file_uploader("שחרר קבצים כאן", type=["txt", "xlsx", "msg", "eml"],
                           accept_multiple_files=True, key=up_key)
    st.caption("ממצאים חדשים נכנסים כ'נשלח' (המיילים יוצאים אוטומטית עם פריקת הקובץ בארגון).")

    if ups and st.button("📥 קלוט הכול", type="primary"):
        logs = []
        for up in ups:
            try:
                parsed = core.parse_upload(up.name, up.getvalue())
                if parsed["kind"] == "mail":
                    res = core.apply_mail(led, parsed)
                    msg = f"✉️ {up.name}: {res['mail_type']} — עודכנו {res['touched']} ממצאים"
                    if res.get("note"):
                        msg += f" ⚠️ {res['note']}"
                    logs.append(msg)
                else:
                    res = core.merge_findings(led, parsed)
                    logs.append(f"📄 {up.name}: תקופה {res['period'] or '?'} — "
                                f"נוספו {res['added']} ממצאים (דולגו {res['skipped']} קיימים)"
                                + (f", תפוקה: {res['prod_added']}" if res.get("prod_added") else "")
                                + (f", נסגרו אוטומטית {res['closed_auto']} (תוקנו — לא נמצאים יותר בקובץ)"
                                   if res.get("closed_auto") else ""))
            except Exception as e:
                logs.append(f"❌ {up.name}: {e}")
        if persist():
            logs.append("💾 נשמר אוטומטית" + (" לענן" if MODE == "sheets" else " למאגר"))
        st.session_state.flash_logs = logs
        st.session_state.up_gen = st.session_state.get("up_gen", 0) + 1
        st.rerun()

    # ----- קליטת-עבר מרוכזת: סריקת תיקייה -----
    default_scan = cfg.get("scan_root", r"C:\Users\ran.nahum1\Downloads\בקרות")
    show_scan = MODE == "local" or os.path.isdir(default_scan)
    if show_scan:
        st.markdown("---")
        st.markdown("### 🗂️ קליטה מתיקייה — כל מה שכבר הופק, בבת אחת")
        sc1, sc2 = st.columns([3, 1])
        scan_root = sc1.text_input("תיקייה לסריקה", value=default_scan, key="scan_root_in")
        if sc2.button("🔍 סרוק", use_container_width=True):
            cfg["scan_root"] = scan_root
            save_cfg(cfg)
            st.session_state.scan_results = core.scan_folder(scan_root)
        scan = st.session_state.get("scan_results")
        if scan is not None:
            if not scan:
                st.warning("לא נמצאו תוצרי-צינור בתיקייה")
            else:
                n_periods = len({s["תקופה"] for s in scan if s["תקופה"]})
                n_mail = sum(1 for s in scan if s["סוג"] == "מייל/תשובה")
                st.markdown(f"<div class='note'>נמצאו <b>{len(scan)}</b> קבצים ב-<b>{n_periods}</b> תקופות"
                            + (f" (כולל {n_mail} מיילי-תשובה)" if n_mail else "") +
                            " — כל תקופה נקלטת מהגרסה העדכנית ביותר שלה בלבד.</div>",
                            unsafe_allow_html=True)
                sdf = pd.DataFrame(scan)
                sdf.insert(0, "קלוט", True)
                picked = st.data_editor(
                    sdf[["קלוט", "סוג", "תקופה", "קובץ", "תאריך הריצה"]]
                        .sort_values(["תקופה", "סוג"]),
                    hide_index=True, use_container_width=True,
                    disabled=["סוג", "תקופה", "קובץ", "תאריך הריצה"], key="scan_pick")
                if st.button("📥 קלוט את המסומנים", type="primary", key="scan_go"):
                    logs = []
                    picked_items = [scan[i] for i, row in picked.iterrows() if row["קלוט"]]
                    picked_items.sort(key=lambda it: 1 if it["סוג"] == "מייל/תשובה" else 0)
                    for item in picked_items:
                        try:
                            with open(item["נתיב"], "rb") as fh:
                                parsed = core.parse_upload(item["קובץ"], fh.read())
                            if parsed.get("kind") == "mail":
                                res = core.apply_mail(led, parsed)
                                tag = "תשובה→בטיפול" if res["mail_type"] == "מענה" else "משלוח"
                                logs.append(f"✉️ {item['קובץ']}: {tag} — {res['touched']} ממצאים"
                                            + (f" ⚠️ {res['note']}" if res.get("note") else ""))
                            else:
                                res = core.merge_findings(led, parsed, mark_sent=True,
                                                          sent_date=item["תאריך הריצה"])
                                logs.append(f"📄 {item['קובץ']}: תקופה {res['period'] or '?'} — "
                                            f"נוספו {res['added']} (דולגו {res['skipped']})"
                                            + (f", תפוקה: {res['prod_added']}" if res.get("prod_added") else "")
                                            + (f", נסגרו אוטומטית {res['closed_auto']}"
                                               if res.get("closed_auto") else ""))
                        except Exception as e:
                            logs.append(f"❌ {item['קובץ']}: {e}")
                    if persist():
                        logs.append("💾 נשמר אוטומטית" + (" לענן" if MODE == "sheets" else " למאגר"))
                    st.session_state.flash_logs = logs
                    st.session_state.scan_results = None
                    st.rerun()

# ---------- תשובות ומשלוחים — המקום המרכזי שאוסף את כל התשובות ----------
with tab_ship:
    # --- תור-אימות: הדבר היחיד שדורש מבט אנושי. השאר נסגר/מסווג אוטומטית מהתשובה ---
    if not f_all.empty:
        auto_done = f_all[(f_all["מקור חיווי"].astype(str) == "מייל (אוטומטי)")
                          & (f_all["סטטוס"] == "טופל")]
        needs = f_all[f_all["הערה"].astype(str).str.contains("דרוש אימות", na=False)
                      & ~f_all["סטטוס"].isin(core.CLOSED_STATUSES)]
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='kpi green'><div class='v'>{len(auto_done)}</div>"
                    "<div class='t'>✓ נסגרו אוטומטית מתשובה</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='kpi orange'><div class='v'>{len(needs)}</div>"
                    "<div class='t'>⚠ דרוש אימות ידני</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='kpi blue'><div class='v'>"
                    f"{int((f_all['מקור חיווי'].astype(str)=='מייל (אוטומטי)').sum())}</div>"
                    "<div class='t'>📩 תשובות שנקלטו</div></div>", unsafe_allow_html=True)
        if len(needs):
            st.markdown("#### 🔎 דרוש אימות ידני — הסורק לא היה בטוח בסיווג")
            st.caption("רק אלה דורשים את מבטך. השאר טופל/סווג אוטומטית לפי תשובת האנליסט.")
            nv = needs.copy()
            nv["תשובת האנליסט"] = (nv["הערה"].astype(str)
                                   .str.replace(r".*תשובה:\s*", "", regex=True).str.strip())
            st.dataframe(nv[["אנליסט", "מספר בקשה", "שורה", "מקט", "תיאור", "תשובת האנליסט"]],
                         use_container_width=True, hide_index=True)
            st.caption("לסגירה/שינוי: טאב 'לפי תקופה' → כרטיס האנליסט → סמן 'טופל'/'בטיפול' ושמור.")
        st.markdown("---")

    st.markdown("### 📩 תשובות שהתקבלו")
    st.caption("כל מה שהאנליסטים השיבו (אוטומטית מסורק-התשובות, או מגרירת מייל) — לפי בקשה ואנליסט. "
               "תשובת 'טופל' ברורה → נסגר לבד; 'עדיין' → בטיפול; לא-בטוח → תור-האימות למעלה.")
    if f_all.empty:
        rep = f_all
    else:
        has_reply = (f_all["מקור חיווי"].astype(str).isin(["מייל", "מייל (אוטומטי)"])
                     | f_all["הערה"].astype(str).str.contains("תשובה:", na=False))
        rep = f_all[has_reply]
    if rep.empty:
        st.info("עדיין לא נקלטו תשובות. כשהאנליסטים משיבים והסורק רץ (או כשגוררים מייל-תשובה) — "
                "הן יופיעו כאן והממצא יעבור ל'בטיפול'.")
    else:
        auto = int((rep["מקור חיווי"].astype(str) == "מייל (אוטומטי)").sum())
        st.markdown(f"<div class='note'><b>{len(rep)}</b> ממצאים שהתקבלה עליהם תשובה "
                    f"({auto} אוטומטית מהסורק) · {rep['אנליסט'].nunique()} אנליסטים · "
                    f"{int(rep['סטטוס'].isin(core.CLOSED_STATUSES).sum())} כבר נסגרו</div>",
                    unsafe_allow_html=True)
        rv = rep.copy()
        rv["תוכן התשובה"] = (rv["הערה"].astype(str)
                             .str.replace(r".*תשובה:\s*", "", regex=True).str.strip())
        cols = ["מצב", "אנליסט", "מספר בקשה", "שורה", "מקט", "סוג ממצא", "תיאור",
                "חיווי בתאריך", "תוכן התשובה"]
        rv["מצב"] = rv["סטטוס"].map(STATUS_BADGE).fillna(rv["סטטוס"])
        st.dataframe(rv[cols].sort_values(["חיווי בתאריך", "אנליסט"], ascending=[False, True]),
                     use_container_width=True, hide_index=True, height=400)
        st.caption("לסגירה: עבור לטאב 'לפי תקופה', פתח את כרטיס האנליסט, אמת וסמן 'טופל'.")

    st.markdown("---")
    st.markdown("### ✉️ יומן מיילים — מה יצא ומה נכנס")
    st.caption("רישום כרונולוגי דו-כיווני: כל מייל-בקרה שיצא (מסורק ה-Sent) וכל תשובה שנקלטה (מסורק התשובות).")
    if led["shipments"].empty:
        st.info("אין רישומים עדיין — יתמלא אוטומטית מסורק-השליחות (Sent) ומסורק-התשובות.")
    else:
        sh_df = led["shipments"]
        if "סוג" in sh_df.columns:
            vc = sh_df["סוג"].value_counts()
            sent_c = int(vc.get("מייל-נשלח", 0) + vc.get("מעקב-נשלח", 0) + vc.get("משלוח", 0))
            reply_c = int(vc.get("מענה", 0))
            st.markdown(f"<div class='note'>📤 <b>{sent_c}</b> מיילים שיצאו · "
                        f"📩 <b>{reply_c}</b> סבבי-תשובות · {len(sh_df)} רשומות סה\"כ</div>",
                        unsafe_allow_html=True)
        st.dataframe(sh_df.iloc[::-1], use_container_width=True, hide_index=True)

# ---------- תפוקה ----------
with tab_prod:
    p = led["prod"]
    if p.empty:
        st.info("גרור דוח תפוקה (או תור מיילים) כדי לראות נתוני תפוקה.")
    else:
        pp = p.copy()
        pp["סהכ"] = pd.to_numeric(pp["סהכ"], errors="coerce").fillna(0)
        fig = px.bar(pp, x="אנליסט", y="סהכ", color="תקופת בקרה", barmode="group")
        fig.update_layout(title=rtl_title("תנועות טיפול לפי אנליסט ותקופה"), height=360, **PLOTLY_DARK)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(p.iloc[::-1], use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("<div class='note'>לוח בקרת קטלוג · המאגר בתיקייה השיתופית הוא מקור האמת · "
            "כל שינוי נשמר עם גיבוי מתוארך</div>", unsafe_allow_html=True)
