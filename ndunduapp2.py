# ==========================================
# Member Contribution & Interest App
# SQLite + CSV + Excel + PDF + Ledger Statements
# ==========================================

import streamlit as st
import datetime
import sqlite3
import pandas as pd
from fpdf import FPDF
from io import BytesIO

# ==========================================
# CONFIG
# ==========================================
INTEREST_RATE = 0.12
COMPOUND_FREQUENCY = "daily"
DB_NAME = "members.db"

# ==========================================
# DATABASE SETUP
# ==========================================
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            member_id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id TEXT,
            amount REAL,
            date TEXT,
            FOREIGN KEY(member_id) REFERENCES members(member_id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

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

def fetch_members():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM members", conn)
    conn.close()
    return df

def fetch_contributions():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM contributions", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def compute_totals(member_id, contributions_df):
    df = contributions_df[contributions_df["member_id"] == member_id]
    principal = df["amount"].sum()
    interest = sum(
        compute_interest(r.amount, r.date)
        for r in df.itertuples()
    )
    return principal, interest, principal + interest

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
    pdf.set_font("Arial", size=11)

    pdf.cell(200, 8, "Member Ledger Statement", ln=True)
    pdf.cell(200, 8, f"Member Name: {name}", ln=True)
    pdf.cell(200, 8, f"Member ID: {member_id}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(35, 8, "Date", border=1)
    pdf.cell(45, 8, "Principal", border=1)
    pdf.cell(45, 8, "Interest", border=1)
    pdf.cell(55, 8, "Total Value", border=1, ln=True)

    pdf.set_font("Arial", size=10)

    for _, r in ledger_df.iterrows():
        pdf.cell(35, 8, str(r["date"]), border=1)
        pdf.cell(45, 8, f"{r['amount']:,.2f}", border=1)
        pdf.cell(45, 8, f"{r['Interest']:,.2f}", border=1)
        pdf.cell(55, 8, f"{r['Total Value']:,.2f}", border=1, ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=11)
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
            conn = get_connection()
            try:
                conn.execute(
                    "INSERT INTO members (member_id, name) VALUES (?, ?)",
                    (member_id, name.strip())
                )
                conn.commit()
                st.success(f"Member '{name}' added")
            except sqlite3.IntegrityError:
                st.error("Member ID already exists")
            conn.close()

# ------------------------------------------
# ADD CONTRIBUTION
# ------------------------------------------
st.subheader("Add Contribution")
if not members_df.empty:
    with st.form("add_contribution"):
        member_options = [
            f"{r['member_id']} - {r['name']}"
            for _, r in members_df.iterrows()
        ]
        selected = st.selectbox("Select Member", member_options)
        c_member_id, c_member_name = selected.split(" - ")

        amount = st.number_input("Amount", min_value=1.0)
        date = st.date_input("Date")
        submit_c = st.form_submit_button("Add Contribution")

        if submit_c:
            conn = get_connection()
            conn.execute(
                "INSERT INTO contributions (member_id, amount, date) VALUES (?, ?, ?)",
                (c_member_id, amount, date.isoformat())
            )
            conn.commit()
            conn.close()
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

    summary["Interest"] = summary.apply(
        lambda r: compute_interest(r["amount"], r["date"]),
        axis=1
    )
    summary["Total Value"] = summary["amount"] + summary["Interest"]

    st.dataframe(
        summary[["member_id", "name", "date", "amount", "Interest", "Total Value"]]
        .rename(columns={
            "member_id": "Member ID",
            "name": "Member Name",
            "date": "Date",
            "amount": "Principal"
        }),
        use_container_width=True
    )

    st.metric("Total Principal", f"{summary['amount'].sum():,.2f}")
    st.metric("Total Interest", f"{summary['Interest'].sum():,.2f}")
    st.metric("Grand Total", f"{summary['Total Value'].sum():,.2f}")
else:
    st.info("No contributions yet")

# ------------------------------------------
# MEMBER LEDGER STATEMENT (SEARCH)
# ------------------------------------------
st.subheader("Member Ledger Statement")

search = st.text_input("Search by Member ID or Name")

if search:
    match = members_df[
        members_df["member_id"].str.contains(search, case=False) |
        members_df["name"].str.contains(search, case=False)
    ]

    if match.empty:
        st.warning("No matching member found")
    else:
        m = match.iloc[0]
        ledger = contributions_df[contributions_df["member_id"] == m["member_id"]]

        if ledger.empty:
            st.info("No transactions for this member")
        else:
            ledger = ledger.copy()
            ledger["Interest"] = ledger.apply(
                lambda r: compute_interest(r["amount"], r["date"]),
                axis=1
            )
            ledger["Total Value"] = ledger["amount"] + ledger["Interest"]

            st.dataframe(
                ledger[["date", "amount", "Interest", "Total Value"]]
                .rename(columns={"date": "Date", "amount": "Principal"}),
                use_container_width=True
            )

            pdf = generate_ledger_pdf(m["member_id"], m["name"], ledger)

            st.download_button(
                "Download Ledger Statement (PDF)",
                pdf,
                f"ledger_{m['member_id']}.pdf",
                "application/pdf"
            )

# ------------------------------------------
# GENERATE ALL MEMBER STATEMENTS
# ------------------------------------------
st.subheader("Generate Statements")

if st.button("Generate All Member Statements") and not members_df.empty:
    grand_total = 0
    totals = {}

    for _, r in members_df.iterrows():
        p, i, t = compute_totals(r["member_id"], contributions_df)
        totals[r["member_id"]] = (r["name"], p, i, t)
        grand_total += t

    for member_id, (name, p, i, t) in totals.items():
        ratio = t / grand_total if grand_total else 0
        pdf = generate_pdf(member_id, name, p, i, t, ratio)

        st.download_button(
            f"Download Statement – {name}",
            pdf,
            f"statement_{member_id}.pdf",
            "application/pdf"
        )

    st.success("All statements generated successfully")


