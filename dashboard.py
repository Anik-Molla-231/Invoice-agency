# dashboard.py
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go


# ------------------- PAGE CONFIG -------------------
st.set_page_config(
    page_title="Invoice Agency Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------- API CONFIG -------------------
API_BASE_URL = "http://localhost:8000/api"  # Your FastAPI backend

# ------------------- SIDEBAR -------------------
st.sidebar.image("https://img.icons8.com/fluency/96/000000/invoice.png", width=80)
st.sidebar.title("📊 Invoice Agency")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigation",
    ["📈 Dashboard", "📄 Invoices", "📤 Upload Invoice", "💰 Yearly Spending", "📊 Monthly Spending", "⚙️ Settings"]
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Connected to: {API_BASE_URL}")
st.sidebar.caption(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ------------------- HELPER FUNCTIONS -------------------
@st.cache_data(ttl=60)  # Cache for 60 seconds
def fetch_invoices():
    """Fetch all invoices from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/invoices")
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Could not connect to API: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_spend_summary():
    """Fetch spend summary from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/spend-summary")
        if response.status_code == 200:
            return response.json()
        else:
            return {"total_spent": 0, "total_invoices": 0, "vendor_breakdown": []}
    except Exception as e:
        st.error(f"Could not connect to API: {e}")
        return {"total_spent": 0, "total_invoices": 0, "vendor_breakdown": []}

def approve_invoice(invoice_id):
    """Approve an invoice via API."""
    try:
        response = requests.post(f"{API_BASE_URL}/invoices/{invoice_id}/approve?approved_by=dashboard")
        if response.status_code == 200:
            st.success(f"✅ Invoice #{invoice_id} approved!")
            st.cache_data.clear()
            return True
        else:
            st.error(f"❌ Failed to approve: {response.text}")
            return False
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return False

def reject_invoice(invoice_id):
    """Reject an invoice via API."""
    try:
        response = requests.post(f"{API_BASE_URL}/invoices/{invoice_id}/reject?reason=Rejected from dashboard")
        if response.status_code == 200:
            st.success(f"❌ Invoice #{invoice_id} rejected!")
            st.cache_data.clear()
            return True
        else:
            st.error(f"❌ Failed to reject: {response.text}")
            return False
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return False

# ------------------- PAGE RENDERING -------------------

# 1. DASHBOARD PAGE
if page == "📈 Dashboard":
    st.title("📈 Dashboard")
    st.markdown("---")
    
    # Fetch data
    invoices = fetch_invoices()
    summary = fetch_spend_summary()
    
    # Filter out error invoices for metrics
    valid_invoices = [inv for inv in invoices if inv.get('total') is not None]
    
    # Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Invoices", len(valid_invoices))
    with col2:
        st.metric("Total Spend", f"${summary.get('total_spent', 0):,.2f}")
    with col3:
        pending = len([inv for inv in valid_invoices if inv.get('status') == 'pending_approval'])
        st.metric("Pending Approval", pending)
    with col4:
        approved = len([inv for inv in valid_invoices if inv.get('status') == 'approved'])
        st.metric("Approved", approved)
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Spend by Vendor")
        if summary.get('vendor_breakdown'):
            df_vendors = pd.DataFrame(summary['vendor_breakdown'])
            if not df_vendors.empty:
                fig = px.pie(df_vendors, values='total', names='vendor', title='Vendor Spend Distribution')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No vendor data available")
        else:
            st.info("No data to display")
    
    with col2:
        st.subheader("📈 Invoice Status Distribution")
        if valid_invoices:
            df_status = pd.DataFrame(valid_invoices)
            status_counts = df_status['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig = px.bar(status_counts, x='Status', y='Count', title='Invoice Status', color='Status')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data to display")
    
    # Recent Invoices Table
    st.markdown("---")
    st.subheader("📋 Recent Invoices")
    if valid_invoices:
        df_recent = pd.DataFrame(valid_invoices).sort_values('created_at', ascending=False).head(10)
        # Select relevant columns
        cols_to_show = ['id', 'invoice_number', 'vendor_name', 'total', 'status', 'created_at']
        df_recent = df_recent[[col for col in cols_to_show if col in df_recent.columns]]
        st.dataframe(df_recent, use_container_width=True)
    else:
        st.info("No invoices found. Upload your first invoice!")

# 2. INVOICES PAGE
elif page == "📄 Invoices":
    st.title("📄 All Invoices")
    st.markdown("---")
    
    invoices = fetch_invoices()
    
    if not invoices:
        st.info("No invoices found. Upload one to get started!")
        st.stop()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All"] + list(set([inv.get('status') for inv in invoices if inv.get('status')])))
    with col2:
        vendor_filter = st.selectbox("Filter by Vendor", ["All"] + list(set([inv.get('vendor_name') for inv in invoices if inv.get('vendor_name')])))
    with col3:
        search = st.text_input("🔍 Search", placeholder="Invoice # or Vendor...")
    
    # Apply filters
    filtered_invoices = invoices
    if status_filter != "All":
        filtered_invoices = [inv for inv in filtered_invoices if inv.get('status') == status_filter]
    if vendor_filter != "All":
        filtered_invoices = [inv for inv in filtered_invoices if inv.get('vendor_name') == vendor_filter]
    if search:
        filtered_invoices = [
            inv for inv in filtered_invoices 
            if search.lower() in str(inv.get('invoice_number', '')).lower() 
            or search.lower() in str(inv.get('vendor_name', '')).lower()
        ]
    
    st.caption(f"Showing {len(filtered_invoices)} invoices")
    
    # Display invoices with action buttons
    for inv in filtered_invoices:
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
            
            with col1:
                st.write(f"**#{inv.get('invoice_number', 'N/A')}**")
                st.caption(f"Vendor: {inv.get('vendor_name', 'Unknown')}")
            with col2:
                st.write(f"${inv.get('total', 0):,.2f}")
                st.caption(f"Created: {inv.get('created_at', '')[:10]}")
            with col3:
                status = inv.get('status', 'unknown')
                if status == 'approved':
                    st.success(f"✅ {status}")
                elif status == 'pending_approval':
                    st.warning(f"⏳ {status}")
                elif status == 'rejected':
                    st.error(f"❌ {status}")
                elif status == 'error':
                    st.error(f"⚠️ {status}")
                else:
                    st.info(f"📄 {status}")
            with col4:
                if inv.get('status') == 'pending_approval':
                    if st.button("✅ Approve", key=f"approve_{inv['id']}"):
                        approve_invoice(inv['id'])
                        st.rerun()
            with col5:
                if inv.get('status') == 'pending_approval':
                    if st.button("❌ Reject", key=f"reject_{inv['id']}"):
                        reject_invoice(inv['id'])
                        st.rerun()
        st.divider()

# 3. UPLOAD PAGE
elif page == "📤 Upload Invoice":
    st.title("📤 Upload Invoice")
    st.markdown("---")
    
    st.info("Upload a PDF invoice. The system will automatically extract, categorise, and process it.")
    
    uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'])
    
    if uploaded_file is not None:
        # Show file details
        st.write(f"📄 **File:** {uploaded_file.name}")
        st.write(f"📦 **Size:** {len(uploaded_file.getvalue()) / 1024:.2f} KB")
        
        if st.button("🚀 Process Invoice"):
            with st.spinner("Processing..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                    response = requests.post(f"{API_BASE_URL}/upload-invoice", files=files)
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success("✅ Invoice processed successfully!")
                        st.json(result)
                        st.cache_data.clear()
                    else:
                        st.error(f"❌ Failed: {response.text}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

# 4. SETTINGS PAGE
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    st.markdown("---")
    
    st.subheader("🔗 API Connection")
    st.code(API_BASE_URL)
    
    st.subheader("📊 Database Stats")
    try:
        response = requests.get(f"{API_BASE_URL}/invoices")
        if response.status_code == 200:
            st.metric("Total Invoices in DB", len(response.json()))
        else:
            st.error("Could not fetch stats")
    except Exception as e:
        st.error(f"Error: {e}")
    
    st.subheader("🔄 Actions")
    if st.button("🗑️ Clear Cache"):
        st.cache_data.clear()
        st.success("✅ Cache cleared!")

# Add this import at the top if not already present


# Helper function to format currency
def format_currency(amount):
    if amount >= 10000000:
        return f"₹{amount/10000000:.1f}Cr"
    elif amount >= 100000:
        return f"₹{amount/100000:.1f}L"
    else:
        return f"₹{amount:,.0f}"

# --- YEARLY SPENDING PAGE ---
if page == "💰 Yearly Spending":
    st.title("💰 Yearly Spending Analysis")
    st.markdown("---")
    
    try:
        response = requests.get(f"{API_BASE_URL}/spend-yearly")
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                yearly_data = data['data']
                
                # Display metrics
                total_spent = sum(item['total_spent'] for item in yearly_data)
                total_invoices = sum(item['invoice_count'] for item in yearly_data)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Spent (All Time)", format_currency(total_spent))
                with col2:
                    st.metric("Total Invoices", total_invoices)
                with col3:
                    avg_spent = total_spent / len(yearly_data) if yearly_data else 0
                    st.metric("Average Yearly Spend", format_currency(avg_spent))
                
                st.markdown("---")
                
                # Yearly breakdown table
                st.subheader("📋 Yearly Breakdown")
                
                df_yearly = pd.DataFrame(yearly_data)
                df_yearly['formatted_spent'] = df_yearly['total_spent'].apply(format_currency)
                
                # Create a bar chart
                fig = px.bar(
                    df_yearly,
                    x='year',
                    y='total_spent',
                    title='Yearly Spending Trend',
                    labels={'year': 'Year', 'total_spent': 'Total Spent'},
                    color='total_spent',
                    color_continuous_scale='Blues',
                    text=df_yearly['total_spent'].apply(lambda x: format_currency(x))
                )
                fig.update_traces(textposition='outside')
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # Display table
                st.dataframe(
                    df_yearly[['year', 'formatted_spent', 'invoice_count']].rename(
                        columns={'year': 'Year', 'formatted_spent': 'Total Spend', 'invoice_count': 'Invoice Count'}
                    ),
                    use_container_width=True
                )
                
                # Yearly analysis insights
                st.markdown("---")
                st.subheader("📈 Insights")
                
                if len(yearly_data) >= 2:
                    latest = yearly_data[0]['total_spent']
                    previous = yearly_data[1]['total_spent']
                    if latest > previous:
                        change = ((latest - previous) / previous * 100)
                        st.success(f"✅ Spending increased by {change:.1f}% from {yearly_data[1]['year']} to {yearly_data[0]['year']}")
                    else:
                        change = ((previous - latest) / previous * 100)
                        st.info(f"📉 Spending decreased by {change:.1f}% from {yearly_data[1]['year']} to {yearly_data[0]['year']}")
                
                if len(yearly_data) >= 3:
                    avg = sum(item['total_spent'] for item in yearly_data) / len(yearly_data)
                    latest = yearly_data[0]['total_spent']
                    if latest > avg:
                        st.success(f"📈 {yearly_data[0]['year']} spending (₹{latest:,.0f}) is above average (₹{avg:,.0f})")
                    else:
                        st.info(f"📉 {yearly_data[0]['year']} spending is below average")
            else:
                st.info("No yearly data available yet. Process some invoices first.")
        else:
            st.error(f"API Error: {response.status_code}")
    except Exception as e:
        st.error(f"Error: {e}")

# --- MONTHLY SPENDING PAGE ---
elif page == "📊 Monthly Spending":
    st.title("📊 Monthly Spending Analysis")
    st.markdown("---")
    
    # Get the latest year from the data
    try:
        response = requests.get(f"{API_BASE_URL}/spend-yearly")
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                yearly_data = data['data']
                if yearly_data:
                    # Get available years
                    available_years = sorted([item['year'] for item in yearly_data], reverse=True)
                    
                    # Year selector
                    selected_year = st.selectbox(
                        "📅 Select Year",
                        available_years,
                        index=0
                    )
                    
                    st.markdown("---")
                    
                    # Fetch monthly data for selected year
                    response2 = requests.get(f"{API_BASE_URL}/spend-monthly/{selected_year}")
                    if response2.status_code == 200:
                        monthly_data = response2.json()
                        
                        if monthly_data.get('success') and monthly_data.get('data'):
                            data = monthly_data['data']
                            
                            # Summary metrics
                            total_year = sum(item['total_spent'] for item in data)
                            total_invoices = sum(item['invoice_count'] for item in data)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric(f"Total Spend in {selected_year}", format_currency(total_year))
                            with col2:
                                st.metric("Total Invoices", total_invoices)
                            with col3:
                                avg_month = total_year / 12 if data else 0
                                st.metric("Average Monthly Spend", format_currency(avg_month))
                            
                            st.markdown("---")
                            
                            # Monthly chart
                            df_monthly = pd.DataFrame(data)
                            df_monthly['formatted_spent'] = df_monthly['total_spent'].apply(format_currency)
                            
                            # Bar chart
                            fig = px.bar(
                                df_monthly,
                                x='month',
                                y='total_spent',
                                title=f'Monthly Spending - {selected_year}',
                                labels={'month': 'Month', 'total_spent': 'Total Spend'},
                                color='total_spent',
                                color_continuous_scale='Greens',
                                text=df_monthly['total_spent'].apply(lambda x: format_currency(x))
                            )
                            fig.update_traces(textposition='outside')
                            fig.update_layout(height=400)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Monthly table
                            st.subheader("📋 Monthly Breakdown")
                            
                            # Highlight months with high spending
                            avg = total_year / 12
                            df_monthly['vs_avg'] = df_monthly['total_spent'].apply(
                                lambda x: f"🟢 {((x - avg) / avg * 100):.1f}%" if x > avg else f"🔴 {((x - avg) / avg * 100):.1f}%"
                            )
                            
                            st.dataframe(
                                df_monthly[['month', 'formatted_spent', 'invoice_count', 'vs_avg']].rename(
                                    columns={'month': 'Month', 'formatted_spent': 'Total Spend', 'invoice_count': 'Invoice Count', 'vs_avg': 'vs Average'}
                                ),
                                use_container_width=True
                            )
                            
                            # Insights
                            st.markdown("---")
                            st.subheader("📈 Monthly Insights")
                            
                            # Find highest and lowest spending months
                            max_month = max(data, key=lambda x: x['total_spent'])
                            min_month = min(data, key=lambda x: x['total_spent'])
                            
                            if max_month['total_spent'] > 0:
                                st.success(f"🚀 Highest spending month: **{max_month['month']}** ({format_currency(max_month['total_spent'])})")
                            if min_month['total_spent'] > 0:
                                st.info(f"📉 Lowest spending month: **{min_month['month']}** ({format_currency(min_month['total_spent'])})")
                            
                            # Check if Q4 is the highest
                            q4_months = ['October', 'November', 'December']
                            q4_total = sum(item['total_spent'] for item in data if item['month'] in q4_months)
                            q1_total = sum(item['total_spent'] for item in data if item['month'] in ['January', 'February', 'March'])
                            
                            if q4_total > q1_total:
                                st.info(f"💡 Q4 spending (₹{q4_total:,.0f}) is higher than Q1 (₹{q1_total:,.0f}) by {((q4_total - q1_total) / q1_total * 100):.1f}%")
                        else:
                            st.info(f"No data available for {selected_year}")
                    else:
                        st.error(f"API Error: {response2.status_code}")
                else:
                    st.info("No data available yet. Process some invoices first.")
            else:
                st.info("No data available yet. Process some invoices first.")
        else:
            st.error(f"API Error: {response.status_code}")
    except Exception as e:
        st.error(f"Error: {e}")