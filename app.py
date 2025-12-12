import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Majlis Hari Inovasi UiTM 2025",
    page_icon="🎫",
    layout="centered"
)

DB_NAME = "dinner.db"

# Optional: letak PIN admin (tukar ikut suka)
ADMIN_PIN_ENABLED = True
ADMIN_PIN = "2025"   # tukar PIN di sini

# =========================
# DB HELPERS
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

def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # standardize column names (case/space tolerant)
    df.columns = [str(c).strip() for c in df.columns]

    required = ["Email", "Nama", "Gelaran", "No_Meja"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolum wajib tiada: {missing}. Perlu: {required}")

    df["Email"] = df["Email"].astype(str).str.strip().str.lower()
    df["Nama"] = df["Nama"].astype(str).str.strip()
    df["Gelaran"] = df["Gelaran"].astype(str).str.strip()
    df["No_Meja"] = df["No_Meja"].astype(str).str.strip()
    df = df[df["Email"].str.len() > 3]  # buang row kosong pelik
    df = df.drop_duplicates(subset=["Email"], keep="last")
    return df[required]

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
        row = c.fetchone()
    return row  # (email, nama, gelaran, no_meja)

def already_checked_in(email: str) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM attendance WHERE email=? LIMIT 1", (email,))
        return c.fetchone() is not None

def confirm_checkin(row):
    # row = (email, nama, gelaran, no_meja)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # micro-safety: reduce collision when ramai tekan serentak
    time.sleep(0.15)
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
        return pd.read_sql("SELECT * FROM attendance ORDER BY timestamp DESC", conn)

def load_winners():
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM winners ORDER BY timestamp DESC", conn)

def pick_winner():
    with get_conn() as conn:
        att = pd.read_sql("SELECT * FROM attendance", conn)
        win = pd.read_sql("SELECT * FROM winners", conn)

        if att.empty:
            return None, "Belum ada tetamu check-in."

        eligible = att if win.empty else att[~att["email"].isin(win["email"])]

        if eligible.empty:
            return None, "Semua tetamu yang hadir sudah menang."

        row = eligible.sample(1).iloc[0]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
        INSERT OR IGNORE INTO winners(email, timestamp, nama, gelaran, no_meja)
        VALUES (?, ?, ?, ?, ?)
        """, (row["email"], now, row["nama"], row["gelaran"], row["no_meja"]))
        conn.commit()

    return row, None

# =========================
# UI STYLES (premium + animation)
# =========================
def inject_global_css():
    st.markdown("""
    <style>
      /* tighten top padding a bit */
      .block-container { padding-top: 1.3rem; }

      @keyframes popFade {
        0%   { opacity: 0; transform: translateY(14px) scale(0.98); filter: blur(2px); }
        60%  { opacity: 1; transform: translateY(-2px) scale(1.01); filter: blur(0); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
      }
      .vip-animate { animation: popFade 520ms ease-out both; }

      .vip-card {
        background: linear-gradient(135deg, #4B1F78, #6A2FA3);
        border-radius: 22px;
        padding: 26px 22px;
        margin-top: 16px;
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
      .vip-title{
        position: relative;
        text-align:center;
        font-weight: 900;
        letter-spacing: .6px;
        font-size: 18px;
      }
      .vip-sub{
        position: relative;
        text-align:center;
        font-size: 13px;
        opacity: .92;
        margin-top: 4px;
      }
      .vip-name{
        position: relative;
        text-align:center;
        font-size: 20px;
        font-weight: 800;
        margin-top: 16px;
        line-height: 1.2;
      }
      .vip-meja-box{
        position: relative;
        background: linear-gradient(180deg, #FFF7E6, #ffffff);
        border-radius: 18px;
        padding: 18px 14px;
        text-align:center;
        margin: 16px auto 0;
        width: min(520px, 92%);
        box-shadow: inset 0 0 0 2px rgba(201,162,39,.95);
      }
      .vip-meja-label{
        font-size: 12px;
        font-weight: 900;
        color: #6A4B00;
        letter-spacing: 1px;
      }

      @keyframes pulseMeja {
        0%, 100% { transform: scale(1); }
        50%      { transform: scale(1.06); }
      }
      .vip-meja-no{
        font-size: 64px;
        font-weight: 950;
        color: #4B1F78;
        line-height: 1;
        margin-top: 6px;
        animation: pulseMeja 900ms ease-in-out 1;
      }

      .vip-status{
        position: relative;
        margin-top: 14px;
        text-align:center;
        font-size: 14px;
        font-weight: 900;
        color: #D1FAE5;
      }
      .vip-meta{
        position: relative;
        margin-top: 10px;
        text-align:center;
        font-size: 12px;
        opacity:.9;
      }
    </style>
    """, unsafe_allow_html=True)

def vip_card(gelaran, nama, email, meja, status_text="✔ Kehadiran Disahkan"):
    st.markdown(
        f"""
        <div class="vip-card vip-animate">
          <div class="vip-title">🎓 MAJLIS HARI INOVASI UiTM 2025</div>
          <div class="vip-sub">Tema: Nusantara • 18 Disember 2025</div>

          <div class="vip-name">
            Selamat Datang<br>
            {gelaran} {nama}
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
inject_global_css()

st.title("🎫 Majlis Hari Inovasi UiTM 2025")
st.caption("Check-in Digital • Email → Papar Nombor Meja • Tema Nusantara")

tab1, tab2 = st.tabs(["✅ Check-in Tetamu", "🛠️ Admin Dashboard"])

# =========================
# TAB 1: CHECK-IN
# =========================
with tab1:
    st.subheader("Semakan Kehadiran Tetamu")
    email = st.text_input(
        "Masukkan Email Jemputan",
        placeholder="contoh: zahari@uitm.edu.my"
    ).strip().lower()

    if email:
        row = get_guest(email)
        if not row:
            st.error("Email tidak dijumpai dalam senarai jemputan. Sila hubungi urusetia.")
        else:
            email_db, nama, gelaran, no_meja = row

            # show VIP card immediately
            if already_checked_in(email_db):
                vip_card(gelaran, nama, email_db, no_meja, status_text="ℹ️ Rekod wujud (sudah check-in sebelum ini)")
            else:
                vip_card(gelaran, nama, email_db, no_meja, status_text="✔ Sila sahkan kehadiran anda")

            # Confirm button
            colA, colB = st.columns([1, 1])
            with colA:
                confirm = st.button("✅ Confirm Check-in", use_container_width=True)
            with colB:
                refresh = st.button("🔄 Reset / Tetamu seterusnya", use_container_width=True)

            if confirm:
                confirm_checkin(row)
                st.success("Check-in berjaya direkod. Terima kasih!")
                st.toast("✅ Check-in confirmed", icon="🎉")

            if refresh:
                # streamlit reset: rerun will clear input
                st.rerun()

# =========================
# TAB 2: ADMIN
# =========================
with tab2:
    st.subheader("Admin Dashboard")

    # Admin PIN (optional)
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

    with st.expander("📥 Import / Update Master List (Excel)", expanded=True):
        up = st.file_uploader("Upload Excel (Master)", type=["xlsx"])
        if up is not None:
            try:
                df = pd.read_excel(up)
                import_master(df)
                st.success("Master list berjaya diimport / dikemaskini.")
            except Exception as e:
                st.error(f"Gagal import: {e}")

    total, hadir, belum = count_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jemputan", total)
    c2.metric("Dah Check-in", hadir)
    c3.metric("Belum Hadir", belum)

    st.markdown("---")

    st.write("### 📋 Senarai Kehadiran (Real-time)")
    att = load_attendance()
    st.dataframe(att, use_container_width=True, height=280)

    st.download_button(
        "⬇️ Download Attendance (CSV)",
        data=att.to_csv(index=False).encode("utf-8"),
        file_name="attendance.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.markdown("---")

    st.write("### 🎁 Cabutan Bertuah")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🎲 Pick Winner", use_container_width=True):
            winner, err = pick_winner()
            if err:
                st.error(err)
            else:
                st.balloons()
                st.success(f"PEMENANG: {winner['gelaran']} {winner['nama']}  •  Meja {winner['no_meja']}")
                st.caption(f"Email: {winner['email']}")
    with col2:
        if st.button("🔄 Refresh Dashboard", use_container_width=True):
            st.rerun()

    st.write("#### Winners Log")
    win = load_winners()
    st.dataframe(win, use_container_width=True, height=220)

    with st.expander("⚠️ Maintenance", expanded=False):
        st.caption("Gunakan hanya jika perlu (contoh: sebelum event test).")
        colx, coly = st.columns(2)
        with colx:
            if st.button("Reset Attendance (kosongkan)", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM attendance")
                    conn.commit()
                st.success("Attendance dikosongkan.")
                st.rerun()
        with coly:
            if st.button("Reset Winners (kosongkan)", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM winners")
                    conn.commit()
                st.success("Winners dikosongkan.")
                st.rerun()
