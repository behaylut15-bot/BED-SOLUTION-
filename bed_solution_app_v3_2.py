import streamlit as st
import pandas as pd
import datetime
import gspread
import json
import base64
import time
from collections import defaultdict
from google.oauth2 import service_account
from fpdf import FPDF
from kenat import Kenat
import os
import urllib.request

# =====================================================================
# PAGE CONFIG & BRAND PALETTE (BED SOLUTION BY LIQ FURNITURE)
# =====================================================================
st.set_page_config(
    page_title="Bed Solution — Executive & Batch Dashboard",
    page_icon="🛏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Brand Colors extracted from Bed Solution logo
FOREST_GREEN = "#2E5434"
DARK_GREEN   = "#182E1C"
DEEP_BLACK   = "#0B120D"
CARD_BG      = "#132416"
AMBER_GOLD   = "#E0A13B"
SOFT_GOLD    = "#F2C46D"
CRISP_WHITE  = "#FFFFFF"
MUTED_TEXT   = "#B8C7BA"

# --- AUTO-DOWNLOAD FONTS FOR PDF (SAFE FALLBACK) ---
font_ready = os.path.exists('DejaVuSans.ttf') and os.path.exists('DejaVuSans-Bold.ttf')
if not font_ready:
    try:
        urllib.request.urlretrieve("https://unpkg.com/dejavu-fonts-ttf@2.37/ttf/DejaVuSans.ttf", "DejaVuSans.ttf")
        urllib.request.urlretrieve("https://unpkg.com/dejavu-fonts-ttf@2.37/ttf/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf")
        font_ready = os.path.exists('DejaVuSans.ttf') and os.path.exists('DejaVuSans-Bold.ttf')
    except Exception:
        font_ready = False

# =====================================================================
# LUXURY DARK FOREST & AMBER GOLD UI THEME
# =====================================================================
st.markdown(f"""
    <style>
    .stApp {{
        background: radial-gradient(circle at top right, #1b3620 0%, {DEEP_BLACK} 55%);
        color: {CRISP_WHITE};
    }}
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {DARK_GREEN} 0%, {DEEP_BLACK} 100%);
        border-right: 1px solid rgba(224, 161, 59, 0.25);
    }}
    .brand-hero {{
        background: linear-gradient(135deg, {FOREST_GREEN} 0%, {DARK_GREEN} 100%);
        border: 1px solid rgba(224, 161, 59, 0.45);
        border-radius: 18px;
        padding: 22px 28px;
        margin-bottom: 22px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.45);
        text-align: center;
    }}
    .golden-title {{
        font-family: 'Segoe UI', 'Arial', sans-serif;
        font-size: clamp(36px, 6vw, 68px) !important;
        font-weight: 900 !important;
        letter-spacing: -1px;
        margin: 0;
        line-height: 1.05;
    }}
    .golden-title span.bed {{ color: {AMBER_GOLD}; }}
    .golden-title span.sol {{ color: {CRISP_WHITE}; font-weight: 300; }}
    .sub-title {{
        color: {MUTED_TEXT};
        font-size: clamp(12px, 1.5vw, 16px);
        letter-spacing: 4px;
        margin-top: 6px;
        font-weight: 700;
        text-transform: uppercase;
    }}
    .stMetric {{
        background: linear-gradient(145deg, {CARD_BG} 0%, #0d180f 100%);
        padding: 18px 20px;
        border-radius: 14px;
        color: {CRISP_WHITE};
        box-shadow: 0 6px 18px rgba(0,0,0,0.35);
        border: 1px solid rgba(224, 161, 59, 0.2);
        border-left: 5px solid {AMBER_GOLD};
    }}
    .stMetric label {{
        color: {MUTED_TEXT} !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}
    .stMetric [data-testid="stMetricValue"] {{
        color: {CRISP_WHITE} !important;
        font-size: 26px !important;
        font-weight: 800 !important;
    }}
    div[data-testid="stExpander"] {{
        background-color: rgba(19, 36, 22, 0.75);
        border: 1px solid rgba(224, 161, 59, 0.28);
        border-radius: 12px;
    }}
    div[data-baseweb="tab-list"] {{
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 8px !important;
        background: rgba(19, 36, 22, 0.6);
        padding: 8px;
        border-radius: 12px;
        border: 1px solid rgba(224, 161, 59, 0.2);
    }}
    .stTabs [data-baseweb="tab"] {{
        height: auto !important;
        white-space: normal !important;
        background-color: transparent !important;
        border-radius: 8px !important;
        padding: 9px 14px !important;
        color: {MUTED_TEXT} !important;
        font-weight: 600;
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {FOREST_GREEN} 0%, #224127 100%) !important;
        color: {AMBER_GOLD} !important;
        border: 1px solid {AMBER_GOLD} !important;
        font-weight: 800 !important;
    }}
    .alert-box {{
        background: rgba(160, 28, 28, 0.22);
        color: #FF8A8A;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #FF4B4B;
        margin-bottom: 16px;
        font-weight: 700;
    }}
    .smart-insight {{
        background: linear-gradient(135deg, rgba(46,84,52,0.45) 0%, rgba(19,36,22,0.85) 100%);
        border: 1px solid rgba(224, 161, 59, 0.35);
        border-left: 4px solid {AMBER_GOLD};
        padding: 14px 18px;
        border-radius: 10px;
        margin-bottom: 14px;
    }}
    .user-badge {{
        background: linear-gradient(135deg, {FOREST_GREEN} 0%, {DARK_GREEN} 100%);
        color: {AMBER_GOLD};
        padding: 12px;
        border-radius: 10px;
        text-align: center;
        font-weight: 800;
        margin-bottom: 12px;
        border: 1px solid {AMBER_GOLD};
    }}
    </style>
""", unsafe_allow_html=True)

# =====================================================================
# HELPERS & ETHIOPIAN CALENDAR
# =====================================================================
def to_ethiopian(date_val):
    if pd.isna(date_val):
        return ""
    try:
        k = Kenat(date_val.date() if hasattr(date_val, 'date') else date_val)
        return k.format({'lang': 'english'})
    except Exception:
        return str(date_val)

def get_eth_month_label(y, m):
    eth_months = ["Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit", "Megabit", "Miazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"]
    try:
        y_int, m_int = int(y), int(m)
        if y_int > 0 and 1 <= m_int <= 13:
            return f"{eth_months[m_int-1]} {y_int}"
    except Exception:
        pass
    return "Unknown Date"

def extract_id(val):
    if pd.isna(val):
        return ""
    val = str(val)
    if "(" in val and ")" in val:
        return val.split("(")[-1].replace(")", "").strip()
    return val.strip()

def fmt_qty(val):
    try:
        f = float(val)
        return f"{f:g}"
    except Exception:
        return str(val)

def get_logo_path():
    for fname in ["logo.png", "logo.jpg", "image_4da0a7.png", "bed_solution_logo.png"]:
        if os.path.exists(fname):
            return fname
    return None

def get_google_creds():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_service_account" in st.secrets:
            secret_data = st.secrets["gcp_service_account"]
            if "key_base64" in secret_data:
                json_str = base64.b64decode(secret_data["key_base64"]).decode('utf-8')
                key_dict = json.loads(json_str)
                return service_account.Credentials.from_service_account_info(key_dict, scopes=scope)
            else:
                return service_account.Credentials.from_service_account_info(secret_data, scopes=scope)
    except Exception:
        return service_account.Credentials.from_service_account_file('key.json', scopes=scope)

def get_sheet_url():
    return st.secrets.get("bed_solution_url", st.secrets.get("liq_url", ""))

# =====================================================================
# PROFESSIONAL PDF REPORT ENGINE (BED SOLUTION BRANDING)
# =====================================================================
class BedSolutionPDF(FPDF):
    def __init__(self, font_name='Helvetica'):
        super().__init__()
        self.font_name = font_name
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(10, 10, 10)

    def footer(self):
        self.set_y(self.h - 15)
        self.set_draw_color(224, 161, 59)
        self.set_line_width(0.35)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.set_y(self.h - 12)
        self.set_font(self.font_name, '', 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, f"Bed Solution by LIQ Furniture  |  Production & Inventory Report  |  Page {self.page_no()}", align='C')

def _init_pdf(fonts_available):
    if fonts_available:
        try:
            pdf = BedSolutionPDF('DejaVu')
            pdf.add_font('DejaVu', '', 'DejaVuSans.ttf')
            pdf.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf')
            return pdf
        except Exception:
            pass
    return BedSolutionPDF('Helvetica')

def _draw_report_header(pdf, f_name, title, subtitle):
    GREEN, GOLD = (46, 84, 52), (224, 161, 59)
    LIGHT_GRAY = (244, 247, 244)

    pdf.set_fill_color(*GREEN); pdf.rect(0, 0, pdf.w, 23, 'F')
    pdf.set_fill_color(*GOLD); pdf.rect(0, 23, pdf.w, 1.8, 'F')

    text_x = 10
    logo_file = get_logo_path()
    if logo_file:
        try:
            pdf.image(logo_file, x=10, y=4, w=15, h=15)
            text_x = 29
        except Exception:
            pass

    pdf.set_xy(text_x, 5); pdf.set_font(f_name, 'B', 16); pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, "BED SOLUTION", ln=True, align='L')
    pdf.set_xy(text_x, 13); pdf.set_font(f_name, '', 8); pdf.set_text_color(240, 245, 240)
    pdf.cell(0, 4, "BY LIQ FURNITURE  |  Mattress & Bed Manufacturing", align='L')

    pdf.set_y(7); pdf.set_x(10); pdf.set_font(f_name, 'B', 9); pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, "BATCH & COST REPORT", align='R')

    pdf.set_y(31); pdf.set_font(f_name, 'B', 13); pdf.set_text_color(*GREEN)
    pdf.cell(0, 8, title, ln=True, align='C')
    pdf.set_font(f_name, '', 9); pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, subtitle, ln=True, align='C')
    pdf.ln(3)

    meta_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, meta_y, pdf.w - 20, 8, 'DF')

    pdf.set_y(meta_y + 2); pdf.set_x(10); pdf.set_font(f_name, '', 8); pdf.set_text_color(50, 50, 50)
    gen_eth = to_ethiopian(pd.Timestamp.now())
    gen_greg = datetime.datetime.now().strftime("%b %d, %Y  %H:%M")
    pdf.cell(0, 4, f"Generated: {gen_greg}     |     {gen_eth} EC", ln=True, align='C')
    pdf.ln(4)

def _draw_table(pdf, f_name, headers, rows, font_size=7):
    GREEN, WHITE = (46, 84, 52), (255, 255, 255)
    LIGHT_GRAY, DARK = (244, 247, 244), (40, 40, 40)
    col_w = (pdf.w - 20) / len(headers)

    def _header_row():
        pdf.set_fill_color(*GREEN); pdf.set_text_color(*WHITE); pdf.set_font(f_name, 'B', font_size + 0.5)
        pdf.set_x(10)
        for h in headers:
            pdf.cell(col_w, 6, h, border=0, align='C', fill=True)
        pdf.ln()

    _header_row()

    if not rows:
        pdf.set_font(f_name, '', font_size + 1); pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 10, "No records found.", ln=True, align='C')
        return

    pdf.set_font(f_name, '', font_size); pdf.set_text_color(*DARK)

    def _fit(text):
        s = str(text).strip().replace('\n', ' ').replace('\r', '')
        if not s or s.lower() in ('nan', 'none'):
            return ''
        while pdf.get_string_width(s) > (col_w - 1.5) and len(s) > 1:
            s = s[:-1]
        return s

    for i, row in enumerate(rows):
        if pdf.get_y() + 5 > pdf.h - pdf.b_margin - 5:
            pdf.add_page()
            _header_row()
            pdf.set_font(f_name, '', font_size); pdf.set_text_color(*DARK)

        pdf.set_fill_color(*(LIGHT_GRAY if i % 2 == 0 else WHITE))
        pdf.set_x(10)
        for item in row:
            pdf.cell(col_w, 5.5, _fit(item), border=0, align='C', fill=True)
        pdf.ln()

def _draw_total_box(pdf, f_name, label, amount):
    GREEN, GOLD, WHITE = (46, 84, 52), (224, 161, 59), (255, 255, 255)
    pdf.ln(5)
    if pdf.get_y() + 20 > pdf.h - pdf.b_margin:
        pdf.add_page()

    box_w = 95; box_x = pdf.w - 10 - box_w; box_y = pdf.get_y()
    pdf.set_fill_color(*GOLD); pdf.rect(box_x, box_y, 3, 16, 'F')
    pdf.set_fill_color(*GREEN); pdf.rect(box_x + 3, box_y, box_w - 3, 16, 'F')

    pdf.set_xy(box_x + 8, box_y + 2); pdf.set_font(f_name, 'B', 8); pdf.set_text_color(*GOLD)
    pdf.cell(box_w - 11, 5, label.upper(), ln=True, align='L')

    pdf.set_xy(box_x + 8, box_y + 8); pdf.set_font(f_name, 'B', 13); pdf.set_text_color(*WHITE)
    pdf.cell(box_w - 11, 6, f"ETB {amount:,.2f}", ln=True, align='R')

def generate_batch_pdf(batch_no, bed_model, target_qty, status, total_cost, cost_per_bed, mat_df):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, f"Batch Production & BOM Report: {batch_no}", f"Model: {bed_model}  |  Status: {status}")

    GREEN, GOLD = (46, 84, 52), (224, 161, 59)
    LIGHT_GRAY, DARK = (244, 247, 244), (40, 40, 40)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, info_y, pdf.w - 20, 24, 'DF')
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 24, 'F')

    fields = [
        ("Batch Number", batch_no),
        ("Bed Model / Spec", bed_model),
        ("Produced / Target Qty", f"{fmt_qty(target_qty)} units  (Unit Material Cost: ETB {cost_per_bed:,.2f} / bed)")
    ]
    pdf.set_y(info_y + 3)
    for label, value in fields:
        pdf.set_x(18); pdf.set_font(f_name, 'B', 9); pdf.set_text_color(*GREEN)
        pdf.cell(42, 6, f"{label}:")
        pdf.set_font(f_name, '', 9); pdf.set_text_color(*DARK)
        pdf.cell(0, 6, str(value), ln=True)

    pdf.ln(3); _draw_total_box(pdf, f_name, "Total Batch Material Cost (FIFO)", total_cost); pdf.ln(8)

    pdf.set_font(f_name, 'B', 11); pdf.set_text_color(*GREEN)
    pdf.cell(0, 8, "Issued Raw Materials Breakdown", ln=True)

    headers = ["Date (EC)", "Stage / Component", "Material Name", "Qty Issued", "FIFO Cost (ETB)", "Operator"]
    rows = []
    if not mat_df.empty:
        for _, r in mat_df.iterrows():
            rows.append([
                str(to_ethiopian(r['Date'])),
                str(r.get('Sub_Item', 'General'))[:18],
                str(r.get('Material_Name', r['Material_ID']))[:24],
                fmt_qty(r['Qty']),
                f"{r['Cost']:,.2f}",
                str(r.get('Employee_Name', ''))[:14]
            ])
    _draw_table(pdf, f_name, headers, rows, font_size=7)
    return bytes(pdf.output())

def generate_stock_audit_pdf(month_label, op_qty, op_val, in_qty, in_val, out_qty, out_val, clo_qty, clo_val, per_mat_df, sig_sk, sig_mgr):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, "Stock Audit & Reconciliation", f"Month: {month_label}")

    GREEN, GOLD = (46, 84, 52), (224, 161, 59)
    LIGHT_GRAY, DARK = (244, 247, 244), (40, 40, 40)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.4)
    pdf.rect(10, info_y, pdf.w - 20, 26, 'DF')
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 26, 'F')

    pdf.set_xy(18, info_y + 4); pdf.set_font(f_name, 'B', 9); pdf.set_text_color(*GREEN)
    pdf.cell(0, 6, "FINANCIAL & QUANTITY SUMMARY", align='L')
    pdf.set_draw_color(*GOLD); pdf.line(18, info_y + 12, pdf.w - 14, info_y + 12)

    pdf.set_font(f_name, '', 8); pdf.set_text_color(*DARK)
    pdf.set_xy(20, info_y + 14); pdf.cell(85, 5, f"Opening: {fmt_qty(op_qty)} units / ETB {op_val:,.2f}")
    pdf.set_xy(20, info_y + 20); pdf.cell(85, 5, f"Purchased (+): {fmt_qty(in_qty)} units / ETB {in_val:,.2f}")
    pdf.set_xy(110, info_y + 14); pdf.cell(85, 5, f"Batch Issued (-): {fmt_qty(out_qty)} units / ETB {out_val:,.2f}")
    pdf.set_xy(110, info_y + 20); pdf.cell(85, 5, f"Closing: {fmt_qty(clo_qty)} units / ETB {clo_val:,.2f}")

    pdf.set_y(info_y + 30); _draw_total_box(pdf, f_name, "Closing Stock Value", clo_val); pdf.ln(8)

    headers = ["Material Name", "Opening", "In (+)", "Out (-)", "Closing", "Closing Value (ETB)"]
    rows = []
    if not per_mat_df.empty:
        for _, r in per_mat_df.iterrows():
            rows.append([
                str(r['Material_Name']),
                fmt_qty(r['Open_Qty']),
                fmt_qty(r['In_Qty']),
                fmt_qty(r['Out_Qty']),
                fmt_qty(r['Close_Qty']),
                f"{r['Close_Val']:,.2f}"
            ])
    _draw_table(pdf, f_name, headers, rows, font_size=6.5)

    pdf.ln(15); pdf.set_font(f_name, '', 9); sig_y = pdf.get_y()
    if sig_y > pdf.h - 40:
        pdf.add_page(); sig_y = pdf.get_y() + 10

    pdf.set_xy(15, sig_y); pdf.cell(70, 5, "Prepared By (Store Keeper):", align='L')
    pdf.set_xy(15, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_sk}", align='L')
    pdf.set_xy(15, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align='L')

    pdf.set_xy(115, sig_y); pdf.cell(70, 5, "Audited By (Production Manager):", align='L')
    pdf.set_xy(115, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_mgr}", align='L')
    pdf.set_xy(115, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align='L')
    return bytes(pdf.output())

# =====================================================================
# AUTHENTICATION
# =====================================================================
def authenticate():
    if "user" in st.session_state:
        return True

    st.markdown("## 🔒 Bed Solution — Sign In")
    users_secrets = None
    try:
        if "users" in st.secrets:
            users_secrets = st.secrets["users"]
    except Exception:
        users_secrets = None

    if not users_secrets:
        pwd = st.text_input("Password", type="password", key="legacy_pwd")
        if st.button("Login", type="primary"):
            if pwd == st.secrets.get("app_password", "BED2026"):
                st.session_state.user = {"username": "manager", "name": "Manager", "role": "manager"}
                st.rerun()
            else:
                st.error("❌ Wrong password")
        return False

    user_options = {}
    for uname, udata in users_secrets.items():
        display_name = udata.get('name', uname)
        role_name = udata.get('role', 'manager').title()
        user_options[f"{display_name} ({role_name})"] = uname

    with st.form("login_form", clear_on_submit=False):
        selected_display = st.selectbox("Select User Profile:", list(user_options.keys()))
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

    if submitted:
        uname = user_options[selected_display]
        user_data = users_secrets[uname]
        if user_data.get("password", "") == password:
            st.session_state.user = {
                "username": uname,
                "name": user_data.get("name", uname),
                "role": user_data.get("role", "manager")
            }
            st.rerun()
        else:
            st.error("❌ Incorrect password for this profile.")
    return False

def color_negative_red(val):
    if pd.isna(val):
        return ''
    try:
        return 'color: #FF5C5C; font-weight: bold;' if float(val) < 0 else ''
    except Exception:
        return ''

# =====================================================================
# GOOGLE SHEETS HELPERS (AUTO-CREATES TABS IF MISSING)
# =====================================================================
def _get_sheets_global():
    creds = get_google_creds()
    return gspread.authorize(creds).open_by_url(get_sheet_url())

def _ensure_sheet(ws_name, headers):
    sh = _get_sheets_global()
    try:
        ws = sh.worksheet(ws_name)
        first_row = ws.row_values(1)
        if not first_row:
            ws.append_row(headers)
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=2000, cols=len(headers))
        ws.append_row(headers)
        return ws

def get_sheet_df(sheet, tab_name):
    try:
        raw = sheet.worksheet(tab_name).get_all_values()
        if len(raw) > 1:
            df = pd.DataFrame(raw[1:], columns=raw[0])
            df = df.replace('', pd.NA).dropna(how='all')
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# =====================================================================
# MAIN APPLICATION
# =====================================================================
try:
    _run_app = authenticate()
except Exception as _auth_err:
    st.error(f"Startup / Auth Error: {_auth_err}")
    st.exception(_auth_err)
    _run_app = False

if _run_app:
    try:
        user = st.session_state.user
        role = str(user.get("role", "manager")).strip().lower()
        user_name = user.get("name", user.get("username", "Manager"))

        with st.sidebar:
            st.markdown(f'<div class="user-badge">🛏️ {user_name}<br><span style="font-size:11px; color:#FFFFFF;">{role.upper()}</span></div>', unsafe_allow_html=True)
            c_sb1, c_sb2 = st.columns(2)
            if c_sb1.button("🚪 Logout", use_container_width=True):
                del st.session_state.user
                st.rerun()
            if c_sb2.button("🔄 Refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        # HERO HEADER WITH LOGO
        logo_file = get_logo_path()
        logo_html = ""
        if logo_file:
            try:
                with open(logo_file, "rb") as f:
                    enc = base64.b64encode(f.read()).decode()
                ext = "png" if logo_file.endswith(".png") else "jpeg"
                logo_html = f'<img src="data:image/{ext};base64,{enc}" style="width: 210px; border-radius: 14px; margin-bottom: 10px; box-shadow: 0 6px 18px rgba(0,0,0,0.45);" /><br>'
            except Exception:
                pass

        st.markdown(f"""
            <div class="brand-hero">
                {logo_html}
                <p class="golden-title"><span class="bed">bed</span> <span class="sol">solution</span></p>
                <p class="sub-title">BY LIQ FURNITURE &nbsp;•&nbsp; SMART BATCH MANUFACTURING & INVENTORY</p>
            </div>
        """, unsafe_allow_html=True)

        # ETHIOPIAN DATE FILTERS
        st.sidebar.header("📅 Ethiopian Date Filters")
        eth_months = ["Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit", "Megabit", "Miazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"]
        try:
            eth_today = Kenat(datetime.date.today()).get_ethiopian()
            curr_eth_year, curr_eth_month, curr_eth_day = eth_today['year'], eth_today['month'], eth_today['day']
        except Exception:
            curr_eth_year, curr_eth_month, curr_eth_day = 2019, 3, 14

        def get_greg_date(eth_y, eth_m, eth_d):
            try:
                g = Kenat(f"{eth_y}/{eth_m}/{eth_d}").get_gregorian()
                return pd.to_datetime(datetime.date(g['year'], g['month'], g['day']))
            except Exception:
                return pd.NaT

        filter_option = st.sidebar.radio("Select Period:", ["All Time", "This Month (EC)", "Last Month (EC)", "This Year (EC)", "Custom Range (EC)"])

        if filter_option == "This Month (EC)":
            start_date = get_greg_date(curr_eth_year, curr_eth_month, 1)
            end_date = pd.to_datetime(datetime.date.today())
            st.sidebar.info(f"Filtering: {eth_months[curr_eth_month-1]} {curr_eth_year} EC")
        elif filter_option == "Last Month (EC)":
            prev_y, prev_m = (curr_eth_year - 1, 13) if curr_eth_month == 1 else (curr_eth_year, curr_eth_month - 1)
            start_date = get_greg_date(prev_y, prev_m, 1)
            end_date = get_greg_date(curr_eth_year, curr_eth_month, 1) - datetime.timedelta(days=1)
            st.sidebar.info(f"Filtering: {eth_months[prev_m-1]} {prev_y} EC")
        elif filter_option == "This Year (EC)":
            start_date = get_greg_date(curr_eth_year, 1, 1)
            end_date = pd.to_datetime(datetime.date.today())
            st.sidebar.info(f"Filtering: Year {curr_eth_year} EC")
        elif filter_option == "Custom Range (EC)":
            st.sidebar.write("**From**")
            c1, c2, c3 = st.sidebar.columns(3)
            start_y = c1.selectbox("Year", range(curr_eth_year - 5, curr_eth_year + 2), index=5, key="sy")
            start_m = c2.selectbox("Month", range(1, 14), index=curr_eth_month-1, format_func=lambda x: eth_months[x-1], key="sm")
            start_d = c3.selectbox("Day", range(1, 31), index=0, key="sd")
            st.sidebar.write("**To**")
            c4, c5, c6 = st.sidebar.columns(3)
            end_y = c4.selectbox("Year", range(curr_eth_year - 5, curr_eth_year + 2), index=5, key="ey")
            end_m = c5.selectbox("Month", range(1, 14), index=curr_eth_month-1, format_func=lambda x: eth_months[x-1], key="em")
            end_d = c6.selectbox("Day", range(1, 31), index=curr_eth_day-1, key="ed")
            start_date = get_greg_date(start_y, start_m, start_d)
            end_date = get_greg_date(end_y, end_m, end_d)
        else:
            start_date = pd.to_datetime('2000-01-01')
            end_date = pd.to_datetime('2100-01-01')
            st.sidebar.info("Showing All Time Data")

        if pd.isna(start_date): start_date = pd.to_datetime('2000-01-01')
        if pd.isna(end_date): end_date = pd.to_datetime('2100-01-01')

        # LOAD DATA FROM GOOGLE SHEETS
        @st.cache_data(ttl=180)
        def load_bed_data():
            creds = get_google_creds()
            sheet = gspread.authorize(creds).open_by_url(get_sheet_url())
            return {
                "Materials": get_sheet_df(sheet, "Materials"),
                "Suppliers": get_sheet_df(sheet, "Suppliers"),
                "Batches": get_sheet_df(sheet, "Batches"),
                "Purchases": get_sheet_df(sheet, "Purchases"),
                "Stock_Out": get_sheet_df(sheet, "Stock_Out"),
                "Opening_Stock": get_sheet_df(sheet, "Opening_Stock"),
                "Supplier_Payments": get_sheet_df(sheet, "Supplier_Payments"),
                "Opening_Payables": get_sheet_df(sheet, "Opening_Payables"),
                "Employees": get_sheet_df(sheet, "Employees"),
            }

        data = load_bed_data()
        df_mat      = data["Materials"]
        df_sup      = data["Suppliers"]
        df_batches  = data["Batches"]
        df_pur      = data["Purchases"]
        df_out      = data["Stock_Out"]
        df_op_stock = data["Opening_Stock"]
        df_pay      = data["Supplier_Payments"]
        df_op_pay   = data["Opening_Payables"]
        df_emp      = data["Employees"]

        # Normalize empty DataFrames with expected columns
        if df_mat.empty:
            df_mat = pd.DataFrame(columns=['Material_ID', 'Material_Name', 'Unit', 'Reorder_Level'])
        if 'Unit' not in df_mat.columns:
            df_mat['Unit'] = 'pcs'
        if df_sup.empty:
            df_sup = pd.DataFrame(columns=['Supplier_ID', 'Supplier_Name', 'Contact_Person', 'Phone', 'Address', 'TIN_No', 'Notes'])
        if df_batches.empty:
            df_batches = pd.DataFrame(columns=['Batch_No', 'Bed_Model', 'Batch_Date', 'Bed_Qty', 'Status', 'Notes'])
        if df_pur.empty:
            df_pur = pd.DataFrame(columns=['Purchase_ID', 'Date', 'Material_ID', 'Supplier_ID', 'Qty', 'Unit_Cost', 'Payment_Type', 'Invoice_No', 'Notes'])
        if df_out.empty:
            df_out = pd.DataFrame(columns=['Issue_ID', 'Date', 'Batch_No', 'Material_ID', 'Qty', 'Employee_ID', 'Sub_Item', 'Notes'])
        if 'Batch_No' not in df_out.columns and 'Project_ID' in df_out.columns:
            df_out['Batch_No'] = df_out['Project_ID']
        if 'Sub_Item' not in df_out.columns:
            df_out['Sub_Item'] = df_out.get('Sub_Project_Item', 'General')
        if df_op_stock.empty:
            df_op_stock = pd.DataFrame(columns=['Date', 'Material_ID', 'Qty', 'Unit_Cost'])
        if df_pay.empty:
            df_pay = pd.DataFrame(columns=['Date', 'Supplier_ID', 'Amount'])
        if df_op_pay.empty:
            df_op_pay = pd.DataFrame(columns=['Supplier_ID', 'Amount_Owed'])

        # Clean IDs & numeric fields (Preserving full decimals: 0.5, 0.7, etc.)
        for col in ['Supplier_ID', 'Material_ID', 'Batch_No', 'Employee_ID']:
            if col in df_pur.columns: df_pur[col] = df_pur[col].apply(extract_id)
            if col in df_out.columns: df_out[col] = df_out[col].apply(extract_id)
            if col in df_op_stock.columns: df_op_stock[col] = df_op_stock[col].apply(extract_id)
            if col in df_pay.columns: df_pay[col] = df_pay[col].apply(extract_id)
            if col in df_op_pay.columns: df_op_pay[col] = df_op_pay[col].apply(extract_id)
            if col in df_batches.columns: df_batches[col] = df_batches[col].apply(extract_id)

        for df in [df_pur, df_out, df_op_stock, df_pay]:
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        if 'Batch_Date' in df_batches.columns:
            df_batches['Batch_Date'] = pd.to_datetime(df_batches['Batch_Date'], errors='coerce')

        for df, col in [(df_pur, 'Qty'), (df_pur, 'Unit_Cost'), (df_out, 'Qty'),
                        (df_op_stock, 'Qty'), (df_op_stock, 'Unit_Cost'),
                        (df_pay, 'Amount'), (df_op_pay, 'Amount_Owed'),
                        (df_mat, 'Reorder_Level'), (df_batches, 'Bed_Qty')]:
            if col in df.columns and not df.empty:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0.0)

        mat_name_dict = dict(zip(df_mat['Material_ID'], df_mat['Material_Name'])) if not df_mat.empty else {}
        mat_unit_dict = dict(zip(df_mat['Material_ID'], df_mat['Unit'].fillna('pcs'))) if not df_mat.empty else {}
        sup_name_dict = dict(zip(df_sup['Supplier_ID'], df_sup['Supplier_Name'])) if not df_sup.empty else {}
        sup_info_dict = {}
        if not df_sup.empty:
            for _, sr in df_sup.iterrows():
                sup_info_dict[str(sr['Supplier_ID']).strip()] = {
                    'name': str(sr.get('Supplier_Name', '') or ''),
                    'contact': str(sr.get('Contact_Person', '') or ''),
                    'phone': str(sr.get('Phone', '') or ''),
                    'address': str(sr.get('Address', '') or ''),
                    'tin': str(sr.get('TIN_No', '') or ''),
                    'notes': str(sr.get('Notes', '') or '')
                }

        # =====================================================================
        # FIFO INVENTORY & BATCH COSTING ENGINE (DECIMAL PRECISION)
        # =====================================================================
        layers = []
        if not df_op_stock.empty:
            for _, r in df_op_stock.iterrows():
                layers.append({'Date': r['Date'], 'Material_ID': r['Material_ID'], 'Qty': float(r['Qty']), 'Unit_Cost': float(r['Unit_Cost'])})
        if not df_pur.empty:
            for _, r in df_pur.iterrows():
                layers.append({'Date': r['Date'], 'Material_ID': r['Material_ID'], 'Qty': float(r['Qty']), 'Unit_Cost': float(r['Unit_Cost'])})

        df_layers = pd.DataFrame(layers).sort_values(by='Date') if layers else pd.DataFrame(columns=['Date', 'Material_ID', 'Qty', 'Unit_Cost'])
        if not df_layers.empty:
            df_layers['Qty'] = df_layers['Qty'].astype(float)
            df_layers['Unit_Cost'] = df_layers['Unit_Cost'].astype(float)

        unit_cost_lookup = {}
        if not df_layers.empty:
            for _, r in df_layers.iterrows():
                if r['Unit_Cost'] > 0:
                    unit_cost_lookup[r['Material_ID']] = float(r['Unit_Cost'])

        current_stock = {}
        if not df_layers.empty:
            for _, layer in df_layers.iterrows():
                mid = layer['Material_ID']
                current_stock[mid] = round(current_stock.get(mid, 0.0) + float(layer['Qty']), 4)

        batch_costs = {}
        batch_usage_details = []
        workshop_usage_details = []

        if not df_out.empty:
            df_out = df_out.sort_values(by='Date')
            for _, issue in df_out.iterrows():
                m_id = issue['Material_ID']
                qty_needed = float(issue['Qty'])
                b_no = str(issue.get('Batch_No', '')).strip()
                actual_cost = 0.0

                if m_id not in current_stock:
                    current_stock[m_id] = 0.0

                if not df_layers.empty:
                    for i, row in df_layers[df_layers['Material_ID'] == m_id].iterrows():
                        if df_layers.at[i, 'Qty'] > 1e-9 and qty_needed > 1e-9:
                            take = min(df_layers.at[i, 'Qty'], qty_needed)
                            actual_cost += take * df_layers.at[i, 'Unit_Cost']
                            df_layers.at[i, 'Qty'] = round(df_layers.at[i, 'Qty'] - take, 4)
                            qty_needed = round(qty_needed - take, 4)
                            current_stock[m_id] = round(current_stock[m_id] - take, 4)

                if qty_needed > 1e-9:
                    current_stock[m_id] = round(current_stock[m_id] - qty_needed, 4)

                clean_note = "" if pd.isna(issue.get('Notes')) or str(issue.get('Notes')).lower() == 'nan' else str(issue.get('Notes'))
                clean_sub = "General" if pd.isna(issue.get('Sub_Item')) or str(issue.get('Sub_Item')).lower() in ('nan', '') else str(issue.get('Sub_Item'))

                if b_no and b_no.lower() != 'nan':
                    batch_costs[b_no] = batch_costs.get(b_no, 0.0) + actual_cost
                    batch_usage_details.append({
                        'Issue_ID': issue.get('Issue_ID', ''),
                        'Date': issue['Date'],
                        'Batch_No': b_no,
                        'Material_ID': m_id,
                        'Qty': float(issue['Qty']),
                        'Cost': actual_cost,
                        'Sub_Item': clean_sub,
                        'Employee_ID': issue.get('Employee_ID', ''),
                        'Notes': clean_note
                    })
                else:
                    workshop_usage_details.append({
                        'Date': issue['Date'],
                        'Material_ID': m_id,
                        'Qty': float(issue['Qty']),
                        'Cost': actual_cost,
                        'Employee_ID': issue.get('Employee_ID', ''),
                        'Notes': clean_note
                    })

        # Filtered period metrics
        batch_costs_filt, batch_usage_filt = {}, []
        for item in batch_usage_details:
            if pd.notna(item['Date']) and start_date <= pd.to_datetime(item['Date']) <= end_date:
                batch_costs_filt[item['Batch_No']] = batch_costs_filt.get(item['Batch_No'], 0.0) + item['Cost']
                batch_usage_filt.append(item)

        workshop_usage_filt = [x for x in workshop_usage_details if pd.notna(x['Date']) and start_date <= pd.to_datetime(x['Date']) <= end_date]

        # Supplier balances
        supplier_balances = {}
        if not df_op_pay.empty:
            for _, r in df_op_pay.iterrows():
                supplier_balances[r['Supplier_ID']] = supplier_balances.get(r['Supplier_ID'], 0.0) + r['Amount_Owed']
        if not df_pur.empty:
            for _, r in df_pur.iterrows():
                if str(r.get('Payment_Type', '')).strip().lower() == 'credit':
                    supplier_balances[r['Supplier_ID']] = supplier_balances.get(r['Supplier_ID'], 0.0) + (r['Qty'] * r['Unit_Cost'])
        if not df_pay.empty:
            for _, r in df_pay.iterrows():
                supplier_balances[r['Supplier_ID']] = supplier_balances.get(r['Supplier_ID'], 0.0) - r['Amount']

        # =====================================================================
        # NAVIGATION TABS
        # =====================================================================
        tabs = st.tabs([
            "📊 Executive Summary",
            "📤 Issue Material by Batch",
            "🛏️ Batch Costing & BOM",
            "🧠 Smart Production Intelligence",
            "📦 Live Inventory (Decimals)",
            "🛒 Record Purchase / Stock In",
            "📈 Monthly Stock Audit"
        ])

        # ---------------------------------------------------------------------
        # TAB 1: EXECUTIVE SUMMARY
        # ---------------------------------------------------------------------
        with tabs[0]:
            total_batch_cost = sum(batch_costs_filt.values())
            total_beds_targeted = df_batches['Bed_Qty'].sum() if not df_batches.empty else 0
            avg_cost_per_bed = (sum(batch_costs.values()) / total_beds_targeted) if total_beds_targeted > 0 else 0.0
            inv_value = sum([r['Qty'] * r['Unit_Cost'] for _, r in df_layers.iterrows() if r['Qty'] > 0]) if not df_layers.empty else 0.0
            total_debt = sum([v for v in supplier_balances.values() if v > 0])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Batch Production Spend", f"ETB {total_batch_cost:,.2f}")
            c2.metric("Avg Material Cost / Bed", f"ETB {avg_cost_per_bed:,.2f}", f"{fmt_qty(total_beds_targeted)} Beds Planned")
            c3.metric("Live Warehouse Value", f"ETB {inv_value:,.2f}")
            c4.metric("Supplier Credit Debt", f"ETB {total_debt:,.2f}")

            st.markdown("")
            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("🛏️ Cost by Production Batch")
                if batch_costs_filt:
                    df_bc = pd.DataFrame(list(batch_costs_filt.items()), columns=['Batch_No', 'Cost'])
                    if not df_batches.empty:
                        model_col = 'Bed_Model' if 'Bed_Model' in df_batches.columns else None
                        qty_col = 'Bed_Qty' if 'Bed_Qty' in df_batches.columns else ('Target_Qty' if 'Target_Qty' in df_batches.columns else None)
                        merge_cols = ['Batch_No'] + ([model_col] if model_col else []) + ([qty_col] if qty_col else [])
                        df_bc = df_bc.merge(df_batches[merge_cols], on='Batch_No', how='left')
                        if model_col:
                            df_bc['Label'] = df_bc['Batch_No'] + " (" + df_bc[model_col].fillna('Bed').astype(str) + ")"
                        else:
                            df_bc['Label'] = df_bc['Batch_No']
                    else:
                        df_bc['Label'] = df_bc['Batch_No']
                    df_bc_top = df_bc.sort_values('Cost', ascending=False).head(10).set_index('Label')[['Cost']]
                    st.bar_chart(df_bc_top, color=AMBER_GOLD, use_container_width=True)
                else:
                    st.info("No batch issuances recorded in this period yet. Go to **📤 Issue Material by Batch** to start!")

            with col_r:
                st.subheader("🧩 Spend by Manufacturing Stage")
                if batch_usage_filt:
                    df_stage = pd.DataFrame(batch_usage_filt).groupby('Sub_Item')['Cost'].sum().reset_index().sort_values('Cost', ascending=False)
                    st.bar_chart(df_stage.set_index('Sub_Item')[['Cost']], color=AMBER_GOLD, use_container_width=True)
                    st.dataframe(
                        df_stage.style.format({'Cost': 'ETB {:,.2f}'}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No component/stage breakdown data yet.")

        # ---------------------------------------------------------------------
        # TAB 2: ISSUE MATERIAL BY BATCH NUMBER (CORE WORKFLOW)
        # ---------------------------------------------------------------------
        with tabs[1]:
            st.subheader("📤 Issue Raw Materials by Batch Number")
            st.caption("Supports exact decimal quantities (`0.5`, `0.7`, `1.25`, etc.) and automatically deducts from FIFO inventory in Google Sheets.")

            if "issue_flash" in st.session_state:
                st.success(st.session_state.pop("issue_flash"))

            col_create, col_issue = st.columns([1, 1.4], gap="large")

            # LEFT: CREATE NEW PRODUCTION BATCH
            with col_create:
                st.markdown("#### 1️⃣ Create New Production Batch")
                default_batch_code = f"BATCH-{datetime.datetime.now().strftime('%y%m%d')}-{len(df_batches)+1:02d}"
                with st.form("create_batch_form", clear_on_submit=True):
                    new_b_no = st.text_input("Batch Number:", value=default_batch_code)
                    bed_model = st.selectbox("Bed / Mattress Model:", [
                        "Queen Orthopedic Mattress (160x200)",
                        "King Luxury Spring Bed (180x200)",
                        "Single Standard Bed (90x200)",
                        "Double Semi-Orthopedic (140x200)",
                        "Upholstered Bed Frame + Headboard",
                        "Custom Size / Special Order"
                    ])
                    custom_model = st.text_input("Or type custom Bed Model (overrides dropdown):")
                    st.info("🛏️ **Rule Active:** One Bed has **1 Batch Number** (`Bed_Qty = 1`).")
                    target_qty = 1
                    b_date = st.date_input("Batch Start Date:", value=datetime.date.today())
                    b_notes = st.text_input("Batch Notes (optional):", placeholder="e.g. Serial / Showroom / Client bed")
                    create_b_btn = st.form_submit_button("✨ Register Single-Bed Batch", type="primary", use_container_width=True)

                if create_b_btn:
                    final_model = custom_model.strip() if custom_model.strip() else bed_model
                    clean_bno = new_b_no.strip().upper()
                    if not clean_bno:
                        st.error("Please enter a Batch Number.")
                    elif not df_batches.empty and clean_bno in df_batches['Batch_No'].values:
                        st.warning(f"Batch `{clean_bno}` already exists! Each bed batch number must be unique.")
                    else:
                        try:
                            b_ws = _ensure_sheet("Batches", ["Batch_No", "Bed_Model", "Batch_Date", "Bed_Qty", "Status", "Notes"])
                            b_ws.append_row([
                                clean_bno, final_model, b_date.strftime("%Y-%m-%d"),
                                1, "In Production", b_notes
                            ], value_input_option='USER_ENTERED')
                            st.session_state.issue_flash = f"✅ Single-Bed Batch **{clean_bno}** ({final_model} — 1 Bed) created!"
                            load_bed_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not save batch: {e}")

            # RIGHT: ISSUE MATERIALS TO SELECTED BATCH
            with col_issue:
                st.markdown("#### 2️⃣ Issue Materials to a Batch")
                if df_mat.empty:
                    st.warning("Your `Materials` sheet is empty. Add raw materials first in **🛒 Record Purchase / Stock In** or Google Sheets.")
                else:
                    batch_opts = []
                    batch_labels = {}
                    if not df_batches.empty:
                        for _, br in df_batches.iloc[::-1].iterrows():
                            bno = str(br['Batch_No']).strip()
                            if bno:
                                batch_opts.append(bno)
                                batch_labels[bno] = f"{bno}  —  {br.get('Bed_Model', '')} ({fmt_qty(br.get('Bed_Qty', 1))} beds) [{br.get('Status', 'Active')}]"

                    batch_filter = st.text_input("🔎 Filter Batch Dropdown:", placeholder="Type batch code or bed model...")
                    if batch_filter.strip():
                        f_txt = batch_filter.strip().lower()
                        filtered_b_opts = [b for b in batch_opts if f_txt in b.lower() or f_txt in batch_labels.get(b, '').lower()]
                    else:
                        filtered_b_opts = batch_opts
                    sel_batch = st.selectbox(
                        "Select Target Batch Number:",
                        options=filtered_b_opts if filtered_b_opts else (batch_opts if batch_opts else ["NO-BATCH"]),
                        format_func=lambda x: batch_labels.get(x, "Create a batch on the left first")
                    )

                    emp_opts = [""] + (df_emp['Employee_ID'].tolist() if not df_emp.empty else [])
                    emp_map = dict(zip(df_emp['Employee_ID'], df_emp['Employee_Name'])) if not df_emp.empty else {}

                    c_st1, c_st2 = st.columns(2)
                    sub_stage = c_st1.selectbox("Manufacturing Stage / Component:", [
                        "Wood Frame & Carpentry",
                        "Spring & Foam Core",
                        "Quilting & Upholstery Fabric",
                        "Headboard & Finishing",
                        "Packaging & Accessories",
                        "Rework / Quality Fix"
                    ])
                    emp_id = c_st2.selectbox("Issued To (Operator):", emp_opts, format_func=lambda x: f"{emp_map.get(x, x)} ({x})" if x else "Unassigned")

                    issue_date = st.date_input("Issue Date:", value=datetime.date.today(), key="iss_dt")
                    search_m = st.text_input("🔍 Filter materials:", placeholder="Search foam, fabric, wood, spring, glue...")

                    df_m_sub = df_mat.copy()
                    if search_m:
                        df_m_sub = df_m_sub[df_m_sub['Material_Name'].str.contains(search_m, case=False, na=False)]

                    editor_df = pd.DataFrame({
                        'Issue?': [False] * len(df_m_sub),
                        'Material': df_m_sub['Material_Name'].values,
                        'Unit': df_m_sub['Unit'].fillna('pcs').values,
                        'In Stock': [current_stock.get(mid, 0.0) for mid in df_m_sub['Material_ID']],
                        'Qty to Issue': [0.5] * len(df_m_sub)
                    })

                    edited_issue = st.data_editor(
                        editor_df,
                        column_config={
                            'Issue?': st.column_config.CheckboxColumn('Select', default=False),
                            'Material': st.column_config.TextColumn('Raw Material', disabled=True, width="large"),
                            'Unit': st.column_config.TextColumn('Unit', disabled=True, width="small"),
                            'In Stock': st.column_config.NumberColumn('Available', disabled=True, format="%.2f"),
                            'Qty to Issue': st.column_config.NumberColumn('Qty (0.5, 0.7...)', min_value=0.01, step=0.1, format="%.2f")
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=320,
                        key="batch_issue_editor"
                    )

                    iss_notes = st.text_input("Issue Notes (optional):", placeholder="e.g. Top layer high-density foam")

                    if st.button("🚀 Confirm & Issue Selected Materials to Batch", type="primary", use_container_width=True):
                        if sel_batch == "NO-BATCH":
                            st.error("Please create a Batch Number first on the left.")
                        else:
                            to_post = []
                            over_stock_warnings = []
                            ts_prefix = datetime.datetime.now().strftime('%y%m%d%H%M%S')
                            for idx, row in edited_issue.iterrows():
                                if row['Issue?']:
                                    q_val = round(float(row['Qty to Issue']), 4)
                                    if q_val <= 0:
                                        continue
                                    m_id = df_m_sub.iloc[idx]['Material_ID']
                                    avail = current_stock.get(m_id, 0.0)
                                    if q_val > avail:
                                        over_stock_warnings.append(f"{row['Material']} (Issuing {fmt_qty(q_val)} > Stock {fmt_qty(avail)})")
                                    to_post.append([
                                        f"ISS-{ts_prefix}-{len(to_post)+1:02d}",
                                        issue_date.strftime("%Y-%m-%d"),
                                        sel_batch,
                                        m_id,
                                        mat_name_dict.get(m_id, m_id),
                                        q_val,
                                        emp_id,
                                        sub_stage,
                                        iss_notes
                                    ])

                            if not to_post:
                                st.warning("Check at least one material box and set Qty > 0.")
                            else:
                                try:
                                    out_ws = _ensure_sheet("Stock_Out", ["Issue_ID", "Date", "Batch_No", "Material_ID", "Material_Name", "Qty", "Employee_ID", "Sub_Item", "Notes"])
                                    out_ws.append_rows(to_post, value_input_option='USER_ENTERED')
                                    warn_txt = f" (⚠️ Low stock alert: {', '.join(over_stock_warnings)})" if over_stock_warnings else ""
                                    st.session_state.issue_flash = f"✅ Issued {len(to_post)} material(s) to **{sel_batch}**!{warn_txt}"
                                    load_bed_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to record issuance: {e}")

        # ---------------------------------------------------------------------
        # TAB 3: BATCH COSTING & BOM EXPLORER
        # ---------------------------------------------------------------------
        with tabs[2]:
            st.subheader("🛏️ Batch Production Costing & Bill of Materials")
            if df_batches.empty and not batch_usage_details:
                st.info("No production batches recorded yet.")
            else:
                all_b_nos = sorted(list(set(
                    (df_batches['Batch_No'].dropna().tolist() if not df_batches.empty else []) +
                    list(batch_costs.keys())
                )), reverse=True)

                # Summary comparison table across all batches
                summary_rows = []
                for bno in all_b_nos:
                    b_meta = df_batches[df_batches['Batch_No'] == bno].iloc[0] if (not df_batches.empty and not df_batches[df_batches['Batch_No'] == bno].empty) else {}
                    t_qty = float(b_meta.get('Bed_Qty', 1) or 1)
                    tot_c = batch_costs.get(bno, 0.0)
                    summary_rows.append({
                        'Batch No': bno,
                        'Bed Model': b_meta.get('Bed_Model', 'Standard Bed'),
                        'Status': b_meta.get('Status', 'In Production'),
                        'Beds Qty': t_qty,
                        'Total Material Cost (ETB)': tot_c,
                        'Cost Per Bed (ETB)': tot_c / t_qty if t_qty > 0 else 0.0
                    })
                df_bsum = pd.DataFrame(summary_rows)
                st.dataframe(
                    df_bsum.style.format({
                        'Beds Qty': '{:g}',
                        'Total Material Cost (ETB)': 'ETB {:,.2f}',
                        'Cost Per Bed (ETB)': 'ETB {:,.2f}'
                    }),
                    use_container_width=True,
                    hide_index=True
                )

                st.divider()
                sel_b_view = st.selectbox("Inspect Detailed Batch BOM & Download PDF:", all_b_nos, key="inspect_batch_sel")
                if sel_b_view:
                    b_info = df_batches[df_batches['Batch_No'] == sel_b_view].iloc[0] if (not df_batches.empty and not df_batches[df_batches['Batch_No'] == sel_b_view].empty) else {}
                    b_items = [x for x in batch_usage_details if x['Batch_No'] == sel_b_view]
                    t_qty = float(b_info.get('Bed_Qty', 1) or 1)
                    tot_b_cost = sum(x['Cost'] for x in b_items)
                    unit_bed_cost = tot_b_cost / t_qty if t_qty > 0 else 0.0

                    bc1, bc2, bc3, bc4 = st.columns(4)
                    bc1.metric("Bed Model", str(b_info.get('Bed_Model', 'N/A'))[:22])
                    bc2.metric("Batch Quantity", f"{fmt_qty(t_qty)} Beds")
                    bc3.metric("Total Batch Material Cost", f"ETB {tot_b_cost:,.2f}")
                    bc4.metric("Material Cost / Bed", f"ETB {unit_bed_cost:,.2f}")

                    if b_items:
                        df_b_det = pd.DataFrame(b_items).merge(df_mat[['Material_ID', 'Material_Name', 'Unit']], on='Material_ID', how='left')
                        if not df_emp.empty:
                            df_b_det = df_b_det.merge(df_emp[['Employee_ID', 'Employee_Name']], on='Employee_ID', how='left')
                        else:
                            df_b_det['Employee_Name'] = df_b_det['Employee_ID']
                        df_b_det['Date (EC)'] = df_b_det['Date'].apply(to_ethiopian)

                        st.dataframe(
                            df_b_det[['Date (EC)', 'Sub_Item', 'Material_Name', 'Qty', 'Unit', 'Cost', 'Employee_Name', 'Notes']].style.format({
                                'Qty': '{:g}',
                                'Cost': 'ETB {:,.2f}'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )

                        pdf_data = generate_batch_pdf(
                            sel_b_view,
                            b_info.get('Bed_Model', 'Bed'),
                            t_qty,
                            b_info.get('Status', 'Active'),
                            tot_b_cost,
                            unit_bed_cost,
                            df_b_det
                        )
                        st.download_button(
                            f"📥 Download Batch {sel_b_view} Cost & BOM PDF",
                            data=pdf_data,
                            file_name=f"BedSolution_{sel_b_view}.pdf",
                            mime="application/pdf",
                            type="primary"
                        )
                    else:
                        st.info("No materials have been issued to this batch yet.")

        # ---------------------------------------------------------------------
        # TAB 4: SMART PRODUCTION INTELLIGENCE (ANOMALY, REORDER & EFFICIENCY)
        # ---------------------------------------------------------------------
        with tabs[3]:
            st.subheader("🧠 Smart Manufacturing Intelligence & Cost Optimization")
            st.caption("Automated diagnostics comparing batch unit efficiency, material price inflation, and stockout runway.")

            # 1. SMART UNIT COST BENCHMARKING ACROSS BATCHES
            st.markdown("#### 1️⃣ Batch Unit Cost Efficiency & Anomaly Detector")
            if not df_batches.empty and batch_costs:
                eff_rows = []
                for _, br in df_batches.iterrows():
                    bno = br['Batch_No']
                    model = br.get('Bed_Model', 'Standard')
                    qty = float(br.get('Bed_Qty', 1) or 0)
                    cost = batch_costs.get(bno, 0.0)
                    if qty > 0 and cost > 0:
                        eff_rows.append({'Batch_No': bno, 'Bed_Model': model, 'Qty': qty, 'Total_Cost': cost, 'Cost_Per_Bed': cost / qty})

                if eff_rows:
                    df_eff = pd.DataFrame(eff_rows)
                    model_avg = df_eff.groupby('Bed_Model')['Cost_Per_Bed'].transform('mean')
                    df_eff['Model Avg / Bed'] = model_avg
                    df_eff['Variance %'] = ((df_eff['Cost_Per_Bed'] - df_eff['Model Avg / Bed']) / df_eff['Model Avg / Bed']) * 100
                    df_eff['Smart Status'] = df_eff['Variance %'].apply(
                        lambda v: "🔴 High Material Waste (> +8%)" if v > 8 else ("🟢 Optimal Yield (< -5%)" if v < -5 else "🟡 Normal Range")
                    )

                    high_waste = df_eff[df_eff['Variance %'] > 8]
                    if not high_waste.empty:
                        st.markdown(
                            f'<div class="smart-insight">💡 <b>Smart Alert:</b> {len(high_waste)} batch(es) exceeded the average material cost per bed for their model by more than 8%. Inspect foam/fabric offcuts or rework issuances on those batches.</div>',
                            unsafe_allow_html=True
                        )

                    st.dataframe(
                        df_eff.style.format({
                            'Qty': '{:g}', 'Total_Cost': 'ETB {:,.2f}',
                            'Cost_Per_Bed': 'ETB {:,.2f}', 'Model Avg / Bed': 'ETB {:,.2f}',
                            'Variance %': '{:+.1f}%'
                        }),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Issue materials to at least one batch with Target Qty > 0 to unlock per-bed efficiency benchmarking.")
            else:
                st.info("Create batches and issue materials to see unit cost benchmarking.")

            st.divider()

            # 2. PREDICTIVE REORDER & DAYS-OF-SUPPLY ENGINE
            st.markdown("#### 2️⃣ Predictive Stockout & Reorder Advisor (30-Day Burn Rate)")
            if not df_mat.empty and current_stock:
                thirty_days_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
                recent_out = df_out[df_out['Date'] >= thirty_days_ago] if not df_out.empty else pd.DataFrame()
                pred_rows = []
                for _, mr in df_mat.iterrows():
                    mid = mr['Material_ID']
                    mname = mr['Material_Name']
                    unit = mr.get('Unit', 'pcs')
                    on_hand = current_stock.get(mid, 0.0)
                    min_lvl = float(mr.get('Reorder_Level', 0) or 0)
                    used_30d = recent_out[recent_out['Material_ID'] == mid]['Qty'].sum() if not recent_out.empty else 0.0
                    daily_use = used_30d / 30.0
                    days_left = (on_hand / daily_use) if daily_use > 0 else 999
                    est_price = unit_cost_lookup.get(mid, 0.0)
                    sug_order = max(0.0, round((daily_use * 21) + min_lvl - on_hand, 1)) if (on_hand <= min_lvl or days_left < 14) else 0.0

                    if on_hand < 0:
                        urgency = "🚨 Negative Stock"
                    elif on_hand <= min_lvl or days_left <= 7:
                        urgency = "🔴 Order Immediately (<7d)"
                    elif days_left <= 14:
                        urgency = "🟡 Reorder Soon (<14d)"
                    else:
                        urgency = "🟢 Healthy"

                    pred_rows.append({
                        'Material': mname,
                        'On Hand': on_hand,
                        'Unit': unit,
                        '30d Usage': used_30d,
                        'Days Left': round(days_left, 1) if days_left < 999 else 999,
                        'Suggested Reorder': sug_order,
                        'Est. Order Cost': sug_order * est_price,
                        'Priority': urgency
                    })
                df_pred = pd.DataFrame(pred_rows).sort_values(by=['Days Left', 'On Hand'])
                st.dataframe(
                    df_pred.style.format({
                        'On Hand': '{:g}', '30d Usage': '{:g}',
                        'Days Left': '{:.1f}', 'Suggested Reorder': '{:g}',
                        'Est. Order Cost': 'ETB {:,.2f}'
                    }),
                    use_container_width=True, hide_index=True
                )

            st.divider()

            # 3. SUPPLIER INFLATION TRACKER
            st.markdown("#### 3️⃣ Raw Material Price Inflation Tracker")
            if not df_pur.empty and not df_mat.empty:
                df_pv = df_pur[df_pur['Unit_Cost'] > 0].sort_values('Date').merge(df_mat[['Material_ID', 'Material_Name']], on='Material_ID', how='left')
                inf_rows = []
                for mid, grp in df_pv.groupby('Material_ID'):
                    if len(grp) >= 2:
                        p0, p1 = grp['Unit_Cost'].iloc[0], grp['Unit_Cost'].iloc[-1]
                        chg = ((p1 - p0) / p0) * 100 if p0 > 0 else 0
                        inf_rows.append({
                            'Material': grp['Material_Name'].iloc[0],
                            'First Unit Cost': p0,
                            'Latest Unit Cost': p1,
                            'Change %': chg
                        })
                if inf_rows:
                    st.dataframe(
                        pd.DataFrame(inf_rows).sort_values('Change %', ascending=False).style.format({
                            'First Unit Cost': 'ETB {:,.2f}', 'Latest Unit Cost': 'ETB {:,.2f}', 'Change %': '{:+.1f}%'
                        }),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Price inflation comparisons appear once a material has 2 or more recorded purchases.")

        # ---------------------------------------------------------------------
        # TAB 5: LIVE INVENTORY (EXACT DECIMALS: 0.5, 0.7, ETC.)
        # ---------------------------------------------------------------------
        with tabs[4]:
            st.subheader("📦 Live Raw Material Inventory (Exact Decimal Precision)")
            t_inv1, t_inv2 = st.tabs(["⚠️ Low / Negative Alerts", "📋 Full Warehouse Stock"])

            with t_inv1:
                if not df_mat.empty and current_stock:
                    low_items = []
                    for _, r in df_mat.iterrows():
                        mid = r['Material_ID']
                        q = current_stock.get(mid, 0.0)
                        mn = float(r.get('Reorder_Level', 0) or 0)
                        if q <= mn or q < 0:
                            low_items.append({
                                'Material ID': mid,
                                'Material Name': r['Material_Name'],
                                'Unit': r.get('Unit', 'pcs'),
                                'Current Qty': q,
                                'Reorder Level': mn
                            })
                    if low_items:
                        st.markdown('<div class="alert-box">⚠️ Action Needed: Materials below reorder level or in negative balance.</div>', unsafe_allow_html=True)
                        st.dataframe(
                            pd.DataFrame(low_items).style.format({'Current Qty': '{:g}', 'Reorder Level': '{:g}'}).map(color_negative_red, subset=['Current Qty']),
                            use_container_width=True, hide_index=True
                        )
                    else:
                        st.success("✅ All raw materials are above reorder thresholds.")
                else:
                    st.info("No materials found.")

            with t_inv2:
                if current_stock:
                    all_stk = []
                    for mid, q in current_stock.items():
                        uc = unit_cost_lookup.get(mid, 0.0)
                        all_stk.append({
                            'Material ID': mid,
                            'Material Name': mat_name_dict.get(mid, mid),
                            'Unit': mat_unit_dict.get(mid, 'pcs'),
                            'On Hand Qty': q,
                            'Latest Unit Cost': uc,
                            'Total Value (ETB)': max(0.0, q * uc)
                        })
                    df_all_stk = pd.DataFrame(all_stk).sort_values('Material Name')
                    st.dataframe(
                        df_all_stk.style.format({
                            'On Hand Qty': '{:g}',
                            'Latest Unit Cost': 'ETB {:,.2f}',
                            'Total Value (ETB)': 'ETB {:,.2f}'
                        }).map(color_negative_red, subset=['On Hand Qty']),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Warehouse stock is empty.")

        # ---------------------------------------------------------------------
        # TAB 6: RECORD PURCHASE & ADD NEW MATERIAL
        # ---------------------------------------------------------------------
        with tabs[5]:
            st.subheader("🛒 Stock In — Record Purchase or Add New Material")
            c_p1, c_p2 = st.columns([1.3, 1], gap="large")

            with c_p1:
                st.markdown("#### 📥 Record Material Purchase")
                if df_mat.empty:
                    st.info("Add your first raw material on the right 👉")
                else:
                    with st.form("add_purchase_form", clear_on_submit=True):
                        mat_ids = df_mat['Material_ID'].tolist()
                        sel_m_pur = st.selectbox("Select Material:", mat_ids, format_func=lambda x: f"{x} — {mat_name_dict.get(x, x)}")
                        sup_ids = [""] + (df_sup['Supplier_ID'].tolist() if not df_sup.empty else [])
                        sel_s_pur = st.selectbox(
                            "Select Supplier ID (Shows Full Name & Phone):",
                            sup_ids,
                            format_func=lambda x: f"{x} — {sup_name_dict.get(x, x)} ({sup_info_dict.get(x, {}).get('phone', 'No phone')})" if x else "Cash / Walk-in Supplier"
                        )
                        if sel_s_pur and sel_s_pur in sup_info_dict:
                            s_det = sup_info_dict[sel_s_pur]
                            st.caption(f"🏢 **{s_det['name']}** | 👤 {s_det['contact'] or 'N/A'} | 📞 {s_det['phone'] or 'N/A'} | 📍 {s_det['address'] or 'N/A'} | TIN: {s_det['tin'] or 'N/A'}")

                        cp1, cp2 = st.columns(2)
                        p_qty = cp1.number_input("Purchased Qty (0.5, 0.7, 10...):", min_value=0.01, value=1.0, step=0.5, format="%.2f")
                        p_cost = cp2.number_input("Unit Cost (ETB):", min_value=0.0, value=float(unit_cost_lookup.get(sel_m_pur, 0.0)), step=10.0)

                        cp3, cp4 = st.columns(2)
                        p_type = cp3.selectbox("Payment Type:", ["Cash", "Credit"])
                        p_date = cp4.date_input("Purchase Date:", value=datetime.date.today())

                        p_inv = st.text_input("Invoice / Receipt No (optional):")
                        p_note = st.text_input("Notes (optional):")
                        save_pur = st.form_submit_button("💾 Save Purchase to Google Sheets", type="primary", use_container_width=True)

                    if save_pur:
                        try:
                            pur_ws = _ensure_sheet("Purchases", ["Purchase_ID", "Date", "Material_ID", "Supplier_ID", "Supplier_Name", "Qty", "Unit_Cost", "Payment_Type", "Invoice_No", "Notes"])
                            pid = f"PUR-{datetime.datetime.now().strftime('%y%m%d%H%M%S')}"
                            pur_ws.append_row([
                                pid, p_date.strftime("%Y-%m-%d"), sel_m_pur, sel_s_pur,
                                sup_name_dict.get(sel_s_pur, ""), float(p_qty), float(p_cost), p_type, p_inv, p_note
                            ], value_input_option='USER_ENTERED')
                            st.success(f"✅ Purchase `{pid}` recorded ({fmt_qty(p_qty)} units)!")
                            load_bed_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving purchase: {e}")

            with c_p2:
                st.markdown("#### ➕ Register New Raw Material")
                with st.form("add_material_form", clear_on_submit=True):
                    new_mid = st.text_input("Material ID:", value=f"MAT-{len(df_mat)+1:03d}")
                    new_mname = st.text_input("Material Name:", placeholder="e.g. High Density Foam 10cm")
                    new_unit = st.selectbox("Unit of Measure:", ["pcs", "meters", "sheets", "kg", "liters", "rolls", "sets"])
                    new_reord = st.number_input("Reorder Alert Level:", min_value=0.0, value=5.0, step=0.5)
                    save_mat = st.form_submit_button("➕ Add Material", use_container_width=True)

                if save_mat and new_mname.strip():
                    try:
                        m_ws = _ensure_sheet("Materials", ["Material_ID", "Material_Name", "Unit", "Reorder_Level"])
                        m_ws.append_row([new_mid.strip(), new_mname.strip(), new_unit, float(new_reord)], value_input_option='USER_ENTERED')
                        st.success(f"✅ Added `{new_mname}`!")
                        load_bed_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add material: {e}")

            st.divider()
            st.markdown("#### 🏦 Set Opening Balances (Opening Stock & Opening Supplier Payables)")
            ob1, ob2 = st.columns(2, gap="large")

            with ob1:
                st.markdown("**📦 Set Opening Stock Balance (Decimals Supported: `0.5`, `0.7`, etc.)**")
                with st.form("opening_stock_form", clear_on_submit=True):
                    if not df_mat.empty:
                        ob_m_id = st.selectbox("Material:", df_mat['Material_ID'].tolist(), format_func=lambda x: f"{x} — {mat_name_dict.get(x, x)}", key="ob_mat_sel")
                    else:
                        ob_m_id = st.text_input("Material ID:", key="ob_mat_txt")
                    ob_qty = st.number_input("Opening Qty:", min_value=0.0, value=0.5, step=0.1, format="%.2f", key="ob_qty_inp")
                    ob_ucost = st.number_input("Opening Unit Cost (ETB):", min_value=0.0, value=0.0, step=10.0, key="ob_ucost_inp")
                    ob_date = st.date_input("Opening Date:", value=datetime.date.today(), key="ob_dt_inp")
                    save_ob_stk = st.form_submit_button("💾 Save Opening Stock", use_container_width=True)

                if save_ob_stk and str(ob_m_id).strip():
                    try:
                        os_ws = _ensure_sheet("Opening_Stock", ["Date", "Material_ID", "Material_Name", "Qty", "Unit_Cost"])
                        os_ws.append_row([ob_date.strftime("%Y-%m-%d"), str(ob_m_id).strip(), mat_name_dict.get(str(ob_m_id).strip(), ""), float(ob_qty), float(ob_ucost)], value_input_option='USER_ENTERED')
                        st.success(f"✅ Opening stock of `{fmt_qty(ob_qty)}` saved for `{ob_m_id}`!")
                        load_bed_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save opening stock: {e}")

            with ob2:
                st.markdown("**💳 Set Opening Supplier Payable Balance**")
                with st.form("opening_payable_form", clear_on_submit=True):
                    if not df_sup.empty:
                        op_s_id = st.selectbox(
                            "Select Supplier ID (Shows Name):",
                            df_sup['Supplier_ID'].tolist(),
                            format_func=lambda x: f"{x} — {sup_name_dict.get(x, x)}",
                            key="op_sup_sel"
                        )
                    else:
                        op_s_id = st.text_input("Supplier ID (e.g. SUP-001):", key="op_sup_txt")
                    op_amt = st.number_input("Opening Amount Owed (ETB):", min_value=0.0, value=0.0, step=100.0, key="op_amt_inp")
                    save_op_pay = st.form_submit_button("💾 Save Opening Payable", use_container_width=True)

                if save_op_pay and str(op_s_id).strip():
                    try:
                        op_ws = _ensure_sheet("Opening_Payables", ["Supplier_ID", "Supplier_Name", "Amount_Owed"])
                        op_ws.append_row([str(op_s_id).strip(), sup_name_dict.get(str(op_s_id).strip(), ""), float(op_amt)], value_input_option='USER_ENTERED')
                        st.success(f"✅ Opening payable of `ETB {op_amt:,.2f}` saved for `{op_s_id} — {sup_name_dict.get(str(op_s_id).strip(), '')}`!")
                        load_bed_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save opening payable: {e}")

            st.divider()
            st.markdown("#### 🏢 Register Supplier Full Info & Supplier Directory")
            sd1, sd2 = st.columns([1, 1.4], gap="large")

            with sd1:
                with st.form("add_supplier_full_form", clear_on_submit=True):
                    new_sid = st.text_input("Supplier ID:", value=f"SUP-{len(df_sup)+1:03d}")
                    new_sname = st.text_input("Company / Supplier Name *:", placeholder="e.g. Addis Foam & Sponge Factory")
                    new_scontact = st.text_input("Contact Person:", placeholder="e.g. Ato Girma Bekele")
                    new_sphone = st.text_input("Phone Number:", placeholder="e.g. +251-911-234567")
                    new_saddr = st.text_input("Address / Location:", placeholder="e.g. Kality, Addis Ababa")
                    new_stin = st.text_input("TIN Number (optional):", placeholder="e.g. 0045128910")
                    new_snotes = st.text_input("Notes / Supplied Items:", placeholder="e.g. Foam, springs, fabric")
                    save_sup_btn = st.form_submit_button("💾 Save Full Supplier Profile", type="primary", use_container_width=True)

                if save_sup_btn:
                    if not new_sname.strip():
                        st.error("Please enter Supplier Name.")
                    else:
                        try:
                            sup_ws = _ensure_sheet("Suppliers", ["Supplier_ID", "Supplier_Name", "Contact_Person", "Phone", "Address", "TIN_No", "Notes"])
                            sup_ws.append_row([
                                new_sid.strip().upper(), new_sname.strip(), new_scontact.strip(),
                                new_sphone.strip(), new_saddr.strip(), new_stin.strip(), new_snotes.strip()
                            ], value_input_option='USER_ENTERED')
                            st.success(f"✅ Supplier **{new_sid.strip().upper()} — {new_sname.strip()}** saved!")
                            load_bed_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save supplier: {e}")

            with sd2:
                st.markdown("**📋 Registered Suppliers & Live Credit Balances**")
                if not df_sup.empty:
                    df_sup_view = df_sup.copy()
                    df_sup_view['Balance Owed (ETB)'] = df_sup_view['Supplier_ID'].apply(lambda sid: supplier_balances.get(str(sid).strip(), 0.0))
                    st.dataframe(
                        df_sup_view.style.format({'Balance Owed (ETB)': 'ETB {:,.2f}'}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No suppliers registered yet. Add your first supplier on the left.")

        # ---------------------------------------------------------------------
        # TAB 7: MONTHLY STOCK AUDIT (DECIMAL PRECISION + PDF)
        # ---------------------------------------------------------------------
        with tabs[6]:
            st.subheader("📈 Monthly Stock Audit & Reconciliation")
            all_dates = []
            if not df_pur.empty: all_dates.extend(df_pur['Date'].dropna().tolist())
            if not df_out.empty: all_dates.extend(df_out['Date'].dropna().tolist())

            if not all_dates:
                st.info("Record purchases or batch issuances to run monthly stock audits.")
            else:
                ym_set = set()
                for d in all_dates:
                    k = Kenat(d).get_ethiopian()
                    ym_set.add((k['year'], k['month']))
                audit_opts = [(y, m, get_eth_month_label(y, m)) for y, m in sorted(list(ym_set), reverse=True)]

                sel_aud = st.selectbox("Select Ethiopian Month:", audit_opts, format_func=lambda x: x[2])
                ay, am, alabel = sel_aud
                s_m = get_greg_date(ay, am, 1)
                e_m = get_greg_date(ay + (1 if am == 13 else 0), 1 if am == 13 else am + 1, 1) - datetime.timedelta(days=1)

                pre_p = df_pur[df_pur['Date'] < s_m] if not df_pur.empty else pd.DataFrame()
                cur_p = df_pur[(df_pur['Date'] >= s_m) & (df_pur['Date'] <= e_m)] if not df_pur.empty else pd.DataFrame()
                df_iss_all = pd.DataFrame(batch_usage_details + workshop_usage_details)
                pre_i = df_iss_all[df_iss_all['Date'] < s_m] if not df_iss_all.empty else pd.DataFrame()
                cur_i = df_iss_all[(df_iss_all['Date'] >= s_m) & (df_iss_all['Date'] <= e_m)] if not df_iss_all.empty else pd.DataFrame()

                aud_rows = []
                tot_op_q = tot_in_q = tot_out_q = tot_cl_q = 0.0
                for _, mr in df_mat.iterrows():
                    mid = mr['Material_ID']
                    op_q = (df_op_stock[df_op_stock['Material_ID'] == mid]['Qty'].sum() if not df_op_stock.empty else 0.0) +                        (pre_p[pre_p['Material_ID'] == mid]['Qty'].sum() if not pre_p.empty else 0.0) -                        (pre_i[pre_i['Material_ID'] == mid]['Qty'].sum() if not pre_i.empty else 0.0)
                    in_q = cur_p[cur_p['Material_ID'] == mid]['Qty'].sum() if not cur_p.empty else 0.0
                    out_q = cur_i[cur_i['Material_ID'] == mid]['Qty'].sum() if not cur_i.empty else 0.0
                    cl_q = round(op_q + in_q - out_q, 4)
                    if abs(op_q) < 1e-6 and abs(in_q) < 1e-6 and abs(out_q) < 1e-6:
                        continue
                    cl_val = max(0.0, cl_q * unit_cost_lookup.get(mid, 0.0))
                    aud_rows.append({
                        'Material_Name': mr['Material_Name'],
                        'Open_Qty': op_q, 'In_Qty': in_q, 'Out_Qty': out_q, 'Close_Qty': cl_q, 'Close_Val': cl_val
                    })
                    tot_op_q += op_q; tot_in_q += in_q; tot_out_q += out_q; tot_cl_q += cl_q

                df_aud = pd.DataFrame(aud_rows)
                if not df_aud.empty:
                    st.dataframe(
                        df_aud.style.format({
                            'Open_Qty': '{:g}', 'In_Qty': '{:g}', 'Out_Qty': '{:g}',
                            'Close_Qty': '{:g}', 'Close_Val': 'ETB {:,.2f}'
                        }).map(color_negative_red, subset=['Close_Qty']),
                        use_container_width=True, hide_index=True
                    )
                    cs1, cs2 = st.columns(2)
                    sk_name = cs1.text_input("Store Keeper Name:", "_________________")
                    mg_name = cs2.text_input("Production Manager Name:", "_________________")
                    aud_pdf = generate_stock_audit_pdf(
                        alabel, tot_op_q, 0.0, tot_in_q, (cur_p['Qty'] * cur_p['Unit_Cost']).sum() if not cur_p.empty else 0.0,
                        tot_out_q, cur_i['Cost'].sum() if not cur_i.empty else 0.0, tot_cl_q, df_aud['Close_Val'].sum(),
                        df_aud, sk_name, mg_name
                    )
                    st.download_button("📥 Download Monthly Stock Audit PDF", data=aud_pdf, file_name=f"BedSolution_Audit_{alabel.replace(' ', '_')}.pdf", mime="application/pdf", type="primary")
                else:
                    st.info("No stock movements during this month.")
    except Exception as _app_err:
        st.error(f"Runtime Error: {_app_err}")
        st.exception(_app_err)
