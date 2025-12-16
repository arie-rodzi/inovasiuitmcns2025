import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time
import pytz
from PIL import Image, ImageDraw
import io

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Event Check-in + Layout", page_icon="🎫", layout="centered")

DB_NAME = "dinner.db"

ADMIN_PIN_ENABLED = True
ADMIN_PIN = "2025"   # tukar PIN di sini

TZ = pytz.timezone("Asia/Kuala_Lumpur")

# =========================
# DB
# =========================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # Master + Attendance + Winners (kekal gelaran utk backward-compat, tapi UI tak guna)
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

        # Layout config (1 row sahaja)
        c.execute("""
        CREATE TABLE IF NOT EXISTS layout_config (
            id INTEGER PRIMARY KEY CHECK (id=1),
            filename TEXT,
            image_bytes BLOB,
            updated_at TEXT
        )""")

        # Mapping meja -> koordinat
        c.execute("""
        CREATE TABLE IF NOT EXISTS table_map (
            no_meja TEXT PRIMARY KEY,
            x INTEGER,
            y INTEGER,
            r INTEGER
        )""")

        conn.commit()

def now_myt_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

# =========================
# MASTER IMPORT
# =========================
def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    """
    Master Excel kolum wajib:
      - Email
      - Nama
      - No_Meja

    Kolum optional:
      - Gelaran (jika ada, sistem simpan; jika tiada, auto kosong)
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["Email", "Nama", "No_Meja"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolum wajib tiada: {missing}. Perlu: {required}")

    if "Gelaran" not in df.columns:
        df["Gelaran"] = ""

    df["Email"] = df["Email"].astype(str).str.strip().str.lower()
    df["Nama"] = df["Nama"].astype(str).str.strip()
    df["No_Meja"] = df["No_Meja"].astype(str).str.strip()
    df["Gelaran"] = df["Gelaran"].astype(str).str.strip()

    df = df[df["Email"].str.len() > 3]
    df = df.drop_duplicates(subset=["Email"], keep="last")
    return df[["Email", "Nama", "Gelaran", "No_Meja"]]

def import_master(df: pd.DataFrame):
    df = normalize_master(df)
    with get_conn() as conn:
        c = conn.cursor()
        for _, r in df.iterrows():
            c.execute("""
            INSERT INTO master(email, nama, gelaran, no_meja)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              nama=excluded.nama,
              gelaran=excluded.gelaran,
              no_meja=excluded.no_meja
            """, (r["Email"], r["Nama"], r["Gelaran"], r["No_Meja"]))
        conn.commit()

def get_guest(email: str):
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT email, nama, gelaran, no_meja FROM master WHERE email=?", (email,))
        return c.fetchone()

def already_checked_in(email: str) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM attendance WHERE email=? LIMIT 1", (email,))
        return c.fetchone() is not None

def confirm_checkin(row):
    now = now_myt_str()
    time.sleep(0.12)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO attendance(email, timestamp, nama, gelaran, no_meja)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          timestamp=excluded.timestamp,
          nama=excluded.nama,
          gelaran=excluded.gelaran,
          no_meja=excluded.no_meja
        """, (row[0], now, row[1], row[2], row[3]))
        conn.commit()

def count_stats():
    with get_conn() as conn:
        c = conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM master").fetchone()[0]
        hadir = c.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    return total, hadir, max(total - hadir, 0)

def load_attendance():
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT email, timestamp, nama, no_meja FROM attendance ORDER BY timestamp DESC",
            conn
        )

# =========================
# LAYOUT + MAP
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
        row = conn.execute("SELECT filename, image_bytes, updated_at FROM layout_config WHERE id=1").fetchone()
    return row  # (filename, bytes, updated_at) atau None

def upsert_table_map(df_map: pd.DataFrame):
    """
    Mapping file kolum wajib:
      - No_Meja
      - x
      - y
    Kolum optional:
      - r (default 18)
    """
    df = df_map.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["No_Meja", "x", "y"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolum wajib tiada: {missing}. Perlu: {required}")

    if "r" not in df.columns:
        df["r"] = 18

    df["No_Meja"] = df["No_Meja"].astype(str).str.strip().str.upper()
    df["x"] = pd.to_numeric(df["x"], errors="coerce").fillna(0).astype(int)
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0).astype(int)
    df["r"] = pd.to_numeric(df["r"], errors="coerce").fillna(18).astype(int)

    df = df[df["No_Meja"].str.len() > 0]

    with get_conn() as conn:
        c = conn.cursor()
        for _, r in df.iterrows():
            c.execute("""
            INSERT INTO table_map(no_meja, x, y, r)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(no_meja) DO UPDATE SET
              x=excluded.x, y=excluded.y, r=excluded.r
            """, (r["No_Meja"], int(r["x"]), int(r["y"]), int(r["r"])))
        conn.commit()

def get_table_pos(no_meja: str):
    key = (no_meja or "").strip().upper()
    if not key:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT x, y, r FROM table_map WHERE no_meja=?", (key,)).fetchone()
    return row  # (x,y,r) or None

def list_mapped_tables(limit=500):
    with get_conn() as conn:
        df = pd.read_sql("SELECT no_meja, x, y, r FROM table_map ORDER BY no_meja ASC", conn)
    return df.head(limit)

def render_layout_with_highlight(layout_bytes: bytes, no_meja: str):
    img = Image.open(io.BytesIO(layout_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    pos = get_table_pos(no_meja)
    key = (no_meja or "").strip().upper()
    if pos and key:
        x, y, r = pos
        r = max(int(r), 8)
        # double ring
        draw.ellipse((x-r, y-r, x+r, y+r), outline="red", width=6)
        draw.ellipse((x-r-4, y-r-4, x+r+4, y+r+4), outline="white", width=2)
        draw.text((x + r + 8, y - 10), f"MEJA {key}", fill="red")
    return img

# =========================
# UI (CSS)
# =========================
def inject_css():
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
    </style>
    """, unsafe_allow_html=True)

def vip_card(nama, email, meja, status_text):
    st.markdown(
        f"""
        <div class="vip-card vip-animate">
          <div class="vip-title">🎓 EVENT CHECK-IN</div>
          <div class="vip-sub">Paparan Meja + Layout • MYT</div>

          <div class="vip-name">
            Selamat Datang<br>
            {nama}
          </div>

          <div class="vip-meja-box">
            <div class="vip-meja-label">NOMBOR MEJA ANDA</div>
            <div class="vip-meja-no">{meja}</div>
          </div>

          <div class="vip-status">{status_text}</div>
          <div class="vip-meta">{email} • MYT</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================
# APP
# =========================
init_db()
inject_css()

st.title("🎫 Sistem Check-in + Layout Meja")
st.caption("Admin upload Excel tetamu + gambar layout + mapping koordinat → Tetamu terus nampak meja & lokasi.")

tab1, tab2 = st.tabs(["✅ Check-in Tetamu", "🛠️ Admin (Setup Event)"])

# -------- TAB 1: CHECK-IN --------
with tab1:
    st.subheader("Semakan Kehadiran Tetamu")

    email = st.text_input("Masukkan Email Jemputan", placeholder="contoh: nama@uitm.edu.my").strip().lower()

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tidak dijumpai dalam senarai jemputan. Sila hubungi urusetia.")
        else:
            email_db, nama, gelaran, no_meja = row

            if already_checked_in(email_db):
                vip_card(nama, email_db, no_meja, "ℹ️ Rekod wujud (sudah check-in sebelum ini)")
            else:
                vip_card(nama, email_db, no_meja, "✔ Sila sahkan kehadiran anda")

            colA, colB = st.columns([1, 1])
            with colA:
                confirm = st.button("✅ Confirm Check-in", use_container_width=True)
            with colB:
                refresh = st.button("🔄 Reset / Tetamu seterusnya", use_container_width=True)

            if confirm:
                confirm_checkin(row)
                st.success("Check-in berjaya direkod. Terima kasih!")
                st.toast("✅ Check-in confirmed", icon="🎉")

            # Papar layout + highlight
            layout_row = load_layout_image_bytes()
            if layout_row:
                filename, layout_bytes, updated_at = layout_row
                if layout_bytes:
                    img_h = render_layout_with_highlight(layout_bytes, no_meja)
                    st.image(img_h, use_container_width=True, caption=f"Lokasi Meja {no_meja} (Layout: {filename})")
                else:
                    st.info("Layout disimpan tetapi tiada data imej. Admin perlu upload semula.")
            else:
                st.info("Layout belum diset. Admin perlu upload gambar layout & mapping dahulu.")

            # Warn kalau meja belum ada mapping
            if not get_table_pos(no_meja):
                st.warning(f"Mapping koordinat untuk meja {no_meja} belum ada. Admin perlu tambah dalam Table Map.")

            if refresh:
                st.rerun()

# -------- TAB 2: ADMIN --------
with tab2:
    st.subheader("Admin (Setup Event)")

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

    st.markdown("### 1) Upload Master List Tetamu (Excel)")
    st.caption("Kolum wajib: Email, Nama, No_Meja. (Gelaran tak perlu)")
    up_master = st.file_uploader("Upload Excel (Master)", type=["xlsx"], key="master_upl")
    if up_master is not None:
        try:
            df = pd.read_excel(up_master)
            import_master(df)
            st.success("Master list berjaya diimport / dikemaskini.")
        except Exception as e:
            st.error(f"Gagal import master: {e}")

    st.markdown("---")
    st.markdown("### 2) Upload Layout Image (JPG/PNG)")
    up_img = st.file_uploader("Upload Layout Image", type=["jpg", "jpeg", "png"], key="layout_upl")
    if up_img is not None:
        try:
            img_bytes = up_img.read()
            save_layout_image(up_img.name, img_bytes)
            st.success("Layout image berjaya disimpan.")
            st.image(Image.open(io.BytesIO(img_bytes)), use_container_width=True, caption=f"Preview: {up_img.name}")
        except Exception as e:
            st.error(f"Gagal simpan layout: {e}")

    layout_row = load_layout_image_bytes()
    if layout_row:
        fn, _, upd = layout_row
        st.caption(f"Layout semasa: {fn} • last update: {upd} (MYT)")

    st.markdown("---")
    st.markdown("### 3) Upload Table Map (Koordinat Meja)")
    st.caption("Fail CSV/XLSX dengan kolum: No_Meja, x, y, (optional r). Contoh: A1, 610, 390, 18")

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

    st.markdown("### 4) Tambah / Edit 1 Meja (Manual)")
    with st.form("add_one_map"):
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
        with c1:
            meja_in = st.text_input("No_Meja", placeholder="A1 / VIP1 / AJK1")
        with c2:
            x_in = st.number_input("x", min_value=0, max_value=10000, value=0, step=1)
        with c3:
            y_in = st.number_input("y", min_value=0, max_value=10000, value=0, step=1)
        with c4:
            r_in = st.number_input("r", min_value=5, max_value=200, value=18, step=1)

        save_one = st.form_submit_button("💾 Save Mapping")
        if save_one:
            try:
                df_one = pd.DataFrame([{"No_Meja": meja_in, "x": x_in, "y": y_in, "r": r_in}])
                upsert_table_map(df_one)
                st.success(f"Mapping {meja_in.strip().upper()} disimpan.")
            except Exception as e:
                st.error(f"Gagal simpan mapping: {e}")

    st.markdown("---")
    st.markdown("### 5) Preview Highlight (Test)")
    df_map_show = list_mapped_tables()
    st.dataframe(df_map_show, use_container_width=True, height=240)

    if layout_row and layout_row[1]:
        test_meja = st.text_input("Test No_Meja untuk highlight", placeholder="contoh: A1").strip().upper()
        if test_meja:
            img_test = render_layout_with_highlight(layout_row[1], test_meja)
            st.image(img_test, use_container_width=True, caption=f"Preview highlight: {test_meja}")
            if not get_table_pos(test_meja):
                st.warning("Meja ini belum ada mapping.")
    else:
        st.info("Upload layout image dahulu untuk preview highlight.")

    st.markdown("---")
    total, hadir, belum = count_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jemputan", total)
    c2.metric("Dah Check-in", hadir)
    c3.metric("Belum Hadir", belum)

    st.write("### 📋 Senarai Kehadiran (Real-time)")
    att = load_attendance()
    st.dataframe(att, use_container_width=True, height=280)

    with st.expander("⚠️ Maintenance", expanded=False):
        colx, coly, colz = st.columns(3)
        with colx:
            if st.button("Reset Attendance", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM attendance")
                    conn.commit()
                st.success("Attendance dikosongkan.")
                st.rerun()
        with coly:
            if st.button("Reset Winners", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM winners")
                    conn.commit()
                st.success("Winners dikosongkan.")
                st.rerun()
        with colz:
            if st.button("Reset Table Map", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM table_map")
                    conn.commit()
                st.success("Table map dikosongkan.")
                st.rerun()
