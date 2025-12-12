import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import random

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Majlis Hari Inovasi UiTM 2025",
    page_icon="🎫",
    layout="centered"
)

DB_NAME = "dinner.db"

# =========================
# DATABASE FUNCTIONS
# =========================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS master (
        email TEXT PRIMARY KEY,
        nama TEXT,
        gelaran TEXT,
        no_meja TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        email TEXT PRIMARY KEY,
        timestamp TEXT,
        nama TEXT,
        gelaran TEXT,
        no_meja TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS winners (
        email TEXT PRIMARY KEY,
        timestamp TEXT,
        nama TEXT,
        gelaran TEXT,
        no_meja TEXT
    )
    """)

    conn.commit()
    conn.close()

def import_master(df):
    conn = get_conn()
    c = conn.cursor()

    for _, r in df.iterrows():
        c.execute("""
        INSERT OR REPLACE INTO master (email, nama, gelaran, no_meja)
        VALUES (?, ?, ?, ?)
        """, (
            r["Email"].strip().lower(),
            r["Nama"],
            r["Gelaran"],
            str(r["No_Meja"])
        ))

    conn.commit()
    conn.close()

def get_guest(email):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM master WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    return row

def confirm_checkin(guest):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    INSERT OR REPLACE INTO attendance
    VALUES (?, ?, ?, ?, ?)
    """, (
        guest[0],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        guest[1],
        guest[2],
        guest[3]
    ))
    conn.commit()
    conn.close()

def count_stats():
    conn = get_conn()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM master").fetchone()[0]
    hadir = c.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    conn.close()
    return total, hadir, total - hadir

def pick_winner():
    conn = get_conn()
    att = pd.read_sql("SELECT * FROM attendance", conn)
    win = pd.read_sql("SELECT * FROM winners", conn)

    eligible = att[~att["email"].isin(win["email"])] if not win.empty else att
    if eligible.empty:
        return None

    row = eligible.sample(1).iloc[0]
    conn.execute("""
    INSERT OR IGNORE INTO winners VALUES (?, ?, ?, ?, ?)
    """, (
        row["email"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        row["nama"],
        row["gelaran"],
        row["no_meja"]
    ))
    conn.commit()
    conn.close()
    return row

# =========================
# INIT
# =========================
init_db()

# =========================
# UI
# =========================
st.title("🎫 Majlis Hari Inovasi UiTM 2025")
st.caption("Check-in Digital • Email → Papar Nombor Meja • Tema Nusantara")

tab1, tab2 = st.tabs(["✅ Check-in Tetamu", "🛠️ Admin Dashboard"])

# =========================
# TAB 1 – CHECK-IN
# =========================
with tab1:
    st.subheader("Semakan Kehadiran Tetamu")

    email = st.text_input(
        "Masukkan Email Jemputan",
        placeholder="contoh: zahari@uitm.edu.my"
    ).strip().lower()

    if email:
        guest = get_guest(email)

        if guest:
            st.success(f"Selamat Datang {guest[2]} {guest[1]}")

            st.markdown(
                f"""
                <div style="
                    border:2px dashed #C9A227;
                    border-radius:16px;
                    padding:20px;
                    text-align:center;
                    margin-top:10px;">
                    <div style="font-size:14px; font-weight:700;">
                        NOMBOR MEJA ANDA
                    </div>
                    <div style="font-size:56px; font-weight:900; color:#4B1F78;">
                        {guest[3]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button("✅ Confirm Check-in", use_container_width=True):
                confirm_checkin(guest)
                st.toast("Check-in berjaya direkod", icon="🎉")

        else:
            st.error("Email tidak dijumpai dalam senarai jemputan.")

# =========================
# TAB 2 – ADMIN
# =========================
with tab2:
    st.subheader("Admin Dashboard")

    st.markdown("### 📥 Import Master List (Excel)")
    upload = st.file_uploader(
        "Upload Template_Master_Majlis_Inovasi_UiTM_2025.xlsx",
        type=["xlsx"]
    )

    if upload:
        df = pd.read_excel(upload)
        required = {"Email", "Nama", "Gelaran", "No_Meja"}

        if not required.issubset(df.columns):
            st.error("Kolum wajib: Email, Nama, Gelaran, No_Meja")
        else:
            import_master(df)
            st.success("Master list berjaya diimport")

    total, hadir, belum = count_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jemputan", total)
    c2.metric("Dah Hadir", hadir)
    c3.metric("Belum Hadir", belum)

    st.markdown("### 📋 Senarai Kehadiran")
    conn = get_conn()
    att_df = pd.read_sql("SELECT * FROM attendance ORDER BY timestamp DESC", conn)
    conn.close()
    st.dataframe(att_df, use_container_width=True)

    st.markdown("### 🎁 Cabutan Bertuah")
    if st.button("🎲 Pick Winner", use_container_width=True):
        winner = pick_winner()
        if winner is not None:
            st.balloons()
            st.success(
                f"PEMENANG: {winner['gelaran']} {winner['nama']}  |  Meja {winner['no_meja']}"
            )
        else:
            st.warning("Tiada peserta layak.")
