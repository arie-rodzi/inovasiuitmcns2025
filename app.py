import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import pytz
import time
from PIL import Image
import io
import re

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Event Check-in", page_icon="🎫", layout="centered")

DB_NAME = "dinner.db"
ADMIN_PIN = "2025"
TZ = pytz.timezone("Asia/Kuala_Lumpur")

# =========================
# HELPERS
# =========================
def norm_email(v):
    return str(v).strip().lower() if v else ""

def norm_meja(v):
    if not v:
        return ""
    s = str(v).strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s.replace(" ", "")

def now_myt():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# =========================
# DB INIT + MIGRATION
# =========================
def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS master (
            email TEXT PRIMARY KEY,
            nama TEXT,
            gelaran TEXT,
            no_meja TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            email TEXT PRIMARY KEY,
            timestamp TEXT,
            nama TEXT,
            gelaran TEXT,
            no_meja TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS layout_config (
            id INTEGER PRIMARY KEY CHECK (id=1),
            filename TEXT,
            image_bytes BLOB,
            updated_at TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS event_assets (
            id INTEGER PRIMARY KEY CHECK (id=1)
        )""")

        cols = [r[1] for r in c.execute("PRAGMA table_info(event_assets)")]

        def add(col, typ):
            if col not in cols:
                c.execute(f"ALTER TABLE event_assets ADD COLUMN {col} {typ}")

        add("poster_filename", "TEXT")
        add("poster_bytes", "BLOB")
        add("aturcara_filename", "TEXT")
        add("aturcara_bytes", "BLOB")
        add("updated_at", "TEXT")

        conn.commit()

# =========================
# MASTER
# =========================
def import_master(df):
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    for col in ["Email", "Nama", "No_Meja"]:
        if col not in df.columns:
            raise ValueError("Kolum wajib: Email, Nama, No_Meja")

    if "Gelaran" not in df.columns:
        df["Gelaran"] = ""

    df["Email"] = df["Email"].apply(norm_email)
    df["No_Meja"] = df["No_Meja"].apply(norm_meja)
    df = df.drop_duplicates("Email")

    with get_conn() as conn:
        for _, r in df.iterrows():
            conn.execute("""
            INSERT INTO master(email,nama,gelaran,no_meja)
            VALUES (?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
            nama=excluded.nama,
            gelaran=excluded.gelaran,
            no_meja=excluded.no_meja
            """, (r["Email"], r["Nama"], r["Gelaran"], r["No_Meja"]))
        conn.commit()

def get_guest(email):
    with get_conn() as conn:
        return conn.execute(
            "SELECT email,nama,gelaran,no_meja FROM master WHERE email=?",
            (email,)
        ).fetchone()

def already_checked(email):
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM attendance WHERE email=?",
            (email,)
        ).fetchone() is not None

def confirm_checkin(row):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO attendance(email,timestamp,nama,gelaran,no_meja)
        VALUES (?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET timestamp=excluded.timestamp
        """, (*row, now_myt()))
        conn.commit()

# =========================
# ASSETS
# =========================
def save_layout(fn, b):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO layout_config(id,filename,image_bytes,updated_at)
        VALUES (1,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
        filename=excluded.filename,
        image_bytes=excluded.image_bytes,
        updated_at=excluded.updated_at
        """, (fn, b, now_myt()))
        conn.commit()

def load_layout():
    with get_conn() as conn:
        return conn.execute(
            "SELECT filename,image_bytes FROM layout_config WHERE id=1"
        ).fetchone()

def save_asset(col_fn, col_b, fn, b):
    with get_conn() as conn:
        conn.execute(f"""
        INSERT INTO event_assets(id,{col_fn},{col_b},updated_at)
        VALUES (1,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
        {col_fn}=excluded.{col_fn},
        {col_b}=excluded.{col_b},
        updated_at=excluded.updated_at
        """, (fn, b, now_myt()))
        conn.commit()

def load_assets():
    with get_conn() as conn:
        return conn.execute("""
        SELECT poster_filename,poster_bytes,
               aturcara_filename,aturcara_bytes
        FROM event_assets WHERE id=1
        """).fetchone()

# =========================
# APP START
# =========================
init_db()

page = st.sidebar.radio("Menu", ["Tetamu", "Admin"])

# =========================
# TETAMU
# =========================
if page == "Tetamu":
    st.title("🎫 Check-in Tetamu")

    poster_fn, poster_b, atur_fn, atur_b = load_assets() or (None,None,None,None)

    # POSTER
    st.subheader("Poster")
    if poster_b:
        st.image(Image.open(io.BytesIO(poster_b)), use_container_width=True)
        st.download_button("Download poster", poster_b, poster_fn)
    else:
        st.info("Poster belum dimasukkan.")

    st.divider()

    # CHECK-IN
    st.subheader("Check-in")
    email = norm_email(st.text_input("Email jemputan"))

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tiada dalam senarai.")
        else:
            _, nama, _, meja = row
            st.success(f"Nama: {nama}")
            st.info(f"No Meja: **{meja}**")

            if already_checked(email):
                st.caption("Sudah check-in.")
            else:
                if st.button("Confirm Check-in"):
                    confirm_checkin(row)
                    st.success("Check-in berjaya.")

    st.divider()

    # LAYOUT
    st.subheader("Layout Meja")
    layout = load_layout()
    if layout and layout[1]:
        st.image(Image.open(io.BytesIO(layout[1])), use_container_width=True)
        st.download_button("Download layout", layout[1], layout[0])
    else:
        st.info("Layout belum dimasukkan.")

    st.divider()

    # ATURCARA
    st.subheader("Aturcara Majlis")
    if atur_b:
        st.image(Image.open(io.BytesIO(atur_b)), use_container_width=True)
        st.download_button("Download aturcara", atur_b, atur_fn)
    else:
        st.info("Aturcara belum dimasukkan.")

# =========================
# ADMIN
# =========================
else:
    st.title("🛠️ Admin")

    pin = st.text_input("PIN Admin", type="password")
    if pin != ADMIN_PIN:
        st.stop()

    st.subheader("Upload Master")
    up = st.file_uploader("Excel Master", type=["xlsx"])
    if up:
        import_master(pd.read_excel(up))
        st.success("Master diimport.")

    st.subheader("Upload Poster")
    p = st.file_uploader("Poster (PNG/JPG)", type=["png","jpg","jpeg"])
    if p:
        save_asset("poster_filename","poster_bytes",p.name,p.read())
        st.success("Poster disimpan.")

    st.subheader("Upload Layout")
    l = st.file_uploader("Layout (PNG/JPG)", type=["png","jpg","jpeg"])
    if l:
        save_layout(l.name,l.read())
        st.success("Layout disimpan.")

    st.subheader("Upload Aturcara")
    a = st.file_uploader("Aturcara (PNG/JPG)", type=["png","jpg","jpeg"])
    if a:
        save_asset("aturcara_filename","aturcara_bytes",a.name,a.read())
        st.success("Aturcara disimpan.")
