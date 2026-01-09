# ==========================================
# Member Contribution & Interest App
# SUPABASE + Streamlit + PDF + Ledger
# Fully Polished Version (FIXED – with Edit Contribution + Running Balance PDF)
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
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame(
        columns=["id", "member_id", "amount", "date"]
    )
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

# ==========================================
# STREAMLIT UI
# ==========================================
st.title("Member Contribution & Interest App")

members_df = fetch_members()
contributions_df = fetch_contributions()

# ------------------------------------------
# ADD MEMBER
# ------------------------------------------
st.subheader("Add Member")
with st.form("add_member"):
    member_id = st.text_input("Member ID")
    name = st.text_input("Name")
    submit = st.form_submit_button("Add Member")

    if submit:
        if not member_id or not name:
            st.error("All fields required")
        else:
            try:
                add_member(member_id, name)
                st.success(f"Member '{name}' added")
                st.rerun()
            except Exception:
                st.error("Member ID already exists")

# ------------------------------------------
# ADD CONTRIBUTION
# ------------------------------------------
st.subheader("Add Contribution")
if not members_df.empty:
    with st.form("add_contribution"):
        member_options = [f"{r['member_id']} - {r['name']}" for _, r in members_df.iterrows()]
        selected = st.selectbox("Select Member", member_options)
        c_member_id, c_member_name = selected.split(" - ")

        amount = st.number_input("Amount", min_value=1.0)
        date = st.date_input("Date")
        submit_c = st.form_submit_button("Add Contribution")

        if submit_c:
            add_contribution(c_member_id, amount, date)
            st.success(f"Contribution added for {c_member_name}")
            st.rerun()
else:
    st.info("Add members first")

# ------------------------------------------
# CONTRIBUTION SUMMARY
# ------------------------------------------
st.subheader("Contribution Summary (Including Interest)")
if not contributions_df.empty:
    summary = contributions_df.merge(members_df, on="member_id", how="left")
    summary["Interest"] = summary.apply(lambda r: compute_interest(r["amount"], r["date"]), axis=1)
    summary["Total Value"] = summary["amount"] + summary["Interest"]

    display_summary = summary[
        ["member_id", "name", "date", "amount", "Interest", "Total Value"]
    ].rename(columns={
        "member_id": "Member ID",
        "name": "Member Name",
        "date": "Date",
        "amount": "Principal"
    })

    for col in ["Principal", "Interest", "Total Value"]:
        display_summary[col] = display_summary[col].map(lambda x: f"{x:,.2f}")

    st.dataframe(display_summary, width="stretch")
else:
    st.info("No contributions yet")

# ------------------------------------------
# MEMBER LEDGER STATEMENT
# ------------------------------------------
st.subheader("Member Ledger Statement")
search = st.text_input("Search by Member ID or Name")

if search and not members_df.empty:
    match = members_df[
        members_df["member_id"].str.contains(search, case=False) |
        members_df["name"].str.contains(search, case=False)
    ]

    if not match.empty:
        m = match.iloc[0]
        ledger = fetch_contributions(m["member_id"])

        if not ledger.empty:
            ledger = ledger.sort_values("date")
            ledger["Interest"] = ledger.apply(lambda r: compute_interest(r["amount"], r["date"]), axis=1)
            ledger["Total Value"] = ledger["amount"] + ledger["Interest"]
            ledger["Running Balance"] = ledger["Total Value"].cumsum()

            display_ledger = ledger[
                ["date", "amount", "Interest", "Total Value", "Running Balance"]
            ].rename(columns={"date": "Date", "amount": "Principal"})

            for col in ["Principal", "Interest", "Total Value", "Running Balance"]:
                display_ledger[col] = display_ledger[col].map(lambda x: f"{x:,.2f}")

            st.dataframe(display_ledger, width="stretch")

            pdf = generate_ledger_pdf(m["member_id"], m["name"], ledger)
            st.download_button(
                "Download Ledger Statement (PDF)",
                pdf,
                f"ledger_{m['member_id']}.pdf",
                "application/pdf"
            )

    else:
        st.warning("No matching member found")
