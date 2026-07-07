# -*- coding: utf-8 -*-
"""
לוח בקרת קטלוג — דשבורד ניהול ממצאים
דף חי לניהול מעגל-הבקרה המלא: קליטת ריצות (בגרירה), מעקב למי נשלח,
חיווי שנצפה, טיפול וסגירה. עיצוב כהה עם נורות ירוק/כתום/אדום.
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
  .stApp { direction: rtl; }
  section[data-testid="stSidebar"] { direction: rtl; }
  .stApp, .stMarkdown, p, span, label, input { font-family: "Segoe UI", Arial, sans-serif; }
  h1, h2, h3 { letter-spacing: 0.3px; }
  div[data-testid="stMetric"] { background: #151a22; border: 1px solid #232a35;
      border-radius: 12px; padding: 14px 16px; }
  .kpi { background:#151a22; border:1px solid #232a35; border-radius:14px;
         padding:16px 18px; text-align:center; }
  .kpi .v { font-size:34px; font-weight:700; line-height:1.1; }
  .kpi .t { font-size:13px; color:#8b93a3; margin-top:4px; }
  .kpi.red    { border-right: 5px solid #ef4444; }  .kpi.red .v    { color:#ef4444; }
  .kpi.orange { border-right: 5px solid #f59e0b; }  .kpi.orange .v { color:#f59e0b; }
  .kpi.green  { border-right: 5px solid #22c55e; }  .kpi.green .v  { color:#22c55e; }
  .kpi.blue   { border-right: 5px solid #38bdf8; }  .kpi.blue .v   { color:#38bdf8; }
  .kpi.gray   { border-right: 5px solid #6b7280; }  .kpi.gray .v   { color:#6b7280; }
  .chip { display:inline-block; background:#151a22; border:1px solid #232a35; border-radius:20px;
          padding:5px 14px; margin:0 4px 4px 0; font-size:13px; color:#c7cdd9; }
  .chip b { color:#e5e9f0; }
  div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { direction: ltr; }
  div[data-testid="stFileUploader"] { border: 2px dashed #2c3646; border-radius: 14px;
      padding: 8px; background: #10151d; }
  .stTabs [data-baseweb="tab"] { font-size: 15px; }
  .note { color:#8b93a3; font-size:13px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
PLOTLY_DARK = dict(template="plotly_dark", paper_bgcolor="#0b0e13", plot_bgcolor="#0b0e13")
STATUS_BADGE = {"פתוח": "🟠 פתוח", "נשלח": "🟡 נשלח", "נצפה": "🔵 נצפה",
                "בטיפול": "🟡 בטיפול", "טופל": "🟢 טופל", "לא רלוונטי": "⚪ לא רלוונטי"}


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

# ---------------------------------------------------------------- כותרת (נקייה — בלי קוביות)

st.markdown("# 🎛️ לוח בקרת קטלוג")

# ---------------------------------------------------------------- טאבים
# 'לפי תקופה' ראשון — זו מסך העבודה היומיומי; 'סקירה' (תמונת-על כוללת) משנית.

tab_period, tab_over, tab_manage, tab_ingest, tab_ship, tab_prod = st.tabs(
    ["📄 לפי תקופה", "📊 סקירה", "📋 ניהול ממצאים (הכל)", "📥 קליטה בגרירה", "✉️ משלוחים", "📈 תפוקה"])

# ---------- לפי תקופה — מסך העבודה הראשי: בעיות הקובץ, למי נשלח, וניהול מלא ----------
with tab_period:
    if f_all.empty:
        st.info("המאגר ריק — גרור ריצה ראשונה בטאב 'קליטה בגרירה'.")
    else:
        periods = sorted(f_all["תקופת בקרה"].unique(), reverse=True)
        sel = st.selectbox("תקופת בקרה", periods)
        g = f_all[f_all["תקופת בקרה"] == sel]
        side_mask = g["סוג ממצא"].isin(core.SIDE_TYPES)
        act = g[~side_mask]   # ממצאים לטיפול בפועל (בלי 'בצד')

        n_total = len(act)
        n_sent = int((act["סטטוס"] == "נשלח").sum())
        n_progress = int(act["סטטוס"].isin(["נצפה", "בטיפול"]).sum())
        n_done = int(act["סטטוס"].isin(core.CLOSED_STATUSES).sum())
        n_late = int(act["באיחור"].sum())

        # 4 קוביות בלבד — הכי חשוב, בלי כפילויות; 'באיחור' מופיעה רק אם יש בפועל
        cards = [(n_total, "ממצאים בתקופה", "blue"),
                 (n_sent, "נשלחו — ממתינים למענה", "orange" if n_sent else "gray"),
                 (n_progress, "נצפו / בטיפול", "blue" if n_progress else "gray"),
                 (n_done, "טופלו", "green" if n_done else "gray")]
        if n_late:
            cards.append((n_late, "באיחור", "red"))
        kk = st.columns(len(cards))
        for col, (v, t, c) in zip(kk, cards):
            col.markdown(f"<div class='kpi {c}'><div class='v'>{v}</div><div class='t'>{t}</div></div>",
                         unsafe_allow_html=True)

        # פירוט לפי סוג-ממצא — שורת-צ'יפים קומפקטית, לא קוביות נוספות
        tc = act["סוג ממצא"].value_counts()
        if not tc.empty:
            chips = "".join(f"<span class='chip'><b>{n}</b> {t}</span>" for t, n in tc.items())
            st.markdown(f"<div style='margin:8px 0 4px'>{chips}</div>", unsafe_allow_html=True)
        if int(side_mask.sum()):
            st.caption(f"ℹ️ בנוסף {int(side_mask.sum())} ממצאי 'מיפוי בצד' (PROD וכו') — בלי מייל, לא בטיפול.")

        st.markdown("---")

        # מבט 1 — למי נשלחו מיילים ומה הסטטוס (מצומצם: עמודת התקדמות אחת במקום 4)
        st.markdown("#### ✉️ מי קיבל מייל, ומה הסטטוס")
        pr = core.period_analyst_rows(g)
        if not pr.empty:
            pr = pr.copy()
            pr["התקדמות"] = pr["טופל"].astype(str) + " / " + pr["ממצאים"].astype(str) + " טופלו"
            show = pr[["אנליסט", "כתובת מייל", "ממצאים", "נשלח בתאריך", "התקדמות", "חיווי התקבל"]]
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            st.caption("עדיין לא נשלחו מיילים בתקופה זו.")

        st.markdown("---")

        # מבט 2 — ניהול מלא של הממצאים: עריכה + סימון-כנשלח ישירות כאן (בלי לעבור טאב)
        st.markdown(f"#### 📋 ניהול הממצאים בקובץ {sel}")
        st.markdown("<div class='note'>סמן שורות (עמודת 'בחר') כדי לסמן אותן כנשלחו-היום, "
                    "או ערוך ישירות סטטוס/הערה ולחץ שמור.</div>", unsafe_allow_html=True)
        gv = g.copy()
        gv.insert(0, "בחר", False)
        cols_show = ["בחר", "סטטוס", "מספר בקשה", "שורה", "מקט", "סוג ממצא", "תיאור",
                     "נמצא", "צפוי", "אנליסט", "נשלח בתאריך", "חיווי בתאריך", "הערה", "מזהה"]
        edited_p = st.data_editor(
            gv[cols_show].sort_values(["סוג ממצא", "אנליסט"]),
            hide_index=True, use_container_width=True, height=420,
            disabled=[c for c in cols_show if c not in ("בחר", "סטטוס", "הערה")],
            column_config={
                "סטטוס": st.column_config.SelectboxColumn("סטטוס", options=core.STATUSES, width="small"),
                "בחר": st.column_config.CheckboxColumn(" ", width="small"),
                "מזהה": None,
            }, key=f"period_editor_{sel}")

        ac1, ac2, ac3 = st.columns([1.3, 1.3, 2])
        if ac1.button("✅ סמן נבחרים כ-נשלח היום", use_container_width=True, key=f"mark_sent_{sel}"):
            ids_sel = edited_p.loc[edited_p["בחר"], "מזהה"].tolist()
            edits = {fid: {"סטטוס": "נשלח", "נשלח בתאריך": core.today_str()} for fid in ids_sel}
            n = update_findings(edits, "mark-sent")
            if persist():
                st.session_state.flash = f"סומנו {len(ids_sel)} ממצאים כנשלחו היום"
            st.rerun()
        if ac2.button("💾 שמור שינויים", type="primary", use_container_width=True, key=f"save_p_{sel}"):
            edits = {r["מזהה"]: {"סטטוס": r["סטטוס"], "הערה": r["הערה"]} for _, r in edited_p.iterrows()}
            changed = update_findings(edits, "edit")
            saved = persist()
            st.session_state.flash = f"עודכנו {changed} שדות" + ("" if saved else " — בזיכרון בלבד!")
            st.rerun()
        an_opts = sorted(set(g["אנליסט"]) - {""})
        if an_opts:
            sel_an = ac3.selectbox("חיווי מהיר (אישר בע\"פ)", an_opts, key=f"seen_an_{sel}",
                                   label_visibility="collapsed", placeholder="חיווי מהיר לפי אנליסט...")
            if st.button(f"👁️ סמן ל-{sel_an} כנצפה", key=f"seen_btn_{sel}"):
                n = core.mark_analyst_seen(led, sel_an)
                persist()
                st.session_state.flash = f"סומן חיווי ל-{n} ממצאים של {sel_an}"
                st.rerun()

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
                    bar_color = "#ef4444"
                elif pct >= 80:
                    bar_color = "#22c55e"
                elif pct >= 40:
                    bar_color = "#f59e0b"
                else:
                    bar_color = "#38bdf8"
                late_badge = (f"<span style='color:#ef4444;font-weight:700'> 🔴 {r['באיחור']} באיחור</span>"
                              if r["באיחור"] else "")
                st.markdown(
                    f"<div style='background:#151a22;border:1px solid #232a35;border-radius:10px;"
                    f"padding:10px 14px;margin:6px 0'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:14px'>"
                    f"<span><b>{r['אנליסט']}</b>{late_badge}</span>"
                    f"<span class='note'>נשלחו {r['נשלחו']} · נצפו/בטיפול {r['נצפו/בטיפול']} · "
                    f"טופלו {r['טופלו']} מתוך {r['סהכ']}</span></div>"
                    f"<div style='background:#232a35;border-radius:6px;height:10px;margin-top:8px'>"
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
    mark_sent = st.checkbox("סמן ממצאים חדשים כ'נשלח' מיד (המיילים יוצאים בסוף הריצה)", value=True)

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
                    res = core.merge_findings(led, parsed, mark_sent=mark_sent)
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
                                tag = "תשובה→נצפה" if res["mail_type"] == "מענה" else "משלוח→נשלח"
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

# ---------- משלוחים ----------
with tab_ship:
    st.markdown("### יומן משלוחים ומענים")
    per_opts = sorted(f_all["תקופת בקרה"].unique()) if not f_all.empty else []
    if per_opts:
        cc1, cc2 = st.columns([2, 1])
        sel_p = cc1.selectbox("סימון מהיר — כל ממצאי התקופה שנפתחו יסומנו כנשלחו היום", per_opts)
        if cc2.button("✅ סמן כנשלחו", use_container_width=True):
            n = core.mark_period_sent(led, sel_p)
            persist()
            st.session_state.flash = f"סומנו {n} ממצאים כנשלחו"
            st.rerun()
    if led["shipments"].empty:
        st.info("אין משלוחים רשומים עדיין — גרור מייל שנשלח, או השתמש בסימון המהיר.")
    else:
        st.dataframe(led["shipments"].iloc[::-1], use_container_width=True, hide_index=True)

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
