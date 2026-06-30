import streamlit as st
import requests
import pandas as pd
import time

API = "http://localhost:8000"

st.set_page_config(page_title="PhishGuard India", page_icon="🎣", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0a0b0f; }
  [data-testid="stSidebar"] { background: #111318; border-right: 1px solid #222630; }
  .metric-card { background: #111318; border: 1px solid #222630; border-radius: 8px; padding: 20px 24px; text-align: center; }
  .metric-num { font-size: 32px; font-weight: 800; line-height: 1; }
  .metric-label { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-top: 6px; }
  .red { color: #ff4c29; } .gold { color: #ffb830; } .teal { color: #00d4aa; }
  .pg-title { font-size: 28px; font-weight: 800; letter-spacing: -1px; margin-bottom: 4px; }
  .pg-sub { color: #6b7280; font-size: 14px; margin-bottom: 24px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🎣 PhishGuard")
    st.markdown("---")
    page = st.radio("Navigate", [
        "📊 Dashboard", "🚀 Launch Campaign", "🔍 Campaign Detail",
        "🏢 Customers", "📥 Leads", "💳 Payments",
    ], label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:11px;color:#4b5563'>PhishGuard MVP · v1.0<br/>Running on localhost</div>", unsafe_allow_html=True)


def api_get(path):
    try:
        r = requests.get(f"{API}{path}", timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot reach the PhishGuard API. Run: `uvicorn main:app --reload` inside /backend")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# ════════════════════════ DASHBOARD ════════════════════════
if page == "📊 Dashboard":
    st.markdown('<div class="pg-title">📊 Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Overview of all phishing campaigns</div>', unsafe_allow_html=True)

    campaigns = api_get("/analytics/campaigns")
    if campaigns is None:
        st.stop()
    if not campaigns:
        st.info("No campaigns yet. Go to 🚀 Launch Campaign to create your first one.")
        st.stop()

    total_sent = sum(c["total_sent"] for c in campaigns)
    total_clicks = sum(c["total_clicks"] for c in campaigns)
    click_rate = round((total_clicks / total_sent * 100) if total_sent else 0, 1)

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-num">{len(campaigns)}</div><div class="metric-label">Campaigns</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-num teal">{total_sent}</div><div class="metric-label">Emails Sent</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-num gold">{total_clicks}</div><div class="metric-label">Links Clicked</div></div>', unsafe_allow_html=True)
    with col4:
        color = "red" if click_rate > 30 else "gold" if click_rate > 15 else "teal"
        st.markdown(f'<div class="metric-card"><div class="metric-num {color}">{click_rate}%</div><div class="metric-label">Click Rate</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### All Campaigns")
    df = pd.DataFrame(campaigns)
    df["click_rate"] = df.apply(lambda r: f"{round(r['total_clicks']/r['total_sent']*100, 1)}%" if r["total_sent"] else "—", axis=1)
    df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%d %b %Y %H:%M")
    st.dataframe(df[["id", "name", "template", "total_sent", "total_clicks", "click_rate", "created_at"]],
                 use_container_width=True, hide_index=True)

    if len(campaigns) > 0:
        st.markdown("#### Click Rate by Campaign")
        chart_df = pd.DataFrame({
            "Campaign": [c["name"] for c in campaigns],
            "Click Rate (%)": [round(c["total_clicks"]/c["total_sent"]*100, 1) if c["total_sent"] else 0 for c in campaigns],
        })
        st.bar_chart(chart_df.set_index("Campaign"))


# ════════════════════════ LAUNCH CAMPAIGN ════════════════════════
elif page == "🚀 Launch Campaign":
    st.markdown('<div class="pg-title">🚀 Launch Campaign</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Upload employees and fire a simulated phishing campaign</div>', unsafe_allow_html=True)

    col_form, col_preview = st.columns([1, 1], gap="large")

    with col_form:
        customers = api_get("/customers/all") or []
        customer_options = {f"{c['company_name']} (#{c['id']})": c["id"] for c in customers}
        customer_options["No customer (test campaign)"] = None

        st.markdown("#### Campaign Details")
        campaign_name = st.text_input("Campaign Name", placeholder="e.g. Finance Team - Jan 2025")
        selected_customer_label = st.selectbox("Customer", options=list(customer_options.keys()))
        customer_id = customer_options[selected_customer_label]

        if customer_id:
            cust = next(c for c in customers if c["id"] == customer_id)
            if not cust["authorization_signed"]:
                st.warning("⚠️ This customer has NOT signed the authorization agreement. Campaign will be blocked until they do (see 🏢 Customers tab).")

        template = st.selectbox("Phishing Template", options=["hdfc_alert", "gst_notice", "epfo_refund", "razorpay_hold"],
            format_func=lambda x: {
                "hdfc_alert": "🏦 HDFC Bank Security Alert",
                "gst_notice": "🏛️ GST Department Notice",
                "epfo_refund": "💰 EPFO Refund Approved",
                "razorpay_hold": "💳 Razorpay Settlement Hold",
            }.get(x, x))

        st.markdown("#### Employee CSV")
        st.markdown('<div style="font-size:12px;color:#6b7280;margin-bottom:8px">CSV columns: <code>email</code>, <code>name</code>, <code>department</code> (optional)</div>', unsafe_allow_html=True)

        sample_csv = "email,name,department\npriya.sharma@example.com,Priya Sharma,Finance\nrahul.gupta@example.com,Rahul Gupta,Sales\n"
        st.download_button("⬇️ Download sample CSV", data=sample_csv, file_name="sample_employees.csv", mime="text/csv")

        csv_file = st.file_uploader("Upload Employee CSV", type=["csv"])
        if csv_file:
            try:
                preview_df = pd.read_csv(csv_file)
                csv_file.seek(0)
                st.success(f"✅ {len(preview_df)} employees loaded")
                st.dataframe(preview_df.head(5), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"CSV error: {e}")

        st.markdown("---")
        if st.button("🎣 Launch Campaign", type="primary", use_container_width=True):
            if not campaign_name:
                st.error("Please enter a campaign name.")
            elif not csv_file:
                st.error("Please upload a CSV file.")
            else:
                csv_file.seek(0)
                with st.spinner("Sending emails..."):
                    try:
                        data = {"name": campaign_name, "template": template}
                        if customer_id:
                            data["customer_id"] = str(customer_id)
                        response = requests.post(f"{API}/campaign/create", data=data,
                            files={"csv_file": ("employees.csv", csv_file, "text/csv")}, timeout=60)
                        result = response.json()
                        if response.status_code == 200:
                            st.success(f"✅ {result['message']}")
                            st.json(result)
                        else:
                            st.error(f"Error: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"Failed to reach API: {e}")

    with col_preview:
        st.markdown("#### Email Preview")
        preview_url = f"{API}/analytics/preview/{template}"
        st.markdown(f'<iframe src="{preview_url}" width="100%" height="500" style="border:1px solid #222630;border-radius:6px;background:#fff"></iframe>', unsafe_allow_html=True)


# ════════════════════════ CAMPAIGN DETAIL ════════════════════════
elif page == "🔍 Campaign Detail":
    st.markdown('<div class="pg-title">🔍 Campaign Detail</div>', unsafe_allow_html=True)
    campaigns = api_get("/analytics/campaigns")
    if not campaigns:
        st.info("No campaigns yet.")
        st.stop()

    selected = st.selectbox("Select Campaign", options=campaigns,
        format_func=lambda c: f"#{c['id']} — {c['name']} ({c['created_at'][:10]})")

    if selected:
        detail = api_get(f"/analytics/campaign/{selected['id']}")
        if not detail:
            st.stop()
        recipients = detail["recipients"]
        if not recipients:
            st.info("No recipients found.")
            st.stop()

        total = len(recipients)
        clicked = sum(1 for r in recipients if r["click_count"] > 0)
        safe = total - clicked
        rate = round(clicked / total * 100, 1) if total else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.markdown(f'<div class="metric-card"><div class="metric-num">{total}</div><div class="metric-label">Total Sent</div></div>', unsafe_allow_html=True)
        with col2: st.markdown(f'<div class="metric-card"><div class="metric-num red">{clicked}</div><div class="metric-label">Clicked</div></div>', unsafe_allow_html=True)
        with col3: st.markdown(f'<div class="metric-card"><div class="metric-num teal">{safe}</div><div class="metric-label">Stayed Safe</div></div>', unsafe_allow_html=True)
        with col4:
            color = "red" if rate > 30 else "gold" if rate > 15 else "teal"
            st.markdown(f'<div class="metric-card"><div class="metric-num {color}">{rate}%</div><div class="metric-label">Click Rate</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        df = pd.DataFrame(recipients)
        df["status"] = df["click_count"].apply(lambda x: "🔴 Clicked" if x > 0 else "🟢 Safe")
        df["first_click"] = df["first_click"].fillna("—")
        st.dataframe(df[["name", "email", "department", "status", "click_count", "first_click"]], use_container_width=True, hide_index=True)

        if st.checkbox("🔄 Auto-refresh every 10 seconds"):
            time.sleep(10)
            st.rerun()


# ════════════════════════ CUSTOMERS ════════════════════════
elif page == "🏢 Customers":
    st.markdown('<div class="pg-title">🏢 Customers</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Manage paying companies and authorization agreements</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["All Customers", "Add New Customer"])

    with tab1:
        customers = api_get("/customers/all") or []
        if not customers:
            st.info("No customers yet.")
        else:
            for cust in customers:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.markdown(f"**{cust['company_name']}**")
                        st.caption(f"{cust['contact_name']} · {cust['contact_email']}")
                    with c2:
                        st.markdown(f"Plan: **{cust['plan']}**")
                        st.caption(f"Limit: {cust['employee_limit']} employees")
                    with c3:
                        if cust["authorization_signed"]:
                            st.success("✅ Authorized")
                        else:
                            if st.button(f"Mark as Signed", key=f"sign_{cust['id']}"):
                                requests.post(f"{API}/customers/{cust['id']}/sign-authorization")
                                st.rerun()

    with tab2:
        with st.form("new_customer"):
            company_name = st.text_input("Company Name")
            contact_name = st.text_input("Contact Person Name")
            contact_email = st.text_input("Contact Email")
            phone = st.text_input("Phone (optional)")
            plan = st.selectbox("Plan", ["trial", "starter", "growth", "enterprise"])
            submitted = st.form_submit_button("Add Customer")
            if submitted:
                if not (company_name and contact_name and contact_email):
                    st.error("Company name, contact name, and email are required.")
                else:
                    r = requests.post(f"{API}/customers/create", data={
                        "company_name": company_name, "contact_name": contact_name,
                        "contact_email": contact_email, "phone": phone, "plan": plan,
                    })
                    if r.status_code == 200:
                        st.success("✅ Customer added! Don't forget to get the authorization agreement signed before launching campaigns.")
                    else:
                        st.error(r.json().get("error", "Failed to add customer"))


# ════════════════════════ LEADS ════════════════════════
elif page == "📥 Leads":
    st.markdown('<div class="pg-title">📥 Leads</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">People who requested a free audit from the landing page</div>', unsafe_allow_html=True)

    leads = api_get("/leads/all") or []
    if not leads:
        st.info("No leads yet. Once your landing page is live, free-audit signups will appear here.")
    else:
        df = pd.DataFrame(leads)
        st.dataframe(df[["email", "company_name", "phone", "source", "status", "created_at"]],
                     use_container_width=True, hide_index=True)
        st.caption(f"Total leads: {len(leads)}")


# ════════════════════════ PAYMENTS ════════════════════════
elif page == "💳 Payments":
    st.markdown('<div class="pg-title">💳 Payments</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Razorpay transaction history</div>', unsafe_allow_html=True)

    payments = api_get("/payments/all") or []
    if not payments:
        st.info("No payments yet. Once Razorpay is configured (see .env), transactions will appear here.")
    else:
        df = pd.DataFrame(payments)
        df["amount_inr"] = df["amount"] / 100
        st.dataframe(df[["customer_id", "plan", "amount_inr", "status", "created_at"]],
                     use_container_width=True, hide_index=True)
        captured = df[df["status"] == "captured"]["amount_inr"].sum()
        st.metric("Total Revenue Captured", f"₹{captured:,.0f}")
