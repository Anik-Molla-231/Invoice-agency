# admin_dashboard.py
"""
Admin Dashboard for Invoice Automation Agency
Run: streamlit run admin_dashboard.py
"""

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta
import secrets
import base64

# ------------------- PAGE CONFIG -------------------
st.set_page_config(
    page_title="Admin Dashboard - Invoice Agency",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------- API CONFIG -------------------
API_BASE_URL = "https://invoice-agency-api.onrender.com/api"

# ------------------- SIDEBAR -------------------
st.sidebar.title("⚙️ Admin Dashboard")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigation",
    [
        "📊 Overview",
        "👥 Clients",
        "📄 All Invoices",
        "➕ Add Client",
        "💰 Revenue",
        "⚙️ Settings"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption(f"API: {API_BASE_URL}")
st.sidebar.caption(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ------------------- HELPER FUNCTIONS -------------------

@st.cache_data(ttl=30)
def fetch_all_invoices():
    """Fetch all invoices from API."""
    try:
        response = requests.get(f"{API_BASE_URL}/invoices", timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

@st.cache_data(ttl=30)
def fetch_all_clients():
    """Fetch all clients from API."""
    try:
        response = requests.get(f"{API_BASE_URL}/clients", timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def generate_api_key():
    """Generate a secure API key."""
    return f"ck_{secrets.token_urlsafe(32)}"

def create_client(name, email, tier, threshold):
    """Create a new client via API."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/clients",
            json={
                "client_name": name,
                "contact_email": email,
                "tier": tier,
                "auto_approve_threshold": threshold
            },
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Failed: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ------------------- PAGE RENDER -------------------

# 1. OVERVIEW PAGE
if page == "📊 Overview":
    st.title("📊 Overview")
    st.markdown("---")
    
    invoices = fetch_all_invoices()
    clients = fetch_all_clients()
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total_invoices = len(invoices)
    total_clients = len(clients)
    
    approved = len([i for i in invoices if i.get('status') == 'approved'])
    pending = len([i for i in invoices if i.get('status') == 'pending_approval'])
    
    total_revenue = sum([i.get('total', 0) for i in invoices if i.get('status') in ['approved', 'synced', 'paid']])
    
    with col1:
        st.metric("Total Clients", total_clients)
    with col2:
        st.metric("Total Invoices", total_invoices)
    with col3:
        st.metric("Pending Approval", pending, delta=f"{pending} waiting")
    with col4:
        st.metric("Total Revenue", f"₹{total_revenue:,.2f}")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        if invoices:
            df = pd.DataFrame(invoices)
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig = px.pie(status_counts, values='Count', names='Status', title='Invoice Status Distribution')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No invoice data")
    
    with col2:
        if clients:
            df_clients = pd.DataFrame(clients)
            tier_counts = df_clients['tier'].value_counts().reset_index()
            tier_counts.columns = ['Tier', 'Count']
            fig = px.bar(tier_counts, x='Tier', y='Count', title='Client Tiers', color='Tier')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No client data")
    
    # Recent Activity
    st.markdown("---")
    st.subheader("🔄 Recent Activity")
    
    if invoices:
        df_recent = pd.DataFrame(invoices).sort_values('created_at', ascending=False).head(10)
        df_recent['created_at'] = pd.to_datetime(df_recent['created_at'])
        df_recent['created_at'] = df_recent['created_at'].dt.strftime('%Y-%m-%d %H:%M')
        
        cols_to_show = ['id', 'invoice_number', 'vendor_name', 'total', 'status', 'created_at']
        cols_to_show = [c for c in cols_to_show if c in df_recent.columns]
        st.dataframe(df_recent[cols_to_show], use_container_width=True)
    else:
        st.info("No recent activity")

# 2. CLIENTS PAGE
elif page == "👥 Clients":
    st.title("👥 Client Management")
    st.markdown("---")
    
    clients = fetch_all_clients()
    DASHBOARD_URL = "https://anik-molla-231-invoice-agency-dashboard-3xmcob.streamlit.app"

    if clients:
        df = pd.DataFrame(clients)
        
        # Display client cards
        for _, client in df.iterrows():
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
                
                with col1:
                    st.write(f"**{client.get('client_name', 'Unknown')}**")
                    st.caption(f"ID: {client.get('client_id', 'N/A')}")
                
                with col2:
                    st.write(f"📧 {client.get('contact_email', 'No email')}")
                    st.caption(f"Tier: {client.get('tier', 'starter')}")
                
                with col3:
                    status = client.get('status', 'trial')
                    if status == 'active':
                        st.success("🟢 Active")
                    elif status == 'trial':
                        st.warning("🟡 Trial")
                    else:
                        st.error("🔴 Inactive")
                
                with col4:
                    st.write(f"₹{client.get('auto_approve_threshold', 1000):,.0f}")
                    st.caption("Auto-approve")
                
                with col5:
                    DASHBOARD_URL = "https://anik-molla-231-invoice-agency-dashboard-3xmcob.streamlit.app"
                    magic_link = f"{DASHBOARD_URL}?api_key={client.get('api_key')}"
                    # Display magic link
                    st.text_input("🔗 Client Access Link", value=magic_link, disabled=True)
                    st.caption("Send this link to your client. They don't need a password.")

                # View button
                if st.button("📋 View", key=f"view_{client.get('id')}"):
                    st.session_state.selected_client = client.to_dict()
                    st.rerun()
        
        st.markdown("---")
        
        # Show selected client details
        if st.session_state.get('selected_client') is not None:
            client = st.session_state.selected_client
            st.subheader(f"📋 Client Details: {client.get('client_name')}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Client ID:** {client.get('client_id')}")
                st.write(f"**Email:** {client.get('contact_email')}")
                st.write(f"**Tier:** {client.get('tier')}")
                st.write(f"**Status:** {client.get('status')}")
            with col2:
                st.write(f"**Auto-Approve Threshold:** ₹{client.get('auto_approve_threshold', 1000):,.0f}")
                st.write(f"**Created:** {client.get('created_at', 'N/A')}")
                st.write(f"**API Key:** `{client.get('api_key', 'No key')}`")
            
            if st.button("Close Details"):
                st.session_state.selected_client = None
                st.rerun()
    else:
        st.info("No clients found. Add your first client!")

    
    


# 3. ALL INVOICES PAGE
elif page == "📄 All Invoices":
    st.title("📄 All Invoices")
    st.markdown("---")
    
    invoices = fetch_all_invoices()
    
    if invoices:
        df = pd.DataFrame(invoices)
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Filter by Status", ["All"] + list(df['status'].unique()))
        with col2:
            vendor_filter = st.selectbox("Filter by Vendor", ["All"] + list(df['vendor_name'].dropna().unique()))
        with col3:
            search = st.text_input("🔍 Search", placeholder="Invoice # or Vendor...")
        
        # Apply filters
        filtered_df = df.copy()
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df['status'] == status_filter]
        if vendor_filter != "All":
            filtered_df = filtered_df[filtered_df['vendor_name'] == vendor_filter]
        if search:
            filtered_df = filtered_df[
                filtered_df['invoice_number'].astype(str).str.contains(search, case=False, na=False) |
                filtered_df['vendor_name'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        st.caption(f"Showing {len(filtered_df)} invoices")
        
        # Display as table
        display_cols = ['id', 'invoice_number', 'vendor_name', 'total', 'status', 'category', 'created_at']
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        st.dataframe(filtered_df[display_cols], use_container_width=True)
    else:
        st.info("No invoices found")

# 4. ADD CLIENT PAGE
elif page == "➕ Add Client":
    st.title("➕ Add New Client")
    st.markdown("---")
    
    st.info("Fill in the details below to add a new client. An API key will be auto-generated.")
    
    with st.form("add_client_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            client_name = st.text_input("Client Name *", placeholder="Acme Corp")
            contact_email = st.text_input("Contact Email *", placeholder="admin@acme.com")
            billing_email = st.text_input("Billing Email", placeholder="finance@acme.com")
            
            # ========== NEW: Company Name for Branding ==========
            company_name = st.text_input("🏷️ Company Name (for dashboard)", 
                                         placeholder="Acme Corporation",
                                         help="This will appear on the client's dashboard")
            
            # ========== NEW: Logo Upload ==========
            logo_file = st.file_uploader("Upload Company Logo (PNG/JPG)", 
                                         type=['png', 'jpg', 'jpeg'],
                                         help="Upload your client's logo. It will appear on their dashboard.")
            if logo_file:
                st.image(logo_file, width=100, caption="Preview")
        
        with col2:
            tier = st.selectbox("Tier", ["starter", "professional", "enterprise"])
            auto_approve_threshold = st.number_input("Auto-Approval Threshold (₹)", min_value=0, value=5000)
            monthly_invoice_limit = st.number_input("Monthly Invoice Limit", min_value=1, value=100)
        
        notes = st.text_area("Notes (Optional)")
        
        submitted = st.form_submit_button("✅ Add Client")
        
        if submitted:
            if not client_name or not contact_email:
                st.error("Client Name and Contact Email are required!")
            else:
                # Prepare logo as base64
                logo_base64 = None
                if logo_file:
                    import base64
                    logo_base64 = base64.b64encode(logo_file.getvalue()).decode()
                
                # Prepare payload
                payload = {
                    "client_name": client_name,
                    "contact_email": contact_email,
                    "billing_email": billing_email or contact_email,
                    "tier": tier,
                    "auto_approve_threshold": auto_approve_threshold,
                    "monthly_invoice_limit": monthly_invoice_limit,
                    "company_name": company_name or client_name,  # Use client name if not provided
                    "logo_base64": logo_base64,
                    "notes": notes
                }
                
                # Send to backend
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/clients",
                        json=payload,
                        headers={"X-API-Key": st.secrets["ADMIN_API_KEY"]},
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ Client '{client_name}' added successfully!")
                        st.balloons()
                        
                        # Display the magic link
                        DASHBOARD_URL = "https://anik-molla-231-invoice-agency-dashboard-3xmcob.streamlit.app"
                        magic_link = f"{DASHBOARD_URL}?api_key={result.get('api_key')}"
                        st.info(f"🔗 Client Access Link: `{magic_link}`")
                        st.caption("Copy this link and send it to your client.")
                        
                        st.json(result)
                        st.cache_data.clear()
                    else:
                        st.error(f"❌ Failed: {response.text}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    
# 5. REVENUE PAGE
elif page == "💰 Revenue":
    st.title("💰 Revenue Analytics")
    st.markdown("---")
    
    invoices = fetch_all_invoices()
    
    if invoices:
        df = pd.DataFrame(invoices)
        
        # Convert to datetime
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['month'] = df['created_at'].dt.strftime('%Y-%m')
        
        # Approved/synced invoices only
        df_revenue = df[df['status'].isin(['approved', 'synced', 'paid'])]
        
        # Monthly revenue
        monthly_revenue = df_revenue.groupby('month')['total'].sum().reset_index()
        
        col1, col2 = st.columns(2)
        
        with col1:
            total_revenue = df_revenue['total'].sum()
            st.metric("Total Revenue", f"₹{total_revenue:,.2f}")
        
        with col2:
            avg_invoice = df_revenue['total'].mean() if len(df_revenue) > 0 else 0
            st.metric("Average Invoice", f"₹{avg_invoice:,.2f}")
        
        st.markdown("---")
        
        # Revenue chart
        if not monthly_revenue.empty:
            fig = px.line(
                monthly_revenue,
                x='month',
                y='total',
                title='Monthly Revenue Trend',
                labels={'month': 'Month', 'total': 'Revenue (₹)'},
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No revenue data yet")
        
        # Top vendors
        st.markdown("---")
        st.subheader("🏆 Top Vendors by Spend")
        
        top_vendors = df_revenue.groupby('vendor_name')['total'].sum().sort_values(ascending=False).head(10).reset_index()
        if not top_vendors.empty:
            fig = px.bar(
                top_vendors,
                x='vendor_name',
                y='total',
                title='Top 10 Vendors by Total Spend',
                labels={'vendor_name': 'Vendor', 'total': 'Total Spend (₹)'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No vendor data")
    else:
        st.info("No invoice data available")

# 6. SETTINGS PAGE
elif page == "⚙️ Settings":
    st.title("⚙️ System Settings")
    st.markdown("---")
    
    st.subheader("🔗 API Connection")
    st.code(API_BASE_URL)
    
    st.subheader("📊 Database Stats")
    
    try:
        invoices = fetch_all_invoices()
        clients = fetch_all_clients()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Invoices", len(invoices))
        with col2:
            st.metric("Total Clients", len(clients))
        with col3:
            st.metric("API Status", "✅ Online")
    except:
        st.error("Could not fetch stats")
    
    st.markdown("---")
    
    st.subheader("🔄 Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ Clear Cache"):
            st.cache_data.clear()
            st.success("✅ Cache cleared!")
    
    with col2:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    
    with col3:
        if st.button("📊 Generate Report"):
            st.info("📊 Report generation coming soon!")
    
    st.markdown("---")
    
    st.subheader("📋 System Info")
    
    try:
        import platform
        info = {
            "Python Version": platform.python_version(),
            "Platform": platform.platform(),
            "Current Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        st.json(info)
    except:
        st.info("System info not available")

# ------------------- RUN -------------------
if __name__ == "__main__":
    # Initialize session state
    if "selected_client" not in st.session_state:
        st.session_state.selected_client = None