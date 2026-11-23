import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import gspread
import json
import base64
from google.oauth2 import service_account
from fpdf import FPDF
from kenat import Kenat
import os
import urllib.request

st.set_page_config(page_title="Bed Solution Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- CONSTANTS & HEADERS ---
_REQ_HDRS = [
    "Request_ID", "Submitted_Date", "Submitted_By", "Supplier_Preference",
    "Material_ID", "Material_Name", "Requested_Qty", "Est_Unit_Cost", "Status", "Notes"
]

# --- AUTO-DOWNLOAD FONTS ---
try:
    if not os.path.exists("DejaVuSans.ttf"):
        urllib.request.urlretrieve("https://unpkg.com/dejavu-fonts-ttf@2.37/ttf/DejaVuSans.ttf", "DejaVuSans.ttf")
    if not os.path.exists("DejaVuSans-Bold.ttf"):
        urllib.request.urlretrieve("https://unpkg.com/dejavu-fonts-ttf@2.37/ttf/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf")
    font_ready = True
except Exception:
    font_ready = False

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .golden-title {
        font-family: 'Arial', sans-serif; font-size: clamp(50px, 10vw, 120px) !important;
        font-weight: 900 !important; color: #D4AF37 !important; text-shadow: 3px 3px 8px rgba(0,0,0,0.8);
        text-align: center; margin-top: 0px; margin-bottom: 0px; padding-bottom: 0px; line-height: 1.1;
    }
    .sub-title {
        color: #A0A0A0; font-size: clamp(14px, 2vw, 24px); text-align: center; letter-spacing: 3px;
        margin-top: 10px; margin-bottom: 30px; font-weight: bold;
    }
    .stMetric {
        background: linear-gradient(135deg, #1f3864 0%, #111111 100%);
        padding: 15px; border-radius: 10px; color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 5px solid #D4AF37;
        min-width: 0;
    }
    .stMetric label { color: #E0E0E0 !important; font-size: 14px; font-weight: 600; white-space: normal; }
    .stMetric [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 22px; font-weight: bold; }

    div[data-testid="stExpander"] { border: 1px solid #333; border-radius: 8px; }

    /* FORCE TABS TO WRAP */
    div[data-baseweb="tab-list"] {
        display: flex !important;
        flex-wrap: wrap !important;
        overflow-x: visible !important;
        gap: 10px !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto !important;
        white-space: normal !important;
        background-color: transparent !important;
        border-radius: 4px 4px 0px 0px !important;
        padding: 10px 15px !important;
    }
    .stTabs [aria-selected="true"] { background-color: #1f3864 !important; color: #D4AF37 !important; font-weight: bold; }

    .info-box { background-color: #e6f2ff; color: #003366; padding: 10px; border-radius: 5px; border-left: 5px solid #003366; margin-bottom: 15px; font-size: 14px; }
    .warn-box { background-color: #ffcccc; color: #990000; padding: 15px; border-radius: 5px; border-left: 5px solid #990000; margin-bottom: 20px; font-weight: bold; }
    .health-ok { background-color: #e6f7ed; color: #14532d; padding: 12px; border-radius: 5px; border-left: 5px solid #16a34a; margin-bottom: 15px; font-size: 14px; }
    .user-badge { background: #1f3864; color: #D4AF37; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 10px; border: 1px solid #D4AF37; }
    .purchaser-card { background: #1a1a1a; padding: 12px; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- HELPERS ---
def to_ethiopian(date_val):
    if pd.isna(date_val):
        return ""
    try:
        k = Kenat(date_val.date() if hasattr(date_val, "date") else date_val)
        return k.format({"lang": "english"})
    except Exception:
        return str(date_val)

def get_eth_month_label(y, m):
    eth_months = [
        "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
        "Megabit", "Miazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"
    ]
    try:
        y_int, m_int = int(y), int(m)
        if y_int > 0 and 1 <= m_int <= 13:
            return f"{eth_months[m_int - 1]} {y_int}"
    except Exception:
        pass
    return "Unknown Date"

def extract_id(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    if "(" in s and ")" in s:
        return s.split("(")[-1].replace(")", "").strip()
    return s

def clean_numeric_col(series, default=0.0):
    if series is None:
        return pd.Series(dtype=float)
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("ETB", "", regex=False)
        .str.replace("birr", "", case=False, regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(default)

def safe_div(numerator, denominator, default=0.0):
    try:
        num = float(numerator)
        den = float(denominator)
        if pd.isna(num) or pd.isna(den) or den == 0.0:
            return float(default)
        return num / den
    except Exception:
        return float(default)

def normalize_payment_type(val):
    s = str(val or "").strip().title()
    return "Credit" if s == "Credit" else "Cash"

def get_google_creds():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            secret_data = st.secrets["gcp_service_account"]
            if "key_base64" in secret_data:
                json_str = base64.b64decode(secret_data["key_base64"]).decode("utf-8")
                key_dict = json.loads(json_str)
                return service_account.Credentials.from_service_account_info(key_dict, scopes=scope)
            return service_account.Credentials.from_service_account_info(secret_data, scopes=scope)
    except Exception:
        return service_account.Credentials.from_service_account_file("key.json", scopes=scope)

def _get_sheets_global():
    creds = get_google_creds()
    url = str(st.secrets.get("bed_solution_url", st.secrets.get("sofabet_url", ""))).strip()
    return gspread.authorize(creds).open_by_url(url)

def _ensure_sheet(ws_name, headers):
    sh = _get_sheets_global()
    try:
        ws = sh.worksheet(ws_name)
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != headers[0]:
            ws.insert_row(headers, index=1)
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=2000, cols=len(headers))
        ws.append_row(headers)
        return ws

def _get_all_records_robust(ws):
    try:
        all_vals = ws.get_all_values()
        if not all_vals or len(all_vals) < 2:
            return []
        headers = [str(h).strip() for h in all_vals[0]]
        if not headers or headers[0] == "":
            return []
        data = []
        for row in all_vals[1:]:
            if not any(row):
                continue
            if len(row) < len(headers):
                row = list(row) + [""] * (len(headers) - len(row))
            elif len(row) > len(headers):
                row = list(row)[:len(headers)]
            data.append(dict(zip(headers, row)))
        return data
    except Exception:
        return []

def _find_all_matching_rows(ws, match_fn):
    out = []
    try:
        all_vals = ws.get_all_values()
        if not all_vals or len(all_vals) < 2:
            return out
        headers = [str(h).strip() for h in all_vals[0]]
        for i, row in enumerate(all_vals[1:], start=2):
            padded = list(row) + [""] * (len(headers) - len(row))
            rec = dict(zip(headers, padded))
            try:
                if match_fn(rec):
                    out.append(i)
            except Exception:
                continue
    except Exception:
        pass
    return out

# ============================================================
# PROFESSIONAL PDF REPORT ENGINE (BED SOLUTION BRANDING)
# ============================================================
class BedSolutionReportPDF(FPDF):
    def __init__(self, font_name="Helvetica"):
        super().__init__()
        self.font_name = font_name
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(10, 10, 10)

    def footer(self):
        self.set_y(self.h - 15)
        self.set_draw_color(212, 175, 55)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.set_y(self.h - 12)
        self.set_font(self.font_name, "", 7)
        self.set_text_color(140, 140, 140)
        self.cell(0, 5, f"Bed Solution  |  Confidential Audit Report  |  Page {self.page_no()}", align="C")

def _init_pdf(fonts_available):
    if fonts_available:
        try:
            pdf = BedSolutionReportPDF("DejaVu")
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf")
            pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf")
            return pdf
        except Exception:
            pass
    return BedSolutionReportPDF("Helvetica")

def _draw_report_header(pdf, f_name, title, subtitle):
    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY = (245, 247, 250)

    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 22, "F")
    pdf.set_fill_color(*GOLD)
    pdf.rect(0, 22, pdf.w, 1.5, "F")

    text_x = 10
    if os.path.exists("logo.jpg"):
        try:
            pdf.image("logo.jpg", x=10, y=4, w=14, h=14)
            text_x = 28
        except Exception:
            text_x = 10

    brand_name = "ቤድ ሶሉሽን BED SOLUTION" if f_name == "DejaVu" else "BED SOLUTION"

    pdf.set_xy(text_x, 5); pdf.set_font(f_name, "B", 16); pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, brand_name, ln=True, align="L")

    pdf.set_xy(text_x, 13); pdf.set_font(f_name, "", 8); pdf.set_text_color(230, 230, 230)
    pdf.cell(0, 4, "Quality Bed Manufacturing", align="L")

    pdf.set_y(7); pdf.set_x(10); pdf.set_font(f_name, "B", 9); pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, "OFFICIAL AUDIT REPORT", align="R")

    pdf.set_y(30); pdf.set_font(f_name, "B", 13); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, title, ln=True, align="C")

    pdf.set_font(f_name, "", 9); pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 5, subtitle, ln=True, align="C")
    pdf.ln(3)

    meta_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, meta_y, pdf.w - 20, 8, "DF")

    pdf.set_y(meta_y + 2); pdf.set_x(10); pdf.set_font(f_name, "", 8); pdf.set_text_color(60, 60, 60)
    gen_eth = to_ethiopian(pd.Timestamp.now())
    gen_greg = datetime.datetime.now().strftime("%b %d, %Y  %H:%M")
    pdf.cell(0, 4, f"Generated: {gen_greg}     |     {gen_eth} EC", ln=True, align="C")
    pdf.ln(4)

def _draw_table(pdf, f_name, headers, rows, font_size=6):
    NAVY, WHITE = (31, 56, 100), (255, 255, 255)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)
    col_w = (pdf.w - 20) / len(headers)

    def _header_row():
        pdf.set_fill_color(*NAVY); pdf.set_text_color(*WHITE); pdf.set_font(f_name, "B", font_size + 0.5)
        pdf.set_x(10)
        for h in headers:
            pdf.cell(col_w, 6, h, border=0, align="C", fill=True)
        pdf.ln()

    _header_row()

    if not rows:
        pdf.set_font(f_name, "", font_size + 1); pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 10, "No records found for this period.", ln=True, align="C")
        return

    pdf.set_font(f_name, "", font_size); pdf.set_text_color(*DARK)

    def _fit(text):
        s = str(text).strip().replace("\n", " ").replace("\r", "")
        if not s or s.lower() in ("nan", "none"):
            return ""
        while pdf.get_string_width(s) > (col_w - 1) and len(s) > 1:
            s = s[:-1]
        return s

    for i, row in enumerate(rows):
        if pdf.get_y() + 5 > pdf.h - pdf.b_margin - 5:
            pdf.add_page()
            _header_row()
            pdf.set_font(f_name, "", font_size); pdf.set_text_color(*DARK)

        pdf.set_fill_color(*(LIGHT_GRAY if i % 2 == 0 else WHITE))
        pdf.set_x(10)
        for item in row:
            pdf.cell(col_w, 5, _fit(item), border=0, align="C", fill=True)
        pdf.ln()

def _draw_total_box(pdf, f_name, label, amount):
    NAVY, GOLD, WHITE = (31, 56, 100), (212, 175, 55), (255, 255, 255)
    pdf.ln(6)
    if pdf.get_y() + 20 > pdf.h - pdf.b_margin:
        pdf.add_page()

    box_w = 90; box_x = pdf.w - 10 - box_w; box_y = pdf.get_y()

    pdf.set_fill_color(*GOLD); pdf.rect(box_x, box_y, 3, 16, "F")
    pdf.set_fill_color(*NAVY); pdf.rect(box_x + 3, box_y, box_w - 3, 16, "F")

    pdf.set_xy(box_x + 8, box_y + 2); pdf.set_font(f_name, "B", 8); pdf.set_text_color(*GOLD)
    pdf.cell(box_w - 11, 5, label.upper(), ln=True, align="L")

    pdf.set_xy(box_x + 8, box_y + 8); pdf.set_font(f_name, "B", 13); pdf.set_text_color(*WHITE)
    pdf.cell(box_w - 11, 6, f"ETB {amount:,.2f}", ln=True, align="R")

# --- PDF GENERATORS ---
def generate_stock_audit_pdf(month_label, op_qty, op_val, in_qty, in_val, out_qty, out_val, clo_qty, clo_val, per_mat_df, sig_stock_keeper, sig_manager):
    pdf = _init_pdf(font_ready)
    f_name = pdf.font_name
    pdf.add_page()
    _draw_report_header(pdf, f_name, "Stock Audit & Reconciliation", f"Month: {month_label}")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.4)
    pdf.rect(10, info_y, pdf.w - 20, 26, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 26, "F")

    pdf.set_xy(18, info_y + 4); pdf.set_font(f_name, "B", 9); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "FINANCIAL SUMMARY", align="L")
    pdf.set_draw_color(*GOLD); pdf.line(18, info_y + 12, pdf.w - 14, info_y + 12)

    pdf.set_font(f_name, "", 8); pdf.set_text_color(*DARK)
    pdf.set_xy(20, info_y + 14); pdf.cell(80, 5, f"Opening: {op_qty:,.0f} units / ETB {op_val:,.2f}")
    pdf.set_xy(20, info_y + 20); pdf.cell(80, 5, f"In (+): {in_qty:,.0f} units / ETB {in_val:,.2f}")
    pdf.set_xy(110, info_y + 14); pdf.cell(80, 5, f"Out (-): {out_qty:,.0f} units / ETB {out_val:,.2f}")
    pdf.set_xy(110, info_y + 20); pdf.cell(80, 5, f"Closing: {clo_qty:,.0f} units / ETB {clo_val:,.2f}")

    pdf.set_y(info_y + 30); _draw_total_box(pdf, f_name, "Closing Stock Value", clo_val); pdf.ln(8)

    pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Per-Material Breakdown (For Physical Count)", ln=True)

    headers = ["Material Name", "Opening Qty", "In Qty", "Out Qty", "Closing Qty", "Closing Value (ETB)"]
    rows = []
    if not per_mat_df.empty:
        for _, r in per_mat_df.iterrows():
            rows.append([
                str(r["Material_Name"]), f"{r['Open_Qty']:,.0f}", f"{r['In_Qty']:,.0f}",
                f"{r['Out_Qty']:,.0f}", f"{r['Close_Qty']:,.0f}", f"{r['Close_Val']:,.2f}"
            ])
    _draw_table(pdf, f_name, headers, rows, font_size=6)

    pdf.ln(15); pdf.set_font(f_name, "", 9); sig_y = pdf.get_y()
    if sig_y > pdf.h - 40:
        pdf.add_page(); sig_y = pdf.get_y() + 10

    pdf.set_xy(15, sig_y); pdf.cell(70, 5, "Prepared By (Stock Keeper):", align="L")
    pdf.set_xy(15, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_stock_keeper}", align="L")
    pdf.set_xy(15, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    pdf.set_xy(115, sig_y); pdf.cell(70, 5, "Audited By (Manager):", align="L")
    pdf.set_xy(115, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_manager}", align="L")
    pdf.set_xy(115, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    return bytes(pdf.output())

def generate_supplier_audit_pdf(month_label, op_bal, credit_amt, pay_amt, clo_bal, sup_sum_df, details_df, sig_acc, sig_mgr):
    pdf = _init_pdf(font_ready)
    f_name = pdf.font_name
    pdf.add_page()
    _draw_report_header(pdf, f_name, "Supplier Credit Audit", f"Month: {month_label}")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.4)
    pdf.rect(10, info_y, pdf.w - 20, 26, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 26, "F")

    pdf.set_xy(18, info_y + 4); pdf.set_font(f_name, "B", 9); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "FINANCIAL SUMMARY", align="L")
    pdf.set_draw_color(*GOLD); pdf.line(18, info_y + 12, pdf.w - 14, info_y + 12)

    pdf.set_font(f_name, "", 8); pdf.set_text_color(*DARK)
    pdf.set_xy(20, info_y + 14); pdf.cell(80, 5, f"Opening Balance: ETB {op_bal:,.2f}")
    pdf.set_xy(20, info_y + 20); pdf.cell(80, 5, f"New Credit (+): ETB {credit_amt:,.2f}")
    pdf.set_xy(110, info_y + 14); pdf.cell(80, 5, f"Payments (-): ETB {pay_amt:,.2f}")
    pdf.set_xy(110, info_y + 20); pdf.cell(80, 5, f"Closing Balance: ETB {clo_bal:,.2f}")

    pdf.set_y(info_y + 30); _draw_total_box(pdf, f_name, "Closing Debt", clo_bal); pdf.ln(8)

    pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Per-Supplier Summary (For Reconciliation)", ln=True)

    sup_headers = ["Supplier Name", "Opening Balance", "New Credit (+)", "Payments (-)", "Closing Balance"]
    sup_rows = []
    if not sup_sum_df.empty:
        for _, r in sup_sum_df.iterrows():
            sup_rows.append([
                str(r["Supplier_Name"]), f"{r['Opening_Bal']:,.2f}",
                f"{r['New_Credit']:,.2f}", f"{r['Payments']:,.2f}", f"{r['Closing_Bal']:,.2f}"
            ])
    _draw_table(pdf, f_name, sup_headers, sup_rows, font_size=6.5)

    pdf.ln(8)
    pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Detailed Movements", ln=True)

    headers = ["Date (EC)", "Type", "Supplier", "Amount (ETB)"]
    rows = []
    if not details_df.empty:
        for _, r in details_df.iterrows():
            rows.append([
                str(to_ethiopian(r["Date"])), str(r["Type"]),
                str(r["Supplier_Name"])[:25], f"{r['Amount']:,.2f}"
            ])
    _draw_table(pdf, f_name, headers, rows, font_size=6.5)

    pdf.ln(15); pdf.set_font(f_name, "", 9); sig_y = pdf.get_y()
    if sig_y > pdf.h - 40:
        pdf.add_page(); sig_y = pdf.get_y() + 10

    pdf.set_xy(15, sig_y); pdf.cell(70, 5, "Prepared By (Accountant):", align="L")
    pdf.set_xy(15, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_acc}", align="L")
    pdf.set_xy(15, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    pdf.set_xy(115, sig_y); pdf.cell(70, 5, "Audited By (Manager):", align="L")
    pdf.set_xy(115, sig_y + 10); pdf.cell(70, 5, f"Name: {sig_mgr}", align="L")
    pdf.set_xy(115, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    return bytes(pdf.output())

def generate_batch_pdf(batch_id, model_name, qty, total_cost, direct_cost, overhead, mat_df):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, "Batch Production Report", "Detailed Batch Cost Analysis")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, info_y, pdf.w - 20, 22, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 22, "F")

    fields = [("Batch ID", batch_id), ("Bed Model", model_name), ("Quantity", qty)]
    pdf.set_y(info_y + 3)
    for label, value in fields:
        pdf.set_x(18); pdf.set_font(f_name, "B", 9); pdf.set_text_color(*NAVY)
        pdf.cell(30, 5, f"{label}:")
        pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
        pdf.cell(0, 5, str(value), ln=True)

    pdf.ln(4); _draw_total_box(pdf, f_name, "Total True Cost", total_cost); pdf.ln(4)

    summary_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD)
    pdf.rect(10, summary_y, pdf.w - 20, 10, "DF")
    pdf.set_y(summary_y + 3); pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
    pdf.cell(0, 4, f"Direct Cost: ETB {direct_cost:,.2f}     |     Allocated Overhead: ETB {overhead:,.2f}", ln=True, align="C")
    pdf.ln(6)

    pdf.set_font(f_name, "B", 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Detailed Material List", ln=True)

    mat_headers = ["Date (EC)", "Material", "Qty", "Cost (ETB)"]
    mat_rows = []
    if not mat_df.empty:
        for _, r in mat_df.iterrows():
            mat_rows.append([
                str(to_ethiopian(r["Date"])), str(r.get("Material_Name", r["Material_ID"])),
                str(r["Qty"]), f"{r['Cost']:,.2f}"
            ])
    _draw_table(pdf, f_name, mat_headers, mat_rows, font_size=8)

    return bytes(pdf.output())

def generate_income_statement_pdf(month_name, eth_year, revenue, direct_cogs, overhead_cogs, total_cogs, gross_profit, model_df, trans_df):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, f"Income Statement: {month_name} {eth_year}", "Monthly Financial Performance Report")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)
    GREEN, RED = (22, 120, 45), (170, 40, 40)

    margin_pct = safe_div(gross_profit * 100.0, revenue, 0.0)

    box_h = 72
    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.4)
    pdf.rect(10, info_y, pdf.w - 20, box_h, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 4, box_h, "F")

    pdf.set_xy(18, info_y + 4); pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "PROFIT & LOSS SUMMARY", align="L")
    pdf.set_draw_color(*GOLD); pdf.line(18, info_y + 12, pdf.w - 14, info_y + 12)

    line_items = [
        ("Revenue", f"ETB {revenue:,.2f}", DARK, True),
        ("Less: Direct Materials (FIFO)", f"(ETB {direct_cogs:,.2f})", RED, False),
        ("Less: Allocated Workshop Overhead", f"(ETB {overhead_cogs:,.2f})", RED, False),
        ("Total Cost of Goods Sold", f"(ETB {total_cogs:,.2f})", DARK, True),
        ("Gross Profit", f"ETB {gross_profit:,.2f}", GREEN, True),
        ("Gross Margin %", f"{margin_pct:.2f}%", GREEN, True),
    ]

    y = info_y + 16
    for label, value, color, bold in line_items:
        pdf.set_xy(20, y); pdf.set_font(f_name, "B" if bold else "", 10); pdf.set_text_color(*color)
        pdf.cell(120, 7, label, align="L")
        pdf.set_xy(pdf.w - 90, y); pdf.cell(76, 7, value, align="R")
        y += 8

    pdf.set_y(info_y + box_h + 6)

    pdf.set_font(f_name, "B", 12); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Sales Breakdown by Model", ln=True)
    pdf.ln(1)

    if not model_df.empty:
        _draw_table(pdf, f_name, list(model_df.columns), model_df.values.tolist(), font_size=8)
    else:
        pdf.cell(0, 8, "No model breakdown available.", ln=True, align="C")

    pdf.ln(6); pdf.set_font(f_name, "B", 12); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Transaction Details", ln=True)
    pdf.ln(1)

    if not trans_df.empty:
        _draw_table(pdf, f_name, list(trans_df.columns), trans_df.values.tolist(), font_size=6.5)
    else:
        pdf.cell(0, 8, "No transactions available.", ln=True, align="C")

    return bytes(pdf.output())

def generate_purchase_request_pdf(req_id, date_str, supplier_name, request_df, total_cost, req_name, appr_name, notes=""):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, "Purchase Request / Order", f"Request ID: {req_id}")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, info_y, pdf.w - 20, 22, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 22, "F")

    fields = [("Date", date_str), ("Supplier", supplier_name), ("Status", "Pending Approval")]
    pdf.set_y(info_y + 3)
    for label, value in fields:
        pdf.set_x(18); pdf.set_font(f_name, "B", 9); pdf.set_text_color(*NAVY)
        pdf.cell(30, 5, f"{label}:")
        pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
        pdf.cell(0, 5, str(value), ln=True)

    pdf.ln(4); _draw_total_box(pdf, f_name, "Total Estimated Cost", total_cost); pdf.ln(8)

    if notes:
        pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
        pdf.cell(0, 6, "Notes:", ln=True)
        pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
        pdf.multi_cell(0, 5, notes)
        pdf.ln(4)

    pdf.set_font(f_name, "B", 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Requested Items", ln=True)

    headers = ["#", "Material Name", "Qty", "Est. Unit Cost", "Total (ETB)"]
    rows = []
    for i, r in request_df.iterrows():
        rows.append([
            str(i + 1), str(r["Material_Name"]), str(r["Qty"]),
            f"{r['Unit_Cost']:,.2f}", f"{r['Total_Cost']:,.2f}"
        ])

    _draw_table(pdf, f_name, headers, rows, font_size=8)

    pdf.ln(20); pdf.set_font(f_name, "", 10); sig_y = pdf.get_y()
    if sig_y > pdf.h - 40:
        pdf.add_page(); sig_y = pdf.get_y() + 10

    pdf.set_xy(15, sig_y); pdf.cell(70, 5, "Requested By:", align="L")
    pdf.set_xy(15, sig_y + 10); pdf.cell(70, 5, f"Name: {req_name}", align="L")
    pdf.set_xy(15, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    pdf.set_xy(115, sig_y); pdf.cell(70, 5, "Approved By:", align="L")
    pdf.set_xy(115, sig_y + 10); pdf.cell(70, 5, f"Name: {appr_name}", align="L")
    pdf.set_xy(115, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    return bytes(pdf.output())

def generate_purchase_report_pdf(batch_id, report_df, purchaser_name, notes=""):
    pdf = _init_pdf(font_ready); f_name = pdf.font_name; pdf.add_page()
    _draw_report_header(pdf, f_name, "Purchase Submission Report", f"Batch / Ref ID: {batch_id}")

    NAVY, GOLD = (31, 56, 100), (212, 175, 55)
    LIGHT_GRAY, DARK = (245, 247, 250), (50, 50, 50)

    info_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_GRAY); pdf.set_draw_color(*GOLD); pdf.set_line_width(0.3)
    pdf.rect(10, info_y, pdf.w - 20, 18, "DF")
    pdf.set_fill_color(*GOLD); pdf.rect(10, info_y, 3, 18, "F")

    pdf.set_xy(18, info_y + 3)
    pdf.set_font(f_name, "B", 9); pdf.set_text_color(*NAVY)
    pdf.cell(30, 5, "Submitted By:")
    pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
    pdf.cell(0, 5, purchaser_name, ln=True)

    total_amt = 0.0
    if "Total" in report_df.columns:
        total_amt = float(clean_numeric_col(report_df["Total"], 0.0).sum())

    pdf.ln(4); _draw_total_box(pdf, f_name, "Total Purchase Amount", total_amt); pdf.ln(6)

    if notes:
        pdf.set_font(f_name, "B", 10); pdf.set_text_color(*NAVY)
        pdf.cell(0, 6, "Purchaser Notes:", ln=True)
        pdf.set_font(f_name, "", 9); pdf.set_text_color(*DARK)
        pdf.multi_cell(0, 5, notes)
        pdf.ln(4)

    pdf.set_font(f_name, "B", 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Submitted Items Breakdown", ln=True)

    headers = ["Supplier", "Material", "Qty", "Unit Cost", "Payment", "Total (ETB)"]
    rows = []
    for _, r in report_df.iterrows():
        qty_val = pd.to_numeric(str(r.get("Qty", 0)).replace(",", ""), errors="coerce")
        uc_val = pd.to_numeric(str(r.get("Unit_Cost", 0)).replace(",", ""), errors="coerce")
        tot_val = pd.to_numeric(str(r.get("Total", 0)).replace(",", ""), errors="coerce")

        qty_str = f"{qty_val:,.0f}" if pd.notna(qty_val) else "0"
        uc_str = f"{uc_val:,.2f}" if pd.notna(uc_val) else "0.00"
        tot_str = f"{tot_val:,.2f}" if pd.notna(tot_val) else "0.00"

        rows.append([
            str(r.get("Supplier_Name", "")), str(r.get("Material_Name", "")),
            qty_str, uc_str, str(r.get("Payment_Type", "Cash")), tot_str
        ])

    _draw_table(pdf, f_name, headers, rows, font_size=7)

    pdf.ln(20); pdf.set_font(f_name, "", 10); sig_y = pdf.get_y()
    if sig_y > pdf.h - 40:
        pdf.add_page(); sig_y = pdf.get_y() + 10

    pdf.set_xy(15, sig_y); pdf.cell(70, 5, "Submitted By (Purchaser):", align="L")
    pdf.set_xy(15, sig_y + 10); pdf.cell(70, 5, f"Name: {purchaser_name}", align="L")
    pdf.set_xy(15, sig_y + 15); pdf.cell(70, 5, "Signature: _______________________", align="L")

    return bytes(pdf.output())

# --- AUTHENTICATION (ROLE-BASED DROPDOWN) ---
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
        pwd = st.text_input("Master Password", type="password", key="legacy_pwd")
        if st.button("Login", type="primary"):
            if pwd == st.secrets.get("app_password", "BED2026"):
                st.session_state.user = {"username": "manager", "name": "Manager", "role": "manager"}
                st.rerun()
            else:
                st.error("❌ Wrong password")
        return False

    user_options = {}
    for uname, udata in users_secrets.items():
        display = f"{udata.get('name', uname)} ({udata.get('role', 'viewer').title()})"
        user_options[display] = uname

    with st.form("login_form", clear_on_submit=True):
        selected_display = st.selectbox("Select Your Profile:", list(user_options.keys()))
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

    if submitted:
        uname = user_options[selected_display]
        user_data = users_secrets[uname]
        stored_pwd = user_data.get("password", "")
        stored_name = user_data.get("name", uname)
        stored_role = user_data.get("role", "viewer")

        if stored_pwd == password:
            st.session_state.user = {"username": uname, "name": stored_name, "role": stored_role}
            st.rerun()
        else:
            st.error("❌ Invalid password for this profile.")

    return False

# --- STYLER FOR NEGATIVE NUMBERS ---
def color_negative_red(val):
    if pd.isna(val):
        return ""
    try:
        if float(val) < 0:
            return "color: #FF4B4B; font-weight: bold;"
        return ""
    except Exception:
        return ""

# =====================================================================
# MAIN APP
# =====================================================================
if authenticate():
    user = st.session_state.user
    role = str(user.get("role", "")).strip().lower()
    user_name = user.get("name", user.get("username", "Guest"))

    with st.sidebar:
        st.markdown(f'<div class="user-badge">👤 {user_name}<br><span style="font-size:12px;">{role.upper()}</span></div>', unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            del st.session_state.user
            st.rerun()
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.markdown('<p class="golden-title">ቤድ ሶሉሽን</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">EXECUTIVE DASHBOARD</p>', unsafe_allow_html=True)

    # --- ETHIOPIAN DATE FILTERS ---
    st.sidebar.header("📅 Ethiopian Date Filters")
    eth_months = [
        "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
        "Megabit", "Miazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"
    ]

    eth_today = Kenat(datetime.date.today()).get_ethiopian()
    curr_eth_year, curr_eth_month, curr_eth_day = eth_today["year"], eth_today["month"], eth_today["day"]

    def get_greg_date(eth_y, eth_m, eth_d):
        try:
            g = Kenat(f"{eth_y}/{eth_m}/{eth_d}").get_gregorian()
            return pd.to_datetime(datetime.date(g["year"], g["month"], g["day"]))
        except Exception:
            return pd.NaT

    filter_option = st.sidebar.radio(
        "Select Range:",
        ["All Time", "This Month (EC)", "Last Month (EC)", "This Year (EC)", "Custom Range (EC)"]
    )

    if filter_option == "This Month (EC)":
        start_date = get_greg_date(curr_eth_year, curr_eth_month, 1)
        end_date = pd.to_datetime(datetime.date.today())
        st.sidebar.info(f"Filtering: {eth_months[curr_eth_month - 1]} {curr_eth_year} EC")
    elif filter_option == "Last Month (EC)":
        prev_y, prev_m = (curr_eth_year - 1, 13) if curr_eth_month == 1 else (curr_eth_year, curr_eth_month - 1)
        start_date = get_greg_date(prev_y, prev_m, 1)
        curr_start_greg = get_greg_date(curr_eth_year, curr_eth_month, 1)
        end_date = curr_start_greg - datetime.timedelta(days=1)
        st.sidebar.info(f"Filtering: {eth_months[prev_m - 1]} {prev_y} EC")
    elif filter_option == "This Year (EC)":
        start_date = get_greg_date(curr_eth_year, 1, 1)
        end_date = pd.to_datetime(datetime.date.today())
        st.sidebar.info(f"Filtering: Year {curr_eth_year} EC")
    elif filter_option == "Custom Range (EC)":
        st.sidebar.write("**From**")
        c1, c2, c3 = st.sidebar.columns(3)
        start_y = c1.selectbox("Year", range(curr_eth_year - 5, curr_eth_year + 2), index=5, key="sy")
        start_m = c2.selectbox("Month", range(1, 14), index=curr_eth_month - 1, format_func=lambda x: eth_months[x - 1], key="sm")
        start_d = c3.selectbox("Day", range(1, 31), index=0, key="sd")
        st.sidebar.write("**To**")
        c4, c5, c6 = st.sidebar.columns(3)
        end_y = c4.selectbox("Year", range(curr_eth_year - 5, curr_eth_year + 2), index=5, key="ey")
        end_m = c5.selectbox("Month", range(1, 14), index=curr_eth_month - 1, format_func=lambda x: eth_months[x - 1], key="em")
        end_d = c6.selectbox("Day", range(1, 31), index=max(0, curr_eth_day - 1), key="ed")
        start_date = get_greg_date(start_y, start_m, start_d)
        end_date = get_greg_date(end_y, end_m, end_d)
    else:
        start_date = pd.to_datetime("2000-01-01")
        end_date = pd.to_datetime("2100-01-01")
        st.sidebar.info("Showing All Time Data")

    if pd.isna(start_date):
        start_date = pd.to_datetime("2000-01-01")
    if pd.isna(end_date):
        end_date = pd.to_datetime("2100-01-01")

    @st.cache_data(ttl=300, show_spinner="Loading Bed Solution data...")
    def load_data():
        url = str(st.secrets.get("bed_solution_url", st.secrets.get("sofabet_url", ""))).strip()
        if not url:
            st.error("❌ Missing 'bed_solution_url' or 'sofabet_url' in Streamlit Secrets.")
            st.stop()

        tabs = [
            "Materials", "Suppliers", "Purchases", "Bed_Models",
            "Production", "Material_Issues", "Sales", "Opening_Stock",
            "Opening_Payables", "Supplier_Payments"
        ]

        try:
            creds = get_google_creds()
            client = gspread.authorize(creds)
            sheet = client.open_by_url(url)

            ranges = [f"'{tab}'!A:Z" for tab in tabs]
            batch_res = sheet.values_batch_get(ranges)
            value_ranges = batch_res.get("valueRanges", [])

            result = {}
            for tab, vr in zip(tabs, value_ranges):
                raw = vr.get("values", [])
                if len(raw) > 1:
                    raw_headers = [str(h).strip() for h in raw[0]]
                    valid_cols = [(idx, h) for idx, h in enumerate(raw_headers) if h != ""]
                    if not valid_cols:
                        result[tab] = pd.DataFrame()
                        continue

                    headers = [h for _, h in valid_cols]
                    n_cols = len(headers)
                    normalized_rows = []
                    for r in raw[1:]:
                        if not any(r):
                            continue
                        extracted = [r[idx] if idx < len(r) else "" for idx, _ in valid_cols]
                        if len(extracted) < n_cols:
                            extracted += [""] * (n_cols - len(extracted))
                        elif len(extracted) > n_cols:
                            extracted = extracted[:n_cols]
                        normalized_rows.append(extracted)

                    if normalized_rows:
                        df = pd.DataFrame(normalized_rows, columns=headers).replace("", pd.NA).dropna(how="all")
                        result[tab] = df
                    else:
                        result[tab] = pd.DataFrame()
                else:
                    result[tab] = pd.DataFrame()
            return result

        except gspread.exceptions.APIError as e:
            status = getattr(e.response, "status_code", "Unknown")
            if status == 403:
                st.error("❌ Permission Denied (403): Share the Google Sheet with your service account email as Editor.")
            elif status == 429:
                st.warning("⚠️ Google Sheets Rate Limit (429): Too many requests. Please wait 60 seconds and refresh.")
            elif status == 404:
                st.error("❌ Spreadsheet Not Found (404): Check 'bed_solution_url' in Streamlit Secrets.")
            else:
                st.error(f"❌ Google Sheets API Error ({status}): {e}")
            st.stop()

    data = load_data()
    df_mat, df_sup, df_pur = data["Materials"], data["Suppliers"], data["Purchases"]
    df_op_stock, df_op_pay, df_pay = data["Opening_Stock"], data["Opening_Payables"], data["Supplier_Payments"]
    df_models, df_prod, df_issues, df_sales = data["Bed_Models"], data["Production"], data["Material_Issues"], data["Sales"]

    # --- BULLETPROOF DATAFRAMES & SCHEMA SAFETY ---
    if df_pur.empty:
        df_pur = pd.DataFrame(columns=["Date", "Supplier_ID", "Material_ID", "Qty", "Unit_Cost", "Payment_Type"])
    if df_issues.empty:
        df_issues = pd.DataFrame(columns=["Date", "Material_ID", "Batch_ID", "Qty"])
    if df_pay.empty:
        df_pay = pd.DataFrame(columns=["Date", "Supplier_ID", "Amount"])
    if df_op_pay.empty:
        df_op_pay = pd.DataFrame(columns=["Supplier_ID", "Amount_Owed"])
    if df_op_stock.empty:
        df_op_stock = pd.DataFrame(columns=["Date", "Material_ID", "Qty", "Unit_Cost"])
    if df_sup.empty:
        df_sup = pd.DataFrame(columns=["Supplier_ID", "Supplier_Name"])
    if df_mat.empty:
        df_mat = pd.DataFrame(columns=["Material_ID", "Material_Name", "Reorder_Level"])
    if df_models.empty:
        df_models = pd.DataFrame(columns=["Model_ID", "Model_Name", "Type"])
    if df_prod.empty:
        df_prod = pd.DataFrame(columns=[
            "Date", "Batch_ID", "Model_ID", "Qty_Produced", "Status",
            "Direct_Mat_Cost", "Absorbed_Overhead_Cost", "Total_True_Cost", "True_Unit_Cost"
        ])
    if df_sales.empty:
        df_sales = pd.DataFrame(columns=["Date", "Batch_ID", "Model_ID", "Client_Name", "Qty_Sold", "Total_Sale_Price"])

    if "Supplier_Name" in df_sup.columns:
        df_sup["Supplier_Name"] = df_sup["Supplier_Name"].astype(str).str.strip()
    if "Material_Name" in df_mat.columns:
        df_mat["Material_Name"] = df_mat["Material_Name"].astype(str).str.strip()
    if "Model_Name" in df_models.columns:
        df_models["Model_Name"] = df_models["Model_Name"].astype(str).str.strip()

    for col in ["Supplier_ID", "Material_ID", "Model_ID", "Batch_ID"]:
        for df_target in [df_mat, df_sup, df_models, df_pur, df_issues, df_prod, df_sales, df_op_stock, df_op_pay, df_pay]:
            if col in df_target.columns:
                df_target[col] = df_target[col].apply(extract_id)

    for df_target in [df_pur, df_issues, df_prod, df_sales, df_op_stock, df_op_pay, df_pay]:
        if "Date" in df_target.columns:
            df_target["Date"] = pd.to_datetime(df_target["Date"], errors="coerce")

    if not df_pur.empty:
        df_pur["Qty"] = clean_numeric_col(df_pur.get("Qty"), 0.0)
        df_pur["Unit_Cost"] = clean_numeric_col(df_pur.get("Unit_Cost"), 0.0)
        df_pur["Payment_Type"] = df_pur.get("Payment_Type", pd.Series(["Cash"] * len(df_pur))).apply(normalize_payment_type)
    if not df_issues.empty:
        df_issues["Qty"] = clean_numeric_col(df_issues.get("Qty"), 0.0)
    if not df_op_stock.empty:
        df_op_stock["Qty"] = clean_numeric_col(df_op_stock.get("Qty"), 0.0)
        df_op_stock["Unit_Cost"] = clean_numeric_col(df_op_stock.get("Unit_Cost"), 0.0)
    if not df_pay.empty:
        df_pay["Amount"] = clean_numeric_col(df_pay.get("Amount"), 0.0)
    if not df_op_pay.empty:
        df_op_pay["Amount_Owed"] = clean_numeric_col(df_op_pay.get("Amount_Owed"), 0.0)
    if not df_mat.empty and "Reorder_Level" in df_mat.columns:
        df_mat["Reorder_Level"] = clean_numeric_col(df_mat.get("Reorder_Level"), 0.0)

    # --- FIXED FIFO ENGINE ---
    layers = []
    if not df_op_stock.empty:
        for _, row in df_op_stock.iterrows():
            layers.append({
                "Date": row["Date"], "Material_ID": row["Material_ID"],
                "Qty": float(row["Qty"]), "Unit_Cost": float(row["Unit_Cost"])
            })
    if not df_pur.empty:
        for _, row in df_pur.iterrows():
            layers.append({
                "Date": row["Date"], "Material_ID": row["Material_ID"],
                "Qty": float(row["Qty"]), "Unit_Cost": float(row["Unit_Cost"])
            })

    df_layers = pd.DataFrame(layers).sort_values(by="Date") if layers else pd.DataFrame(columns=["Date", "Material_ID", "Qty", "Unit_Cost"])
    if not df_layers.empty:
        df_layers["Qty"] = df_layers["Qty"].astype(float)
        df_layers["Unit_Cost"] = df_layers["Unit_Cost"].astype(float)

    batch_costs, current_stock, batch_issue_details = {}, {}, []
    workshop_issues = []

    if not df_layers.empty:
        for _, layer in df_layers.iterrows():
            m_key = layer["Material_ID"]
            if m_key:
                current_stock[m_key] = current_stock.get(m_key, 0.0) + float(layer["Qty"])

    if not df_issues.empty:
        df_issues = df_issues.sort_values(by="Date")
        for _, issue in df_issues.iterrows():
            m_id = issue["Material_ID"]
            qty_needed = float(issue["Qty"])
            batch_id = issue["Batch_ID"]
            cost = 0.0
            if m_id not in current_stock:
                current_stock[m_id] = 0.0
            if not df_layers.empty:
                for i, _ in df_layers[df_layers["Material_ID"] == m_id].iterrows():
                    avail = float(df_layers.at[i, "Qty"])
                    if avail > 0.0 and qty_needed > 0.0:
                        take = min(avail, qty_needed)
                        cost += take * float(df_layers.at[i, "Unit_Cost"])
                        df_layers.at[i, "Qty"] = avail - take
                        qty_needed -= take
                        current_stock[m_id] -= take
            if qty_needed > 0.0:
                current_stock[m_id] -= qty_needed

            if pd.notna(batch_id) and str(batch_id).strip() != "" and str(batch_id).strip().lower() != "workshop":
                b_key = str(batch_id).strip().upper()
                batch_costs[b_key] = batch_costs.get(b_key, 0.0) + cost
                batch_issue_details.append({
                    "Date": issue["Date"], "Batch_ID": b_key,
                    "Material_ID": m_id, "Qty": float(issue["Qty"]), "Cost": cost
                })
            else:
                workshop_issues.append({
                    "Date": issue["Date"], "Cost": cost,
                    "Qty": float(issue["Qty"]), "Material_ID": m_id
                })

    # --- CALCULATE PRODUCTION ---
    monthly_overhead = pd.DataFrame(columns=["Eth_Year", "Eth_Month", "Monthly_Qty_Produced", "Monthly_Consumable_Cost", "Overhead_Per_Unit"])
    if not df_prod.empty:
        df_prod["Batch_ID"] = df_prod["Batch_ID"].astype(str).str.strip().str.upper()
        df_prod["Qty_Produced"] = clean_numeric_col(df_prod.get("Qty_Produced"), 0.0)
        df_prod["Direct_Mat_Cost"] = df_prod["Batch_ID"].map(lambda x: batch_costs.get(x, 0.0))
        df_prod["Direct_Unit_Cost"] = df_prod.apply(
            lambda r: safe_div(r["Direct_Mat_Cost"], r["Qty_Produced"], 0.0), axis=1
        )
        if not df_models.empty and "Model_ID" in df_prod.columns:
            cols_m = [c for c in ["Model_ID", "Model_Name", "Type"] if c in df_models.columns]
            df_prod = df_prod.merge(df_models[cols_m].drop_duplicates(subset=["Model_ID"]), on="Model_ID", how="left")
        if "Model_Name" not in df_prod.columns:
            df_prod["Model_Name"] = df_prod["Model_ID"]
        else:
            df_prod["Model_Name"] = df_prod["Model_Name"].fillna(df_prod["Model_ID"])
        if "Status" not in df_prod.columns:
            df_prod["Status"] = "In Progress"

    # --- MONTHLY OVERHEAD ABSORPTION ---
    df_workshop = pd.DataFrame(workshop_issues) if workshop_issues else pd.DataFrame(columns=["Date", "Cost", "Qty", "Material_ID"])
    if not df_workshop.empty:
        df_workshop["Eth_Year"] = df_workshop["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
        df_workshop["Eth_Month"] = df_workshop["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)

    if not df_prod.empty:
        df_prod["Eth_Year"] = df_prod["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
        df_prod["Eth_Month"] = df_prod["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)

        if not df_workshop.empty:
            monthly_consumables = df_workshop.groupby(["Eth_Year", "Eth_Month"])["Cost"].sum().reset_index()
            monthly_consumables.columns = ["Eth_Year", "Eth_Month", "Monthly_Consumable_Cost"]
        else:
            monthly_consumables = pd.DataFrame(columns=["Eth_Year", "Eth_Month", "Monthly_Consumable_Cost"])

        monthly_production = df_prod.groupby(["Eth_Year", "Eth_Month"])["Qty_Produced"].sum().reset_index()
        monthly_production.columns = ["Eth_Year", "Eth_Month", "Monthly_Qty_Produced"]

        monthly_overhead = monthly_production.merge(monthly_consumables, on=["Eth_Year", "Eth_Month"], how="left").fillna(0.0)
        monthly_overhead["Overhead_Per_Unit"] = monthly_overhead.apply(
            lambda r: safe_div(r["Monthly_Consumable_Cost"], r["Monthly_Qty_Produced"], 0.0), axis=1
        )

        df_prod = df_prod.merge(
            monthly_overhead[["Eth_Year", "Eth_Month", "Overhead_Per_Unit"]],
            on=["Eth_Year", "Eth_Month"],
            how="left"
        )
        df_prod["Overhead_Per_Unit"] = clean_numeric_col(df_prod.get("Overhead_Per_Unit"), 0.0)
        df_prod["Absorbed_Overhead_Cost"] = df_prod["Qty_Produced"] * df_prod["Overhead_Per_Unit"]
        df_prod["Total_True_Cost"] = df_prod["Direct_Mat_Cost"] + df_prod["Absorbed_Overhead_Cost"]
        df_prod["True_Unit_Cost"] = df_prod.apply(
            lambda r: safe_div(r["Total_True_Cost"], r["Qty_Produced"], 0.0), axis=1
        )

    # --- OPTIMIZED SALES & COGS LOOKUP ---
    missing_batches = []
    if not df_sales.empty:
        df_sales["Batch_ID"] = df_sales.get("Batch_ID", pd.Series([""] * len(df_sales))).astype(str).str.strip().str.upper()
        df_sales["Qty_Sold"] = clean_numeric_col(df_sales.get("Qty_Sold"), 0.0)
        df_sales["Total_Sale_Price"] = clean_numeric_col(df_sales.get("Total_Sale_Price"), 0.0)

        if not df_prod.empty:
            prod_dedup = df_prod.drop_duplicates(subset=["Batch_ID"], keep="last")
            true_unit_cost_map = dict(zip(prod_dedup["Batch_ID"], prod_dedup["True_Unit_Cost"]))
            model_name_map = dict(zip(prod_dedup["Batch_ID"], prod_dedup["Model_Name"]))
            df_sales["True_Unit_Cost"] = df_sales["Batch_ID"].map(true_unit_cost_map)
            df_sales["Model_Name"] = df_sales["Batch_ID"].map(model_name_map).fillna(df_sales["Batch_ID"])
            missing_batches = df_sales[(df_sales["True_Unit_Cost"].isna()) & (df_sales["Batch_ID"] != "")]["Batch_ID"].unique().tolist()
        else:
            df_sales["True_Unit_Cost"] = 0.0
            df_sales["Model_Name"] = df_sales["Batch_ID"]

        df_sales["COGS"] = df_sales["Qty_Sold"] * clean_numeric_col(df_sales.get("True_Unit_Cost"), 0.0)
        df_sales["Gross_Profit"] = df_sales["Total_Sale_Price"] - df_sales["COGS"]

    # --- PAYABLES ---
    supplier_balances = {}
    if not df_op_pay.empty:
        for _, row in df_op_pay.iterrows():
            s_id = str(row.get("Supplier_ID", "")).strip()
            if s_id:
                supplier_balances[s_id] = supplier_balances.get(s_id, 0.0) + float(row.get("Amount_Owed", 0.0))
    if not df_pur.empty:
        for _, row in df_pur.iterrows():
            s_id = str(row.get("Supplier_ID", "")).strip()
            if s_id and row.get("Payment_Type") == "Credit":
                supplier_balances[s_id] = supplier_balances.get(s_id, 0.0) + float(row["Qty"]) * float(row["Unit_Cost"])
    if not df_pay.empty:
        for _, row in df_pay.iterrows():
            s_id = str(row.get("Supplier_ID", "")).strip()
            if s_id:
                supplier_balances[s_id] = supplier_balances.get(s_id, 0.0) - float(row.get("Amount", 0.0))

    # --- FILTERS ---
    if not df_sales.empty and "Date" in df_sales.columns:
        df_sales_filt = df_sales[(df_sales["Date"] >= start_date) & (df_sales["Date"] <= end_date)].copy()
    else:
        df_sales_filt = pd.DataFrame()

    if not df_prod.empty and "Date" in df_prod.columns:
        df_prod_filt = df_prod[(df_prod["Date"] >= start_date) & (df_prod["Date"] <= end_date)].copy()
    else:
        df_prod_filt = pd.DataFrame()

    # --- AUDIT DATA PREP ---
    if not df_pur.empty:
        df_pur["Eth_Year"] = df_pur["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
        df_pur["Eth_Month"] = df_pur["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)
        df_pur["Total_Value"] = df_pur["Qty"] * df_pur["Unit_Cost"]
        df_pur["Credit_Value"] = df_pur.apply(
            lambda r: r["Total_Value"] if normalize_payment_type(r.get("Payment_Type", "")) == "Credit" else 0.0,
            axis=1
        )
    else:
        df_pur = pd.DataFrame(columns=[
            "Date", "Supplier_ID", "Material_ID", "Qty", "Unit_Cost",
            "Payment_Type", "Eth_Year", "Eth_Month", "Total_Value", "Credit_Value"
        ])

    if not df_pay.empty:
        df_pay["Eth_Year"] = df_pay["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
        df_pay["Eth_Month"] = df_pay["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)
    else:
        df_pay = pd.DataFrame(columns=["Date", "Supplier_ID", "Amount", "Eth_Year", "Eth_Month"])

    all_issues = batch_issue_details + workshop_issues
    if all_issues:
        df_issues_all = pd.DataFrame(all_issues)
        df_issues_all["Eth_Year"] = df_issues_all["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
        df_issues_all["Eth_Month"] = df_issues_all["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)
    else:
        df_issues_all = pd.DataFrame(columns=["Date", "Batch_ID", "Material_ID", "Qty", "Cost", "Eth_Year", "Eth_Month"])

    months_list = []
    if not df_pur.empty:
        months_list.extend(df_pur[["Eth_Year", "Eth_Month"]].values.tolist())
    if all_issues:
        months_list.extend(df_issues_all[["Eth_Year", "Eth_Month"]].values.tolist())
    if not df_pay.empty:
        months_list.extend(df_pay[["Eth_Year", "Eth_Month"]].values.tolist())

    unique_months = sorted({tuple(x) for x in months_list}, reverse=True)
    audit_month_opts = [
        (y, m, get_eth_month_label(y, m))
        for y, m in unique_months if get_eth_month_label(y, m) != "Unknown Date"
    ]

    # --- DATA HEALTH CHECK ---
    health_warnings = []
    if missing_batches:
        health_warnings.append(
            f"Sales reference unknown Batch IDs ({', '.join(missing_batches)}) — their COGS is currently ETB 0.00."
        )
    if not df_prod.empty and "Direct_Mat_Cost" in df_prod.columns:
        zero_mat_b = df_prod[df_prod["Direct_Mat_Cost"] == 0]["Batch_ID"].dropna().unique().tolist()
        if zero_mat_b:
            health_warnings.append(
                f"Production batches with ETB 0 direct material cost: {', '.join(zero_mat_b[:8])}."
            )
    neg_stock_items = [k for k, v in current_stock.items() if float(v) < 0]
    if neg_stock_items:
        health_warnings.append(
            f"Negative stock balance detected on {len(neg_stock_items)} material code(s) — check issue dates vs. purchases/opening stock."
        )

    # =====================================================================
    # ROLE-BASED TAB VISIBILITY
    # =====================================================================
    ALL_TABS = [
        ("exec", "📊 Exec Summary"),
        ("prod", "🏭 Production"),
        ("sales", "🛒 Sales & Income Statement"),
        ("inv", "📦 Inventory"),
        ("sup", "🧾 Suppliers"),
        ("stock_audit", "📈 Stock Audit"),
        ("sup_audit", "💳 Supplier Audit"),
        ("request", "📝 Purchase Request"),
        ("purch", "🛒 Purchaser & Approver"),
        ("analytics", "📈 Advanced Analytics")
    ]

    if role == "manager":
        allowed_keys = [k for k, _ in ALL_TABS]
    elif role == "maker":
        allowed_keys = ["request", "stock_audit", "inv"]
    elif role in ("purchaser", "approver"):
        allowed_keys = ["purch"]
    else:
        st.error(f"❌ Unknown role: '{role}'. Contact Admin.")
        st.stop()

    visible = [(k, l) for k, l in ALL_TABS if k in allowed_keys]
    tabs_objs = st.tabs([l for _, l in visible])
    tab_map = {k: t for (k, _), t in zip(visible, tabs_objs)}

    # --- TAB: EXECUTIVE SUMMARY ---
    if "exec" in tab_map:
        with tab_map["exec"]:
            if health_warnings:
                bullets = "<br>".join(f"• {w}" for w in health_warnings)
                st.markdown(
                    f'<div class="warn-box">🩺 <b>Data Health Check ({len(health_warnings)} item(s) to review):</b><br>{bullets}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    '<div class="health-ok">🩺 <b>Data Health Check:</b> All batch links, stock balances, and COGS mappings look clean.</div>',
                    unsafe_allow_html=True
                )

            total_rev = df_sales_filt["Total_Sale_Price"].sum() if not df_sales_filt.empty and "Total_Sale_Price" in df_sales_filt.columns else 0.0
            total_cogs = df_sales_filt["COGS"].sum() if not df_sales_filt.empty and "COGS" in df_sales_filt.columns else 0.0
            total_profit = df_sales_filt["Gross_Profit"].sum() if not df_sales_filt.empty and "Gross_Profit" in df_sales_filt.columns else 0.0
            margin = safe_div(total_profit * 100.0, total_rev, 0.0)
            total_payables = sum(v for v in supplier_balances.values() if v > 0)
            inv_value = sum(float(row["Qty"]) * float(row["Unit_Cost"]) for _, row in df_layers.iterrows() if float(row["Qty"]) > 0) if not df_layers.empty else 0.0

            c1, c2, c3 = st.columns(3)
            c1.metric("Revenue", f"ETB {total_rev:,.2f}")
            c2.metric("True COGS (Inc. Overhead)", f"ETB {total_cogs:,.2f}")
            c3.metric("Gross Profit", f"ETB {total_profit:,.2f}", delta=f"{margin:.1f}% Margin")

            c4, c5 = st.columns(2)
            c4.metric("Inventory Value", f"ETB {inv_value:,.2f}")
            c5.metric("Total Debt", f"ETB {total_payables:,.2f}")

            st.divider()
            c_left, c_right = st.columns(2)
            with c_left:
                st.subheader("Top Selling Bed Models")
                if not df_sales_filt.empty and "Model_Name" in df_sales_filt.columns:
                    top_models = df_sales_filt.groupby("Model_Name")["Qty_Sold"].sum().reset_index().sort_values(by="Qty_Sold", ascending=False).head(5)
                    fig = px.bar(top_models, x="Model_Name", y="Qty_Sold", color="Qty_Sold", color_continuous_scale="Teal")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No sales volume data for this period.")
            with c_right:
                st.subheader("Production vs Sales Volume")
                if not df_prod_filt.empty and not df_sales_filt.empty:
                    prod_vol = df_prod_filt.groupby("Model_Name")["Qty_Produced"].sum().reset_index()
                    sold_vol = df_sales_filt.groupby("Model_Name")["Qty_Sold"].sum().reset_index()
                    merged = pd.merge(prod_vol, sold_vol, on="Model_Name", how="outer").fillna(0)
                    fig = go.Figure(data=[
                        go.Bar(name="Produced", x=merged["Model_Name"], y=merged["Qty_Produced"], marker_color="#1f77b4"),
                        go.Bar(name="Sold", x=merged["Model_Name"], y=merged["Qty_Sold"], marker_color="#D4AF37")
                    ])
                    fig.update_layout(barmode="group")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Need both production and sales records in this range to compare.")

    # --- TAB: PRODUCTION ---
    if "prod" in tab_map:
        with tab_map["prod"]:
            st.subheader("Production Performance")
            if not df_prod_filt.empty:
                zero_cost_batches = df_prod_filt[df_prod_filt["Direct_Mat_Cost"] == 0]["Batch_ID"].unique()
                if len(zero_cost_batches) > 0:
                    st.info(f"ℹ️ Note: Batches {', '.join(zero_cost_batches)} have ETB 0 direct material cost. Make sure materials are issued with the matching Batch_ID in Material_Issues.")

                c1, c2, c3 = st.columns(3)
                c1.metric("Total Units Produced", f"{df_prod_filt['Qty_Produced'].sum():,.0f}")
                c2.metric("Direct Material Cost", f"ETB {df_prod_filt['Direct_Mat_Cost'].sum():,.2f}")
                c3.metric("Absorbed Workshop Overhead", f"ETB {df_prod_filt['Absorbed_Overhead_Cost'].sum():,.2f}")

                df_prod_disp = df_prod_filt.copy()
                df_prod_disp["Date (EC)"] = df_prod_disp["Date"].apply(to_ethiopian)
                st.dataframe(
                    df_prod_disp[[
                        "Date (EC)", "Batch_ID", "Model_Name", "Qty_Produced",
                        "Status", "Direct_Mat_Cost", "Absorbed_Overhead_Cost",
                        "Total_True_Cost", "True_Unit_Cost"
                    ]],
                    use_container_width=True,
                    hide_index=True
                )

                st.divider()
                if batch_issue_details:
                    df_batch_details = pd.DataFrame(batch_issue_details)
                    if not df_mat.empty:
                        df_batch_details = df_batch_details.merge(
                            df_mat[["Material_ID", "Material_Name"]].drop_duplicates(subset=["Material_ID"]),
                            on="Material_ID",
                            how="left"
                        )
                        df_batch_details["Material_Name"] = df_batch_details["Material_Name"].fillna(df_batch_details["Material_ID"])

                    batch_options = df_prod_filt["Batch_ID"].unique().tolist()
                    selected_batch = st.selectbox("Select a Batch to view its material details:", batch_options)

                    if selected_batch:
                        df_selected = df_batch_details[df_batch_details["Batch_ID"] == selected_batch].copy()
                        if not df_selected.empty:
                            df_selected["Date (EC)"] = df_selected["Date"].apply(to_ethiopian)
                            st.dataframe(df_selected[["Date (EC)", "Material_Name", "Qty", "Cost"]], use_container_width=True, hide_index=True)

                            b_slice = df_prod_filt[df_prod_filt["Batch_ID"] == selected_batch]
                            batch_overhead = b_slice["Absorbed_Overhead_Cost"].sum()
                            direct_cost = df_selected["Cost"].sum()
                            total_b_cost = direct_cost + batch_overhead

                            c_direct, c_overhead, c_total = st.columns(3)
                            c_direct.metric("Direct Material Cost", f"ETB {direct_cost:,.2f}")
                            c_overhead.metric("Allocated Workshop Overhead", f"ETB {batch_overhead:,.2f}")
                            c_total.metric("Total Batch Cost", f"ETB {total_b_cost:,.2f}")

                            model_n = b_slice["Model_Name"].values[0] if not b_slice.empty else "Unknown"
                            qty_p = b_slice["Qty_Produced"].values[0] if not b_slice.empty else 0

                            batch_pdf_bytes = generate_batch_pdf(selected_batch, model_n, qty_p, total_b_cost, direct_cost, batch_overhead, df_selected)
                            st.download_button(
                                f"📥 Download PDF for Batch {selected_batch}",
                                data=batch_pdf_bytes,
                                file_name=f"Bed_Solution_Batch_{selected_batch}.pdf",
                                mime="application/pdf",
                                type="primary"
                            )
                        else:
                            st.info(f"No direct material issues recorded for batch {selected_batch}.")
            else:
                st.info("No production records in this range.")

    # --- TAB: SALES & COGS ---
    if "sales" in tab_map:
        with tab_map["sales"]:
            if not df_sales_filt.empty:
                df_sales_filt["Eth_Year"] = df_sales_filt["Date"].apply(lambda x: Kenat(x).get_ethiopian()["year"] if pd.notna(x) else 0)
                df_sales_filt["Eth_Month"] = df_sales_filt["Date"].apply(lambda x: Kenat(x).get_ethiopian()["month"] if pd.notna(x) else 0)
                monthly = (
                    df_sales_filt.groupby(["Eth_Year", "Eth_Month"])
                    .agg({"Total_Sale_Price": "sum", "COGS": "sum", "Gross_Profit": "sum"})
                    .reset_index()
                    .sort_values(["Eth_Year", "Eth_Month"], ascending=False)
                )

                for _, row in monthly.iterrows():
                    m_name = get_eth_month_label(row["Eth_Year"], row["Eth_Month"])
                    with st.expander(
                        f"📅 {m_name} | Revenue: ETB {row['Total_Sale_Price']:,.0f} | Profit: ETB {row['Gross_Profit']:,.0f}",
                        expanded=True
                    ):
                        df_m = df_sales_filt[(df_sales_filt["Eth_Year"] == row["Eth_Year"]) & (df_sales_filt["Eth_Month"] == row["Eth_Month"])]
                        df_m_calc = df_m.copy()

                        if not df_prod.empty:
                            p_dedup = df_prod.drop_duplicates(subset=["Batch_ID"], keep="last")
                            dir_unit_cost_map = dict(zip(p_dedup["Batch_ID"], p_dedup["Direct_Unit_Cost"]))
                            oh_unit_cost_map = dict(zip(p_dedup["Batch_ID"], p_dedup["Overhead_Per_Unit"]))
                        else:
                            dir_unit_cost_map, oh_unit_cost_map = {}, {}

                        df_m_calc["Direct_Unit_Cost"] = df_m_calc["Batch_ID"].map(dir_unit_cost_map).fillna(0.0)
                        df_m_calc["Overhead_Unit_Cost"] = df_m_calc["Batch_ID"].map(oh_unit_cost_map).fillna(0.0)

                        direct_cogs = (df_m_calc["Qty_Sold"] * df_m_calc["Direct_Unit_Cost"]).sum()
                        absorbed_overhead_cogs = (df_m_calc["Qty_Sold"] * df_m_calc["Overhead_Unit_Cost"]).sum()

                        this_month_oh = monthly_overhead[
                            (monthly_overhead["Eth_Year"] == row["Eth_Year"]) & (monthly_overhead["Eth_Month"] == row["Eth_Month"])
                        ] if not monthly_overhead.empty else pd.DataFrame()

                        if not this_month_oh.empty:
                            month_consumable = float(this_month_oh["Monthly_Consumable_Cost"].values[0])
                            month_produced = float(this_month_oh["Monthly_Qty_Produced"].values[0])
                            month_oh_per_sofa = float(this_month_oh["Overhead_Per_Unit"].values[0])
                        else:
                            month_consumable, month_produced, month_oh_per_sofa = 0.0, 0.0, 0.0

                        st.markdown(f"""
                        <div class="info-box">
                        <b>How Workshop Overhead was calculated for this month:</b><br>
                        Total Month Workshop Consumables ÷ Total Month Production = Overhead per Bed<br>
                        <b>ETB {month_consumable:,.2f}</b> ÷ <b>{month_produced:,.0f} beds</b> = <b>ETB {month_oh_per_sofa:,.2f} per bed</b>
                        </div>
                        """, unsafe_allow_html=True)

                        with st.expander("🔍 View Breakdown of Workshop Consumables"):
                            if not df_workshop.empty:
                                df_ws_month = df_workshop[
                                    (df_workshop["Eth_Year"] == row["Eth_Year"]) & (df_workshop["Eth_Month"] == row["Eth_Month"])
                                ].copy()
                                if not df_ws_month.empty:
                                    if not df_mat.empty:
                                        df_ws_month = df_ws_month.merge(
                                            df_mat[["Material_ID", "Material_Name"]].drop_duplicates(subset=["Material_ID"]),
                                            on="Material_ID",
                                            how="left"
                                        )
                                    else:
                                        df_ws_month["Material_Name"] = df_ws_month["Material_ID"]
                                    st.dataframe(df_ws_month[["Material_ID", "Material_Name", "Qty", "Cost"]], use_container_width=True, hide_index=True)
                                else:
                                    st.write("No workshop consumables for this month.")
                            else:
                                st.write("No workshop consumables recorded.")

                        margin_pct = safe_div(row["Gross_Profit"] * 100.0, row["Total_Sale_Price"], 0.0)
                        st.write("**Profit & Loss Summary:**")
                        st.markdown(f"""
| Line Item | Amount (ETB) |
|---|---:|
| **Revenue** | **{row['Total_Sale_Price']:,.2f}** |
| Less: Direct Materials (FIFO) | ({direct_cogs:,.2f}) |
| Less: Allocated Workshop Overhead | ({absorbed_overhead_cogs:,.2f}) |
| **Total Cost of Goods Sold** | **({direct_cogs + absorbed_overhead_cogs:,.2f})** |
| **Gross Profit** | **{row['Gross_Profit']:,.2f}** |
| **Gross Margin** | **{margin_pct:.2f}%** |
""")

                        model_summary = (
                            df_m_calc.groupby("Model_Name")
                            .agg(Qty_Sold=("Qty_Sold", "sum"), Revenue=("Total_Sale_Price", "sum"), COGS=("COGS", "sum"), Profit=("Gross_Profit", "sum"))
                            .reset_index()
                        )
                        model_summary["Margin %"] = model_summary.apply(
                            lambda r: safe_div(r["Profit"] * 100.0, r["Revenue"], 0.0), axis=1
                        )
                        st.dataframe(model_summary[["Model_Name", "Qty_Sold", "Revenue", "COGS", "Profit", "Margin %"]], use_container_width=True, hide_index=True)

                        df_m_calc["Date (EC)"] = df_m_calc["Date"].apply(to_ethiopian)
                        st.dataframe(
                            df_m_calc[[
                                "Date (EC)", "Client_Name", "Model_Name", "Qty_Sold",
                                "Total_Sale_Price", "Direct_Unit_Cost", "Overhead_Unit_Cost", "COGS", "Gross_Profit"
                            ]],
                            use_container_width=True,
                            hide_index=True
                        )

                        model_df_for_pdf = pd.DataFrame({
                            "Model": model_summary["Model_Name"],
                            "Qty": model_summary["Qty_Sold"].apply(lambda x: f"{x:,.0f}"),
                            "Revenue (ETB)": model_summary["Revenue"].apply(lambda x: f"{x:,.2f}"),
                            "COGS (ETB)": model_summary["COGS"].apply(lambda x: f"{x:,.2f}"),
                            "Profit (ETB)": model_summary["Profit"].apply(lambda x: f"{x:,.2f}"),
                            "Margin": model_summary["Margin %"].apply(lambda x: f"{x:.1f}%")
                        })
                        trans_df_for_pdf = pd.DataFrame({
                            "Date (EC)": df_m_calc["Date (EC)"],
                            "Client": df_m_calc["Client_Name"],
                            "Model": df_m_calc["Model_Name"],
                            "Qty": df_m_calc["Qty_Sold"].apply(lambda x: f"{x:,.0f}"),
                            "Revenue": df_m_calc["Total_Sale_Price"].apply(lambda x: f"{x:,.2f}"),
                            "COGS": df_m_calc["COGS"].apply(lambda x: f"{x:,.2f}"),
                            "Profit": df_m_calc["Gross_Profit"].apply(lambda x: f"{x:,.2f}")
                        })

                        income_pdf_bytes = generate_income_statement_pdf(
                            m_name, int(row["Eth_Year"]), row["Total_Sale_Price"],
                            direct_cogs, absorbed_overhead_cogs, direct_cogs + absorbed_overhead_cogs,
                            row["Gross_Profit"], model_df_for_pdf, trans_df_for_pdf
                        )
                        st.download_button(
                            "📥 Download Income Statement PDF",
                            data=income_pdf_bytes,
                            file_name=f"Income_Statement_{m_name}_{int(row['Eth_Year'])}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key=f"dl_income_{m_name}_{int(row['Eth_Year'])}"
                        )
            else:
                st.info("No sales data in this range.")

    # --- TAB: INVENTORY ---
    if "inv" in tab_map:
        with tab_map["inv"]:
            t1, t2 = st.tabs(["Raw Materials", "Finished Goods"])
            with t1:
                if current_stock:
                    mat_lookup = dict(zip(df_mat["Material_ID"], df_mat["Material_Name"])) if not df_mat.empty else {}
                    raw_data = [
                        {
                            "Material_ID": k,
                            "Material_Name": mat_lookup.get(k, k),
                            "Qty_In_Stock": 0.0 if pd.isna(v) else float(v)
                        }
                        for k, v in current_stock.items()
                    ]
                    df_raw = pd.DataFrame(raw_data).sort_values(by="Material_Name")
                    st.dataframe(
                        df_raw.style.format({"Qty_In_Stock": "{:,.0f}"}).map(color_negative_red, subset=["Qty_In_Stock"]),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No raw material stock records found.")
            with t2:
                if not df_prod.empty:
                    prod = df_prod.groupby("Model_Name")["Qty_Produced"].sum().reset_index()
                    sold = df_sales.groupby("Model_Name")["Qty_Sold"].sum().reset_index() if (not df_sales.empty and "Model_Name" in df_sales.columns) else pd.DataFrame(columns=["Model_Name", "Qty_Sold"])
                    inv = prod.merge(sold, on="Model_Name", how="left").fillna(0)
                    inv["Remaining_Qty"] = inv["Qty_Produced"] - inv["Qty_Sold"]
                    st.dataframe(inv[["Model_Name", "Qty_Produced", "Qty_Sold", "Remaining_Qty"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No finished goods production records found.")

    # --- TAB: SUPPLIERS ---
    if "sup" in tab_map:
        with tab_map["sup"]:
            if supplier_balances:
                df_sup_bal = pd.DataFrame(list(supplier_balances.items()), columns=["Supplier_ID", "Balance"])
                df_sup_bal = df_sup_bal[df_sup_bal["Balance"] > 0]
                if not df_sup_bal.empty:
                    sup_name_dict = {}
                    if not df_sup.empty:
                        for _, row in df_sup.iterrows():
                            s_id = str(row.get("Supplier_ID", "")).strip().upper()
                            s_name = str(row.get("Supplier_Name", "")).strip()
                            if s_id and s_name:
                                sup_name_dict[s_id] = s_name

                    df_sup_bal["Supplier_Name"] = df_sup_bal["Supplier_ID"].apply(lambda x: sup_name_dict.get(str(x).strip().upper(), str(x)))
                    st.dataframe(df_sup_bal[["Supplier_Name", "Balance"]].style.format({"Balance": "ETB {:,.2f}"}), use_container_width=True, hide_index=True)
                else:
                    st.success("All supplier balances are settled!")
            else:
                st.info("No supplier balance records found.")

    # --- TAB: STOCK AUDIT ---
    if "stock_audit" in tab_map:
        with tab_map["stock_audit"]:
            if audit_month_opts:
                selected_month = st.selectbox("Select Month to Audit:", audit_month_opts, format_func=lambda x: x[2])
                sel_y, sel_m, sel_label = selected_month

                hist_layers = []
                if not df_op_stock.empty:
                    for _, r in df_op_stock.iterrows():
                        hist_layers.append({"Date": r["Date"], "Material_ID": r["Material_ID"], "Qty": float(r["Qty"]), "Unit_Cost": float(r["Unit_Cost"])})
                if not df_pur.empty:
                    for _, r in df_pur.iterrows():
                        hist_layers.append({"Date": r["Date"], "Material_ID": r["Material_ID"], "Qty": float(r["Qty"]), "Unit_Cost": float(r["Unit_Cost"])})

                df_hist = pd.DataFrame(hist_layers).sort_values("Date") if hist_layers else pd.DataFrame(columns=["Date", "Material_ID", "Qty", "Unit_Cost"])
                if not df_hist.empty:
                    df_hist["Qty"] = df_hist["Qty"].astype(float)
                    df_hist["Unit_Cost"] = df_hist["Unit_Cost"].astype(float)

                start_of_month = get_greg_date(sel_y, sel_m, 1)
                end_of_month = get_greg_date(sel_y + (1 if sel_m == 13 else 0), 1 if sel_m == 13 else sel_m + 1, 1) - datetime.timedelta(days=1)

                pre_pur = df_pur[df_pur["Date"] < start_of_month] if not df_pur.empty else pd.DataFrame()
                cur_pur = df_pur[(df_pur["Date"] >= start_of_month) & (df_pur["Date"] <= end_of_month)] if not df_pur.empty else pd.DataFrame()
                pre_iss = df_issues_all[df_issues_all["Date"] < start_of_month] if all_issues else pd.DataFrame()
                cur_iss = df_issues_all[(df_issues_all["Date"] >= start_of_month) & (df_issues_all["Date"] <= end_of_month)] if all_issues else pd.DataFrame()

                all_mats = df_mat["Material_ID"].dropna().unique().tolist() if not df_mat.empty else []
                per_mat_data = []
                tot_op, tot_in, tot_out, tot_clo = 0.0, 0.0, 0.0, 0.0

                op_stock_val = (df_op_stock["Qty"] * df_op_stock["Unit_Cost"]).sum() if not df_op_stock.empty else 0.0
                hist_pur_val = (pre_pur["Qty"] * pre_pur["Unit_Cost"]).sum() if not pre_pur.empty else 0.0
                hist_out_val = pre_iss["Cost"].sum() if not pre_iss.empty else 0.0
                tot_op_val = op_stock_val + hist_pur_val - hist_out_val
                tot_in_val = (cur_pur["Qty"] * cur_pur["Unit_Cost"]).sum() if not cur_pur.empty else 0.0
                tot_out_val = cur_iss["Cost"].sum() if not cur_iss.empty else 0.0
                tot_clo_val = tot_op_val + tot_in_val - tot_out_val

                for m_id in all_mats:
                    mat_rows_match = df_mat[df_mat["Material_ID"] == m_id]
                    m_name = mat_rows_match["Material_Name"].values[0] if not mat_rows_match.empty else m_id

                    h_in = pre_pur[pre_pur["Material_ID"] == m_id]["Qty"].sum() if not pre_pur.empty else 0.0
                    h_out = pre_iss[pre_iss["Material_ID"] == m_id]["Qty"].sum() if not pre_iss.empty else 0.0
                    op_st = df_op_stock[df_op_stock["Material_ID"] == m_id]["Qty"].sum() if not df_op_stock.empty else 0.0
                    open_qty = h_in - h_out + op_st
                    in_qty = cur_pur[cur_pur["Material_ID"] == m_id]["Qty"].sum() if not cur_pur.empty else 0.0
                    out_qty = cur_iss[cur_iss["Material_ID"] == m_id]["Qty"].sum() if not cur_iss.empty else 0.0
                    close_qty = open_qty + in_qty - out_qty
                    if open_qty == 0 and in_qty == 0 and out_qty == 0:
                        continue

                    m_layers = df_hist[(df_hist["Material_ID"] == m_id) & (df_hist["Date"] <= end_of_month)].copy()
                    c_qty_needed = h_out + out_qty
                    for idx, _ in m_layers.iterrows():
                        avail = float(m_layers.at[idx, "Qty"])
                        if c_qty_needed > 0 and avail > 0:
                            take = min(avail, c_qty_needed)
                            m_layers.at[idx, "Qty"] = avail - take
                            c_qty_needed -= take
                    close_val = float((m_layers["Qty"] * m_layers["Unit_Cost"]).sum()) if not m_layers.empty else 0.0
                    if close_val < 0:
                        close_val = 0.0
                    per_mat_data.append({
                        "Material_ID": m_id, "Material_Name": m_name,
                        "Open_Qty": open_qty, "In_Qty": in_qty, "Out_Qty": out_qty,
                        "Close_Qty": close_qty, "Close_Val": close_val
                    })
                    tot_op += open_qty
                    tot_in += in_qty
                    tot_out += out_qty
                    tot_clo += close_qty

                df_per_mat = pd.DataFrame(per_mat_data).sort_values(by="Material_Name") if per_mat_data else pd.DataFrame()

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Opening Stock", f"{tot_op:,.0f} units", f"ETB {tot_op_val:,.2f}")
                c2.metric("Stock In", f"+{tot_in:,.0f} units", f"ETB {tot_in_val:,.2f}")
                c3.metric("Stock Out", f"-{tot_out:,.0f} units", f"ETB {tot_out_val:,.2f}")
                c4.metric("Closing Stock", f"{tot_clo:,.0f} units", f"ETB {tot_clo_val:,.2f}")

                if not df_per_mat.empty:
                    st.write("**Per-Material Reconciliation Table:**")
                    st.dataframe(
                        df_per_mat[["Material_Name", "Open_Qty", "In_Qty", "Out_Qty", "Close_Qty", "Close_Val"]]
                        .style.format({
                            "Open_Qty": "{:,.0f}", "In_Qty": "{:,.0f}",
                            "Out_Qty": "{:,.0f}", "Close_Qty": "{:,.0f}",
                            "Close_Val": "ETB {:,.2f}"
                        })
                        .map(color_negative_red, subset=["Close_Qty"]),
                        use_container_width=True,
                        hide_index=True
                    )

                    col_sig1, col_sig2 = st.columns(2)
                    sig_sk = col_sig1.text_input("Prepared By (Stock Keeper Name):", "_________________")
                    sig_mgr = col_sig2.text_input("Audited By (Manager Name):", "_________________")

                    pdf_bytes = generate_stock_audit_pdf(
                        sel_label, tot_op, tot_op_val, tot_in, tot_in_val,
                        tot_out, tot_out_val, tot_clo, tot_clo_val, df_per_mat, sig_sk, sig_mgr
                    )
                    st.download_button(
                        "📥 Download Detailed Stock Audit (PDF)",
                        data=pdf_bytes,
                        file_name=f"Bed_Solution_Stock_Audit_{sel_label.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                else:
                    st.info("No movements this month.")
            else:
                st.info("No data available.")

    # --- TAB: SUPPLIER AUDIT ---
    if "sup_audit" in tab_map:
        with tab_map["sup_audit"]:
            if audit_month_opts:
                selected_month_sup = st.selectbox("Select Month to Audit Suppliers:", audit_month_opts, format_func=lambda x: x[2], key="sup_audit")
                sel_y_s, sel_m_s, sel_label_s = selected_month_sup

                op_bal_global = float(df_op_pay["Amount_Owed"].sum()) if not df_op_pay.empty else 0.0
                start_of_month = get_greg_date(sel_y_s, sel_m_s, 1)

                for y, m, _ in reversed(audit_month_opts):
                    if y == sel_y_s and m == sel_m_s:
                        break
                    m_cr = df_pur[(df_pur["Eth_Year"] == y) & (df_pur["Eth_Month"] == m)]["Credit_Value"].sum() if not df_pur.empty else 0.0
                    m_pay = df_pay[(df_pay["Eth_Year"] == y) & (df_pay["Eth_Month"] == m)]["Amount"].sum() if not df_pay.empty else 0.0
                    op_bal_global += float(m_cr) - float(m_pay)

                cur_cr = df_pur[(df_pur["Eth_Year"] == sel_y_s) & (df_pur["Eth_Month"] == sel_m_s) & (df_pur["Credit_Value"] > 0)] if not df_pur.empty else pd.DataFrame()
                cur_pay = df_pay[(df_pay["Eth_Year"] == sel_y_s) & (df_pay["Eth_Month"] == sel_m_s)] if not df_pay.empty else pd.DataFrame()

                cr_val_global = float(cur_cr["Credit_Value"].sum()) if not cur_cr.empty else 0.0
                pay_val_global = float(cur_pay["Amount"].sum()) if not cur_pay.empty else 0.0
                clo_bal_global = op_bal_global + cr_val_global - pay_val_global

                sup_sum_data = []
                all_sup_ids = set(
                    (df_op_pay["Supplier_ID"].dropna().unique().tolist() if not df_op_pay.empty else []) +
                    (df_pur["Supplier_ID"].dropna().unique().tolist() if not df_pur.empty else []) +
                    (df_pay["Supplier_ID"].dropna().unique().tolist() if not df_pay.empty else [])
                )
                for s_id in all_sup_ids:
                    if not s_id:
                        continue
                    s_match = df_sup[df_sup["Supplier_ID"] == s_id] if not df_sup.empty else pd.DataFrame()
                    s_name = s_match["Supplier_Name"].values[0] if not s_match.empty else s_id
                    s_op = float(df_op_pay[df_op_pay["Supplier_ID"] == s_id]["Amount_Owed"].sum()) if not df_op_pay.empty else 0.0
                    h_cr = float(df_pur[(df_pur["Supplier_ID"] == s_id) & (df_pur["Date"] < start_of_month)]["Credit_Value"].sum()) if not df_pur.empty else 0.0
                    h_pay = float(df_pay[(df_pay["Supplier_ID"] == s_id) & (df_pay["Date"] < start_of_month)]["Amount"].sum()) if not df_pay.empty else 0.0
                    s_opening = s_op + h_cr - h_pay
                    s_cr = float(cur_cr[cur_cr["Supplier_ID"] == s_id]["Credit_Value"].sum()) if not cur_cr.empty else 0.0
                    s_pay = float(cur_pay[cur_pay["Supplier_ID"] == s_id]["Amount"].sum()) if not cur_pay.empty else 0.0
                    s_closing = s_opening + s_cr - s_pay
                    if s_opening == 0 and s_cr == 0 and s_pay == 0:
                        continue
                    sup_sum_data.append({
                        "Supplier_ID": s_id, "Supplier_Name": s_name,
                        "Opening_Bal": s_opening, "New_Credit": s_cr,
                        "Payments": s_pay, "Closing_Bal": s_closing
                    })

                df_sup_sum = pd.DataFrame(sup_sum_data).sort_values(by="Supplier_Name") if sup_sum_data else pd.DataFrame(columns=[
                    "Supplier_ID", "Supplier_Name", "Opening_Bal", "New_Credit", "Payments", "Closing_Bal"
                ])

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Opening Payable", f"ETB {op_bal_global:,.2f}")
                c2.metric("New Credit", f"ETB {cr_val_global:,.2f}")
                c3.metric("Payments", f"ETB {pay_val_global:,.2f}")
                c4.metric("Closing Payable", f"ETB {clo_bal_global:,.2f}")

                if not df_sup_sum.empty:
                    st.write("**Per-Supplier Summary:**")
                    st.dataframe(
                        df_sup_sum[["Supplier_Name", "Opening_Bal", "New_Credit", "Payments", "Closing_Bal"]].style.format({
                            "Opening_Bal": "ETB {:,.2f}", "New_Credit": "ETB {:,.2f}",
                            "Payments": "ETB {:,.2f}", "Closing_Bal": "ETB {:,.2f}"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

                details_sup = []
                if not cur_cr.empty:
                    for _, r in cur_cr.iterrows():
                        s_match = df_sup[df_sup["Supplier_ID"] == r["Supplier_ID"]] if not df_sup.empty else pd.DataFrame()
                        s_name = s_match["Supplier_Name"].values[0] if not s_match.empty else r["Supplier_ID"]
                        details_sup.append({"Date": r["Date"], "Type": "Credit Purchase (+)", "Supplier_Name": s_name, "Amount": r["Credit_Value"]})
                if not cur_pay.empty:
                    for _, r in cur_pay.iterrows():
                        s_match = df_sup[df_sup["Supplier_ID"] == r["Supplier_ID"]] if not df_sup.empty else pd.DataFrame()
                        s_name = s_match["Supplier_Name"].values[0] if not s_match.empty else r["Supplier_ID"]
                        details_sup.append({"Date": r["Date"], "Type": "Payment Made (-)", "Supplier_Name": s_name, "Amount": r["Amount"]})

                df_details_sup = pd.DataFrame(details_sup).sort_values(by="Date") if details_sup else pd.DataFrame(columns=["Date", "Type", "Supplier_Name", "Amount"])
                if not df_details_sup.empty:
                    df_details_sup["Date (EC)"] = df_details_sup["Date"].apply(to_ethiopian)
                    st.write("**Detailed Movements:**")
                    st.dataframe(
                        df_details_sup[["Date (EC)", "Type", "Supplier_Name", "Amount"]].style.format({"Amount": "ETB {:,.2f}"}),
                        use_container_width=True,
                        hide_index=True
                    )

                col_sig1_sup, col_sig2_sup = st.columns(2)
                sig_acc = col_sig1_sup.text_input("Prepared By (Accountant):", "_________________")
                sig_mgr_sup = col_sig2_sup.text_input("Audited By (Manager):", "_________________")

                pdf_bytes_sup = generate_supplier_audit_pdf(
                    sel_label_s, op_bal_global, cr_val_global, pay_val_global,
                    clo_bal_global, df_sup_sum, df_details_sup, sig_acc, sig_mgr_sup
                )
                st.download_button(
                    "📥 Download Detailed Supplier Audit (PDF)",
                    data=pdf_bytes_sup,
                    file_name=f"Bed_Solution_Supplier_Audit_{sel_label_s.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.info("No data available.")

    # =====================================================================
    # TAB: PURCHASE REQUEST
    # =====================================================================
    if "request" in tab_map:
        with tab_map["request"]:
            st.subheader("📝 Create Professional Purchase Request")
            st.caption(f"👤 Signed in as **{user_name}** — this request will carry your name.")
            st.write("Generate purchase requests for materials that are low in stock or needed for upcoming production.")

            try:
                _req_ws_view = _ensure_sheet("Purchase_Requests", _REQ_HDRS)
                _req_data = _get_all_records_robust(_req_ws_view)
                my_reqs = [r for r in _req_data if str(r.get("Submitted_By", "")).strip() == user_name]
                if my_reqs:
                    st.markdown("### 📋 My Sent Requests")
                    df_my_reqs = pd.DataFrame(my_reqs)
                    st.dataframe(df_my_reqs[["Request_ID", "Submitted_Date", "Material_Name", "Requested_Qty", "Status"]], use_container_width=True, hide_index=True)
                    st.divider()
            except Exception:
                pass

            if "pr_cart" not in st.session_state:
                st.session_state.pr_cart = []

            unit_cost_lookup = {}
            if not df_layers.empty:
                for _, _r in df_layers.iterrows():
                    _mid = _r["Material_ID"]
                    _uc = float(_r["Unit_Cost"]) if pd.notna(_r["Unit_Cost"]) else 0.0
                    if _uc > 0:
                        unit_cost_lookup[_mid] = _uc

            st.write("**🔍 Auto-Suggested Items (Below Reorder Level)**")
            if not df_mat.empty and current_stock:
                suggested = []
                for _, row in df_mat.iterrows():
                    m_id = row["Material_ID"]
                    min_lvl = float(row.get("Reorder_Level", 0) or 0)
                    qty = float(current_stock.get(m_id, 0) or 0)
                    if min_lvl > 0 and qty <= min_lvl:
                        suggest_qty = max(1.0, (min_lvl * 2.0) - qty)
                        est_cost = unit_cost_lookup.get(m_id, 0.0)
                        suggested.append({
                            "Material_ID": m_id, "Material_Name": row["Material_Name"],
                            "Current_Stock": qty, "Suggested_Qty": suggest_qty, "Unit_Cost": est_cost
                        })
                if suggested:
                    st.dataframe(pd.DataFrame(suggested), use_container_width=True, hide_index=True)
                else:
                    st.success("All materials are sufficiently stocked! No auto-suggestions.")
            else:
                st.info("No material or stock data available.")

            st.divider()
            st.write("**➕ Bulk Add Items to Request**")
            search_mat = st.text_input("🔍 Filter materials by name (type to search):", "")

            df_mat_filtered = df_mat.copy()
            if search_mat and not df_mat_filtered.empty:
                df_mat_filtered = df_mat_filtered[df_mat_filtered["Material_Name"].str.contains(search_mat, case=False, na=False)]

            if not df_mat_filtered.empty:
                df_bulk = pd.DataFrame({
                    "Material": df_mat_filtered["Material_Name"].values,
                    "Current Stock": df_mat_filtered["Material_ID"].apply(lambda x: current_stock.get(x, 0)).values,
                    "Select": [False] * len(df_mat_filtered),
                    "Qty to Request": [1] * len(df_mat_filtered)
                })

                edited_bulk = st.data_editor(
                    df_bulk,
                    column_config={
                        "Select": st.column_config.CheckboxColumn("Select", default=False),
                        "Material": st.column_config.TextColumn("Material", disabled=True, width="large"),
                        "Current Stock": st.column_config.NumberColumn("Stock", disabled=True, format="%.0f"),
                        "Qty to Request": st.column_config.NumberColumn("Request Qty", min_value=1, step=1, default=1),
                    },
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key="bed_bulk_editor"
                )

                if st.button("➕ Add Selected to Cart", type="primary"):
                    added_count = 0
                    for idx, row in edited_bulk.iterrows():
                        if row["Select"]:
                            m_id = df_mat_filtered.iloc[idx]["Material_ID"]
                            m_name = row["Material"]
                            qty = int(row["Qty to Request"])
                            est_cost = float(unit_cost_lookup.get(m_id, 0.0))

                            existing = next((item for item in st.session_state.pr_cart if item["Material_ID"] == m_id), None)
                            if existing:
                                existing["Qty"] += qty
                                existing["Total_Cost"] = existing["Qty"] * existing["Unit_Cost"]
                            else:
                                st.session_state.pr_cart.append({
                                    "Material_ID": m_id,
                                    "Material_Name": m_name,
                                    "Qty": qty,
                                    "Unit_Cost": est_cost,
                                    "Total_Cost": qty * est_cost
                                })
                            added_count += 1

                    if added_count > 0:
                        st.success(f"Added {added_count} item(s) to request.")
                        st.rerun()
                    else:
                        st.warning("No items selected.")

            if st.session_state.pr_cart:
                st.write("**🛒 Current Request Cart**")
                df_cart = pd.DataFrame(st.session_state.pr_cart)
                st.dataframe(df_cart[["Material_Name", "Qty", "Unit_Cost", "Total_Cost"]], use_container_width=True, hide_index=True)

                total_pr_cost = float(df_cart["Total_Cost"].sum())
                st.metric("Total Estimated Purchase Cost", f"ETB {total_pr_cost:,.2f}")
                st.divider()

                c_form1, c_form2 = st.columns(2)
                supplier_opt = df_sup["Supplier_Name"].dropna().tolist() if not df_sup.empty else ["General Supplier"]
                selected_supplier = c_form1.selectbox("Select Supplier (Optional):", ["Unknown"] + supplier_opt)
                req_name = c_form2.text_input("Requested By (Your Name):", user_name)
                appr_name = c_form2.text_input("Manager Approval Name:", "Manager")

                _req_notes_for_pdf = st.text_area("Notes (for PDF & Purchaser):", key="pr_notes_pdf", height=80, placeholder="e.g. Urgent for Batch X...")

                if st.button("Generate Purchase Request PDF", type="primary"):
                    req_id = f"PR-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
                    date_str = datetime.datetime.now().strftime("%b %d, %Y")
                    st.session_state.pr_pdf = generate_purchase_request_pdf(
                        req_id=req_id, date_str=date_str, supplier_name=selected_supplier,
                        request_df=df_cart, total_cost=total_pr_cost, req_name=req_name,
                        appr_name=appr_name, notes=_req_notes_for_pdf
                    )

                if "pr_pdf" in st.session_state:
                    st.download_button(
                        "📥 Download Purchase Request PDF",
                        data=st.session_state["pr_pdf"],
                        file_name="Bed_Solution_Request.pdf",
                        mime="application/pdf"
                    )

                if st.button("Clear Cart"):
                    st.session_state.pr_cart = []
                    st.session_state.pop("pr_pdf", None)
                    st.rerun()

                st.divider()
                with st.form("send_req_form_bed"):
                    req_sup_pref = st.text_input("Preferred supplier (optional):", "")
                    req_notes_txt = st.session_state.get("pr_notes_pdf", "")
                    send_it = st.form_submit_button("📤 Submit Request to Purchaser", type="primary")

                if send_it:
                    try:
                        _req_ws = _ensure_sheet("Purchase_Requests", _REQ_HDRS)
                        _rid = f"REQ-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                        _rows = []
                        for _, _r in df_cart.iterrows():
                            _rows.append([
                                _rid, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                user_name, req_sup_pref, extract_id(_r["Material_ID"]), _r["Material_Name"],
                                float(_r["Qty"]), float(_r["Unit_Cost"]), "Pending", req_notes_txt
                            ])
                        _req_ws.append_rows(_rows, value_input_option="USER_ENTERED")
                        st.success(f"✅ Request {_rid} sent to Purchaser ({len(_rows)} items).")
                        st.session_state.pr_cart = []
                        st.session_state.pop("pr_pdf", None)
                        load_data.clear()
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Submit failed: {_e}")
            else:
                st.info("Cart is empty. Add items above to create a request.")

    # =====================================================================
    # TAB: PURCHASER & APPROVER
    # =====================================================================
    if "purch" in tab_map:
        with tab_map["purch"]:
            REP_SHEET = "Purchase_Reports"
            REQ_SHEET = "Purchase_Requests"
            REP_HEADERS = [
                "Report_ID", "Submitted_Date", "Supplier_ID", "Supplier_Name",
                "Payment_Type", "Material_ID", "Material_Name",
                "Qty", "Unit_Cost", "Total", "Status", "Approver", "Approved_Date", "Notes"
            ]

            if role == "purchaser":
                mode = "purch"
            elif role == "approver":
                mode = "appr"
            else:
                _sel = st.radio("Select mode:", ["🛒 Purchaser", "✅ Approver"], horizontal=True, key="bed_t9_mode")
                mode = "purch" if _sel.startswith("🛒") else "appr"

            if mode == "purch":
                st.subheader("📱 Purchaser Mobile Hub")
                st.caption(f"Logged in as **{user_name}**. Process requests item-by-item below.")

                if "purch_flash" in st.session_state:
                    st.success(st.session_state.pop("purch_flash"))

                def _safe_float(v):
                    try:
                        return float(str(v).replace(",", "").strip() or 0)
                    except Exception:
                        return 0.0

                @st.cache_data(ttl=60, show_spinner=False)
                def get_purchaser_data(req_sheet_name, rep_sheet_name):
                    try:
                        sh = _get_sheets_global()
                        req_ws = sh.worksheet(req_sheet_name)
                        rep_ws = sh.worksheet(rep_sheet_name)
                        return _get_all_records_robust(req_ws), _get_all_records_robust(rep_ws)
                    except Exception as e:
                        return str(e), []

                req_data_raw, rep_data_raw = get_purchaser_data(REQ_SHEET, REP_SHEET)

                if isinstance(req_data_raw, str):
                    if "429" in req_data_raw or "Quota exceeded" in req_data_raw:
                        st.warning("⚠️ Google API limit reached. Please wait 1 minute and click 'Refresh Data'.")
                    else:
                        st.error(f"Could not load requests: {req_data_raw}")
                    all_req, all_reps, _submitted_pairs = [], [], set()
                else:
                    all_req = req_data_raw
                    all_reps = rep_data_raw
                    _submitted_pairs = set()
                    for rep in all_reps:
                        note = str(rep.get("Notes", ""))
                        if note.startswith("From "):
                            req_id_part = note.split(" | ")[0].replace("From ", "").strip()
                            mat_id = extract_id(rep.get("Material_ID", ""))
                            _submitted_pairs.add((req_id_part, mat_id))

                pend_reqs = [
                    r for r in all_req
                    if str(r.get("Status", "")).strip().lower() == "pending"
                    and (r.get("Request_ID", ""), extract_id(r.get("Material_ID", ""))) not in _submitted_pairs
                ]

                if not pend_reqs:
                    st.info("📭 No pending requests from the Maker right now.")
                else:
                    from collections import defaultdict
                    _grp = defaultdict(list)
                    for r in pend_reqs:
                        _grp[r.get("Request_ID", "")].append(r)

                    st.markdown(f"### 📋 Pending Requests ({len(_grp)})")
                    sel_req = st.selectbox(
                        "Select Request ID:",
                        sorted(_grp.keys(), reverse=True),
                        format_func=lambda x: f"{x} ({len(_grp[x])} items)",
                        key="sel_req_bed_mob"
                    )

                    if sel_req:
                        _items = _grp[sel_req]
                        sup_names_all = df_sup["Supplier_Name"].dropna().tolist() if not df_sup.empty else []
                        sup_options_dropdown = ["(Unknown / Other - Type Below)"] + sup_names_all

                        with st.form(f"submit_req_mobile_{sel_req}"):
                            st.markdown("💡 *Review items below. Uncheck to **drop**, update actual counts, and select individual payment methods.*")
                            _purch_notes = st.text_input("General notes for this submission:", key=f"pn_mob_{sel_req}")
                            st.divider()

                            _inputs = {}
                            for _idx, it in enumerate(_items):
                                m_name = it.get("Material_Name", "")
                                req_qty = _safe_float(it.get("Requested_Qty", 0))
                                est_c = _safe_float(it.get("Est_Unit_Cost", 0))

                                st.markdown(f"""
                                <div class="purchaser-card">
                                    <b>📦 {m_name}</b><br>
                                    <span style="font-size:12px; color:#aaa;">Requested Qty: {req_qty:,.0f} | Est. Cost: ETB {est_c:,.2f}</span>
                                </div>
                                """, unsafe_allow_html=True)

                                keep_item = st.checkbox(f"Include '{m_name}'", value=True, key=f"keep_mob_{sel_req}_{_idx}")
                                c1, c2 = st.columns(2)
                                _aq = c1.number_input("Actual Qty", min_value=0.0, value=req_qty, step=1.0, key=f"aq_mob_{sel_req}_{_idx}")
                                _ac = c2.number_input("Unit Cost", min_value=0.0, value=est_c, step=1.0, key=f"ac_mob_{sel_req}_{_idx}")

                                c3, c4 = st.columns(2)
                                _pay_method = c3.selectbox("Payment Method", ["Cash", "Credit"], key=f"pay_mob_{sel_req}_{_idx}")
                                _sup = c4.selectbox("Supplier", sup_options_dropdown, key=f"sup_mob_{sel_req}_{_idx}")

                                _custom_sup = ""
                                if _sup == "(Unknown / Other - Type Below)":
                                    _custom_sup = st.text_input(f"Type Custom Supplier Name for '{m_name}':", key=f"csup_mob_{sel_req}_{_idx}")

                                st.markdown("---")
                                _inputs[_idx] = {
                                    "keep": keep_item, "aq": _aq, "ac": _ac,
                                    "pay": _pay_method, "sup": _sup, "custom_sup": _custom_sup, "orig": it
                                }

                            submit_now = st.form_submit_button("🚀 Submit Purchase Report", type="primary", use_container_width=True)

                        if submit_now:
                            try:
                                _rep_ws = _ensure_sheet(REP_SHEET, REP_HEADERS)
                                _name2id = {}
                                if not df_sup.empty:
                                    for _, s_row in df_sup.iterrows():
                                        if pd.notna(s_row.get("Supplier_Name")):
                                            _name2id[str(s_row["Supplier_Name"]).strip().lower()] = s_row.get("Supplier_ID", "")

                                _batch = f"RPT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                                _rows = []

                                for _idx, _data in _inputs.items():
                                    if not _data["keep"]:
                                        continue
                                    _sname = str(_data["sup"]).strip()
                                    if _sname == "(Unknown / Other - Type Below)":
                                        _sname = str(_data["custom_sup"]).strip() or "Unknown Supplier"
                                    _sid = _name2id.get(_sname.lower(), "")
                                    _aq = float(_data["aq"])
                                    _ac = float(_data["ac"])
                                    if _aq <= 0:
                                        continue
                                    _orig = _data["orig"]
                                    _rows.append([
                                        f"{_batch}-{len(_rows) + 1:03d}",
                                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        _sid, _sname, _data["pay"],
                                        extract_id(_orig.get("Material_ID", "")),
                                        _orig.get("Material_Name", ""),
                                        float(_aq), float(_ac), float(_aq * _ac),
                                        "Pending", "", "",
                                        f"From {sel_req} | {_purch_notes} | By {user_name}"
                                    ])

                                if not _rows:
                                    st.error("Nothing to submit — please include at least one item with Qty > 0.")
                                else:
                                    _rep_ws.append_rows(_rows, value_input_option="USER_ENTERED")
                                    st.session_state.purch_flash = f"✅ Submitted {len(_rows)} item(s) for approval."
                                    get_purchaser_data.clear()
                                    load_data.clear()
                                    st.rerun()
                            except Exception as e:
                                if "429" in str(e):
                                    st.error("⚠️ Google API limit reached. Please wait 1 minute and try submitting again.")
                                else:
                                    st.error(f"Submit failed: {e}")

                st.divider()
                st.subheader("📥 Download PDF Report")
                my_reps = [r for r in all_reps if user_name in str(r.get("Notes", ""))]
                if my_reps:
                    from collections import defaultdict
                    rep_groups = defaultdict(list)
                    for r in my_reps:
                        rep_groups[str(r.get("Report_ID", ""))[:19]].append(r)

                    sel_rep_id = st.selectbox("Select Report ID to Download:", sorted(rep_groups.keys(), reverse=True))
                    if sel_rep_id:
                        df_rep_sel = pd.DataFrame(rep_groups[sel_rep_id])
                        st.dataframe(df_rep_sel[["Supplier_Name", "Material_Name", "Qty", "Unit_Cost", "Payment_Type", "Total"]], use_container_width=True, hide_index=True)

                        rep_pdf_bytes = generate_purchase_report_pdf(sel_rep_id, df_rep_sel, user_name, notes=df_rep_sel.iloc[0].get("Notes", ""))
                        st.download_button(
                            "📥 Download PDF Report",
                            data=rep_pdf_bytes,
                            file_name=f"Bed_Solution_Purchase_Report_{sel_rep_id}.pdf",
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True
                        )
                else:
                    st.info("No purchase reports found under your name yet.")

            else:
                st.subheader("✅ Approver — Review & Post")
                if "appr_flash" in st.session_state:
                    st.success(st.session_state.pop("appr_flash"))

                approver = st.text_input("Approver name:", value=user_name, key="appr_name_bed")

                try:
                    rep_ws = _ensure_sheet(REP_SHEET, REP_HEADERS)
                    recs = _get_all_records_robust(rep_ws)
                except Exception as e:
                    if "429" in str(e):
                        st.warning("⚠️ Google API limit reached. Please wait 1 minute and click 'Refresh Data'.")
                    else:
                        st.error(f"Could not load reports: {e}")
                    recs = []

                pend = [r for r in recs if str(r.get("Status", "")).strip().lower() == "pending"]

                if not pend:
                    st.info("No pending reports. When the Purchaser submits, they'll appear here.")
                else:
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for r in pend:
                        groups[str(r.get("Report_ID", ""))[:19]].append(r)

                    st.markdown(f"### Pending ({len(pend)} items in {len(groups)} batch(es))")

                    for batch_id, items in groups.items():
                        with st.expander(f"📦 Batch {batch_id} — {len(items)} item(s)", expanded=True):
                            df_b = pd.DataFrame(items)
                            st.dataframe(df_b[["Supplier_Name", "Material_Name", "Qty", "Unit_Cost", "Payment_Type", "Total"]], use_container_width=True, hide_index=True)
                            _ = st.text_input("Approver notes (optional):", key=f"notes_bed_{batch_id}")
                            ac1, ac2 = st.columns(2)

                            if ac1.button("✅ Approve", key=f"ok_bed_{batch_id}", type="primary", use_container_width=True):
                                try:
                                    pur_ws = _ensure_sheet("Purchases", ["Date", "Supplier_ID", "Material_ID", "Qty", "Unit_Cost", "Payment_Type"])
                                    pur_rows = []
                                    for it in items:
                                        pur_rows.append([
                                            datetime.datetime.now().strftime("%Y-%m-%d"),
                                            extract_id(it.get("Supplier_ID", "")),
                                            extract_id(it.get("Material_ID", "")),
                                            float(str(it.get("Qty", 0)).replace(",", "") or 0),
                                            float(str(it.get("Unit_Cost", 0)).replace(",", "") or 0),
                                            normalize_payment_type(it.get("Payment_Type", "Cash"))
                                        ])
                                    pur_ws.append_rows(pur_rows, value_input_option="USER_ENTERED")

                                    hdr = [str(h).strip() for h in rep_ws.row_values(1)]
                                    c_status, c_appr = hdr.index("Status") + 1, hdr.index("Approver") + 1
                                    target_ids = {it.get("Report_ID", "") for it in items}
                                    target_rows = _find_all_matching_rows(rep_ws, lambda rec: rec.get("Report_ID", "") in target_ids)
                                    updates = [gspread.Cell(r, c, v) for r in target_rows for c, v in [(c_status, "Approved"), (c_appr, approver)]]
                                    if updates:
                                        rep_ws.update_cells(updates)

                                    st.session_state.appr_flash = f"✅ Approved {len(items)} item(s)."
                                    load_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")

                            if ac2.button("❌ Reject", key=f"no_bed_{batch_id}", use_container_width=True):
                                try:
                                    hdr = [str(h).strip() for h in rep_ws.row_values(1)]
                                    c_status, c_appr = hdr.index("Status") + 1, hdr.index("Approver") + 1
                                    target_ids = {it.get("Report_ID", "") for it in items}
                                    target_rows = _find_all_matching_rows(rep_ws, lambda rec: rec.get("Report_ID", "") in target_ids)
                                    updates = [gspread.Cell(r, c, v) for r in target_rows for c, v in [(c_status, "Rejected"), (c_appr, approver)]]
                                    if updates:
                                        rep_ws.update_cells(updates)
                                    st.session_state.appr_flash = f"❌ Rejected {len(items)} item(s)."
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")

    # =====================================================================
    # TAB: ADVANCED ANALYTICS (MANAGER EXCLUSIVE)
    # =====================================================================
    if "analytics" in tab_map:
        with tab_map["analytics"]:
            st.subheader("📈 Operational & Financial Intelligence")
            st.caption("Unit economics, stock runway, supplier cost behavior, and tied-up capital.")

            an_tab1, an_tab2, an_tab3, an_tab4 = st.tabs([
                "🛏️ Model Economics",
                "⏳ Stock Runway",
                "🧾 Supplier & Price Intel",
                "🧊 Tied-Up Capital"
            ])

            # TAB 1: MODEL ECONOMICS
            with an_tab1:
                st.markdown("### 🛏️ Bed Model Profitability & Unit Economics")
                if not df_sales_filt.empty and "Model_Name" in df_sales_filt.columns:
                    df_econ = df_sales_filt.copy()
                    model_econ = (
                        df_econ.groupby("Model_Name")
                        .agg(Units_Sold=("Qty_Sold", "sum"), Revenue=("Total_Sale_Price", "sum"), Total_COGS=("COGS", "sum"), Gross_Profit=("Gross_Profit", "sum"))
                        .reset_index()
                    )
                    model_econ["Avg_Unit_Price"] = model_econ.apply(lambda r: safe_div(r["Revenue"], r["Units_Sold"], 0.0), axis=1)
                    model_econ["Avg_Unit_Cost"] = model_econ.apply(lambda r: safe_div(r["Total_COGS"], r["Units_Sold"], 0.0), axis=1)
                    model_econ["Profit_Per_Unit"] = model_econ["Avg_Unit_Price"] - model_econ["Avg_Unit_Cost"]
                    model_econ["Margin_%"] = model_econ.apply(lambda r: safe_div(r["Gross_Profit"] * 100.0, r["Revenue"], 0.0), axis=1)
                    model_econ = model_econ.sort_values(by="Gross_Profit", ascending=False)

                    best_model = model_econ.iloc[0]
                    worst_margin_row = model_econ.sort_values(by="Margin_%", ascending=True).iloc[0]

                    k1, k2, k3 = st.columns(3)
                    k1.metric("Top Profit Driver", str(best_model["Model_Name"]), f"ETB {best_model['Gross_Profit']:,.0f}")
                    k2.metric("Highest Unit Profit", f"ETB {model_econ['Profit_Per_Unit'].max():,.2f}", "Per bed")
                    k3.metric("Tightest Margin Model", str(worst_margin_row["Model_Name"]), f"{worst_margin_row['Margin_%']:.1f}% margin")

                    fig_econ = go.Figure()
                    fig_econ.add_trace(go.Bar(x=model_econ["Model_Name"], y=model_econ["Gross_Profit"], name="Gross Profit (ETB)", marker_color="#D4AF37"))
                    fig_econ.add_trace(go.Scatter(x=model_econ["Model_Name"], y=model_econ["Margin_%"], name="Gross Margin %", yaxis="y2", mode="lines+markers", line=dict(color="#4FC3F7", width=3)))
                    fig_econ.update_layout(
                        title="Profit Contribution vs. Gross Margin % by Model",
                        yaxis=dict(title="Gross Profit (ETB)"),
                        yaxis2=dict(title="Gross Margin (%)", overlaying="y", side="right", showgrid=False),
                        barmode="group"
                    )
                    st.plotly_chart(fig_econ, use_container_width=True)

                    st.dataframe(
                        model_econ[[
                            "Model_Name", "Units_Sold", "Avg_Unit_Price",
                            "Avg_Unit_Cost", "Profit_Per_Unit", "Margin_%", "Revenue", "Gross_Profit"
                        ]].style.format({
                            "Units_Sold": "{:,.0f}", "Avg_Unit_Price": "ETB {:,.2f}",
                            "Avg_Unit_Cost": "ETB {:,.2f}", "Profit_Per_Unit": "ETB {:,.2f}",
                            "Margin_%": "{:.1f}%", "Revenue": "ETB {:,.2f}", "Gross_Profit": "ETB {:,.2f}"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No sales data in the selected range to compute model unit economics.")

            # TAB 2: STOCK RUNWAY
            with an_tab2:
                st.markdown("### ⏳ Stock Runway & Reorder Urgency")
                st.caption("Estimates how many days current stock will last based on recorded issue pace.")

                if not df_mat.empty and current_stock:
                    runway_rows = []
                    df_iss_hist = pd.DataFrame(all_issues) if all_issues else pd.DataFrame(columns=["Date", "Material_ID", "Qty", "Cost"])
                    if not df_iss_hist.empty:
                        df_iss_hist["Date"] = pd.to_datetime(df_iss_hist["Date"], errors="coerce")
                        valid_dates = df_iss_hist["Date"].dropna()
                        span_days = max(1, (valid_dates.max() - valid_dates.min()).days + 1) if not valid_dates.empty else 30
                    else:
                        span_days = 30

                    for _, m_row in df_mat.iterrows():
                        m_id = str(m_row.get("Material_ID", "")).strip()
                        m_name = str(m_row.get("Material_Name", m_id)).strip()
                        reorder_lvl = float(m_row.get("Reorder_Level", 0) or 0)
                        on_hand = float(current_stock.get(m_id, 0) or 0)

                        used_qty = float(df_iss_hist[df_iss_hist["Material_ID"] == m_id]["Qty"].sum()) if not df_iss_hist.empty else 0.0
                        daily_burn = safe_div(used_qty, span_days, 0.0)

                        if on_hand <= 0:
                            days_left = 0.0
                            status = "🔴 Out / Negative"
                        elif daily_burn > 0:
                            days_left = on_hand / daily_burn
                            if reorder_lvl > 0 and on_hand <= reorder_lvl:
                                status = "🟠 Reorder Now"
                            elif days_left <= 14:
                                status = "🟡 Low Runway (<=14d)"
                            else:
                                status = "🟢 Healthy"
                        else:
                            days_left = 999.0
                            status = "🟠 Reorder Now" if (reorder_lvl > 0 and on_hand <= reorder_lvl) else "⚪ No Usage Yet"

                        runway_rows.append({
                            "Material_Name": m_name, "On_Hand_Qty": on_hand,
                            "Reorder_Level": reorder_lvl, "Daily_Usage": daily_burn,
                            "Est_Days_Left": days_left, "Status": status
                        })

                    df_runway = pd.DataFrame(runway_rows)
                    urgent_count = df_runway[df_runway["Status"].str.contains("Out|Reorder|Low", regex=True)].shape[0]
                    st.metric("Materials Needing Attention", f"{urgent_count} of {len(df_runway)}")

                    df_runway_sorted = df_runway.sort_values(by=["Est_Days_Left", "On_Hand_Qty"], ascending=[True, True])
                    chart_runway = df_runway_sorted[df_runway_sorted["Est_Days_Left"] < 999.0].head(15)
                    
                    if not chart_runway.empty:
                        fig_run = px.bar(
                            chart_runway, x="Est_Days_Left", y="Material_Name", orientation="h",
                            color="Est_Days_Left", color_continuous_scale="RdYlGn",
                            title="Estimated Days of Stock Remaining (Top Urgent)"
                        )
                        fig_run.update_layout(yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig_run, use_container_width=True)
                    
                    st.dataframe(df_runway_sorted, use_container_width=True, hide_index=True)
                else:
                    st.info("No stock data available to compute runway.")

            # TAB 3: SUPPLIER & PRICE INTEL
            with an_tab3:
                st.markdown("### 🧾 Supplier & Price Intelligence")
                st.caption("Compare pricing across suppliers and monitor price inflation over time.")
                
                price_subtab1, price_subtab2 = st.tabs(["Cheapest Suppliers", "Material Price Inflation"])
                
                with price_subtab1:
                    if not df_pur.empty and not df_sup.empty:
                        df_price = df_pur.copy()
                        df_price["Unit_Cost"] = clean_numeric_col(df_price["Unit_Cost"], 0.0)
                        df_price = df_price.merge(df_sup[["Supplier_ID", "Supplier_Name"]], on="Supplier_ID", how="left")
                        df_price = df_price.merge(df_mat[["Material_ID", "Material_Name"]], on="Material_ID", how="left")
                        
                        # Average price per supplier per material
                        sup_prices = df_price.groupby(["Material_ID", "Material_Name", "Supplier_Name"])["Unit_Cost"].mean().reset_index()
                        
                        # Find the cheapest supplier for each material
                        idx_min = sup_prices.groupby("Material_ID")["Unit_Cost"].idxmin()
                        cheapest_sups = sup_prices.loc[idx_min].sort_values(by="Unit_Cost", ascending=False)
                        
                        st.write("**Cheapest Supplier Per Material:**")
                        st.dataframe(
                            cheapest_sups[["Material_Name", "Supplier_Name", "Unit_Cost"]].style.format({"Unit_Cost": "ETB {:,.2f}"}),
                            use_container_width=True, hide_index=True
                        )
                    else:
                        st.info("No purchase or supplier data available.")
                
                with price_subtab2:
                    if not df_pur.empty:
                        df_hist_price = df_pur.sort_values("Date").copy()
                        df_hist_price["Unit_Cost"] = clean_numeric_col(df_hist_price["Unit_Cost"], 0.0)
                        df_hist_price = df_hist_price.merge(df_mat[["Material_ID", "Material_Name"]], on="Material_ID", how="left")
                        
                        # Price variance (First vs Last)
                        price_var = df_hist_price.groupby(["Material_ID", "Material_Name"]).agg(
                            First_Price=("Unit_Cost", "first"),
                            Last_Price=("Unit_Cost", "last"),
                            Purchases=("Unit_Cost", "count")
                        ).reset_index()
                        
                        price_var["Change_ETB"] = price_var["Last_Price"] - price_var["First_Price"]
                        price_var["Change_%"] = price_var.apply(lambda r: safe_div(r["Change_ETB"] * 100, r["First_Price"], 0.0), axis=1)
                        
                        inflating = price_var[price_var["Change_ETB"] > 0].sort_values(by="Change_%", ascending=False)
                        
                        if not inflating.empty:
                            st.write("**Top Materials with Inflation (First vs Latest Price):**")
                            fig_infl = px.bar(inflating.head(10), x="Material_Name", y="Change_%", color="Change_%", color_continuous_scale="Reds")
                            st.plotly_chart(fig_infl, use_container_width=True)
                            
                            st.dataframe(
                                inflating[["Material_Name", "First_Price", "Last_Price", "Change_ETB", "Change_%", "Purchases"]].style.format({
                                    "First_Price": "ETB {:,.2f}", "Last_Price": "ETB {:,.2f}",
                                    "Change_ETB": "ETB {:,.2f}", "Change_%": "{:.1f}%"
                                }),
                                use_container_width=True, hide_index=True
                            )
                        else:
                            st.success("No material price inflation detected yet.")
                    else:
                        st.info("No purchase data available.")

            # TAB 4: TIED-UP CAPITAL
            with an_tab4:
                st.markdown("### 🧊 Tied-Up Capital")
                st.caption("Where is your money sitting right now? (Current Stock Qty × FIFO Unit Cost)")
                
                if not df_layers.empty and not df_mat.empty:
                    df_cap = df_layers[df_layers["Qty"] > 0].copy()
                    if not df_cap.empty:
                        df_cap["Total_Value"] = df_cap["Qty"] * df_cap["Unit_Cost"]
                        df_cap = df_cap.merge(df_mat[["Material_ID", "Material_Name"]], on="Material_ID", how="left")
                        df_cap["Material_Name"] = df_cap["Material_Name"].fillna(df_cap["Material_ID"])
                        
                        # Summarize tied-up capital by material
                        cap_summary = df_cap.groupby(["Material_ID", "Material_Name"]).agg(
                            Qty_On_Hand=("Qty", "sum"),
                            Total_Value=("Total_Value", "sum")
                        ).reset_index().sort_values(by="Total_Value", ascending=False)
                        
                        total_tied = cap_summary["Total_Value"].sum()
                        st.metric("Total Capital Tied Up in Inventory", f"ETB {total_tied:,.2f}")
                        
                        c_left, c_right = st.columns([1, 2])
                        with c_left:
                            top_pie = cap_summary.head(10)
                            fig_pie = px.pie(top_pie, values="Total_Value", names="Material_Name", hole=0.4, title="Top 10 Materials by Value")
                            st.plotly_chart(fig_pie, use_container_width=True)
                            
                        with c_right:
                            st.write("**Detailed Capital Breakdown:**")
                            st.dataframe(
                                cap_summary.style.format({"Qty_On_Hand": "{:,.0f}", "Total_Value": "ETB {:,.2f}"}),
                                use_container_width=True, hide_index=True
                            )
                    else:
                        st.info("No active stock layers with value found.")
                else:
                    st.info("No inventory layers or material data available.")
