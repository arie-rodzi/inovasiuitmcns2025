import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time
import pytz
from PIL import Image, ImageDraw
import io
import re
import fitz  # pymupdf

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Event Check-in", page_icon="🎫", layout="centered")

DB_NAME = "dinner.db"

ADMIN_PIN_ENABLED = True
ADMIN_PIN = "2025"   # tukar PIN di sini

TZ = pytz.timezone("Asia/Kuala_Lumpur")


# =========================
# HELPERS: NORMALIZE
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


# =========================
# DB
# =========================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # Master + Attendance
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

        # Layout image (1 row)
        c.execute("""
        CREATE TABLE IF NOT EXISTS layout_config (
            id INTEGER PRIMARY KEY CHECK (id=1),
            filename TEXT,
            image_bytes BLOB,
            updated_at TEXT
        )""")

        # Poster + PDF (1 row)
        c.execute("""
        CREATE TABLE IF NOT EXISTS event_assets (
            id INTEGER PRIMARY KEY CHECK (id=1),
            poster_filename TEXT,
            poster_bytes BLOB,
            pdf_filename TEXT,
            pdf_bytes BLOB,
            updated_at TEXT
        )""")

        conn.commit()


# =========================
# MASTER IMPORT
# =========================
def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    """
    Wajib: Email, Nama, No_Meja
    Gelaran: jika tiada, auto kosong
    """
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
# LAYOUT IMAGE (STORE/LOAD)
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
        row = conn.execute(
            "SELECT filename, image_bytes, updated_at FROM layout_config WHERE id=1"
        ).fetchone()
    return row  # (filename, bytes, updated_at) atau None


# =========================
# EVENT ASSETS (POSTER + PDF)
# =========================
def save_event_poster(filename: str, poster_bytes: bytes):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO event_assets (id, poster_filename, poster_bytes, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            poster_filename=excluded.poster_filename,
            poster_bytes=excluded.poster_bytes,
            updated_at=excluded.updated_at
        """, (filename, poster_bytes, now_myt_str()))
        conn.commit()

def save_event_pdf(filename: str, pdf_bytes: bytes):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO event_assets (id, pdf_filename, pdf_bytes, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            pdf_filename=excluded.pdf_filename,
            pdf_bytes=excluded.pdf_bytes,
            updated_at=excluded.updated_at
        """, (filename, pdf_bytes, now_myt_str()))
        conn.commit()

def load_event_assets():
    with get_conn() as conn:
        row = conn.execute("""
            SELECT poster_filename, poster_bytes, pdf_filename, pdf_bytes, updated_at
            FROM event_assets WHERE id=1
        """).fetchone()
    return row  # (poster_fn, poster_bytes, pdf_fn, pdf_bytes, updated_at) atau None


# =========================
# RENDER: POSTER WITH TABLE TEXT
# =========================
def poster_with_table(poster_bytes: bytes, meja: str):
    img = Image.open(io.BytesIO(poster_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    meja = norm_meja(meja)
    text = f"MEJA {meja}" if meja else "MEJA"

    W, H = img.size

    # Kotak putih tengah (simple & jelas)
    box_w = int(W * 0.72)
    box_h = int(H * 0.14)
    x0 = (W - box_w) // 2
    y0 = int(H * 0.42)
    x1 = x0 + box_w
    y1 = y0 + box_h

    draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255))

    # Teks besar (tanpa font custom supaya deploy senang)
    # Anggaran posisi teks
    tx = x0 + int(box_w * 0.08)
    ty = y0 + int(box_h * 0.25)
    draw.text((tx, ty), text, fill=(0, 0, 0))

    return img


# =========================
# RENDER: PDF BYTES TO IMAGES (ANDROID FRIENDLY)
# =========================
def pdf_bytes_to_images(pdf_bytes: bytes, zoom: float = 2.0, limit_pages=None):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    mat = fitz.Matrix(zoom, zoom)

    total = doc.page_count
    n = total if limit_pages is None else min(total, int(limit_pages))

    images = []
    for i in range(n):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)

    doc.close()
    return images, total


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
      .vip-meja-no{
        font-size: 58px;
        font-weight: 950;
        color: #4B1F78;
        line-height: 1;
        margin-top: 6px;
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
          <div class="vip-sub">Paparan No Meja • MYT</div>

          <div class="vip-name">
            Selamat Datang<br>
            {nama}
          </div>

          <div class="vip-meja-box">
            <div class="vip-meja-label">NOMBOR MEJA ANDA</div>
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
inject_css()

st.title("🎫 Sistem Check-in Tetamu")
st.caption("Masukkan email jemputan untuk paparan nombor meja.")

tab1, tab2, tab3 = st.tabs(["✅ Check-in Tetamu", "🛠️ Admin", "📌 Poster & Aturcara"])

# -------------------------
# TAB 1: TETAMU
# -------------------------
with tab1:
    st.subheader("Semakan Kehadiran")

    email = st.text_input("Masukkan Email Jemputan", placeholder="contoh: nama@uitm.edu.my")
    email = norm_email(email)

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tidak dijumpai dalam senarai jemputan. Sila hubungi urusetia.")
        else:
            email_db, nama, gelaran, no_meja = row
            no_meja = norm_meja(no_meja)

            if already_checked_in(email_db):
                vip_card(nama, email_db, no_meja, "Rekod wujud (sudah check-in)")
            else:
                vip_card(nama, email_db, no_meja, "Sila sahkan kehadiran anda")

            # ✅ Poster pop-up + meja di tengah (jika poster ada)
            assets = load_event_assets()
            if assets:
                poster_fn, poster_bytes, pdf_fn, pdf_bytes, upd = assets
                if poster_bytes:
                    st.image(poster_with_table(poster_bytes, no_meja), use_container_width=True)

            colA, colB = st.columns([1, 1])
            with colA:
                confirm = st.button("✅ Confirm Check-in", use_container_width=True)
            with colB:
                refresh = st.button("🔄 Reset / Tetamu seterusnya", use_container_width=True)

            if confirm:
                confirm_checkin((email_db, nama, gelaran, no_meja))
                st.success("Check-in berjaya direkod. Terima kasih!")
                st.toast("✅ Check-in confirmed", icon="🎉")

            # ✅ Layout hanya paparan gambar (tiada koordinat, tiada teks pelik)
            layout_row = load_layout_image_bytes()
            if layout_row and layout_row[1]:
                with st.expander("Lihat Pelan Meja", expanded=False):
                    fn, layout_bytes, upd = layout_row
                    st.image(Image.open(io.BytesIO(layout_bytes)), use_container_width=True)

            if refresh:
                st.rerun()


# -------------------------
# TAB 2: ADMIN
# -------------------------
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

    st.markdown("### 1) Upload Master List Tetamu (Excel)")
    st.caption("Kolum wajib: Email, Nama, No_Meja. Gelaran jika ada.")
    up_master = st.file_uploader("Upload Excel (Master)", type=["xlsx"], key="master_upl")
    if up_master is not None:
        try:
            df = pd.read_excel(up_master)
            import_master(df)
            st.success("Master list berjaya diimport / dikemaskini.")
        except Exception as e:
            st.error(f"Gagal import master: {e}")

    st.markdown("---")
    st.markdown("### 2) Upload Poster & Aturcara")
    col1, col2 = st.columns(2)

    with col1:
        up_poster = st.file_uploader("Upload Poster (JPG/PNG)", type=["jpg", "jpeg", "png"], key="poster_upl")
        if up_poster is not None:
            try:
                poster_bytes = up_poster.read()
                save_event_poster(up_poster.name, poster_bytes)
                st.success("Poster disimpan.")
                st.image(Image.open(io.BytesIO(poster_bytes)), use_container_width=True)
                st.rerun()
            except Exception as e:
                st.error(f"Gagal simpan poster: {e}")

    with col2:
        up_pdf = st.file_uploader("Upload Aturcara (PDF)", type=["pdf"], key="pdf_upl")
        if up_pdf is not None:
            try:
                pdf_bytes = up_pdf.read()
                save_event_pdf(up_pdf.name, pdf_bytes)
                st.success("Aturcara disimpan.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal simpan PDF: {e}")

    assets = load_event_assets()
    if assets:
        poster_fn, poster_bytes, pdf_fn, pdf_bytes, upd = assets
        st.caption(f"Rekod semasa • Poster: {poster_fn or '-'} • Aturcara: {pdf_fn or '-'} • Kemaskini: {upd or '-'}")

    st.markdown("---")
    st.markdown("### 3) Upload Pelan Meja (Layout)")
    up_layout = st.file_uploader("Upload Layout (JPG/PNG)", type=["jpg", "jpeg", "png"], key="layout_upl")
    if up_layout is not None:
        try:
            layout_bytes = up_layout.read()
            save_layout_image(up_layout.name, layout_bytes)
            st.success("Layout disimpan.")
            st.image(Image.open(io.BytesIO(layout_bytes)), use_container_width=True)
            st.rerun()
        except Exception as e:
            st.error(f"Gagal simpan layout: {e}")

    layout_row = load_layout_image_bytes()
    if layout_row:
        fn, _, upd = layout_row
        st.caption(f"Layout semasa: {fn} • Kemaskini: {upd}")

    st.markdown("---")
    total, hadir, belum = count_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jemputan", total)
    c2.metric("Dah Check-in", hadir)
    c3.metric("Belum Hadir", belum)

    st.write("### 📋 Senarai Kehadiran")
    att = load_attendance()
    st.dataframe(att, use_container_width=True, height=280)


# -------------------------
# TAB 3: POSTER & ATURCARA (PHONE FRIENDLY)
# -------------------------
with tab3:
    st.subheader("Poster & Aturcara")

    assets = load_event_assets()
    if not assets:
        st.info("Poster dan aturcara belum dimasukkan.")
    else:
        poster_fn, poster_bytes, pdf_fn, pdf_bytes, upd = assets

        st.markdown("### Poster")
        if poster_bytes:
            st.image(Image.open(io.BytesIO(poster_bytes)), use_container_width=True)
        else:
            st.info("Poster belum dimasukkan.")

        st.markdown("---")
        st.markdown("### Aturcara Majlis")
        if pdf_bytes:
            # Default: show first 2 pages supaya ringan, boleh tick untuk semua
            show_all = st.checkbox("Papar semua muka surat", value=False)
            limit_pages = None if show_all else 2

            try:
                imgs, total_pages = pdf_bytes_to_images(pdf_bytes, zoom=2.0, limit_pages=limit_pages)
                st.caption(f"Jumlah muka surat: {total_pages}")

                for idx, im in enumerate(imgs, start=1):
                    st.image(im, use_container_width=True, caption=f"Muka surat {idx}")

                if not show_all and total_pages > 2:
                    st.info("Tick 'Papar semua muka surat' untuk lihat keseluruhan aturcara.")
            except Exception as e:
                st.error(f"PDF tidak dapat dipaparkan: {e}")
        else:
            st.info("Aturcara belum dimasukkan.")


# -------------------------
# MAINTENANCE (ADMIN ONLY UI)
# -------------------------
with st.expander("⚠️ Maintenance", expanded=False):
    st.caption("Reset ini akan buang data lama. Guna bila nak mula event baru.")

    col1, col2, col3 = st.columns(3)

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
        if st.button("Reset Poster+Aturcara+Layout", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM event_assets")
                conn.execute("DELETE FROM layout_config")
                conn.commit()
            st.success("Poster, aturcara dan layout dikosongkan.")
            st.rerun()

    st.markdown("---")

    if st.button("🔥 Reset SEMUA", use_container_width=True):
        with get_conn() as conn:
            conn.execute("DELETE FROM master")
            conn.execute("DELETE FROM attendance")
            conn.execute("DELETE FROM event_assets")
            conn.execute("DELETE FROM layout_config")
            conn.commit()
        st.success("SEMUA data dikosongkan. Upload semula master dan bahan program.")
        st.rerun()
