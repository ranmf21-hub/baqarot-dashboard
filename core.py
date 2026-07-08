# -*- coding: utf-8 -*-
"""
core.py — שכבת הנתונים של לוח בקרת הקטלוג.
מאגר ממצאים מתמשך + קליטת קבצים מהצינור (תור מיילים / קובץ בקרה / תפוקה / מיילים).
מופרד מ-app.py כדי שאפשר יהיה לבדוק את הלוגיקה בלי Streamlit.
"""
import io
import os
import re
import json
import datetime as dt
import urllib.parse

import pandas as pd

# ---------------------------------------------------------------- קבועים

# מודל הסטטוסים — מינימלי, לפי התהליך בפועל ומה שהמנהל באמת יכול לדעת:
#   נשלח        — המייל יצא (אוטומטית עם פריקת הקובץ). ממתין. זה מצב-הכניסה.
#   בטיפול      — בעבודה / לא-סגור-עדיין: שאלתי מייל-מעקב, או האנליסט מטפל, או תוקן-אך-לא-כשורה
#                 (עם הערה). מצב-הביניים היחיד. (בלע גם את "נצפה"/"התקבל מענה" — אי אפשר לדעת פר-שורה
#                 אם מייל נצפה/נענה, וזה ממילא אותו דבר כמו 'בעבודה').
#   טופל        — אימתתי שתוקן. (סגור)
#   לא רלוונטי  — אינו ממצא אמיתי / מסומן בצד. (סגור)
# ("פתוח" הוסר: הפריקה תמיד שולחת מייל.)
STATUSES = ["נשלח", "בטיפול", "טופל", "לא רלוונטי"]
CLOSED_STATUSES = {"טופל", "לא רלוונטי"}
ACTIVE_STATUSES = ["נשלח", "בטיפול"]   # דורשים מעקב (לא סגורים)
REPLIED_STATUSES = ["בטיפול"]           # בעבודה (מצב-הביניים)

STATUS_COLORS = {
    "נשלח":      "#dba13a",   # ענבר — ממתין
    "בטיפול":    "#4ea7fc",   # תכלת — בעבודה
    "טופל":      "#4cb782",   # ירוק — הושלם
    "לא רלוונטי": "#6b7280",  # אפור — נדחה
}
# מיפוי סטטוסים ישנים -> חדשים (מיגרציה של נתונים קיימים)
STATUS_MIGRATE = {"פתוח": "נשלח", "נצפה": "בטיפול", "התקבל מענה": "בטיפול"}


def followup_tag(req, line) -> str:
    """תגית-מזהה בנושא המייל — הסורק מחלץ אותה מהתשובה כדי לקשר לממצא המדויק."""
    return f"[#{str(req).strip()}-{str(line).strip()}]"


def _followup_subject_body(row):
    g = (lambda k: str(row.get(k, "") or ""))
    req, line = g("מספר בקשה"), g("שורה")
    subj = f"מעקב בקרת קטלוג — בקשה {req} שורה {line} {followup_tag(req, line)}"
    body = (
        "שלום,\n\n"
        "בהמשך לבקרת הקטלוג השוטפת, נא לאשר את הטיפול בפריט הבא:\n\n"
        f"מספר בקשה: {req}\n"
        f"שורה: {line}\n"
        f'מק"ט: {g("מקט")}\n'
        f"תיאור: {g('תיאור')}\n"
        f"סוג הבעיה: {g('סוג ממצא')}  (נמצא {g('נמצא')}, צפוי {g('צפוי')})\n\n"
        "האם הפריט טופל? נא להשיב: טופל / עדיין בטיפול.\n\n"
        "תודה."
    )
    return subj, body


def _bulk_subject_body(sub):
    lines = [f"• בקשה {r['מספר בקשה']} שורה {r['שורה']} (מק\"ט {r['מקט']}) — "
             f"{r['סוג ממצא']}: {r['תיאור']}" for _, r in sub.iterrows()]
    # התקופה בכותרת — כדי שהסורקים (תשובות/שליחות) יזהו את מייל-הבולק לפי תקופה+אנליסט
    try:
        per = str(sub["תקופת בקרה"].iloc[0] or "").strip()
    except Exception:
        per = ""
    subj = (f"מעקב בקרת קטלוג {per} — אישור טיפול בפריטים" if per
            else "מעקב בקרת קטלוג — אישור טיפול בפריטים")
    body = ("שלום,\n\nבהמשך לבקרת הקטלוג, נא לאשר את הטיפול בפריטים הבאים "
            "(להשיב ליד כל פריט: טופל / עדיין בטיפול):\n\n" + "\n".join(lines) + "\n\nתודה.")
    return subj, body


def followup_mailto(row) -> str:
    """קישור mailto (עובד 1-קליק אם Outlook הוא תוכנת ברירת-המחדל למייל)."""
    subj, body = _followup_subject_body(row)
    q = urllib.parse.quote
    return f"mailto:{str(row.get('נמען','') or '')}?subject={q(subj)}&body={q(body)}"


def followup_mailto_bulk(sub, to) -> str:
    subj, body = _bulk_subject_body(sub)
    q = urllib.parse.quote
    return f"mailto:{to}?subject={q(subj)}&body={q(body)}"


def _esc(v):
    import html as _h
    return _h.escape(str(v if v is not None else ""))


# --- מיילי-מעקב: תואם-Outlook, טקסט תקין ---
# שני כללים חשובים ל-Outlook (מנוע Word):
#  1) מתעלם מ-max-width/margin:auto → מרכוז ורוחב-קבוע דרך טבלה חיצונית (align=center) + width כתכונה.
#  2) tekst משתבש כשמשתמשים ב-dir="rtl" כתכונת-HTML על טבלאות → משתמשים ב-CSS direction:rtl בלבד.
_FONT = "font-family:Arial,'Segoe UI',sans-serif;"
_RTL = "direction:rtl;text-align:right;"
CARD_W = 600


def _cta(bulk=False):
    per = "ליד כל פריט" if bulk else "למייל זה"
    return (
        '<div style="background:#FFF8E1;border-right:5px solid #F5A623;padding:14px 18px;'
        f'margin:18px 0;{_RTL}{_FONT}">'
        '<div style="font-size:17px;font-weight:bold;color:#B26A00;">האם הפריט טופל?</div>'
        f'<div style="font-size:14px;color:#444444;margin-top:7px;">נא להשיב {per} עם אחת התשובות: '
        '<span style="background:#E8F5E9;color:#1a7f37;font-weight:bold;padding:2px 10px;">טופל</span>'
        '&nbsp;&nbsp;<span style="background:#FDECEA;color:#C00000;font-weight:bold;padding:2px 10px;">עדיין בטיפול</span>'
        '<br><span style="color:#777777;">אם עדיין בטיפול — נא לפרט מה חסר.</span></div></div>'
    )


def _email_shell(intro, inner, bulk=False):
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>'
        f'<body style="margin:0;padding:0;background:#eef1f4;{_RTL}{_FONT}">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f4;">'
        '<tr><td align="center" style="padding:20px 10px;">'
        f'<table width="{CARD_W}" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:{CARD_W}px;background:#ffffff;border:1px solid #dfe3e8;">'
        f'<tr><td style="background:#2C3E50;color:#ffffff;padding:15px 22px;{_FONT}font-size:18px;'
        f'font-weight:bold;{_RTL}">מעקב בקרת קטלוג — בקשה לאישור טיפול</td></tr>'
        f'<tr><td style="padding:20px 22px;{_FONT}font-size:15px;color:#333333;{_RTL}">'
        '<div style="margin:0 0 6px;">שלום,</div>'
        f'<div style="margin:0 0 14px;">{intro}</div>'
        f'{inner}{_cta(bulk)}'
        '<div style="margin-top:24px;padding-top:10px;border-top:1px solid #eeeeee;'
        'font-size:13px;color:#888888;">בברכה,<br>צוות בקרת הקטלוג</div>'
        '</td></tr></table></td></tr></table></body></html>'
    )


def _detail_row(lbl, val):
    return (f'<tr>'
            f'<td width="105" style="width:105px;padding:9px 13px;background:#f4f6f8;font-weight:bold;'
            f'border:1px solid #e3e7ec;color:#333333;{_RTL}{_FONT}font-size:14px;">{lbl}</td>'
            f'<td style="padding:9px 13px;border:1px solid #e3e7ec;color:#222222;'
            f'{_RTL}{_FONT}font-size:14px;">{val}</td></tr>')


def _followup_html(row):
    g = (lambda k: _esc(row.get(k, "")))
    issue = (f'{g("סוג ממצא")} — נמצא <b style="color:#C00000;">{g("נמצא")}</b>, '
             f'צפוי <b style="color:#1a7f37;">{g("צפוי")}</b>')
    rows = (_detail_row("מספר בקשה", g("מספר בקשה")) + _detail_row("שורה", g("שורה")) +
            _detail_row('מק"ט', g("מקט")) + _detail_row("תיאור הפריט", g("תיאור")) +
            _detail_row("הבעיה שנמצאה", issue))
    # רוחב-קבוע 440 (לא נמרח), RTL דרך CSS בלבד (בלי dir="rtl" שמשבש ב-Outlook)
    inner = ('<table width="440" cellpadding="0" cellspacing="0" border="0" '
             f'style="width:440px;border-collapse:collapse;{_RTL}">{rows}</table>')
    return _email_shell("בבקרת הקטלוג השוטפת נמצא ליקוי בפריט שקטלגת. נבקש לאשר את סטטוס הטיפול:", inner)


def _bulk_html(sub):
    th = (f'style="background:#2C3E50;color:#ffffff;padding:9px 11px;{_FONT}font-size:13px;'
          'border:1px solid #223;font-weight:bold;text-align:center;"')
    td = f'style="padding:8px 11px;border:1px solid #e3e7ec;{_FONT}font-size:13px;color:#222222;text-align:center;"'
    tdr = f'style="padding:8px 11px;border:1px solid #e3e7ec;{_FONT}font-size:13px;color:#222222;text-align:right;"'
    tde = (f'style="padding:8px 11px;border:1px solid #e3e7ec;{_FONT}font-size:13px;'
           'color:#C00000;font-weight:bold;text-align:center;"')
    body = ""
    for _, r in sub.iterrows():
        g = (lambda k: _esc(r.get(k, "")))
        body += (f'<tr><td {td}>{g("מספר בקשה")}</td><td {td}>{g("שורה")}</td>'
                 f'<td {td}>{g("מקט")}</td><td {tdr}>{g("תיאור")}</td><td {tde}>{g("סוג ממצא")}</td></tr>')
    inner = ('<table width="100%" cellpadding="0" cellspacing="0" border="0" '
             f'style="width:100%;border-collapse:collapse;{_RTL}">'
             f'<tr><th {th}>מס\' בקשה</th><th {th}>שורה</th><th {th}>מק"ט</th>'
             f'<th {th}>תיאור הפריט</th><th {th}>הבעיה</th></tr>{body}</table>')
    return _email_shell("בבקרת הקטלוג נמצאו הליקויים הבאים בפריטים שקטלגת. "
                        "נבקש לאשר את סטטוס הטיפול בכל אחד:", inner, bulk=True)


def _make_eml(to, subj, plain, html) -> bytes:
    """בונה .eml מעוצב (HTML) עם X-Unsent:1 — נפתח ישירות בחלון-כתיבה של Outlook שולחן-העבודה,
    ללא תלות בתוכנת ברירת-המחדל של הדפדפן. גרסת-טקסט פשוטה כגיבוי."""
    from email.message import EmailMessage
    msg = EmailMessage()
    if to:
        msg["To"] = to
    msg["Subject"] = subj
    msg["X-Unsent"] = "1"                    # הדגל שגורם ל-Outlook לפתוח כטיוטה לעריכה ושליחה
    msg.set_content(plain, cte="base64")                    # text/plain (גיבוי)
    msg.add_alternative(html, subtype="html", cte="base64")  # base64 יציב יותר ב-Outlook מ-QP
    return msg.as_bytes()


def followup_eml(row) -> bytes:
    """טיוטת Outlook מעוצבת (.eml) לפריט בודד."""
    subj, plain = _followup_subject_body(row)
    return _make_eml(str(row.get("נמען", "") or ""), subj, plain, _followup_html(row))


def followup_eml_bulk(sub, to) -> bytes:
    """טיוטת Outlook מעוצבת (.eml) לכל הפריטים הפתוחים של אנליסט."""
    subj, plain = _bulk_subject_body(sub)
    return _make_eml(to, subj, plain, _bulk_html(sub))


def migrate_statuses(df):
    """ממיר סטטוסים ישנים לחדשים בעמודת 'סטטוס' (in-place-safe)."""
    if df is None or df.empty or "סטטוס" not in df.columns:
        return df
    df["סטטוס"] = df["סטטוס"].replace(STATUS_MIGRATE)
    return df

FINDING_TYPES = {"שגיאה": "שגיאת סיווג", "יחידה": "יחידת מידה",
                 "מיפוי": "מיפוי חסר", "מיפוי-צד": "מיפוי חסר (בצד)", "רשומה": "רשומה חסרה"}
TYPE_COLORS = {"שגיאת סיווג": "#eb5757", "יחידת מידה": "#dba13a",
               "מיפוי חסר": "#8b83f0", "מיפוי חסר (בצד)": "#6b7280", "רשומה חסרה": "#4ea7fc"}
MAILABLE_Z = {"Z001", "Z002", "Z003", "Z004"}   # פער-מיפוי בסוגים אלה = ממצא אמיתי (מייל)
OK_MISSING_Z = {"Z005", "Z028"}                  # רשומה-חסרה בסוגים אלה = תקין, לא ממצא
SIDE_TYPES = {"מיפוי חסר (בצד)"}                 # מסומן בצד — בלי מייל, סטטוס 'לא רלוונטי'
_DEFAULT_EXPECTED = {"יחידה": "EA", "מיפוי": "אין כלל בקובץ העזר",
                     "מיפוי-צד": "אין כלל בקובץ העזר", "רשומה": "השלמת נתונים בפריקה"}

FINDINGS_COLS = [
    "מזהה", "תקופת בקרה", "סוג ממצא", "מספר בקשה", "שורה", "מקט", "תיאור",
    "נמצא", "צפוי", "אנליסט", "נמען", "נמצא בתאריך", "נשלח בתאריך",
    "חיווי בתאריך", "מקור חיווי", "סטטוס", "הערה", "עדכון אחרון",
]
SHIPMENTS_COLS = ["תאריך", "סוג", "נמען", "נושא", "תקופה", "פרטים", "מקור"]
PROD_COLS = ["תקופת בקרה", "אנליסט", "שם משתמש", "סהכ", "C030", "C040", "C090", "נקלט בתאריך"]

SHEET_FINDINGS, SHEET_SHIPMENTS, SHEET_PROD = "ממצאים", "משלוחים", "תפוקה"

DEFAULT_MAIL_DOMAIN = "moh.gov.il"


def today_str() -> str:
    return dt.date.today().strftime("%d.%m.%Y")


def now_str() -> str:
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M")


# ---------------------------------------------------------------- מבנה המאגר

def empty_ledger() -> dict:
    return {
        "findings": pd.DataFrame(columns=FINDINGS_COLS),
        "shipments": pd.DataFrame(columns=SHIPMENTS_COLS),
        "prod": pd.DataFrame(columns=PROD_COLS),
    }


def load_ledger(path_or_buffer) -> dict:
    """טוען מאגר מקובץ xlsx (נתיב או buffer). גיליונות חסרים -> ריקים."""
    led = empty_ledger()
    xl = pd.ExcelFile(path_or_buffer, engine="openpyxl")
    mapping = {SHEET_FINDINGS: ("findings", FINDINGS_COLS),
               SHEET_SHIPMENTS: ("shipments", SHIPMENTS_COLS),
               SHEET_PROD: ("prod", PROD_COLS)}
    for sheet, (key, cols) in mapping.items():
        if sheet in xl.sheet_names:
            df = xl.parse(sheet, dtype=str).fillna("")
            for c in cols:            # עמודות חדשות בגרסאות עתידיות
                if c not in df.columns:
                    df[c] = ""
            extra = [c for c in df.columns if c not in cols]   # עמודות שהמשתמש הוסיף — נשמרות
            led[key] = df[cols + extra].astype(str)
    migrate_statuses(led["findings"])
    return led


def save_ledger(led: dict, path: str | None = None) -> bytes:
    """שומר את המאגר. אם ניתן נתיב — כותב אליו (עם גיבוי); תמיד מחזיר bytes להורדה."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        led["findings"].to_excel(w, sheet_name=SHEET_FINDINGS, index=False)
        led["shipments"].to_excel(w, sheet_name=SHEET_SHIPMENTS, index=False)
        led["prod"].to_excel(w, sheet_name=SHEET_PROD, index=False)
        for ws in w.book.worksheets:
            ws.sheet_view.rightToLeft = True
    data = buf.getvalue()
    if path:
        if os.path.exists(path):  # גיבוי מתוארך לפני דריסה
            bdir = os.path.join(os.path.dirname(path) or ".", "גיבוי מאגר")
            os.makedirs(bdir, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(bdir, f"מאגר_{stamp}.xlsx"), "wb") as b, open(path, "rb") as src:
                b.write(src.read())
        with open(path, "wb") as f:
            f.write(data)
    return data


# ---------------------------------------------------------------- שדות נגזרים

def _parse_date(s: str):
    s = str(s or "").strip()
    if not s:
        return None
    s = s.split()[0]  # חיתוך רכיב-שעה ('2026-06-25 00:00:00' מעריכה באקסל)
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:  # רשת ביטחון לפורמטים אחרים
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return None if pd.isna(d) else d.date()
    except Exception:
        return None


def days_open(row) -> int:
    if row.get("סטטוס", "") in CLOSED_STATUSES:
        return 0
    d = _parse_date(row.get("נמצא בתאריך", ""))
    return (dt.date.today() - d).days if d else 0


def with_derived(f: pd.DataFrame, reminder_days: int) -> pd.DataFrame:
    """מוסיף עמודות נגזרות לתצוגה: ימים פתוח, באיחור, נורה."""
    f = f.copy()
    if f.empty:
        f["ימים פתוח"], f["באיחור"], f["נורה"] = [], [], []
        return f
    f["ימים פתוח"] = f.apply(days_open, axis=1)
    f["באיחור"] = (f["ימים פתוח"] >= reminder_days) & (~f["סטטוס"].isin(CLOSED_STATUSES))
    def lamp(r):
        if r["סטטוס"] == "טופל":
            return "🟢"
        if r["סטטוס"] == "לא רלוונטי":
            return "⚪"
        if r["באיחור"]:
            return "🔴"
        if r["סטטוס"] in REPLIED_STATUSES:   # בטיפול
            return "🔵"
        return "🟡"                          # נשלח — ממתין
    f["נורה"] = f.apply(lamp, axis=1)
    return f


def finding_id(req, line, ftype, period="") -> str:
    # התקופה חלק מהזהות: ממצא שחוזר בבקרה מאוחרת = שורה חדשה, לא כפילות שקטה
    return f"{str(req).strip()}|{str(line).strip()}|{ftype}|{str(period).strip()}"


def analyst_email(user: str) -> str:
    u = str(user or "").strip()
    if not u or " " in u:
        return ""
    return u.lower() + "@" + DEFAULT_MAIL_DOMAIN


# ---------------------------------------------------------------- קליטה: תור מיילים

_PERIOD_RE = re.compile(r"(\d{2}[.\-]\d{2}(?:\.\d{4})?\s*-\s*\d{2}[.\-]\d{2}\.\d{4}|\d{2}-\d{2}\.\d{2}\.\d{4})")


def parse_mail_queue(data: bytes) -> dict:
    """mail_queue.txt (UTF-16 LE, טאבים) -> ממצאים + תפוקה + תקופה."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:  # קובץ שנשמר-מחדש ידנית כ-UTF-8
        text = data.decode("utf-8-sig", errors="replace")
    period, findings, prod = "", [], []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        p = ln.split("\t")
        tag = p[0]
        if tag == "META" and len(p) >= 2:
            period = p[1]
        elif tag == "PROD" and len(p) >= 7:
            prod.append({"אנליסט": p[1], "שם משתמש": p[2], "סהכ": p[3],
                         "C030": p[4], "C040": p[5], "C090": p[6]})
        elif tag in FINDING_TYPES and len(p) >= 8:
            findings.append({
                "סוג ממצא": FINDING_TYPES[tag], "אנליסט": p[1],
                "מספר בקשה": p[2], "שורה": p[3], "מקט": p[4], "תיאור": p[5],
                "נמצא": p[6], "צפוי": p[7] if p[7] else _DEFAULT_EXPECTED.get(tag, ""),
            })
    return {"kind": "queue", "period": period, "findings": findings, "prod": prod}


# ---------------------------------------------------------------- קליטה: קובץ בקרה

def _period_from_name(name: str) -> str:
    # מעדיפים תמיד את תבנית-התאריכים הנקייה — עמיד לשמות כמו "... (vbs) (1).xlsx"
    m = _PERIOD_RE.search(name)
    if m:
        return m.group(1).strip()
    m = re.search(r"קטלוג שוטף\s+(.+?)\s*(?:\(vbs\))?\s*\.xlsx$", name)
    return m.group(1).strip() if m else ""


def parse_control_xlsx(data: bytes, filename: str = "") -> dict:
    """קובץ בקרה -> ממצאים (השוואה=FALSE + יחידה שאינה EA)."""
    wb = pd.read_excel(io.BytesIO(data), sheet_name="בקרה", header=0, dtype=object, engine="openpyxl")
    cols = list(wb.columns)

    def col(i):  # אינדקס 0-בסיס לפי מבנה 37 העמודות הקבוע
        return wb[cols[i]] if i < len(cols) else pd.Series([None] * len(wb))

    def nz(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    findings = []
    for i in range(len(wb)):
        req, line = nz(col(0)[i]), nz(col(1)[i])
        if not req:
            continue
        base = {"מספר בקשה": req, "שורה": line, "מקט": nz(col(3)[i]),
                "תיאור": nz(col(8)[i]), "אנליסט": nz(col(6)[i])}
        D = base["מקט"]
        E = nz(col(4)[i])       # סוג חומר
        W = nz(col(22)[i])      # היררכיה
        Zc = nz(col(25)[i])     # שרשור סוג+המרה
        AA = nz(col(26)[i])     # סיווג צפוי
        ab = col(27)[i]
        if ab is False or nz(ab).upper() == "FALSE":
            findings.append({**base, "סוג ממצא": "שגיאת סיווג",
                             "נמצא": nz(col(20)[i]), "צפוי": AA})
        unit = nz(col(13)[i])
        if unit and unit.upper() != "EA":
            findings.append({**base, "סוג ממצא": "יחידת מידה", "נמצא": unit, "צפוי": "EA"})
        # אין כלל מיפוי לצירוף: יש שרשור אך אין סיווג צפוי.
        # Z001-Z004 = ממצא אמיתי (מייל); סוגים אחרים (PROD/Z028...) = מסומן בצד.
        if D and Zc and not AA:
            t = "מיפוי חסר" if E in MAILABLE_Z else "מיפוי חסר (בצד)"
            findings.append({**base, "סוג ממצא": t, "נמצא": Zc, "צפוי": "אין כלל בקובץ העזר"})
        # רשומה חסרה בגלם: תקין רק ל-Z005/Z028; כל סוג אחר = חריג שחייב לצוף.
        if D and not W and E not in OK_MISSING_Z:
            findings.append({**base, "סוג ממצא": "רשומה חסרה",
                             "נמצא": E or "סוג חומר לא ידוע", "צפוי": "השלמת נתונים בפריקה"})
    return {"kind": "control", "period": _period_from_name(filename), "findings": findings, "prod": []}


# ---------------------------------------------------------------- קליטה: תפוקה

def _cell(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


def _num(v) -> int:
    s = _cell(v)
    try:
        return int(float(s)) if s else 0
    except ValueError:
        return 0


def parse_productivity_xlsx(data: bytes, filename: str = "") -> dict:
    df = pd.read_excel(io.BytesIO(data), sheet_name="לפי שלב", header=0, dtype=object, engine="openpyxl")
    period = _period_from_name(filename)
    prod = []
    for _, r in df.iterrows():
        name, user = _cell(r.iloc[0]), _cell(r.iloc[1])
        if not name or not user:                       # שורות ריקות/מפרידות
            continue
        if name.replace('"', "").replace("'", "") in ("סהכ", "סה'כ"):   # שורת הסיכום
            continue
        prod.append({"אנליסט": name, "שם משתמש": user,
                     "C030": str(_num(r.iloc[2])), "C040": str(_num(r.iloc[3])),
                     "C090": str(_num(r.iloc[4])), "סהכ": str(_num(r.iloc[5]))})
    return {"kind": "prod", "period": period, "findings": [], "prod": prod}


# ---------------------------------------------------------------- קליטה: מיילים

def _classify_mail(subject: str) -> str:
    s = (subject or "").strip()
    low = s.lower()
    if low.startswith(("re:", "השב:")):            # רק תשובה אמיתית היא מענה
        return "מענה"
    if "דוח תפוקת" in s:
        return "דוח תפוקה"
    if "בקרת קטלוג" in s:                          # כולל FW:/הועבר: של מייל שנשלח
        return "משלוח"
    return "אחר"


def parse_eml(data: bytes) -> dict:
    import email
    from email import policy
    msg = email.message_from_bytes(data, policy=policy.default)
    body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part:
            body = part.get_content()
    except Exception:
        pass
    return _mail_dict(msg.get("subject", ""), msg.get("from", ""), msg.get("to", ""),
                      msg.get("date", ""), body)


def parse_msg(data: bytes) -> dict:
    import tempfile
    import extract_msg
    with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as t:
        t.write(data)
        tmp = t.name
    try:
        m = extract_msg.Message(tmp)
        # שולח: מעדיפים כותרת From (עם כתובת SMTP) על שם-תצוגה
        sender = ""
        try:
            sender = str(m.header.get("From") or "")
        except Exception:
            pass
        if "@" not in sender:
            sender = m.sender or sender
        return _mail_dict(m.subject or "", sender, m.to or "",
                          m.date, (m.body or "")[:2000])   # m.date = datetime אמיתי
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _mail_date(date) -> str:
    """תאריך המייל האמיתי: datetime / RFC-2822 / ISO / dd.mm.yyyy — ואם כלום, היום."""
    if isinstance(date, (dt.datetime, dt.date)):
        return date.strftime("%d.%m.%Y")
    s = str(date or "").strip()
    if not s:
        return today_str()
    try:  # RFC-2822: 'Thu, 18 Jun 2026 09:30:00 +0300'
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%d.%m.%Y")
    except Exception:
        pass
    try:  # ISO: '2026-06-18 09:30:00+03:00'
        return dt.datetime.fromisoformat(s[:19]).strftime("%d.%m.%Y")
    except Exception:
        pass
    mm = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)
    if mm:
        try:
            return dt.date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1))).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return today_str()


def _mail_dict(subject, sender, to, date, body) -> dict:
    m = _PERIOD_RE.search(subject or "")
    return {"kind": "mail", "mail_type": _classify_mail(subject),
            "subject": subject or "", "sender": str(sender or ""), "to": str(to or ""),
            "date": _mail_date(date),
            "period": m.group(1) if m else "", "body": (body or "")[:2000]}


def parse_upload(name: str, data: bytes) -> dict:
    """זיהוי אוטומטי של סוג הקובץ שנגרר."""
    low = name.lower()
    if low.endswith(".txt"):
        return parse_mail_queue(data)
    if low.endswith(".msg"):
        return parse_msg(data)
    if low.endswith(".eml"):
        return parse_eml(data)
    if low.endswith(".xlsx"):
        if "תפוקת" in name:
            return parse_productivity_xlsx(data, name)
        return parse_control_xlsx(data, name)
    raise ValueError(f"סוג קובץ לא מוכר: {name}")


# ---------------------------------------------------------------- מיזוג למאגר

def merge_findings(led: dict, parsed: dict, mark_sent: bool = False, sent_date: str = "") -> dict:
    """ממזג ממצאים שנקלטו למאגר. מחזיר סיכום. שדות ידניים לעולם לא נדרסים.
    sent_date: לקליטת-עבר — תאריך השליחה האמיתי (למשל תאריך קובץ הריצה)."""
    f = led["findings"]
    period = parsed.get("period", "")
    when = sent_date or today_str()
    added = skipped = 0
    for it in parsed.get("findings", []):
        fid = finding_id(it["מספר בקשה"], it["שורה"], it["סוג ממצא"], period)
        if not f.empty and (f["מזהה"] == fid).any():
            skipped += 1
            continue
        side = it.get("סוג ממצא") in SIDE_TYPES   # מסומן בצד — לא נשלח מייל, סגור מראש
        row = {c: "" for c in FINDINGS_COLS}
        row.update({
            "מזהה": fid, "תקופת בקרה": period, **it,
            "נמען": "" if side else analyst_email(it.get("אנליסט", "")),
            "נמצא בתאריך": when,
            # מצב-הכניסה תמיד 'נשלח' — הפריקה שולחת מייל אוטומטית (אין 'פתוח').
            # 'בצד' (PROD וכו') לא נשלח מייל → 'לא רלוונטי'.
            "סטטוס": "לא רלוונטי" if side else "נשלח",
            "נשלח בתאריך": "" if side else when,
            "הערה": "בצד — סוג חומר מחוץ ל-Z001-Z004" if side else "",
            "עדכון אחרון": now_str(),
        })
        f = pd.concat([f, pd.DataFrame([row])[FINDINGS_COLS]], ignore_index=True)
        added += 1
    led["findings"] = f

    # סגירה אוטומטית: קובץ-בקרה/תור-מיילים הוא הרשימה המלאה של הממצאים בתקופה נכון לרגע הריצה —
    # ממצא פתוח מאותה תקופה שלא מופיע יותר בפריקה החדשה = תוקן בפועל (הנתונים חייבים לשקף את הקובץ).
    closed_auto = 0
    if parsed.get("kind") in ("control", "queue") and period:
        current_ids = {finding_id(it["מספר בקשה"], it["שורה"], it["סוג ממצא"], period)
                       for it in parsed.get("findings", [])}
        f = led["findings"]
        for i in f.index:
            if f.at[i, "תקופת בקרה"] != period or f.at[i, "סטטוס"] in CLOSED_STATUSES:
                continue
            if f.at[i, "מזהה"] in current_ids:
                continue
            f.at[i, "סטטוס"] = "טופל"
            f.at[i, "הערה"] = "נסגר אוטומטית — לא נמצא יותר בריצה העדכנית"
            if not f.at[i, "חיווי בתאריך"]:
                f.at[i, "חיווי בתאריך"] = when
            f.at[i, "עדכון אחרון"] = now_str()
            closed_auto += 1
        led["findings"] = f

    prod_added = 0
    if parsed.get("prod"):
        p = led["prod"]
        mask_new = []
        for it in parsed["prod"]:
            exists = (not p.empty and ((p["תקופת בקרה"] == period) & (p["שם משתמש"] == it["שם משתמש"])).any())
            if not exists:
                p = pd.concat([p, pd.DataFrame([{**{c: "" for c in PROD_COLS}, **it,
                                                 "תקופת בקרה": period, "נקלט בתאריך": today_str()}])[PROD_COLS]],
                              ignore_index=True)
                prod_added += 1
        led["prod"] = p
    return {"added": added, "skipped": skipped, "prod_added": prod_added, "period": period, "closed_auto": closed_auto}


def _match_recipient(row_email: str, row_analyst: str, addr: str) -> bool:
    """התאמה לפי כתובת מלאה או לפי החלק-המקומי מול שם המשתמש."""
    a = addr.lower().strip()
    if not a:
        return False
    if row_email.lower() == a:
        return True
    local = a.split("@")[0]
    return bool(local) and local == str(row_analyst or "").lower().strip()


def apply_mail(led: dict, mail: dict) -> dict:
    """מייל שנגרר: משלוח -> ווידוא תאריך-שליחה לממצאי הנמען; מענה -> 'בטיפול' (לאימות).
    בטיחות: בלי נמען/שולח מזוהה — לא מעדכנים כלום (רק נרשם ביומן)."""
    f = led["findings"]
    period, when = mail.get("period", ""), mail.get("date", today_str())
    touched, note = 0, ""
    if mail["mail_type"] == "משלוח":
        rcpts = re.findall(r"[\w.\-]+@[\w.\-]+", str(mail.get("to", "")).lower())
        if not rcpts:
            note = "לא זוהו כתובות נמען במייל — לא עודכנו ממצאים"
        else:
            for i in f.index:
                if period and f.at[i, "תקופת בקרה"] != period:
                    continue
                if not any(_match_recipient(f.at[i, "נמען"], f.at[i, "אנליסט"], a) for a in rcpts):
                    continue
                # משלוח מאשר את השליחה — משלים תאריך-שליחה אם חסר (הסטטוס כבר 'נשלח')
                if not f.at[i, "נשלח בתאריך"]:
                    f.at[i, "נשלח בתאריך"] = when
                    f.at[i, "עדכון אחרון"] = now_str()
                    touched += 1
    elif mail["mail_type"] == "מענה":
        snds = re.findall(r"[\w.\-]+@[\w.\-]+", str(mail.get("sender", "")).lower())
        if not snds:
            note = "לא זוהתה כתובת השולח — לא עודכנו ממצאים (סמן ידנית בטבלה)"
        else:
            snd = snds[0]
            for i in f.index:
                if not _match_recipient(f.at[i, "נמען"], f.at[i, "אנליסט"], snd):
                    continue
                if period and f.at[i, "תקופת בקרה"] != period:
                    continue
                # תשובה התקבלה — ל'בטיפול' (לאימות המנהל). לא מסמנים 'טופל' אוטומטית!
                if f.at[i, "סטטוס"] == "נשלח":
                    f.at[i, "סטטוס"] = "בטיפול"
                    f.at[i, "חיווי בתאריך"] = when
                    f.at[i, "מקור חיווי"] = "מייל"
                    f.at[i, "עדכון אחרון"] = now_str()
                    touched += 1
    led["findings"] = f
    s = led["shipments"]
    ship = {"תאריך": when, "סוג": mail["mail_type"],
            "נמען": mail.get("to") or mail.get("sender", ""),
            "נושא": mail.get("subject", ""), "תקופה": period,
            "פרטים": note or f"עודכנו {touched} ממצאים", "מקור": "גרירת מייל"}
    # אין כפילות ביומן על גרירה חוזרת של אותו מייל
    dup = (not s.empty and ((s["נושא"] == ship["נושא"]) & (s["תאריך"] == ship["תאריך"]) &
                            (s["נמען"] == ship["נמען"]) & (s["סוג"] == ship["סוג"])).any())
    if not dup:
        led["shipments"] = pd.concat([s, pd.DataFrame([ship])[SHIPMENTS_COLS]], ignore_index=True)
    return {"touched": touched, "mail_type": mail["mail_type"], "note": note}


# ---------------------------------------------------------------- Google Sheets (מצב ענן)
# אותו דפוס כמו smart-cataloger: gspread + חשבון-שירות מ-st.secrets, גיליון לפי מפתח.

_GS_MAP = {SHEET_FINDINGS: ("findings", FINDINGS_COLS),
           SHEET_SHIPMENTS: ("shipments", SHIPMENTS_COLS),
           SHEET_PROD: ("prod", PROD_COLS)}


def gs_open(secrets):
    """מתחבר ל-Google Sheets ומחזיר את הגיליון (spreadsheet) של המאגר."""
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(dict(secrets["gcp_service_account"]), scopes=scopes)
    return gspread.authorize(creds).open_by_key(secrets["GOOGLE_SHEET_ID"])


def gs_load_ledger(sh) -> dict:
    led = empty_ledger()
    for title, (key, cols) in _GS_MAP.items():
        try:
            ws = sh.worksheet(title)
        except Exception:
            continue
        vals = ws.get_all_values()
        if len(vals) < 2:
            continue
        df = pd.DataFrame(vals[1:], columns=vals[0]).fillna("")
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        extra = [c for c in df.columns if c not in cols]
        led[key] = df[cols + extra].astype(str)
    migrate_statuses(led["findings"])
    return led


def gs_save_ledger(led: dict, sh):
    """כתיבה מלאה של שלושת הגיליונות (המאגר קטן; היסטוריית-גרסאות של Google מגבה)."""
    for title, (key, cols) in _GS_MAP.items():
        df = led[key].fillna("").astype(str)
        try:
            ws = sh.worksheet(title)
        except Exception:
            ws = sh.add_worksheet(title=title, rows=max(len(df) + 20, 100),
                                  cols=max(len(df.columns) + 2, 25))
        ws.clear()
        data = [list(df.columns)] + df.values.tolist()
        ws.update(range_name="A1", values=data, value_input_option="RAW")


def _peek_queue_period(path: str) -> str:
    """קורא רק את שורת ה-META מתוך mail_queue.txt (בלי לטעון את כל הקובץ) כדי לזהות את התקופה האמיתית."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(4096)
    except OSError:
        return ""
    try:
        text = data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ""
    m = re.search(r"^META\t([^\t\r\n]+)", text, re.M)
    return m.group(1).strip() if m else ""


def scan_folder(root: str) -> list:
    """סורק תיקייה (רקורסיבית) ומאתר את כל תוצרי הצינור לקליטת-עבר מרוכזת."""
    out = []
    if not root or not os.path.isdir(root):
        return out
    skip_dirs = {"גיבוי מאגר", "archive", "__pycache__"}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            if fn.startswith("~$"):
                continue
            low = fn.lower()
            kind = None
            if fn == "mail_queue.txt":
                kind = "תור מיילים"
            elif fn.endswith(".xlsx") and fn.startswith("בקרה - קטלוג שוטף"):
                kind = "קובץ בקרה"
            elif fn.endswith(".xlsx") and fn.startswith("תפוקת אנליסטים"):
                kind = "דוח תפוקה"
            elif low.endswith((".msg", ".eml")):
                kind = "מייל/תשובה"   # מייל שנשלח או תשובת אנליסט
            if not kind:
                continue
            p = os.path.join(dirpath, fn)
            try:
                mt = os.path.getmtime(p)
                mtime = dt.date.fromtimestamp(mt).strftime("%d.%m.%Y")
            except OSError:
                mt, mtime = 0.0, ""
            # תור-מיילים תמיד נקרא "mail_queue.txt" — התקופה נקראת מתוך שורת ה-META בתוכן, לא מהשם
            period = _peek_queue_period(p) if kind == "תור מיילים" else _period_from_name(fn)
            out.append({"סוג": kind, "תקופה": period, "קובץ": fn,
                        "תאריך הריצה": mtime, "נתיב": p, "_mt": mt})
    # קובץ אמת אחד לכל תקופה (לכל סוג בנפרד): כשיש כמה גרסאות/ריצות-חוזרות לאותה תקופה,
    # נקלט רק החדש ביותר — אחרת ממצא שתוקן בריצה מאוחרת "קופץ" בחזרה מגרסה ישנה (פער ה-8/7 של ינואר).
    newest = {}
    dedup_kinds = {"קובץ בקרה", "תור מיילים"}
    for r in out:
        if r["סוג"] in dedup_kinds and r["תקופה"]:
            key = (r["סוג"], r["תקופה"])
            if key not in newest or r["_mt"] > newest[key]["_mt"]:
                newest[key] = r
    out = [r for r in out
           if not (r["סוג"] in dedup_kinds and r["תקופה"] and newest[(r["סוג"], r["תקופה"])] is not r)]
    # קובצי בקרה קודם (מקור הממצאים) → תפוקה → תורים → מיילים אחרונים
    # (המיילים אחרונים כי הם מסמנים ממצאים שכבר חייבים להיות במאגר).
    order = {"קובץ בקרה": 0, "דוח תפוקה": 1, "תור מיילים": 2, "מייל/תשובה": 3}
    out.sort(key=lambda r: (order.get(r["סוג"], 9), r["תקופה"]))
    for r in out:
        r.pop("_mt", None)
    return out


def mark_analyst_seen(led: dict, analyst: str, source: str = "ידני") -> int:
    """סימון בטיפול בקליק: ממצאי האנליסט שב'נשלח' -> 'בטיפול'."""
    f, n = led["findings"], 0
    for i in f.index:
        if f.at[i, "אנליסט"] == analyst and f.at[i, "סטטוס"] == "נשלח":
            f.at[i, "סטטוס"] = "בטיפול"
            f.at[i, "חיווי בתאריך"] = today_str()
            f.at[i, "מקור חיווי"] = source
            f.at[i, "עדכון אחרון"] = now_str()
            n += 1
    led["findings"] = f
    return n


def period_analyst_rows(g: pd.DataFrame) -> pd.DataFrame:
    """לכל אנליסט בתקופה: כתובת שאליה נשלח, כמה ממצאים, מתי נשלח, פילוח סטטוס, מתי התקבל חיווי."""
    g = g[~g["סוג ממצא"].isin(SIDE_TYPES)]   # 'בצד' לא נשלח במייל — לא שייך לטבלת המשלוחים
    if g.empty:
        return pd.DataFrame()
    rows = []
    for an, sub in g.groupby("אנליסט"):
        sent = sorted({d for d in sub["נשלח בתאריך"] if d})
        seen = sorted({d for d in sub["חיווי בתאריך"] if d})
        emails = sorted({e for e in sub["נמען"] if e})
        rows.append({
            "אנליסט": an or "(ללא שם)",
            "כתובת מייל": emails[0] if emails else "— (לא נשלח)",
            "ממצאים": len(sub),
            "נשלח בתאריך": ", ".join(sent) if sent else "טרם נשלח",
            "ממתין למענה": int((sub["סטטוס"] == "נשלח").sum()),
            "בטיפול": int(sub["סטטוס"].isin(REPLIED_STATUSES).sum()),
            "טופל": int((sub["סטטוס"].isin(CLOSED_STATUSES)).sum()),
            "חיווי התקבל": ", ".join(seen) if seen else "—",
        })
    return pd.DataFrame(rows).sort_values("ממצאים", ascending=False)


def analyst_progress(f_all: pd.DataFrame) -> pd.DataFrame:
    """טבלת מעקב לפי אנליסט: כמה ממתינים/הגיבו/טופלו + אחוז סגירה."""
    f_all = f_all[~f_all["סוג ממצא"].isin(SIDE_TYPES)]   # 'בצד' לא נספר במעקב האנליסטים
    if f_all.empty:
        return pd.DataFrame()
    rows = []
    for an, g in f_all.groupby("אנליסט"):
        total = len(g)
        done = int(g["סטטוס"].isin(CLOSED_STATUSES).sum())
        rows.append({
            "אנליסט": an, "סהכ": total,
            "נשלחו": int((g["סטטוס"] == "נשלח").sum()),
            "נצפו/בטיפול": int(g["סטטוס"].isin(REPLIED_STATUSES).sum()),
            "טופלו": done,
            "באיחור": int(g["באיחור"].sum()) if "באיחור" in g else 0,
            "אחוז סגירה": round(100 * done / total) if total else 0,
        })
    return pd.DataFrame(rows).sort_values(["באיחור", "סהכ"], ascending=[False, False])


def mark_period_sent(led: dict, period: str, recipients_note: str = "") -> int:
    """סימון מיידי: כל ממצאי התקופה שפתוחים -> נשלח (היום). נרשם גם במשלוחים."""
    f, n = led["findings"], 0
    for i in f.index:
        if f.at[i, "תקופת בקרה"] == period and f.at[i, "סטטוס"] == "פתוח":
            f.at[i, "סטטוס"] = "נשלח"
            f.at[i, "נשלח בתאריך"] = today_str()
            f.at[i, "עדכון אחרון"] = now_str()
            n += 1
    led["findings"] = f
    if n:
        led["shipments"] = pd.concat([led["shipments"], pd.DataFrame([{
            "תאריך": today_str(), "סוג": "משלוח", "נמען": recipients_note or "אנליסטים (לפי הממצאים)",
            "נושא": f"בקרת קטלוג שוטף {period}", "תקופה": period,
            "פרטים": f"סומנו {n} ממצאים כנשלחו", "מקור": "סימון מהיר",
        }])[SHIPMENTS_COLS]], ignore_index=True)
    return n
