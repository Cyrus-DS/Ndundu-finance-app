# ==========================================
# Member Contribution & Interest App
# ==========================================

import streamlit as st
import datetime
import pandas as pd
from fpdf import FPDF
from io import BytesIO
from supabase import create_client

# ==========================================
# CONFIG
# ==========================================
INTEREST_RATE = 0.085
COMPOUND_FREQUENCY = "daily"
PARTNERSHIP_NAME = "Ndundu Pride Investments LLP"
TARGET_AMOUNT = 500000.00
MONTHLY_CONTRIBUTION_RATE = 2000.00

# ==========================================
# SUPABASE
# ==========================================
@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

supabase = get_supabase()

# ==========================================
# BUSINESS LOGIC
# ==========================================
def compute_interest(amount, date):
    today = datetime.date.today()
    if date > today:
        return 0.0

    delta_days = (today - date).days

    if COMPOUND_FREQUENCY == "monthly":
        months = delta_days / 30
        total = amount * ((1 + INTEREST_RATE / 12) ** months)
    else:
        total = amount * ((1 + INTEREST_RATE / 365) ** delta_days)

    return total - amount


def prepare_member_ledger(member_id, contributions_df):
    ledger = contributions_df[contributions_df["member_id"] == member_id].copy()

    if ledger.empty:
        return pd.DataFrame()

    ledger = ledger.sort_values("date").reset_index(drop=True)
    ledger["Interest"] = ledger.apply(lambda r: compute_interest(r["amount"], r["date"]), axis=1)
    ledger["Total Value"] = ledger["amount"] + ledger["Interest"]
    ledger["Running Balance"] = ledger["Total Value"].cumsum()

    return ledger


def compute_member_totals(ledger_df):
    if ledger_df.empty:
        return 0.0, 0.0, 0.0

    principal = ledger_df["amount"].sum()
    interest = ledger_df["Interest"].sum()
    current_total_value = ledger_df["Running Balance"].iloc[-1]

    return principal, interest, current_total_value


def compute_all_member_totals(members_df, contributions_df):
    member_data = {}
    grand_total = 0.0

    for _, r in members_df.iterrows():
        ledger = prepare_member_ledger(r["member_id"], contributions_df)
        p, i, total = compute_member_totals(ledger)

        member_data[r["member_id"]] = {
            "name": r["name"],
            "ledger": ledger,
            "principal": p,
            "interest": i,
            "total_value": total
        }

        grand_total += total

    return member_data, grand_total


def project_time_to_target(current_value, monthly_contribution, target_amount):
    if current_value >= target_amount:
        return (0, 0, 0)

    monthly_rate = INTEREST_RATE / 12
    months = 0
    value = current_value

    while value < target_amount and months < 1200:
        value = value * (1 + monthly_rate) + monthly_contribution
        months += 1

    years = months // 12
    remaining_months = months % 12

    return (years, remaining_months, 0)


def format_time_to_target(t):
    return f"{t[0]} years, {t[1]} months, {t[2]} days"


# ==========================================
# PDF
# ==========================================
class MemberStatementPDF(FPDF):

    def __init__(self, name):
        super().__init__()
        self.name = name

    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 8, PARTNERSHIP_NAME, ln=True, align="C")
        self.set_font("Arial", "", 10)
        self.cell(0, 6, "Member Contribution Statement", ln=True, align="C")
        self.ln(5)

    def draw_summary_box(
        self,
        member_id,
        name,
        principal,
        interest,
        current_total_value,
        ratio,
        monthly_rate,
        target_amount,
        projection_start_value,
        time_to_target_text
    ):
        self.set_font("Arial", "B", 11)
        self.cell(0, 8, "Member Details", ln=True)

        row_h = 8
        box_w = 190
        box_h = row_h * 11

        x = self.get_x()
        y = self.get_y()

        self.rect(x, y, box_w, box_h)

        rows = [
            ("Member Name", name),
            ("Member ID", member_id),
            ("Total Principal", f"{principal:,.2f}"),
            ("Total Interest", f"{interest:,.2f}"),
            ("Current Total Value", f"{current_total_value:,.2f}"),
            ("Contribution Ratio", f"{ratio:.4%}"),
            ("Projections", ""),
            ("Monthly Contribution Rate", f"{monthly_rate:,.2f}"),
            ("Target Amount", f"{target_amount:,.2f}"),
            ("General Total Start Value", f"{projection_start_value:,.2f}"),
            ("Time to Reach Target", time_to_target_text),
        ]

        for label, value in rows:
            self.set_x(x)

            if label == "Projections":
                self.set_font("Arial", "B", 10)
                self.cell(190, row_h, label, border=1, ln=True, align="C")
            else:
                self.set_font("Arial", "B", 10)
                self.cell(60, row_h, label, border=1)
                self.set_font("Arial", "", 10)
                self.cell(130, row_h, str(value), border=1, ln=True)

    def draw_ledger(self, df):
        self.ln(5)
        self.set_font("Arial", "B", 11)
        self.cell(0, 8, "Transaction History", ln=True)

        self.set_font("Arial", "B", 9)
        headers = ["Date", "Principal", "Interest", "Total", "Balance"]

        widths = [30, 30, 30, 40, 40]

        for i, h in enumerate(headers):
            self.cell(widths[i], 8, h, border=1, align="C")
        self.ln()

        self.set_font("Arial", "", 9)

        for _, r in df.iterrows():
            self.cell(30, 8, str(r["date"]), border=1)
            self.cell(30, 8, f"{r['amount']:,.2f}", border=1)
            self.cell(30, 8, f"{r['Interest']:,.2f}", border=1)
            self.cell(40, 8, f"{r['Total Value']:,.2f}", border=1)
            self.cell(40, 8, f"{r['Running Balance']:,.2f}", border=1)
            self.ln()


def generate_pdf(member_id, name, ledger, ratio, monthly_rate, target_amount, grand_total):
    pdf = MemberStatementPDF(name)
    pdf.add_page()

    p, i, total = compute_member_totals(ledger)

    time = project_time_to_target(grand_total, monthly_rate, target_amount)
    time_text = format_time_to_target(time)

    pdf.draw_summary_box(
        member_id,
        name,
        p,
        i,
        total,
        ratio,
        monthly_rate,
        target_amount,
        grand_total,
        time_text
    )

    if not ledger.empty:
        pdf.draw_ledger(ledger)

    return BytesIO(pdf.output(dest="S").encode("latin1"))


# ==========================================
# UI
# ==========================================
st.title("Ndundu Finance App")

members = supabase.table("members").select("*").execute().data
contributions = supabase.table("contributions").select("*").execute().data

members_df = pd.DataFrame(members)
contributions_df = pd.DataFrame(contributions)

if not contributions_df.empty:
    contributions_df["date"] = pd.to_datetime(contributions_df["date"]).dt.date

member_data, grand_total = compute_all_member_totals(members_df, contributions_df)

# Projection Inputs
st.subheader("Projection Settings")

col1, col2 = st.columns(2)

with col1:
    projection_monthly_rate = st.number_input("Monthly Contribution Rate", value=MONTHLY_CONTRIBUTION_RATE)

with col2:
    projection_target_amount = st.number_input("Target Amount", value=TARGET_AMOUNT)

# Member Statement
search = st.text_input("Search Member")

if search:
    match = members_df[members_df["name"].str.contains(search, case=False)]

    if not match.empty:
        m = match.iloc[0]
        ledger = prepare_member_ledger(m["member_id"], contributions_df)

        p, i, total = compute_member_totals(ledger)
        ratio = total / grand_total if grand_total else 0

        time = project_time_to_target(grand_total, projection_monthly_rate, projection_target_amount)
        time_text = format_time_to_target(time)

        st.write(f"**Name:** {m['name']}")
        st.write(f"**Current Total:** {total:,.2f}")
        st.write(f"**Group Total:** {grand_total:,.2f}")
        st.write(f"**Projection Time:** {time_text}")

        pdf = generate_pdf(
            m["member_id"],
            m["name"],
            ledger,
            ratio,
            projection_monthly_rate,
            projection_target_amount,
            grand_total
        )

        st.download_button("Download PDF", pdf, "statement.pdf")