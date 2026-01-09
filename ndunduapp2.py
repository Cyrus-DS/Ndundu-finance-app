# ==========================================
# Member Contribution & Interest App
# SUPABASE + Streamlit + PDF + Ledger
# Fully Polished Version (FIXED – with Edit Contribution)
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
INTEREST_RATE = 0.085  # 8.5% annual
COMPOUND_FREQUENCY = "daily"

# ==========================================
# SUPABASE CLIENT
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

def compute_totals(member_id, contributions_df):
    df = contributions_df[contributions_df["member_id"] == member_id]
    principal = df["amount"].sum()
    interest = sum(compute_interest(r.amount, r.date) for r in df.itertuples())
    return principal, interest, principal + interest

# ==========================================
# DATA ACCESS (SUPABASE)
# ==========================================
def fetch_members():
    res = supabase.table("members").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["member_id", "name"])

def fetch_contributions(member_id=None):
    query = supabase.table("contributions").select("id, member_id, amount, date")
    if member_id:
        query = query.eq("member_id", member_id)

    res = query.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["id", "member_id", "amount", "date"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def add_member(member_id, name):
    supabase.table("members").insert({
        "member_id": member_id,
        "name": name.strip()
    }).execute()

def add_contribution(member_id, amount, date):
    supabase.table("contributions").insert({
        "member_id": member_id,
        "amount": amount,
        "date": date.isoformat()
    }).execute()

def update_contribution(contribution_id, amount, date):
    supabase.table("contributions").update({
        "amount": amount,
        "date": date.isoformat()
    }).eq("id", contribution_id).execute()

# ==========================================
# PDF GENERATORS
# ==========================================
def generate_pdf(member_id, name, principal, interest, total_value, ratio):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, f"Member Statement - {name}", ln=True)
    pdf.cell(200, 10, f"Member ID: {member_id}", ln=True)
    pdf.ln(5)
    pdf.cell(200, 10, f"Total Principal: {principal:,.2f}", ln=True)
    pdf.cell(200, 10, f"Total Interest: {interest:,.2f}", ln=True)
    pdf.cell(200, 10, f"Portfolio Value: {total_value:,.2f}", ln=True)
    pdf.cell(200, 10, f"Contribution Ratio: {ratio:.4%}", ln=True)
    pdf.ln(15)
    pdf.set_font("Arial", style="B")
    pdf.cell(200, 10, "Signature: ____________________________", ln=True)

    return BytesIO(pdf.output(dest="S").encode("latin1"))

def generate_ledger_pdf(member_id, name, ledger_df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    pdf.cell(200, 8, "Member Ledger Statement", ln=True)
    pdf.cell(200, 8, f"Member Name: {name}", ln=True)
    pdf.cell(200, 8, f"Member ID: {member_id}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", style="B", size=9)
    pdf.cell(25, 8, "Date", border=1)
    pdf.cell(30, 8, "Principal", border=1)
    pdf.cell(30, 8, "Interest", border=1)
    pdf.cell(35, 8, "Total Value", border=1)
    pdf.cell(35, 8, "Run. Balance", border=1, ln=True)

    pdf.set_font("Arial", size=9)
    for _, r in ledger_df.iterrows():
        pdf.cell(25, 8, str(r["date"]), border=1)
        pdf.cell(30, 8, f"{r['amount']:,.2f}", border=1)
        pdf.cell(30, 8, f"{r['Interest']:,.2f}", border=1)
        pdf.cell(35, 8, f"{r['Total Value']:,.2f}", border=1)
        pdf.cell(35, 8, f"{r['Running Balance']:,.2f}", border=1, ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(200, 8, f"Total Principal: {ledger_df['amount'].sum():,.2f}", ln=True)
    pdf.cell(200, 8, f"Total Interest: {ledger_df['Interest'].sum():,.2f}", ln=True)
    pdf.cell(200, 8, f"Grand Total: {ledger_df['Total Value'].sum():,.2f}", ln=True)
    pdf.ln(10)
    pdf.cell(200, 8, "Signature: ____________________________", ln=True)

    return BytesIO(pdf.output(dest="S").encode("latin1"))
