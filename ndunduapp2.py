# ==========================================
# Member Contribution & Interest App
# With SQLite + CSV + Excel Export
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

INTEREST_RATE = 0.085
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
    years = delta_days / 365

    if COMPOUND_FREQUENCY == "monthly":
        months = years * 12
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
        compute_interest(row.amount, row.date)
        for row in df.itertuples()
    )

    return principal, interest, principal + interest


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

    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

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
                    (member_id, name)
                )
                conn.commit()
                st.success("Member added")
            except sqlite3.IntegrityError:
                st.error("Member ID already exists")
            conn.close()

# ------------------------------------------
# ADD CONTRIBUTION
# ------------------------------------------

st.subheader("Add Contribution")

with st.form("add_contribution"):
    c_member_id = st.selectbox("Member", members_df["member_id"].tolist())
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
        st.success("Contribution added")

# ------------------------------------------
# PORTFOLIO SUMMARY
# ------------------------------------------

st.subheader("Portfolio Summary")

total_principal = contributions_df["amount"].sum()
total_interest = sum(
    compute_interest(r.amount, r.date)
    for r in contributions_df.itertuples()
)

st.metric("Total Principal", f"{total_principal:,.2f}")
st.metric("Total Interest", f"{total_interest:,.2f}")
st.metric("Portfolio Value", f"{(total_principal + total_interest):,.2f}")

# ------------------------------------------
# EXPORTS
# ------------------------------------------

st.subheader("Exports")

# CSV
csv_members = members_df.to_csv(index=False).encode("utf-8")
csv_contrib = contributions_df.to_csv(index=False).encode("utf-8")

st.download_button("Download Members CSV", csv_members, "members.csv", "text/csv")
st.download_button("Download Contributions CSV", csv_contrib, "contributions.csv", "text/csv")

# Excel
excel_buffer = BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    members_df.to_excel(writer, sheet_name="Members", index=False)
    contributions_df.to_excel(writer, sheet_name="Contributions", index=False)

excel_buffer.seek(0)

st.download_button(
    "Download Excel Workbook",
    excel_buffer,
    "portfolio_data.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# ------------------------------------------
# STATEMENTS
# ------------------------------------------

st.subheader("Generate Statements")

if st.button("Generate All Member Statements"):
    grand_total = 0
    totals = {}

    for _, row in members_df.iterrows():
        p, i, t = compute_totals(row.member_id, contributions_df)
        totals[row.member_id] = (row.name, p, i, t)
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

    st.success("Statements generated")
