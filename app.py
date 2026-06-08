from pathlib import Path

app_code = r'''
"""
NICHE 2026 — Self Check-In System (Streamlit)
Single-file app.py

Main features:
- Home poster uploaded by admin
- Gala Dinner poster uploaded by admin
- Tentative: Academic / Industry / Dinner from Excel if available
- Academic abstract cards fixed: no overlapping text
- Public registration by email
- Self check-in by email
- Dinner confirmation + table display
- Door gift tick by staff/admin only
- Admin upload Excel, upload posters, manage participants, assign tables
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st


# =============================================================================
# CONFIG
# =============================================================================
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "niche.db"
EXCEL_PATH = BASE_DIR / "niche_data.xlsx"

POSTER_DIR = BASE_DIR / "posters"
POSTER_DIR.mkdir(exist_ok=True)

MAIN_POSTER = POSTER_DIR / "main_poster.jpg"
DINNER_POSTER = POSTER_DIR / "dinner_poster.jpg"

PARTICIPANT_TABLES = [3, 4, 8, 9, 10, 27]
SEATS_PER_TABLE = 10

ADMIN_PASSWORD = os.getenv("NICHE_ADMIN_PASSWORD", "NICHE2026admin")

st.set_page_config(
    page_title="NICHE 2026 · Self Check-In",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "NICHE 2026 — Self Check-In System"},
)


# =============================================================================
# CSS
# =============================================================================
def inject_theme():
    st.markdown(
        """
<style>
:root{
  --navy0:#03061f;
  --navy1:#070d35;
  --navy2:#0b1450;
  --navy3:#111b68;
  --gold1:#8b6914;
  --gold2:#c99b22;
  --gold3:#f4d469;
  --gold4:#fff0a3;
  --white:#f8f4e8;
  --muted:#b7b0c8;
  --line:rgba(244,212,105,.25);
  --glass:rgba(5,10,46,.62);
}

[data-testid="stSidebar"],
[data-testid="collapsedControl"],
#MainMenu, footer, .stDeployButton,
[data-testid="stStatusWidget"]{display:none!important;}

[data-testid="stHeader"]{background:transparent!important;}

.stApp{
  color:var(--white);
  background:
    radial-gradient(circle at 12% 15%, rgba(244,212,105,.12), transparent 26%),
    radial-gradient(circle at 85% 18%, rgba(93,95,239,.18), transparent 32%),
    radial-gradient(circle at 20% 88%, rgba(26,35,126,.65), transparent 35%),
    linear-gradient(180deg,var(--navy0),var(--navy1) 45%,var(--navy0));
  background-attachment:fixed;
}

.stApp:before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  background-image:
    radial-gradient(1px 1px at 10% 20%, rgba(255,255,255,.7), transparent),
    radial-gradient(1px 1px at 25% 70%, rgba(244,212,105,.65), transparent),
    radial-gradient(1px 1px at 60% 30%, rgba(255,255,255,.55), transparent),
    radial-gradient(1.5px 1.5px at 82% 78%, rgba(244,212,105,.85), transparent),
    radial-gradient(1px 1px at 92% 16%, rgba(255,255,255,.55), transparent);
  background-size:420px 420px;
  opacity:.75;
}

.main .block-container{
  max-width:1380px;
  padding:1.05rem 1.5rem 2rem;
  position:relative;
  z-index:1;
}

html,body,p,div,span,label,input,textarea,button{
  font-family:Inter,Segoe UI,Arial,sans-serif!important;
}

h1,h2,h3{
  color:var(--gold4)!important;
  letter-spacing:.2px;
}

.brand{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:16px;
  padding:16px 20px;
  margin:2px 0 14px;
  border:1px solid var(--line);
  border-radius:22px;
  background:linear-gradient(135deg,rgba(5,10,46,.78),rgba(13,22,84,.42));
  box-shadow:0 20px 60px rgba(0,0,0,.28);
  backdrop-filter:blur(16px);
}

.brand-title{
  font-size:34px;
  font-weight:900;
  letter-spacing:2px;
  background:linear-gradient(135deg,#fff2a8,#d7a928,#8b6914);
  -webkit-background-clip:text;
  background-clip:text;
  color:transparent;
}

.brand-sub{
  color:var(--muted);
  font-size:12px;
  letter-spacing:2.5px;
  text-transform:uppercase;
}

.poster{
  border-radius:24px;
  border:1px solid var(--line);
  overflow:hidden;
  box-shadow:0 24px 80px rgba(0,0,0,.40);
  margin-bottom:16px;
}

.hero-card,.glass-card,.abstract-card,.participant-card{
  border:1px solid var(--line);
  border-radius:24px;
  background:linear-gradient(135deg,rgba(5,10,46,.72),rgba(14,25,88,.44));
  box-shadow:0 18px 60px rgba(0,0,0,.25);
  padding:22px;
  margin:14px 0;
  overflow:hidden;
}

.hero-title{
  color:var(--gold4);
  font-size:42px;
  line-height:1.05;
  font-weight:900;
  margin-bottom:8px;
}

.hero-text{
  color:var(--muted);
  font-size:16px;
  line-height:1.6;
}

.gold-pill{
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:7px 12px;
  border-radius:999px;
  color:#0a103c;
  font-weight:800;
  background:linear-gradient(135deg,#fff0a3,#d4af37);
  margin:4px 6px 4px 0;
  font-size:12px;
}

.stTabs [data-baseweb="tab-list"]{
  background:rgba(5,10,46,.56);
  border:1px solid var(--line);
  border-radius:18px;
  padding:7px;
  gap:5px;
}

.stTabs [data-baseweb="tab"]{
  color:var(--muted)!important;
  border-radius:14px;
  padding:11px 15px;
  font-weight:800;
}

.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg,#fff0a3,#c99b22)!important;
  color:#07103e!important;
}

.stTextInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"] > div{
  background:rgba(255,255,255,.08)!important;
  color:var(--white)!important;
  border:1px solid rgba(244,212,105,.28)!important;
  border-radius:14px!important;
}

.stButton > button{
  border:0!important;
  border-radius:14px!important;
  padding:.68rem 1rem!important;
  font-weight:900!important;
  color:#07103e!important;
  background:linear-gradient(135deg,#fff0a3,#d4af37,#b8860b)!important;
  box-shadow:0 12px 30px rgba(212,175,55,.22)!important;
}

.stButton > button:hover{
  transform:translateY(-1px);
  filter:brightness(1.05);
}

.info-box{
  border:1px solid rgba(244,212,105,.22);
  background:rgba(255,255,255,.06);
  border-radius:18px;
  padding:16px;
  color:var(--white);
}

/* ===========================
   ACADEMIC TENTATIVE FIX
   This prevents title/icon/name from bertindih.
   =========================== */
.session-card{
  border:1px solid rgba(244,212,105,.22);
  border-radius:24px;
  background:linear-gradient(135deg,rgba(5,10,46,.84),rgba(10,17,64,.72));
  padding:22px;
  margin:18px 0;
  overflow:hidden;
}

.session-head{
  display:grid;
  grid-template-columns:minmax(145px,220px) 1fr;
  gap:18px;
  align-items:start;
  margin-bottom:14px;
}

.session-time{
  color:var(--gold3);
  font-size:26px;
  line-height:1.2;
  font-weight:900;
  white-space:normal;
  overflow-wrap:anywhere;
}

.session-meta{
  min-width:0;
}

.session-label{
  color:var(--muted);
  font-size:14px;
  letter-spacing:6px;
  text-transform:uppercase;
  margin-bottom:8px;
  overflow-wrap:anywhere;
}

.session-title{
  color:var(--white);
  font-size:25px;
  line-height:1.22;
  font-weight:900;
  overflow-wrap:anywhere;
  word-break:normal;
  white-space:normal;
}

.paper-list{
  display:flex;
  flex-direction:column;
  gap:12px;
}

.paper-card{
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.055);
  border-radius:18px;
  padding:15px 16px;
  overflow:hidden;
  width:100%;
  box-sizing:border-box;
}

.paper-top{
  display:flex;
  flex-wrap:wrap;
  gap:9px 12px;
  align-items:center;
  margin-bottom:7px;
}

.paper-id{
  flex:0 0 auto;
  display:inline-flex;
  max-width:100%;
  padding:5px 9px;
  border-radius:999px;
  color:#07103e;
  background:linear-gradient(135deg,#fff0a3,#d4af37);
  font-weight:900;
  font-size:12px;
  line-height:1.2;
  overflow-wrap:anywhere;
}

.paper-author{
  flex:1 1 230px;
  min-width:0;
  color:var(--white);
  font-weight:800;
  line-height:1.35;
  overflow-wrap:anywhere;
  word-break:normal;
  white-space:normal;
}

.paper-title{
  color:var(--gold4);
  font-size:18px;
  line-height:1.35;
  font-weight:900;
  margin:7px 0;
  overflow-wrap:anywhere;
  word-break:normal;
  white-space:normal;
}

.paper-abstract{
  color:var(--muted);
  font-size:14px;
  line-height:1.58;
  overflow-wrap:anywhere;
  white-space:normal;
}

.small-muted{
  color:var(--muted);
  font-size:13px;
}

.admin-table{
  font-size:13px;
}

@media(max-width:760px){
  .brand{align-items:flex-start;flex-direction:column}
  .brand-title{font-size:27px}
  .hero-title{font-size:30px}
  .session-head{grid-template-columns:1fr}
  .session-time{font-size:22px}
  .session-label{letter-spacing:3px}
  .session-title{font-size:21px}
}
</style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# DATABASE
# =============================================================================
def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def execute(sql: str, params: tuple = ()):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def init_db():
    execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            organisation TEXT,
            phone TEXT,
            participant_type TEXT,
            dinner_join INTEGER DEFAULT 0,
            table_number INTEGER,
            checked_in INTEGER DEFAULT 0,
            checkin_time TEXT,
            door_gift_collected INTEGER DEFAULT 0,
            door_gift_time TEXT,
            created_at TEXT
        )
        """
    )

    execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            details TEXT,
            created_at TEXT
        )
        """
    )


def log_action(action: str, details: str = ""):
    execute(
        "INSERT INTO audit_log(action, details, created_at) VALUES(?,?,?)",
        (action, details, datetime.now().isoformat(timespec="seconds")),
    )


def table_occupancy() -> dict:
    df = query_df(
        """
        SELECT table_number, COUNT(*) AS n
        FROM participants
        WHERE dinner_join=1 AND table_number IS NOT NULL
        GROUP BY table_number
        """
    )
    occ = {t: 0 for t in PARTICIPANT_TABLES}
    for _, r in df.iterrows():
        try:
            occ[int(r["table_number"])] = int(r["n"])
        except Exception:
            pass
    return occ


def next_available_table() -> Optional[int]:
    occ = table_occupancy()
    for t in PARTICIPANT_TABLES:
        if occ.get(t, 0) < SEATS_PER_TABLE:
            return t
    return None


# =============================================================================
# HELPERS
# =============================================================================
def brand_bar():
    st.markdown(
        """
<div class="brand">
  <div>
    <div class="brand-title">NICHE 2026</div>
    <div class="brand-sub">Self Check-In · Academic · Industry · Gala Dinner</div>
  </div>
  <div class="brand-sub">Royale Chulan Seremban · 9–10 June 2026</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def safe_lower(x) -> str:
    return clean_text(x).lower()


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    norm = {re.sub(r"[^a-z0-9]+", "", str(c).lower()): c for c in df.columns}
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in norm:
            return norm[key]
    return None


def read_excel_sheets() -> dict[str, pd.DataFrame]:
    if not EXCEL_PATH.exists():
        return {}
    try:
        return pd.read_excel(EXCEL_PATH, sheet_name=None)
    except Exception as e:
        st.error(f"Excel tidak dapat dibaca: {e}")
        return {}


def get_sheet_by_keywords(sheets: dict[str, pd.DataFrame], keywords: list[str]) -> Optional[pd.DataFrame]:
    for name, df in sheets.items():
        lname = name.lower()
        if any(k.lower() in lname for k in keywords):
            return df.copy()
    return None


def save_uploaded_file(uploaded_file, save_path: Path) -> bool:
    if uploaded_file is None:
        return False
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return True


def display_poster(path: Path):
    if path.exists():
        st.markdown('<div class="poster">', unsafe_allow_html=True)
        st.image(str(path), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


def participant_exists(email: str) -> bool:
    df = query_df("SELECT id FROM participants WHERE lower(email)=lower(?)", (email.strip(),))
    return not df.empty


# =============================================================================
# PAGES
# =============================================================================
def page_home():
    display_poster(MAIN_POSTER)

    st.markdown(
        """
<div class="hero-card">
  <div class="hero-title">Welcome to NICHE 2026</div>
  <div class="hero-text">
    International Halal Conference self check-in system. Participants register using email,
    confirm dinner attendance, check in by themselves, and view assigned dinner table.
  </div>
  <div style="margin-top:14px;">
    <span class="gold-pill">Industrial Conference</span>
    <span class="gold-pill">Academic Conference</span>
    <span class="gold-pill">Exclusive Gala Dinner</span>
    <span class="gold-pill">Self Check-In</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="glass-card">
<h3>Participant Flow</h3>
<div class="hero-text">
1. Register using email.<br>
2. Open Check-In tab and enter the same email.<br>
3. Tick attendance confirmation.<br>
4. Confirm whether joining Gala Dinner.<br>
5. If joining dinner, table number will be shown after assignment by admin.<br>
6. Door gift collection is ticked by staff/admin only.
</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def page_academic():
    st.markdown("## 🎓 Academic Conference Tentative")

    sheets = read_excel_sheets()
    df = get_sheet_by_keywords(sheets, ["academic", "presenter", "abstract"])

    if df is None or df.empty:
        st.info("Academic tentative belum tersedia. Admin boleh upload Excel dalam tab Admin.")
        return

    time_col = find_col(df, ["time", "masa", "slot"])
    session_col = find_col(df, ["session", "parallel session", "sesi"])
    title_col = find_col(df, ["title", "paper title", "presentation title", "tajuk"])
    author_col = find_col(df, ["author", "presenter", "name", "nama"])
    id_col = find_col(df, ["paper id", "abstract id", "id", "code"])
    abstract_col = find_col(df, ["abstract", "full abstract", "abstrak"])

    if title_col is None:
        st.warning("Column tajuk/paper title tidak ditemui dalam Excel.")
        st.dataframe(df, use_container_width=True)
        return

    # Build grouping. If no session/time columns, every row becomes clean card.
    if time_col or session_col:
        group_cols = [c for c in [time_col, session_col] if c]
        grouped = df.groupby(group_cols, dropna=False, sort=False)
        for keys, g in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)

            time_text = clean_text(keys[0]) if time_col else ""
            session_text = clean_text(keys[1] if time_col and session_col else keys[0]) if session_col else "Academic Presentation"

            first_title = clean_text(g.iloc[0][title_col]) if len(g) else "Academic Session"

            st.markdown(
                f"""
<div class="session-card">
  <div class="session-head">
    <div class="session-time">{time_text or "Time TBC"}</div>
    <div class="session-meta">
      <div class="session-label">{session_text or "Academic Session"}</div>
      <div class="session-title">{first_title}</div>
    </div>
  </div>
  <div class="paper-list">
                """,
                unsafe_allow_html=True,
            )

            for _, r in g.iterrows():
                pid = clean_text(r[id_col]) if id_col else ""
                author = clean_text(r[author_col]) if author_col else ""
                title = clean_text(r[title_col])
                abstract = clean_text(r[abstract_col]) if abstract_col else ""

                st.markdown(
                    f"""
<div class="paper-card">
  <div class="paper-top">
    <span class="paper-id">{pid or "Paper"}</span>
    <span class="paper-author">{author or "Presenter TBC"}</span>
  </div>
  <div class="paper-title">{title}</div>
  <div class="paper-abstract">{abstract}</div>
</div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        for _, r in df.iterrows():
            pid = clean_text(r[id_col]) if id_col else ""
            author = clean_text(r[author_col]) if author_col else ""
            title = clean_text(r[title_col])
            abstract = clean_text(r[abstract_col]) if abstract_col else ""

            st.markdown(
                f"""
<div class="paper-card">
  <div class="paper-top">
    <span class="paper-id">{pid or "Paper"}</span>
    <span class="paper-author">{author or "Presenter TBC"}</span>
  </div>
  <div class="paper-title">{title}</div>
  <div class="paper-abstract">{abstract}</div>
</div>
                """,
                unsafe_allow_html=True,
            )


def page_industry():
    st.markdown("## 🏛 Industrial Conference Tentative")

    sheets = read_excel_sheets()
    df = get_sheet_by_keywords(sheets, ["industry", "industrial"])

    if df is None or df.empty:
        st.info("Industry tentative belum tersedia. Admin boleh upload Excel dalam tab Admin.")
        return

    time_col = find_col(df, ["time", "masa", "slot"])
    title_col = find_col(df, ["title", "programme", "program", "agenda", "session"])
    speaker_col = find_col(df, ["speaker", "name", "nama", "presenter"])

    for _, r in df.iterrows():
        time_text = clean_text(r[time_col]) if time_col else ""
        title = clean_text(r[title_col]) if title_col else "Industry Session"
        speaker = clean_text(r[speaker_col]) if speaker_col else ""

        st.markdown(
            f"""
<div class="session-card">
  <div class="session-head">
    <div class="session-time">{time_text or "Time TBC"}</div>
    <div class="session-meta">
      <div class="session-label">Industrial Conference</div>
      <div class="session-title">{title}</div>
      <div class="small-muted">{speaker}</div>
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )


def page_dinner():
    display_poster(DINNER_POSTER)

    st.markdown("## ✨ Exclusive Gala Dinner")

    sheets = read_excel_sheets()
    df = get_sheet_by_keywords(sheets, ["gala", "dinner", "tentatif dinner"])

    if df is None or df.empty:
        st.markdown(
            """
<div class="glass-card">
<h3>Gala Dinner Programme</h3>
<div class="hero-text">
Official launching ceremony, grand welcome dinner, networking session,
cultural performance, photo & media session, and press conference.
</div>
</div>
            """,
            unsafe_allow_html=True,
        )
        return

    time_col = find_col(df, ["time", "masa", "slot"])
    title_col = find_col(df, ["title", "programme", "program", "agenda", "activity", "aktiviti"])

    for _, r in df.iterrows():
        time_text = clean_text(r[time_col]) if time_col else ""
        title = clean_text(r[title_col]) if title_col else "Gala Dinner Activity"

        st.markdown(
            f"""
<div class="session-card">
  <div class="session-head">
    <div class="session-time">{time_text or "Time TBC"}</div>
    <div class="session-meta">
      <div class="session-label">Gala Dinner</div>
      <div class="session-title">{title}</div>
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )


def page_register():
    st.markdown("## 📝 Participant Registration")

    with st.form("register_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            full_name = st.text_input("Full Name *")
            email = st.text_input("Email *")
            organisation = st.text_input("Organisation")
        with c2:
            phone = st.text_input("Phone")
            participant_type = st.selectbox(
                "Participant Type",
                ["Academic Presenter", "Industry Participant", "Speaker", "Delegate", "Guest", "Walk-in"],
            )
            dinner_join = st.radio("Will you attend Gala Dinner?", ["Yes", "No"], horizontal=True)

        submitted = st.form_submit_button("Register")

    if submitted:
        email_clean = email.strip().lower()
        if not full_name.strip() or not email_clean:
            st.error("Nama dan email wajib diisi.")
            return

        if "@" not in email_clean or "." not in email_clean:
            st.error("Format email tidak sah.")
            return

        if participant_exists(email_clean):
            st.warning("Email ini telah didaftarkan. Sila terus ke tab Check-In.")
            return

        try:
            dinner_flag = 1 if dinner_join == "Yes" else 0
            table_no = next_available_table() if dinner_flag else None

            execute(
                """
                INSERT INTO participants
                (full_name,email,organisation,phone,participant_type,dinner_join,table_number,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    full_name.strip(),
                    email_clean,
                    organisation.strip(),
                    phone.strip(),
                    participant_type,
                    dinner_flag,
                    table_no,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            log_action("REGISTER", email_clean)

            st.success("Registration successful. Please proceed to Self Check-In.")
            if dinner_flag:
                if table_no:
                    st.info(f"Gala Dinner selected. Temporary table assignment: Table {table_no}.")
                else:
                    st.warning("Gala Dinner selected, but table is full. Admin will assign manually.")
        except sqlite3.IntegrityError:
            st.warning("Email ini telah didaftarkan. Sila terus ke tab Check-In.")


def page_checkin():
    st.markdown("## ✓ Self Check-In")

    email = st.text_input("Enter your registered email", key="checkin_email").strip().lower()

    if not email:
        st.markdown(
            """
<div class="glass-card">
<div class="hero-text">
Please enter the same email used during registration. Your details, dinner status,
and assigned table will appear here.
</div>
</div>
            """,
            unsafe_allow_html=True,
        )
        return

    df = query_df("SELECT * FROM participants WHERE lower(email)=lower(?)", (email,))

    if df.empty:
        st.warning("Email not found. Please register first or contact admin.")
        return

    p = df.iloc[0]

    st.markdown(
        f"""
<div class="participant-card">
  <h3>{clean_text(p['full_name'])}</h3>
  <div class="hero-text">
    Email: {clean_text(p['email'])}<br>
    Organisation: {clean_text(p['organisation']) or "—"}<br>
    Participant Type: {clean_text(p['participant_type']) or "—"}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**Check-In Status:** {'✅ Checked-in' if int(p['checked_in']) else 'Not yet'}")
    with c2:
        st.markdown(f"**Dinner:** {'✅ Yes' if int(p['dinner_join']) else 'No'}")
    with c3:
        table_text = f"Table {int(p['table_number'])}" if pd.notna(p["table_number"]) else "Not assigned"
        st.markdown(f"**Dinner Table:** {table_text}")

    st.divider()

    if not int(p["checked_in"]):
        if st.button("Confirm My Attendance / Check-In"):
            execute(
                "UPDATE participants SET checked_in=1, checkin_time=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), int(p["id"])),
            )
            log_action("CHECKIN", clean_text(p["email"]))
            st.success("Check-in successful.")
            st.rerun()
    else:
        st.success(f"You have checked in at {clean_text(p['checkin_time'])}.")

    st.markdown("### Gala Dinner Confirmation")

    current_dinner = "Yes" if int(p["dinner_join"]) else "No"
    new_dinner = st.radio(
        "Will you attend Gala Dinner?",
        ["Yes", "No"],
        index=0 if current_dinner == "Yes" else 1,
        horizontal=True,
        key=f"dinner_{p['id']}",
    )

    if st.button("Update Dinner Confirmation"):
        dinner_flag = 1 if new_dinner == "Yes" else 0
        table_no = p["table_number"]

        if dinner_flag and pd.isna(table_no):
            table_no = next_available_table()

        if not dinner_flag:
            table_no = None

        execute(
            "UPDATE participants SET dinner_join=?, table_number=? WHERE id=?",
            (dinner_flag, table_no, int(p["id"])),
        )
        log_action("DINNER_UPDATE", f"{clean_text(p['email'])}: {new_dinner}")
        st.success("Dinner confirmation updated.")
        st.rerun()

    st.markdown("### Door Gift")
    if int(p["door_gift_collected"]):
        st.success(f"Door gift collected at {clean_text(p['door_gift_time'])}.")
    else:
        st.info("Door gift status will be updated by staff/admin after collection.")


def page_admin():
    st.markdown("## 🔐 Admin")

    if "admin_ok" not in st.session_state:
        st.session_state.admin_ok = False

    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.success("Admin login successful.")
                st.rerun()
            else:
                st.error("Wrong password.")
        return

    st.success("Admin mode active.")

    admin_tabs = st.tabs(
        [
            "🖼 Upload Posters",
            "📘 Upload Excel",
            "👥 Participants",
            "🍽 Tables",
            "🎁 Door Gift",
            "➕ Walk-in",
            "🧹 Reset",
        ]
    )

    with admin_tabs[0]:
        st.markdown("### Upload Poster")
        c1, c2 = st.columns(2)
        with c1:
            main_img = st.file_uploader(
                "Upload Main Poster: Industrial + Academic",
                type=["jpg", "jpeg", "png"],
                key="main_poster_upload",
            )
            if st.button("Save Main Poster"):
                if save_uploaded_file(main_img, MAIN_POSTER):
                    log_action("UPLOAD_MAIN_POSTER", "")
                    st.success("Main poster saved.")
                    st.rerun()
                else:
                    st.warning("Choose image first.")

            display_poster(MAIN_POSTER)

        with c2:
            dinner_img = st.file_uploader(
                "Upload Gala Dinner Poster",
                type=["jpg", "jpeg", "png"],
                key="dinner_poster_upload",
            )
            if st.button("Save Gala Dinner Poster"):
                if save_uploaded_file(dinner_img, DINNER_POSTER):
                    log_action("UPLOAD_DINNER_POSTER", "")
                    st.success("Gala Dinner poster saved.")
                    st.rerun()
                else:
                    st.warning("Choose image first.")

            display_poster(DINNER_POSTER)

    with admin_tabs[1]:
        st.markdown("### Upload Excel Data")
        xlsx = st.file_uploader("Upload niche_data.xlsx", type=["xlsx"], key="xlsx_upload")
        if st.button("Save Excel"):
            if save_uploaded_file(xlsx, EXCEL_PATH):
                log_action("UPLOAD_EXCEL", xlsx.name)
                st.success("Excel saved as niche_data.xlsx.")
                st.rerun()
            else:
                st.warning("Choose Excel file first.")

        if EXCEL_PATH.exists():
            st.info(f"Current Excel: {EXCEL_PATH.name}")
            sheets = read_excel_sheets()
            st.write("Sheets detected:", list(sheets.keys()))

    with admin_tabs[2]:
        st.markdown("### Registered Participants")

        df = query_df("SELECT * FROM participants ORDER BY id DESC")
        if df.empty:
            st.info("No participants yet.")
        else:
            search = st.text_input("Search name/email/organisation")
            if search:
                s = search.lower()
                mask = (
                    df["full_name"].fillna("").str.lower().str.contains(s)
                    | df["email"].fillna("").str.lower().str.contains(s)
                    | df["organisation"].fillna("").str.lower().str.contains(s)
                )
                df = df[mask]

            st.dataframe(
                df[
                    [
                        "id",
                        "full_name",
                        "email",
                        "organisation",
                        "participant_type",
                        "dinner_join",
                        "table_number",
                        "checked_in",
                        "door_gift_collected",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    with admin_tabs[3]:
        st.markdown("### Table Assignment")
        occ = table_occupancy()
        occ_df = pd.DataFrame(
            [{"Table": t, "Occupied": occ[t], "Capacity": SEATS_PER_TABLE, "Available": SEATS_PER_TABLE - occ[t]} for t in PARTICIPANT_TABLES]
        )
        st.dataframe(occ_df, use_container_width=True, hide_index=True)

        df = query_df(
            """
            SELECT id, full_name, email, organisation, dinner_join, table_number
            FROM participants
            WHERE dinner_join=1
            ORDER BY table_number IS NULL DESC, table_number, full_name
            """
        )

        for _, p in df.iterrows():
            c1, c2, c3 = st.columns([4, 1.3, 1])
            with c1:
                st.markdown(
                    f"**{clean_text(p['full_name'])}**  \n"
                    f"<span class='small-muted'>{clean_text(p['email'])} · {clean_text(p['organisation']) or '—'}</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                cur = int(p["table_number"]) if pd.notna(p["table_number"]) else None
                options = [None] + PARTICIPANT_TABLES
                new_table = st.selectbox(
                    "Table",
                    options,
                    index=options.index(cur),
                    format_func=lambda x: "— None —" if x is None else f"Table {x}",
                    key=f"table_select_{p['id']}",
                    label_visibility="collapsed",
                )
            with c3:
                if st.button("Save", key=f"save_table_{p['id']}"):
                    if new_table is None:
                        execute("UPDATE participants SET table_number=NULL WHERE id=?", (int(p["id"]),))
                        st.success("Table cleared.")
                        st.rerun()
                    else:
                        occ_now = table_occupancy()
                        if new_table != cur and occ_now.get(new_table, 0) >= SEATS_PER_TABLE:
                            st.error(f"Table {new_table} is full.")
                        else:
                            execute(
                                "UPDATE participants SET table_number=? WHERE id=?",
                                (int(new_table), int(p["id"])),
                            )
                            st.success(f"Assigned to Table {new_table}.")
                            st.rerun()

    with admin_tabs[4]:
        st.markdown("### Door Gift Collection")
        df = query_df(
            """
            SELECT id, full_name, email, organisation, checked_in, door_gift_collected, door_gift_time
            FROM participants
            ORDER BY checked_in DESC, full_name
            """
        )

        q = st.text_input("Search participant for door gift", key="gift_search")
        if q:
            s = q.lower()
            df = df[
                df["full_name"].fillna("").str.lower().str.contains(s)
                | df["email"].fillna("").str.lower().str.contains(s)
            ]

        for _, p in df.iterrows():
            c1, c2 = st.columns([5, 1.3])
            with c1:
                status = "✅ Collected" if int(p["door_gift_collected"]) else "Not collected"
                st.markdown(
                    f"**{clean_text(p['full_name'])}**  \n"
                    f"<span class='small-muted'>{clean_text(p['email'])} · {status}</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                if not int(p["door_gift_collected"]):
                    if st.button("Tick Collected", key=f"gift_{p['id']}"):
                        execute(
                            "UPDATE participants SET door_gift_collected=1, door_gift_time=? WHERE id=?",
                            (datetime.now().isoformat(timespec="seconds"), int(p["id"])),
                        )
                        log_action("DOOR_GIFT", clean_text(p["email"]))
                        st.success("Door gift updated.")
                        st.rerun()
                else:
                    if st.button("Undo", key=f"ungift_{p['id']}"):
                        execute(
                            "UPDATE participants SET door_gift_collected=0, door_gift_time=NULL WHERE id=?",
                            (int(p["id"]),),
                        )
                        st.warning("Door gift status undone.")
                        st.rerun()

    with admin_tabs[5]:
        st.markdown("### Walk-in Registration")
        with st.form("walkin_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full Name")
                email = st.text_input("Email")
                org = st.text_input("Organisation")
            with c2:
                phone = st.text_input("Phone")
                ptype = st.selectbox("Type", ["Walk-in", "Guest", "Industry Participant", "Academic Presenter"])
                dinner = st.radio("Gala Dinner?", ["Yes", "No"], horizontal=True)

            save = st.form_submit_button("Register Walk-in")

        if save:
            if not name.strip() or not email.strip():
                st.error("Name and email required.")
            elif participant_exists(email.strip().lower()):
                st.warning("Email already registered.")
            else:
                dinner_flag = 1 if dinner == "Yes" else 0
                table_no = next_available_table() if dinner_flag else None
                execute(
                    """
                    INSERT INTO participants
                    (full_name,email,organisation,phone,participant_type,dinner_join,table_number,checked_in,checkin_time,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        name.strip(),
                        email.strip().lower(),
                        org.strip(),
                        phone.strip(),
                        ptype,
                        dinner_flag,
                        table_no,
                        1,
                        datetime.now().isoformat(timespec="seconds"),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                log_action("WALKIN", email.strip().lower())
                st.success("Walk-in registered and checked-in.")

    with admin_tabs[6]:
        st.markdown("### Reset Data")
        st.warning("This action will delete participant registration data only. Posters and Excel will remain.")
        confirm = st.text_input("Type RESET to confirm")
        if st.button("Clear All Participants"):
            if confirm == "RESET":
                execute("DELETE FROM participants")
                execute("DELETE FROM sqlite_sequence WHERE name='participants'")
                log_action("RESET_PARTICIPANTS", "")
                st.success("All participants cleared.")
                st.rerun()
            else:
                st.error("Please type RESET exactly.")


# =============================================================================
# MAIN
# =============================================================================
def main():
    inject_theme()
    init_db()
    brand_bar()

    tab_home, tab_ac, tab_in, tab_dn, tab_ci, tab_rg, tab_ad = st.tabs(
        [
            "🏠 Home",
            "🎓 Academic",
            "🏛 Industry",
            "✨ Gala Dinner",
            "✓ Check-In",
            "📝 Register",
            "🔐 Admin",
        ]
    )

    with tab_home:
        page_home()
    with tab_ac:
        page_academic()
    with tab_in:
        page_industry()
    with tab_dn:
        page_dinner()
    with tab_ci:
        page_checkin()
    with tab_rg:
        page_register()
    with tab_ad:
        page_admin()

    st.markdown(
        """
<div style="text-align:center;padding:28px 10px;margin-top:26px;border-top:1px solid rgba(244,212,105,.16);color:var(--muted);font-size:12px;">
NICHE 2026 · International Halal Conference · Royale Chulan Seremban
</div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
'''

out = Path("/mnt/data/app.py")
out.write_text(app_code, encoding="utf-8")
print(f"Created {out}")
