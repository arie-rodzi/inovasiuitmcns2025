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
st.set_page_config(page_title="Pendaftaran Majlis Hari Inovasi UiTMCNS 2025", page_icon="📝", layout="centered")

DB_NAME = "dinner.db"

ADMIN_PIN_ENABLED = True
ADMIN_PIN = "2025"   # tukar PIN di sini

TZ = pytz.timezone("Asia/Kuala_Lumpur")


# =========================
# HELPERS: NORMALIZE
# =========================
def norm_meja(v) -> str:
    """Normalisasi No_Meja supaya match jemputan & koordinat (VIP 1 -> VIP1)."""
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


# =========================
# DB
# =========================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

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
        CREATE TABLE IF NOT EXISTS winners (
            email TEXT PRIMARY KEY,
            timestamp TEXT,
            nama TEXT,
            gelaran TEXT,
            no_meja TEXT
        )""")

        # Kekal (walaupun layout tak highlight lagi)
        c.execute("""
        CREATE TABLE IF NOT EXISTS table_map (
            no_meja TEXT PRIMARY KEY,
            x INTEGER,
            y INTEGER,
            r INTEGER
        )""")

        # minimal table; schema penuh akan dimigrate
        c.execute("""
        CREATE TABLE IF NOT EXISTS event_assets (
            id INTEGER PRIMARY KEY
        )
        """)

        conn.commit()

def migrate_event_assets_schema():
    """Auto-migrate table event_assets supaya DB lama tak crash."""
    cols = {
        "poster_filename": "TEXT",
        "poster_bytes": "BLOB",
        "layout_filename": "TEXT",
        "layout_bytes": "BLOB",
        "aturcara_filename": "TEXT",
        "aturcara_bytes": "BLOB",
        "updated_at": "TEXT",
    }

    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS event_assets (
            id INTEGER PRIMARY KEY,
            poster_filename TEXT,
            poster_bytes BLOB,
            layout_filename TEXT,
            layout_bytes BLOB,
            aturcara_filename TEXT,
            aturcara_bytes BLOB,
            updated_at TEXT
        )
        """)

        existing = [r[1] for r in conn.execute("PRAGMA table_info(event_assets)").fetchall()]
        for col, typ in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE event_assets ADD COLUMN {col} {typ}")

        conn.execute("""
            INSERT OR IGNORE INTO event_assets (id, updated_at)
            VALUES (1, ?)
        """, (now_myt_str(),))

        conn.commit()


# =========================
# ASSETS (Poster/Layout/Aturcara) in DB
# =========================
def save_asset(kind: str, filename: str, data: bytes):
    """kind: 'poster' | 'layout' | 'aturcara'"""
    if kind not in ("poster", "layout", "aturcara"):
        raise ValueError("Invalid kind for asset.")

    col_fn = f"{kind}_filename"
    col_by = f"{kind}_bytes"

    with get_conn() as conn:
        conn.execute(f"""
            UPDATE event_assets
            SET {col_fn} = ?,
                {col_by} = ?,
                updated_at = ?
            WHERE id = 1
        """, (filename, data, now_myt_str()))
        conn.commit()

def load_assets():
    with get_conn() as conn:
        row = conn.execute("""
            SELECT poster_filename, poster_bytes,
                   layout_filename, layout_bytes,
                   aturcara_filename, aturcara_bytes,
                   updated_at
            FROM event_assets
            WHERE id=1
        """).fetchone()
    return row

def get_asset_bytes(kind: str):
    row = load_assets()
    if not row:
        return (None, None, None)
    poster_fn, poster_by, layout_fn, layout_by, atur_fn, atur_by, upd = row
    if kind == "poster":
        return (poster_fn, poster_by, upd)
    if kind == "layout":
        return (layout_fn, layout_by, upd)
    if kind == "aturcara":
        return (atur_fn, atur_by, upd)
    return (None, None, upd)


# =========================
# MASTER IMPORT
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
        row = conn.execute("SELECT email, nama, gelaran, no_meja FROM master WHERE email=?", (email,)).fetchone()
    if not row:
        return None
    return (row[0], row[1], row[2], norm_meja(row[3]))

def already_checked_in(email: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM attendance WHERE email=? LIMIT 1", (email,)).fetchone() is not None

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
# TABLE MAP (KEKAL)
# =========================
def upsert_table_map(df_map: pd.DataFrame):
    df = df_map.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["No_Meja", "x", "y"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolum wajib tiada: {missing}. Perlu: {required}")

    if "r" not in df.columns:
        df["r"] = 18

    df["No_Meja"] = df["No_Meja"].apply(norm_meja)
    df["x"] = pd.to_numeric(df["x"], errors="coerce").fillna(0).astype(int)
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0).astype(int)
    df["r"] = pd.to_numeric(df["r"], errors="coerce").fillna(18).astype(int)

    df = df[df["No_Meja"].str.len() > 0]

    with get_conn() as conn:
        for _, r in df.iterrows():
            conn.execute("""
            INSERT INTO table_map(no_meja, x, y, r)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(no_meja) DO UPDATE SET
              x=excluded.x, y=excluded.y, r=excluded.r
            """, (r["No_Meja"], int(r["x"]), int(r["y"]), int(r["r"])))
        conn.commit()

def list_mapped_tables(limit=500):
    with get_conn() as conn:
        df = pd.read_sql("SELECT no_meja, x, y, r FROM table_map ORDER BY no_meja ASC", conn)
    return df.head(limit)


# =========================
# UI (CSS)
# =========================
def inject_css():
    # LOCK ZOOM untuk phone (laptop tetap boleh zoom browser)
    st.markdown(
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">',
        unsafe_allow_html=True
    )

    st.markdown("""
    <style>
      .block-container { padding-top: 1.1rem; }
      @keyframes popFade {
        0%   { opacity: 0; transform: translateY(12px) scale(0.985); filter: blur(2px); }
        70%  { opacity: 1; transform: translateY(-2px) scale(1.01); filter: blur(0); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
      }
      .vip-animate { animation: popFade 520ms ease-out both; }
      .vip-card {
        background: linear-gradient(135deg, #4B1F78, #6A2FA3);
        border-radius: 22px;
        padding: 22px 18px;
        margin-top: 14px;
        box-shadow: 0 18px 40px rgba(0,0,0,0.25);
        color: white;
        position: relative;
        overflow: hidden;
      }
      .vip-card::before{
        content:"";
        position:absolute;
        width: 280px; height: 280px;
        right:-120px; top:-140px;
        background: radial-gradient(circle at 30% 30%, rgba(201,162,39,.55), transparent 60%);
        transform: rotate(18deg);
      }
      .vip-card::after{
        content:"";
        position:absolute;
        inset: 10px;
        border: 2px dashed rgba(201,162,39,.85);
        border-radius: 18px;
        pointer-events:none;
      }
      .vip-title{ position: relative; text-align:center; font-weight: 900; font-size: 18px; }
      .vip-sub{ position: relative; text-align:center; font-size: 13px; opacity: .92; margin-top: 4px; }
      .vip-name{ position: relative; text-align:center; font-size: 20px; font-weight: 800; margin-top: 14px; }
      .vip-meja-box{
        position: relative;
        background: linear-gradient(180deg, #FFF7E6, #ffffff);
        border-radius: 18px;
        padding: 16px 12px;
        text-align:center;
        margin: 14px auto 0;
        width: min(520px, 92%);
        box-shadow: inset 0 0 0 2px rgba(201,162,39,.95);
      }
      .vip-meja-label{ font-size: 12px; font-weight: 900; color: #6A4B00; letter-spacing: 1px; }
      @keyframes pulseMeja { 0%,100% { transform: scale(1); } 50% { transform: scale(1.06); } }
      .vip-meja-no{
        font-size: 58px;
        font-weight: 950;
        color: #4B1F78;
        line-height: 1;
        margin-top: 6px;
        animation: pulseMeja 900ms ease-in-out 1;
      }
      .vip-status{ position: relative; margin-top: 12px; text-align:center; font-size: 14px; font-weight: 900; color: #D1FAE5; }
      .vip-meta{ position: relative; margin-top: 8px; text-align:center; font-size: 12px; opacity:.9; }
      .titleWrap{
        text-align:center;
        margin: 8px 0 14px 0;
      }
      .titleMain{
        font-size: 44px;
        font-weight: 950;
        letter-spacing: .3px;
        line-height: 1.05;
      }
      .titleSub{
        font-size: 18px;
        font-weight: 800;
        opacity: .75;
        margin-top: 6px;
      }
    </style>
    """, unsafe_allow_html=True)

def vip_card(nama, email, meja, status_text):
    st.markdown(
        f"""
        <div class="vip-card vip-animate">
          <div class="vip-title">📝 PENDAFTARAN</div>
          <div class="vip-sub">Sila semak maklumat anda</div>

          <div class="vip-name">
            Selamat Datang<br>
            {nama}
          </div>

          <div class="vip-meja-box">
            <div class="vip-meja-label">NOMBOR MEJA</div>
            <div class="vip-meja-no">{meja}</div>
          </div>

          <div class="vip-status">{status_text}</div>
          <div class="vip-meta">{email}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# APP START
# =========================
init_db()
migrate_event_assets_schema()
inject_css()

# Tajuk premium (center)
st.markdown("""
<div class="titleWrap">
  <div class="titleMain">Pendaftaran Majlis</div>
  <div class="titleSub">Hari Inovasi UiTMCNS 2025</div>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["✅ Pendaftaran", "🛠️ Admin"])


# =========================================================
# TAB 1: CHECK-IN (Poster → Check-in → Layout → Aturcara)
# =========================================================
with tab1:
    # Poster (atas sekali)
    _, poster_bytes, _ = get_asset_bytes("poster")
    if poster_bytes:
        try:
            st.image(Image.open(io.BytesIO(poster_bytes)), use_container_width=True)
        except Exception:
            st.warning("Poster gagal dibaca. Admin upload semula.")
    else:
        st.info("Poster belum dimasukkan.")

    st.markdown("---")

    # Check-in
    st.subheader("Semakan Kehadiran")
    email = st.text_input("Masukkan Email Jemputan", placeholder="contoh: zahari@uitm.edu.my")
    email = norm_email(email)

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tidak dijumpai dalam senarai jemputan. Sila hubungi urusetia.")
        else:
            email_db, nama, gelaran, no_meja = row
            no_meja = norm_meja(no_meja)

            if already_checked_in(email_db):
                vip_card(nama, email_db, no_meja, "ℹ️ Rekod wujud (sudah daftar)")
            else:
                vip_card(nama, email_db, no_meja, "✔ Sila sahkan pendaftaran anda")

            colA, colB = st.columns([1, 1])
            with colA:
                confirm = st.button("✅ Confirm", use_container_width=True)
            with colB:
                refresh = st.button("🔄 Reset", use_container_width=True)

            if confirm:
                confirm_checkin((email_db, nama, gelaran, no_meja))
                st.success("Pendaftaran berjaya direkod. Terima kasih!")
                st.toast("✅ Confirmed", icon="🎉")

            # Layout (TANPA koordinat / TANPA highlight)
            st.markdown("---")
            st.subheader("🗺️ Layout Dewan")

            _, layout_bytes, _ = get_asset_bytes("layout")
            if layout_bytes:
                try:
                    st.image(Image.open(io.BytesIO(layout_bytes)), use_container_width=True)
                except Exception:
                    st.warning("Layout gagal dibaca. Admin upload semula.")
            else:
                st.info("Layout belum dimasukkan.")

            # Aturcara
            st.markdown("---")
            st.subheader("📌 Aturcara")

            _, atur_bytes, _ = get_asset_bytes("aturcara")
            if atur_bytes:
                try:
                    st.image(Image.open(io.BytesIO(atur_bytes)), use_container_width=True)
                except Exception:
                    st.warning("Aturcara gagal dibaca. Admin upload semula.")
            else:
                st.info("Aturcara belum dimasukkan.")

            if refresh:
                st.rerun()


# =========================================================
# TAB 2: ADMIN (Upload semua 4 file)
# =========================================================
with tab2:
    st.subheader("Admin")

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

    # 1) Master XLSX
    st.markdown("### 1) Upload Master List (Excel)")
    up_master = st.file_uploader("Upload Excel (Master)", type=["xlsx"], key="master_upl")
    if up_master is not None:
        try:
            df = pd.read_excel(up_master)
            import_master(df)
            st.success("Master list berjaya diimport / dikemaskini.")
        except Exception as e:
            st.error(f"Gagal import master: {e}")

    st.markdown("---")

    # 2) Poster
    st.markdown("### 2) Upload Poster (PNG/JPG)")
    up_poster = st.file_uploader("Upload Poster", type=["png", "jpg", "jpeg"], key="poster_upl")
    if up_poster is not None:
        try:
            data = up_poster.read()
            save_asset("poster", up_poster.name, data)
            st.success("Poster disimpan.")
            st.image(Image.open(io.BytesIO(data)), use_container_width=True)
        except Exception as e:
            st.error(f"Gagal simpan poster: {e}")

    st.markdown("---")

    # 3) Layout
    st.markdown("### 3) Upload Layout (PNG/JPG)")
    up_layout = st.file_uploader("Upload Layout", type=["png", "jpg", "jpeg"], key="layout_upl")
    if up_layout is not None:
        try:
            data = up_layout.read()
            save_asset("layout", up_layout.name, data)
            st.success("Layout disimpan.")
            st.image(Image.open(io.BytesIO(data)), use_container_width=True)
        except Exception as e:
            st.error(f"Gagal simpan layout: {e}")

    st.markdown("---")

    # 4) Aturcara
    st.markdown("### 4) Upload Aturcara (PNG/JPG)")
    up_atur = st.file_uploader("Upload Aturcara", type=["png", "jpg", "jpeg"], key="aturcara_upl")
    if up_atur is not None:
        try:
            data = up_atur.read()
            save_asset("aturcara", up_atur.name, data)
            st.success("Aturcara disimpan.")
            st.image(Image.open(io.BytesIO(data)), use_container_width=True)
        except Exception as e:
            st.error(f"Gagal simpan aturcara: {e}")

    # Status ringkas tanpa nama fail
    st.markdown("---")
    st.markdown("### ✅ Status Upload")
    assets = load_assets()
    if assets:
        _, poster_by, _, layout_by, _, atur_by, _ = assets
        c1, c2, c3 = st.columns(3)
        c1.metric("Poster", "✅" if poster_by else "—")
        c2.metric("Layout", "✅" if layout_by else "—")
        c3.metric("Aturcara", "✅" if atur_by else "—")
    else:
        st.info("Belum ada assets disimpan.")

    # Table Map kekal (kalau nak guna kemudian)
    st.markdown("---")
    st.markdown("### Table Map (Optional)")
    map_choice = st.radio("Format mapping", ["CSV", "Excel (XLSX)"], horizontal=True)
    if map_choice == "CSV":
        up_map = st.file_uploader("Upload Mapping CSV", type=["csv"], key="map_csv")
        if up_map is not None:
            try:
                dfm = pd.read_csv(up_map)
                upsert_table_map(dfm)
                st.success("Table map berjaya diimport / dikemaskini.")
            except Exception as e:
                st.error(f"Gagal import mapping: {e}")
    else:
        up_map = st.file_uploader("Upload Mapping Excel", type=["xlsx"], key="map_xlsx")
        if up_map is not None:
            try:
                dfm = pd.read_excel(up_map)
                upsert_table_map(dfm)
                st.success("Table map berjaya diimport / dikemaskini.")
            except Exception as e:
                st.error(f"Gagal import mapping: {e}")

    df_map_show = list_mapped_tables()
    st.dataframe(df_map_show, use_container_width=True, height=220)

    st.markdown("---")
    total, hadir, belum = count_stats()
    a, b, c = st.columns(3)
    a.metric("Total Jemputan", total)
    b.metric("Dah Daftar", hadir)
    c.metric("Belum Hadir", belum)

    st.write("### 📋 Senarai Kehadiran")
    att = load_attendance()
    st.dataframe(att, use_container_width=True, height=280)


# =========================================================
# MAINTENANCE (GLOBAL)
# =========================================================
with st.expander("⚠️ Maintenance", expanded=False):
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if st.button("Reset MASTER", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM master")
                conn.commit()
            st.success("MASTER dikosongkan.")
            st.rerun()

    with col2:
        if st.button("Reset Attendance", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM attendance")
                conn.commit()
            st.success("Attendance dikosongkan.")
            st.rerun()

    with col3:
        if st.button("Reset Winners", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM winners")
                conn.commit()
            st.success("Winners dikosongkan.")
            st.rerun()

    with col4:
        if st.button("Reset Table Map", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM table_map")
                conn.commit()
            st.success("Table map dikosongkan.")
            st.rerun()

    with col5:
        if st.button("Reset Assets", use_container_width=True):
            with get_conn() as conn:
                conn.execute("""
                    UPDATE event_assets
                    SET poster_filename=NULL, poster_bytes=NULL,
                        layout_filename=NULL, layout_bytes=NULL,
                        aturcara_filename=NULL, aturcara_bytes=NULL,
                        updated_at=?
                    WHERE id=1
                """, (now_myt_str(),))
                conn.commit()
            st.success("Assets dikosongkan.")
            st.rerun()

    st.markdown("---")

    if st.button("🔥 Reset SEMUA", use_container_width=True):
        with get_conn() as conn:
            conn.execute("DELETE FROM master")
            conn.execute("DELETE FROM attendance")
            conn.execute("DELETE FROM winners")
            conn.execute("DELETE FROM table_map")
            conn.execute("""
                UPDATE event_assets
                SET poster_filename=NULL, poster_bytes=NULL,
                    layout_filename=NULL, layout_bytes=NULL,
                    aturcara_filename=NULL, aturcara_bytes=NULL,
                    updated_at=?
                WHERE id=1
            """, (now_myt_str(),))
            conn.commit()
        st.success("SEMUA data dikosongkan. Upload semula master + 3 gambar + mapping (optional).")
        st.rerun()
