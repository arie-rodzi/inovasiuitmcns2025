import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time
import pytz
from PIL import Image
import io
import re

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Event Check-in", page_icon="🎫", layout="centered")

DB_NAME = "dinner.db"

ADMIN_PIN_ENABLED = True
ADMIN_PIN = "2025"  # tukar PIN di sini

TZ = pytz.timezone("Asia/Kuala_Lumpur")

# =========================
# HELPERS
# =========================
def norm_meja(v) -> str:
    """Normalize No_Meja: strip, upper, collapse spaces, remove spaces (VIP 1 -> VIP1)."""
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ", "")
    return s

def norm_email(v) -> str:
    return (str(v).strip().lower()) if v is not None else ""

def now_myt_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# =========================
# DB INIT
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

        # Layout (1 row)
        c.execute("""
        CREATE TABLE IF NOT EXISTS layout_config (
            id INTEGER PRIMARY KEY CHECK (id=1),
            filename TEXT,
            image_bytes BLOB,
            updated_at TEXT
        )""")

        # Poster + Aturcara (IMAGE) (1 row)
        c.execute("""
        CREATE TABLE IF NOT EXISTS event_assets (
            id INTEGER PRIMARY KEY CHECK (id=1),
            poster_filename TEXT,
            poster_bytes BLOB,
            aturcara_filename TEXT,
            aturcara_bytes BLOB,
            updated_at TEXT
        )""")

        conn.commit()

# =========================
# MASTER
# =========================
def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["Email", "Nama", "No_Meja"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolum wajib tiada: {missing}. Perlu: {required}")

    if "Gelaran" not in df.columns:
        df["Gelaran"] = ""

    df["Email"] = df["Email"].apply(norm_email)
    df["Nama"] = df["Nama"].astype(str).str.strip()
    df["Gelaran"] = df["Gelaran"].astype(str).str.strip()
    df["No_Meja"] = df["No_Meja"].apply(norm_meja)

    df = df[df["Email"].str.len() > 3]
    df = df.drop_duplicates(subset=["Email"], keep="last")
    return df[["Email", "Nama", "Gelaran", "No_Meja"]]

def import_master(df: pd.DataFrame):
    df = normalize_master(df)
    with get_conn() as conn:
        for _, r in df.iterrows():
            conn.execute("""
            INSERT INTO master(email, nama, gelaran, no_meja)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              nama=excluded.nama,
              gelaran=excluded.gelaran,
              no_meja=excluded.no_meja
            """, (r["Email"], r["Nama"], r["Gelaran"], r["No_Meja"]))
        conn.commit()

def get_guest(email: str):
    email = norm_email(email)
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT email, nama, gelaran, no_meja FROM master WHERE email=?",
            (email,)
        ).fetchone()
    if not row:
        return None
    return (row[0], row[1], row[2], norm_meja(row[3]))

def already_checked_in(email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM attendance WHERE email=? LIMIT 1", (email,)).fetchone()
    return row is not None

def confirm_checkin(row):
    now = now_myt_str()
    time.sleep(0.10)
    email, nama, gelaran, no_meja = row
    no_meja = norm_meja(no_meja)

    with get_conn() as conn:
        conn.execute("""
        INSERT INTO attendance(email, timestamp, nama, gelaran, no_meja)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          timestamp=excluded.timestamp,
          nama=excluded.nama,
          gelaran=excluded.gelaran,
          no_meja=excluded.no_meja
        """, (email, now, nama, gelaran, no_meja))
        conn.commit()

def count_stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM master").fetchone()[0]
        hadir = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    return total, hadir, max(total - hadir, 0)

def load_attendance():
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT email, timestamp, nama, no_meja FROM attendance ORDER BY timestamp DESC",
            conn
        )

# =========================
# LAYOUT
# =========================
def save_layout_image(filename: str, image_bytes: bytes):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO layout_config (id, filename, image_bytes, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            filename=excluded.filename,
            image_bytes=excluded.image_bytes,
            updated_at=excluded.updated_at
        """, (filename, image_bytes, now_myt_str()))
        conn.commit()

def load_layout_image_bytes():
    with get_conn() as conn:
        return conn.execute(
            "SELECT filename, image_bytes, updated_at FROM layout_config WHERE id=1"
        ).fetchone()

# =========================
# EVENT ASSETS (POSTER + ATURCARA IMAGE)
# =========================
def save_poster(filename: str, b: bytes):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO event_assets (id, poster_filename, poster_bytes, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            poster_filename=excluded.poster_filename,
            poster_bytes=excluded.poster_bytes,
            updated_at=excluded.updated_at
        """, (filename, b, now_myt_str()))
        conn.commit()

def save_aturcara(filename: str, b: bytes):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO event_assets (id, aturcara_filename, aturcara_bytes, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            aturcara_filename=excluded.aturcara_filename,
            aturcara_bytes=excluded.aturcara_bytes,
            updated_at=excluded.updated_at
        """, (filename, b, now_myt_str()))
        conn.commit()

def load_assets():
    with get_conn() as conn:
        return conn.execute("""
            SELECT poster_filename, poster_bytes, aturcara_filename, aturcara_bytes, updated_at
            FROM event_assets WHERE id=1
        """).fetchone()

# =========================
# SIMPLE UI CSS
# =========================
def inject_css():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.1rem; }
      .hint { font-size: 0.92rem; opacity: 0.85; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# APP
# =========================
init_db()
inject_css()

# ✅ Phone-safe navigation
page = st.sidebar.radio("Menu", ["✅ Tetamu", "🛠️ Admin"])

# =========================
# TETAMU PAGE
# =========================
if page == "✅ Tetamu":
    st.title("🎫 Check-in Tetamu")

    assets = load_assets()
    poster_fn = poster_b = atur_fn = atur_b = upd = None
    if assets:
        poster_fn, poster_b, atur_fn, atur_b, upd = assets

    # 1) POSTER
    st.subheader("Poster")
    if poster_b:
        st.image(Image.open(io.BytesIO(poster_b)), use_container_width=True)
        st.download_button(
            "📥 Download Poster (untuk zoom)",
            data=poster_b,
            file_name=poster_fn or "poster.png",
            mime="image/png",
            use_container_width=True
        )
    else:
        st.info("Poster belum dimasukkan oleh urusetia.")

    st.markdown("---")

    # 2) CHECK-IN
    st.subheader("Check-in")
    st.markdown('<div class="hint">Masukkan email jemputan untuk semak nombor meja.</div>', unsafe_allow_html=True)
    email = norm_email(st.text_input("Email", placeholder="contoh: nama@uitm.edu.my"))

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tidak dijumpai dalam senarai jemputan. Sila hubungi urusetia.")
        else:
            email_db, nama, gelaran, no_meja = row
            status = "Rekod wujud (sudah check-in)" if already_checked_in(email_db) else "Sila sahkan kehadiran anda"

            st.success(f"Nama: {nama}")
            st.info(f"No Meja: **{no_meja}**")
            st.caption(status)

            colA, colB = st.columns(2)
            with colA:
                if st.button("✅ Confirm Check-in", use_container_width=True):
                    confirm_checkin((email_db, nama, gelaran, no_meja))
                    st.success("Check-in berjaya direkod. Terima kasih!")
                    st.toast("✅ Check-in confirmed", icon="🎉")
            with colB:
                if st.button("🔄 Reset", use_container_width=True):
                    st.rerun()

    st.markdown("---")

    # 3) LAYOUT
    st.subheader("Layout Meja")
    layout_row = load_layout_image_bytes()
    if layout_row and layout_row[1]:
        fn, layout_bytes, updated_at = layout_row
        st.image(Image.open(io.BytesIO(layout_bytes)), use_container_width=True)
        st.download_button(
            "📥 Download Layout (untuk zoom)",
            data=layout_bytes,
            file_name=fn or "layout.png",
            mime="image/png",
            use_container_width=True
        )
    else:
        st.info("Layout belum dimasukkan oleh urusetia.")

    st.markdown("---")

    # 4) ATURCARA (PNG)
    st.subheader("Aturcara Majlis")
    if atur_b:
        st.image(Image.open(io.BytesIO(atur_b)), use_container_width=True)
        st.download_button(
            "📥 Download Aturcara (untuk zoom)",
            data=atur_b,
            file_name=atur_fn or "aturcara.png",
            mime="image/png",
            use_container_width=True
        )
    else:
        st.info("Aturcara belum dimasukkan oleh urusetia.")

# =========================
# ADMIN PAGE
# =========================
else:
    st.title("🛠️ Admin")

    # PIN lock
    if ADMIN_PIN_ENABLED:
        if "admin_ok" not in st.session_state:
            st.session_state.admin_ok = False

        if not st.session_state.admin_ok:
            pin = st.text_input("Masukkan PIN Admin", type="password", placeholder="PIN")
            if st.button("Unlock Admin", use_container_width=True):
                if pin == ADMIN_PIN:
                    st.session_state.admin_ok = True
                    st.success("Admin unlocked.")
                    st.rerun()
                else:
                    st.error("PIN salah.")
            st.stop()

    st.subheader("1) Upload Master List Tetamu (Excel)")
    st.caption("Kolum wajib: Email, Nama, No_Meja")
    up_master = st.file_uploader("Upload Excel (Master)", type=["xlsx"], key="master_upl")
    if up_master is not None:
        try:
            df = pd.read_excel(up_master)
            import_master(df)
            st.success("Master list berjaya diimport / dikemaskini.")
        except Exception as e:
            st.error(f"Gagal import master: {e}")

    st.markdown("---")
    st.subheader("2) Upload Poster / Layout / Aturcara (PNG)")
    col1, col2, col3 = st.columns(3)

    with col1:
        up_poster = st.file_uploader("Upload Poster (JPG/PNG)", type=["jpg", "jpeg", "png"], key="poster_upl")
        if up_poster is not None:
            try:
                b = up_poster.read()
                save_poster(up_poster.name, b)
                st.success("Poster disimpan.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal simpan poster: {e}")

    with col2:
        up_layout = st.file_uploader("Upload Layout (JPG/PNG)", type=["jpg", "jpeg", "png"], key="layout_upl")
        if up_layout is not None:
            try:
                b = up_layout.read()
                save_layout_image(up_layout.name, b)
                st.success("Layout disimpan.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal simpan layout: {e}")

    with col3:
        up_atur = st.file_uploader("Upload Aturcara (JPG/PNG)", type=["jpg", "jpeg", "png"], key="atur_upl")
        if up_atur is not None:
            try:
                b = up_atur.read()
                save_aturcara(up_atur.name, b)
                st.success("Aturcara disimpan.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal simpan aturcara: {e}")

    assets = load_assets()
    if assets:
        poster_fn, poster_b, atur_fn, atur_b, upd = assets
        st.caption(f"Rekod semasa • Poster: {poster_fn or '-'} • Aturcara: {atur_fn or '-'} • Kemaskini: {upd or '-'}")

    st.markdown("---")
    st.subheader("3) Statistik & Kehadiran")
    total, hadir, belum = count_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jemputan", total)
    c2.metric("Dah Check-in", hadir)
    c3.metric("Belum Hadir", belum)

    att = load_attendance()
    st.dataframe(att, use_container_width=True, height=280)

    st.markdown("---")
    with st.expander("⚠️ Maintenance", expanded=False):
        st.caption("Reset untuk event baru.")

        colA, colB, colC = st.columns(3)
        with colA:
            if st.button("Reset MASTER", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM master")
                    conn.commit()
                st.success("MASTER dikosongkan.")
                st.rerun()

        with colB:
            if st.button("Reset Attendance", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM attendance")
                    conn.commit()
                st.success("Attendance dikosongkan.")
                st.rerun()

        with colC:
            if st.button("Reset Poster+Layout+Aturcara", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM event_assets")
                    conn.execute("DELETE FROM layout_config")
                    conn.commit()
                st.success("Poster, layout dan aturcara dikosongkan.")
                st.rerun()

        st.markdown("---")
        if st.button("🔥 Reset SEMUA", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM master")
                conn.execute("DELETE FROM attendance")
                conn.execute("DELETE FROM event_assets")
                conn.execute("DELETE FROM layout_config")
                conn.commit()
            st.success("SEMUA data dikosongkan.")
            st.rerun()
