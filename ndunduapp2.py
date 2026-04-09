# ==========================================
# Member Contribution & Interest App
# SUPABASE + Streamlit + Polished Unified PDF
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
PARTNERSHIP_NAME = "Ndundu Pride Investments LLP"
TARGET_AMOUNT = 4500000.00
MONTHLY_CONTRIBUTION_RATE = 82000.00

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
# AUTH / SESSION
# ==========================================
def init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "role" not in st.session_state:
        st.session_state.role = None
    if "member_id" not in st.session_state:
        st.session_state.member_id = None
    if "member_name" not in st.session_state:
        st.session_state.member_name = None

def logout():
    st.session_state.authenticated = False
    st.session_state.role = None
    st.session_state.member_id = None
    st.session_state.member_name = None
    st.rerun()

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
        return pd.DataFrame(columns=[
            "id", "member_id", "amount", "date",
            "Interest", "Total Value", "Running Balance"
        ])

    ledger = ledger.sort_values("date").reset_index(drop=True)
    ledger["Interest"] = ledger.apply(
        lambda r: compute_interest(r["amount"], r["date"]), axis=1
    )
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
        member_id = r["member_id"]
        name = r["name"]

        ledger = prepare_member_ledger(member_id, contributions_df)
        principal, interest, current_total_value = compute_member_totals(ledger)

        member_data[member_id] = {
            "name": name,
            "ledger": ledger,
            "principal": principal,
            "interest": interest,
            "total_value": current_total_value
        }
        grand_total += current_total_value

    return member_data, grand_total

def project_time_to_target(current_value, monthly_contribution, target_amount, annual_interest_rate=INTEREST_RATE):
    if current_value >= target_amount:
        return 0, 0, 0

    if monthly_contribution <= 0 and current_value < target_amount:
        return None

    projected_value = current_value
    months = 0
    monthly_rate = annual_interest_rate / 12
    max_months = 1200  # safety cap = 100 years

    while projected_value < target_amount and months < max_months:
        projected_value = projected_value * (1 + monthly_rate) + monthly_contribution
        months += 1

    if months >= max_months:
        return None

    years = months // 12
    remaining_months = months % 12
    days = 0

    return years, remaining_months, days

def format_time_to_target(time_tuple):
    if time_tuple is None:
        return "Target not reachable at current contribution rate"

    years, months, days = time_tuple
    return f"{years} years, {months} months, {days} days"

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
        df["member_id"] = df["member_id"].astype(str)
    return df

def add_member(member_id, name):
    supabase.table("members").insert({
        "member_id": str(member_id),
        "name": name.strip()
    }).execute()

def add_contribution(member_id, amount, date):
    supabase.table("contributions").insert({
        "member_id": str(member_id),
        "amount": amount,
        "date": date.isoformat()
    }).execute()

def update_contribution(contribution_id, amount, date):
    supabase.table("contributions").update({
        "amount": amount,
        "date": date.isoformat()
    }).eq("id", contribution_id).execute()

# ==========================================
# PDF CLASS
# ==========================================
class MemberStatementPDF(FPDF):
    def __init__(self, partnership_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partnership_name = partnership_name
        self.col_widths = [28, 35, 30, 35, 42]

    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 8, self.partnership_name, ln=True, align="C")
        self.set_font("Arial", "", 10)
        self.cell(0, 6, "Member Contribution Statement", ln=True, align="C")
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Arial", "I", 8)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")

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

        left_x = self.get_x()
        start_y = self.get_y()

        row_h = 8
        box_w = 190
        box_h = row_h * 11

        self.rect(left_x, start_y, box_w, box_h)

        rows = [
            ("Member Name", name),
            ("Member ID", str(member_id)),
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

        label_w = 60
        value_w = 130

        current_y = start_y
        for label, value in rows:
            self.set_xy(left_x, current_y)

            if label == "Projections":
                self.set_font("Arial", "B", 10)
                self.cell(label_w + value_w, row_h, label, border=1, ln=True, align="C")
            else:
                self.set_font("Arial", "B", 10)
                self.cell(label_w, row_h, label, border=1)
                self.set_font("Arial", "", 10)
                self.cell(value_w, row_h, value, border=1, ln=True)

            current_y += row_h

        self.ln(5)

    def draw_table_header(self):
        self.set_font("Arial", "B", 9)
        headers = ["Date", "Principal", "Interest", "Total Value", "Running Balance"]
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 8, header, border=1, align="C")
        self.ln()

    def draw_ledger_table(self, ledger_df):
        self.set_font("Arial", "B", 11)
        self.cell(0, 8, "Transaction History", ln=True)

        self.draw_table_header()
        self.set_font("Arial", "", 9)

        row_height = 8

        for _, r in ledger_df.iterrows():
            if self.get_y() > 265:
                self.add_page()
                self.set_font("Arial", "B", 11)
                self.cell(0, 8, "Transaction History (continued)", ln=True)
                self.draw_table_header()
                self.set_font("Arial", "", 9)

            values = [
                str(r["date"]),
                f"{r['amount']:,.2f}",
                f"{r['Interest']:,.2f}",
                f"{r['Total Value']:,.2f}",
                f"{r['Running Balance']:,.2f}"
            ]

            for i, value in enumerate(values):
                align = "L" if i == 0 else "R"
                self.cell(self.col_widths[i], row_height, value, border=1, align=align)
            self.ln()

# ==========================================
# UNIFIED PDF GENERATOR
# ==========================================
def generate_unified_pdf(
    member_id,
    name,
    ledger_df,
    ratio,
    monthly_rate,
    target_amount,
    projection_start_value
):
    pdf = MemberStatementPDF(PARTNERSHIP_NAME)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    total_principal, total_interest, current_total_value = compute_member_totals(ledger_df)

    time_to_target = project_time_to_target(
        current_value=projection_start_value,
        monthly_contribution=monthly_rate,
        target_amount=target_amount
    )
    time_to_target_text = format_time_to_target(time_to_target)

    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Generated on: {datetime.date.today().isoformat()}", ln=True)
    pdf.ln(2)

    pdf.draw_summary_box(
        member_id=member_id,
        name=name,
        principal=total_principal,
        interest=total_interest,
        current_total_value=current_total_value,
        ratio=ratio,
        monthly_rate=monthly_rate,
        target_amount=target_amount,
        projection_start_value=projection_start_value,
        time_to_target_text=time_to_target_text
    )

    if not ledger_df.empty:
        pdf.draw_ledger_table(ledger_df)
    else:
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 8, "No contribution records available for this member.", ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "Signature: ____________________________", ln=True)

    return BytesIO(pdf.output(dest="S").encode("latin1"))

# ==========================================
# LOGIN SCREEN
# ==========================================
def login_screen():
    st.title("Member Contribution & Interest App")
    st.subheader("Login")

    login_type = st.radio("Login as", ["Member", "Super Admin"], horizontal=True)

    if login_type == "Super Admin":
        with st.form("admin_login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                if (
                    username == st.secrets["ADMIN_USERNAME"]
                    and password == st.secrets["ADMIN_PASSWORD"]
                ):
                    st.session_state.authenticated = True
                    st.session_state.role = "super_admin"
                    st.session_state.member_id = None
                    st.session_state.member_name = None
                    st.rerun()
                else:
                    st.error("Invalid admin credentials")

    else:
        members_df = fetch_members()

        with st.form("member_login"):
            member_id = st.text_input("Member ID")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                if not member_id or not password:
                    st.error("Member ID and password are required")
                elif password != st.secrets["MEMBER_ACCESS_PASSWORD"]:
                    st.error("Invalid member credentials")
                else:
                    match = members_df[members_df["member_id"].astype(str) == str(member_id)]
                    if match.empty:
                        st.error("Member not found")
                    else:
                        member = match.iloc[0]
                        st.session_state.authenticated = True
                        st.session_state.role = "member"
                        st.session_state.member_id = str(member["member_id"])
                        st.session_state.member_name = str(member["name"])
                        st.rerun()

# ==========================================
# STREAMLIT UI
# ==========================================
init_session()

if not st.session_state.authenticated:
    login_screen()
    st.stop()

st.title("Member Contribution & Interest App")

top_col1, top_col2 = st.columns([4, 1])
with top_col1:
    if st.session_state.role == "super_admin":
        st.caption("Logged in as: Super Admin")
    else:
        st.caption(f"Logged in as: Member ({st.session_state.member_name})")

with top_col2:
    if st.button("Logout"):
        logout()

members_df = fetch_members()
if not members_df.empty:
    members_df["member_id"] = members_df["member_id"].astype(str)

contributions_df = fetch_contributions()
member_data, grand_total = compute_all_member_totals(members_df, contributions_df)

# ------------------------------------------
# PROJECTION SETTINGS
# ------------------------------------------
if st.session_state.role == "super_admin":
    st.subheader("Projection Settings")

    col1, col2 = st.columns(2)

    with col1:
        projection_monthly_rate = st.number_input(
            "Monthly Contribution Rate",
            min_value=0.0,
            value=float(MONTHLY_CONTRIBUTION_RATE),
            step=100.0,
            format="%.2f"
        )

    with col2:
        projection_target_amount = st.number_input(
            "Target Amount",
            min_value=0.0,
            value=float(TARGET_AMOUNT),
            step=1000.0,
            format="%.2f"
        )
else:
    projection_monthly_rate = float(MONTHLY_CONTRIBUTION_RATE)
    projection_target_amount = float(TARGET_AMOUNT)

# ------------------------------------------
# ADD MEMBER
# ------------------------------------------
if st.session_state.role == "super_admin":
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
if st.session_state.role == "super_admin":
    st.subheader("Add Contribution")
    if not members_df.empty:
        with st.form("add_contribution"):
            member_options = [f"{r['member_id']} - {r['name']}" for _, r in members_df.iterrows()]
            selected = st.selectbox("Select Member", member_options)
            c_member_id, c_member_name = selected.split(" - ", 1)

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
if st.session_state.role == "super_admin":
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
        st.metric("Total Principal", f"{summary['amount'].sum():,.2f}")
        st.metric("Total Interest", f"{summary['Interest'].sum():,.2f}")
        st.metric("Grand Total", f"{summary['Total Value'].sum():,.2f}")
    else:
        st.info("No contributions yet")

# ------------------------------------------
# MEMBER STATEMENT
# ------------------------------------------
st.subheader("Member Statement")

if st.session_state.role == "super_admin":
    search = st.text_input("Search by Member ID or Name")
else:
    search = st.session_state.member_id
    st.info(f"Viewing statement for: {st.session_state.member_name} ({st.session_state.member_id})")

if search and not members_df.empty:
    match = members_df[
        members_df["member_id"].astype(str).str.contains(str(search), case=False, na=False) |
        members_df["name"].astype(str).str.contains(str(search), case=False, na=False)
    ]

    if not match.empty:
        if st.session_state.role == "member":
            match = match[match["member_id"].astype(str) == st.session_state.member_id]

        if not match.empty:
            m = match.iloc[0]
            ledger = prepare_member_ledger(str(m["member_id"]), contributions_df)

            if not ledger.empty:
                display_ledger = ledger[
                    ["date", "amount", "Interest", "Total Value", "Running Balance"]
                ].rename(columns={
                    "date": "Date",
                    "amount": "Principal"
                }).copy()

                for col in ["Principal", "Interest", "Total Value", "Running Balance"]:
                    display_ledger[col] = display_ledger[col].map(lambda x: f"{x:,.2f}")

                principal, interest, current_total_value = compute_member_totals(ledger)
                ratio = current_total_value / grand_total if grand_total else 0.0

                monthly_rate = projection_monthly_rate
                target_amount = projection_target_amount
                projection_start_value = grand_total

                time_to_target = project_time_to_target(
                    current_value=projection_start_value,
                    monthly_contribution=monthly_rate,
                    target_amount=target_amount
                )
                time_to_target_text = format_time_to_target(time_to_target)

                st.write(f"**Member Name:** {m['name']}")
                st.write(f"**Member ID:** {m['member_id']}")
                st.write(f"**Total Principal:** {principal:,.2f}")
                st.write(f"**Total Interest:** {interest:,.2f}")
                st.write(f"**Current Total Value:** {current_total_value:,.2f}")
                st.write(f"**Contribution Ratio:** {ratio:.4%}")
                st.write(f"**Monthly Contribution Rate:** {monthly_rate:,.2f}")
                st.write(f"**Target Amount:** {target_amount:,.2f}")
                st.write(f"**General Total Start Value:** {projection_start_value:,.2f}")
                st.write(f"**Estimated Time to Reach Target:** {time_to_target_text}")

                st.dataframe(display_ledger, width="stretch")

                pdf = generate_unified_pdf(
                    m["member_id"],
                    m["name"],
                    ledger,
                    ratio,
                    projection_monthly_rate,
                    projection_target_amount,
                    grand_total
                )
                st.download_button(
                    "Download Member Statement (PDF)",
                    pdf,
                    f"statement_{m['member_id']}.pdf",
                    "application/pdf"
                )

                if st.session_state.role == "super_admin":
                    ledger = ledger.copy()
                    ledger["label"] = ledger.apply(
                        lambda r: f"ID {r['id']} | {r['date']} | {r['amount']:,.2f}",
                        axis=1
                    )

                    selected = st.selectbox("Select contribution to edit", ledger["label"])
                    selected_id = selected.split("|")[0].replace("ID", "").strip()
                    row = ledger[ledger["id"].astype(str) == str(selected_id)].iloc[0]

                    with st.form("edit_contribution"):
                        new_amount = st.number_input("Amount", value=float(row["amount"]), min_value=1.0)
                        new_date = st.date_input("Date", value=row["date"])
                        save = st.form_submit_button("Update Contribution")

                        if save:
                            update_contribution(selected_id, new_amount, new_date)
                            st.success("Contribution updated successfully")
                            st.rerun()
            else:
                st.info("This member has no contributions yet")
        else:
            st.warning("You are only allowed to view your own statement")
    else:
        st.warning("No matching member found")

# ------------------------------------------
# GENERATE ALL MEMBER STATEMENTS
# ------------------------------------------
if st.session_state.role == "super_admin":
    st.subheader("Generate All Member Statements")
    if st.button("Generate All Member Statements") and not members_df.empty:
        for member_id, data in member_data.items():
            ratio = data["total_value"] / grand_total if grand_total else 0.0
            pdf = generate_unified_pdf(
                member_id,
                data["name"],
                data["ledger"],
                ratio,
                projection_monthly_rate,
                projection_target_amount,
                grand_total
            )

            st.download_button(
                f"Download Statement – {data['name']}",
                pdf,
                f"statement_{member_id}.pdf",
                "application/pdf"
            )

        st.success("All statements generated successfully")