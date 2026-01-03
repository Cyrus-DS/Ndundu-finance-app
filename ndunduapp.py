# %%
import streamlit as st
import datetime
from fpdf import FPDF

INTEREST_RATE = 0.12          # 12% annual
COMPOUND_FREQUENCY = "daily"  # "daily" or "monthly"

# In-memory database
if "members" not in st.session_state:
    st.session_state.members = {}   # {member_id: {name, contributions[]}}


# Function to compute compound interest
def compute_interest(amount, date):
    today = datetime.date.today()
    delta_days = (today - date).days
    years = delta_days / 365

    if COMPOUND_FREQUENCY == "monthly":
        months = years * 12
        total = amount * ((1 + INTEREST_RATE/12)**months)
    else:
        total = amount * ((1 + INTEREST_RATE/365)**delta_days)

    return total - amount


# Function to compute totals per member
def compute_totals(member_id):
    member = st.session_state.members[member_id]
    contributions = member["contributions"]

    principal = sum([c["amount"] for c in contributions])
    interest = sum([compute_interest(c["amount"], c["date"]) for c in contributions])
    total_value = principal + interest
    return principal, interest, total_value


# Function to generate PDF
def generate_pdf(member_id, name, principal, interest, total_value, ratio):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt=f"Member Statement - {name}", ln=True)
    pdf.ln(5)
    pdf.cell(200, 10, txt=f"Member ID: {member_id}", ln=True)
    pdf.cell(200, 10, txt=f"Total Principal: {principal:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Total Interest: {interest:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Total Portfolio Value: {total_value:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Contribution Ratio: {ratio:.4f}", ln=True)
    pdf.ln(15)

    pdf.set_font("Arial", style="B")
    pdf.cell(200, 10, txt="Signature: ________________________________", ln=True)

    filename = f"statement_{member_id}.pdf"
    pdf.output(filename)
    return filename


# ==========================================
# STREAMLIT UI
# ==========================================

st.title("Member Contribution & Interest App")

st.subheader("Add Member")
with st.form("add_member_form"):
    member_id = st.text_input("Member ID")
    name = st.text_input("Name")
    submit_member = st.form_submit_button("Add Member")

    if submit_member:
        st.session_state.members[member_id] = {"name": name, "contributions": []}
        st.success(f"Member {name} added!")


st.subheader("Add Contribution")
with st.form("add_contribution_form"):
    c_member_id = st.text_input("Member ID (for contribution)")
    amount = st.number_input("Contribution Amount", min_value=1.0)
    date = st.date_input("Contribution Date")
    submit_contribution = st.form_submit_button("Add Contribution")

    if submit_contribution:
        if c_member_id not in st.session_state.members:
            st.error("Member ID not found!")
        else:
            st.session_state.members[c_member_id]["contributions"].append(
                {"amount": amount, "date": date}
            )
            st.success("Contribution added successfully!")


st.subheader("Generate Statements")

if st.button("Generate All Member Statements"):
    totals = []
    computed = {}

    # Compute totals for all members
    for member_id, data in st.session_state.members.items():
        principal, interest, total_value = compute_totals(member_id)
        computed[member_id] = (principal, interest, total_value)
        totals.append(total_value)

    grand_total = sum(totals)

    # Generate PDFs
    for member_id, data in computed.items():
        principal, interest, total_value = data
        ratio = total_value / grand_total if grand_total > 0 else 0
        filename = generate_pdf(member_id, st.session_state.members[member_id]["name"],
                                principal, interest, total_value, ratio)

        with open(filename, "rb") as f:
            st.download_button(
                label=f"Download Statement for {st.session_state.members[member_id]['name']}",
                data=f,
                file_name=filename,
                mime="application/pdf"
            )

    st.success("PDF statements generated!")


