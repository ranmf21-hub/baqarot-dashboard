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

import pandas as pd

# ---------------------------------------------------------------- קבועים

STATUSES = ["פתוח", "נשלח", "נצפה", "בטיפול", "טופל", "לא רלוונטי"]
CLOSED_STATUSES = {"טופל", "לא רלוונטי"}

STATUS_COLORS = {
    "פתוח":      "#ef4444",   # אדום
    "נשלח":      "#f59e0b",   # כתום
    "נצפה":      "#38bdf8",   # תכלת
    "בטיפול":    "#eab308",   # צהוב
    "טופל":      "#22c55e",   # ירוק
    "לא רלוונטי": "#6b7280",  # אפור
}

FINDING_TYPES = {"שגיאה": "שגיאת סיווג", "יחידה": "יחידת מידה",
                 "מיפוי": "מיפוי חסר", "מיפוי-צד": "מיפוי חסר (בצד)", "רשומה": "רשומה חסרה"}
TYPE_COLORS = {"שגיאת סיווג": "#ef4444", "יחידת מידה": "#f59e0b",
               "מיפוי חסר": "#a855f7", "מיפוי חסר (בצד)": "#6b7280", "רשומה חסרה": "#38bdf8"}
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
        if r["סטטוס"] in ("נצפה", "בטיפול"):
            return "🟡"
        return "🟠"
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
            "סטטוס": "לא רלוונטי" if side else ("נשלח" if mark_sent else "פתוח"),
            "נשלח בתאריך": "" if side else (when if mark_sent else ""),
            "הערה": "בצד — סוג חומר מחוץ ל-Z001-Z004" if side else "",
            "עדכון אחרון": now_str(),
        })
        f = pd.concat([f, pd.DataFrame([row])[FINDINGS_COLS]], ignore_index=True)
        added += 1
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
    return {"added": added, "skipped": skipped, "prod_added": prod_added, "period": period}


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
    """מייל שנגרר: משלוח -> סימון 'נשלח' לממצאי הנמען+תקופה; מענה -> 'נצפה'.
    בטיחות: בלי נמען/שולח מזוהה — לא מעדכנים כלום (רק נרשם ביומן)."""
    f = led["findings"]
    period, when = mail.get("period", ""), mail.get("date", today_str())
    touched, note = 0, ""
    if mail["mail_type"] == "משלוח":
        rcpts = re.findall(r"[\w.\-]+@[\w.\-]+", str(mail.get("to", "")).lower())
        if not rcpts:
            note = "לא זוהו כתובות נמען במייל — לא עודכנו ממצאים (השתמש בסימון המהיר)"
        else:
            for i in f.index:
                if period and f.at[i, "תקופת בקרה"] != period:
                    continue
                if not any(_match_recipient(f.at[i, "נמען"], f.at[i, "אנליסט"], a) for a in rcpts):
                    continue
                if f.at[i, "סטטוס"] == "פתוח":
                    f.at[i, "סטטוס"] = "נשלח"
                    f.at[i, "נשלח בתאריך"] = when
                    f.at[i, "עדכון אחרון"] = now_str()
                    touched += 1
    elif mail["mail_type"] == "מענה":
        snds = re.findall(r"[\w.\-]+@[\w.\-]+", str(mail.get("sender", "")).lower())
        if not snds:
            note = "לא זוהתה כתובת השולח — לא עודכנו ממצאים (סמן חיווי ידנית בטבלה)"
        else:
            snd = snds[0]
            for i in f.index:
                if not _match_recipient(f.at[i, "נמען"], f.at[i, "אנליסט"], snd):
                    continue
                if period and f.at[i, "תקופת בקרה"] != period:
                    continue
                if f.at[i, "סטטוס"] in ("פתוח", "נשלח"):
                    f.at[i, "סטטוס"] = "נצפה"
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
            out.append({"סוג": kind, "תקופה": _period_from_name(fn), "קובץ": fn,
                        "תאריך הריצה": mtime, "נתיב": p, "_mt": mt})
    # קובץ אמת אחד לכל תקופה: כשיש כמה גרסאות של קובץ-בקרה לאותה תקופה,
    # נקלט רק החדש ביותר (איחוד גרסאות ניפח ממצאים שתוקנו בין גרסאות — פער ה-8/7 של ינואר).
    newest = {}
    for r in out:
        if r["סוג"] == "קובץ בקרה" and r["תקופה"]:
            if r["תקופה"] not in newest or r["_mt"] > newest[r["תקופה"]]["_mt"]:
                newest[r["תקופה"]] = r
    out = [r for r in out
           if not (r["סוג"] == "קובץ בקרה" and r["תקופה"] and newest[r["תקופה"]] is not r)]
    # קובצי בקרה קודם (מקור הממצאים) → תפוקה → תורים → מיילים אחרונים
    # (המיילים אחרונים כי הם מסמנים ממצאים שכבר חייבים להיות במאגר).
    order = {"קובץ בקרה": 0, "דוח תפוקה": 1, "תור מיילים": 2, "מייל/תשובה": 3}
    out.sort(key=lambda r: (order.get(r["סוג"], 9), r["תקופה"]))
    for r in out:
        r.pop("_mt", None)
    return out


def mark_analyst_seen(led: dict, analyst: str, source: str = "ידני") -> int:
    """חיווי בקליק: כל ממצאי האנליסט שנשלחו/פתוחים -> נצפה (טלפון/מסדרון)."""
    f, n = led["findings"], 0
    for i in f.index:
        if f.at[i, "אנליסט"] == analyst and f.at[i, "סטטוס"] in ("פתוח", "נשלח"):
            f.at[i, "סטטוס"] = "נצפה"
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
            "פתוח": int((sub["סטטוס"] == "פתוח").sum()),
            "נשלח": int((sub["סטטוס"] == "נשלח").sum()),
            "נצפה/בטיפול": int(sub["סטטוס"].isin(["נצפה", "בטיפול"]).sum()),
            "טופל": int((sub["סטטוס"].isin(["טופל", "לא רלוונטי"])).sum()),
            "חיווי התקבל": ", ".join(seen) if seen else "—",
        })
    return pd.DataFrame(rows).sort_values("ממצאים", ascending=False)


def analyst_progress(f_all: pd.DataFrame) -> pd.DataFrame:
    """טבלת מעקב לפי אנליסט: כמה נשלחו/נצפו/טופלו + אחוז סגירה."""
    f_all = f_all[~f_all["סוג ממצא"].isin(SIDE_TYPES)]   # 'בצד' לא נספר במעקב האנליסטים
    if f_all.empty:
        return pd.DataFrame()
    rows = []
    for an, g in f_all.groupby("אנליסט"):
        total = len(g)
        done = int((g["סטטוס"] == "טופל").sum()) + int((g["סטטוס"] == "לא רלוונטי").sum())
        rows.append({
            "אנליסט": an, "סהכ": total,
            "נשלחו": int((g["סטטוס"] == "נשלח").sum()),
            "נצפו/בטיפול": int(g["סטטוס"].isin(["נצפה", "בטיפול"]).sum()),
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
