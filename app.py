"""
Legal Document Indexer - Streamlit Frontend
Run: streamlit run app.py
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime
import pandas as pd

# Configuration
API_BASE_URL = "http://localhost:8000"

# Page config
st.set_page_config(
    page_title="Legal Document Indexer",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #64748B;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #D1FAE5;
        border-left: 4px solid #10B981;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .error-box {
        background-color: #FEE2E2;
        border-left: 4px solid #EF4444;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .info-box {
        background-color: #DBEAFE;
        border-left: 4px solid #3B82F6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .warning-box {
        background-color: #FEF3C7;
        border-left: 4px solid #F59E0B;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .original-text {
        background-color: #FEF2F2;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #EF4444;
        margin: 0.5rem 0;
    }
    .suggested-text {
        background-color: #F0FDF4;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #10B981;
        margin: 0.5rem 0;
    }
    .document-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .status-pending {
        color: #F59E0B;
        font-weight: bold;
    }
    .status-processing {
        color: #3B82F6;
        font-weight: bold;
    }
    .status-completed {
        color: #10B981;
        font-weight: bold;
    }
    .status-failed {
        color: #EF4444;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'indexing_results' not in st.session_state:
    st.session_state.indexing_results = []
if 'last_job_result' not in st.session_state:
    st.session_state.last_job_result = None
if 'confirm_delete' not in st.session_state:
    st.session_state.confirm_delete = False

# Helper Functions
def api_call(method, endpoint, **kwargs):
    """Make API request with error handling"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = requests.request(method, url, timeout=30, **kwargs)
        return response
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Cannot connect to API at {API_BASE_URL}. Make sure the backend is running!")
        return None
    except requests.exceptions.Timeout:
        st.error("❌ Request timeout. The server took too long to respond.")
        return None
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return None

def poll_job_with_details(job_id, job_type="indexing", max_wait=300):
    """Poll job with detailed progress tracking"""
    start = time.time()
    
    # Create containers for dynamic updates
    progress_container = st.container()
    status_container = st.container()
    details_container = st.container()
    
    with progress_container:
        progress_bar = st.progress(0)
        progress_text = st.empty()
    
    with status_container:
        status_text = st.empty()
    
    last_status = None
    
    while time.time() - start < max_wait:
        resp = api_call("GET", f"/job/{job_id}")
        
        if resp and resp.status_code == 200:
            job = resp.json()
            status = job.get('status')
            elapsed = int(time.time() - start)
            
            # Update progress bar
            if status == 'pending':
                progress = 0.1
            elif status == 'processing':
                progress = min(0.5 + (elapsed / max_wait * 0.4), 0.9)
            elif status == 'completed':
                progress = 1.0
            else:
                progress = min(elapsed / max_wait, 0.99)
            
            progress_bar.progress(progress)
            progress_text.text(f"⏱️ Elapsed Time: {elapsed}s")
            
            # Update status
            if status != last_status:
                last_status = status
                
                if status == 'pending':
                    status_text.markdown('<div class="status-pending">⏳ PENDING - Job queued</div>', unsafe_allow_html=True)
                elif status == 'processing':
                    status_text.markdown('<div class="status-processing">🔄 PROCESSING - Working on it...</div>', unsafe_allow_html=True)
                elif status == 'completed':
                    status_text.markdown('<div class="status-completed">✅ COMPLETED - Job finished successfully!</div>', unsafe_allow_html=True)
                elif status == 'failed':
                    status_text.markdown('<div class="status-failed">❌ FAILED - Job encountered an error</div>', unsafe_allow_html=True)
            
            # Show job details
            if status == 'completed':
                result = job.get('result', {})
                
                with details_container:
                    if job_type == "indexing":
                        st.markdown("### 📊 Indexing Results")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("✅ Successfully Indexed", result.get('indexed', 0))
                        with col2:
                            st.metric("❌ Failed", result.get('failed', 0))
                        
                        # Show failed URLs
                        failed_urls = result.get('failed_urls', [])
                        if failed_urls:
                            st.markdown("#### ⚠️ Failed Documents")
                            for failed in failed_urls:
                                st.markdown(f"""
                                <div class="error-box">
                                    <strong>URL:</strong> {failed['url']}<br>
                                    <strong>Error:</strong> {failed['error']}
                                </div>
                                """, unsafe_allow_html=True)
                    
                    elif job_type == "flagging":
                        st.markdown("### 📊 Flagging Results")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("🔍 Documents Found", result.get('total_found', 0))
                        with col2:
                            st.metric("✅ Validated", result.get('validated', 0))
                        with col3:
                            st.metric("🚩 Flagged", result.get('flagged', 0))
                        with col4:
                            st.metric("📝 Analyzed", result.get('analyzed', 0))
                        
                        # Show flagged documents summary
                        flagged_docs = result.get('flagged_documents', [])
                        if flagged_docs:
                            st.markdown("#### 🚩 Flagged Documents")
                            for doc in flagged_docs:
                                st.markdown(f"""
                                <div class="success-box">
                                    <strong>📄 {doc['title']}</strong><br>
                                    <strong>URL:</strong> <a href="{doc['url']}" target="_blank">{doc['url']}</a><br>
                                    <strong>Suggestions:</strong> {doc['suggestions_count']}
                                </div>
                                """, unsafe_allow_html=True)
                        
                        st.info("👉 Go to '📋 Results' page to view detailed suggestions")
                
                return job
            
            elif status == 'failed':
                error = job.get('error', 'Unknown error')
                with details_container:
                    st.markdown(f"""
                    <div class="error-box">
                        <strong>Error Details:</strong><br>
                        {error}
                    </div>
                    """, unsafe_allow_html=True)
                return job
        
        time.sleep(2)
    
    status_text.warning("⚠️ Job timeout - took too long to complete")
    return None

# Sidebar
st.sidebar.markdown("## ⚖️ Legal Document Indexer")
st.sidebar.markdown("Navigate through the application")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "📑 Pages",
    ["🏠 Home", "📚 Index Documents", "🔍 Flag Documents", "📋 View Results", "📊 Statistics"],
    label_visibility="collapsed"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔗 System Status")

# Check API health
health = api_call("GET", "/health")
if health and health.status_code == 200:
    health_data = health.json()
    st.sidebar.success("✅ API Online")
    
    stats = health_data.get('stats', {})
    st.sidebar.metric("📦 Total Chunks", f"{stats.get('total_chunks', 0):,}")
    st.sidebar.metric("📄 Total Documents", f"{stats.get('total_documents', 0):,}")
    st.sidebar.metric("🚩 Flagged", f"{stats.get('total_flagged', 0):,}")
else:
    st.sidebar.error("❌ API Offline")
    st.sidebar.warning("Make sure backend is running:\n```\ndocker-compose up\n```")

# HOME PAGE
if page == "🏠 Home":
    st.markdown('<div class="main-header">⚖️ Legal Document Indexer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AI-powered legal document analysis and compliance tracking</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="info-box">
            <h3>📚 Index Documents</h3>
            <p>Upload and index legal documents from URLs. Supports webpages and PDFs with semantic search capabilities.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-box">
            <h3>🔍 Flag Documents</h3>
            <p>Identify documents affected by law changes. Get AI-powered suggestions for updates.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="info-box">
            <h3>📋 View Results</h3>
            <p>Review flagged documents with side-by-side comparisons of original vs suggested changes.</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("### 🚀 Quick Start Guide")
    
    st.markdown("""
    #### Step 1: Index Documents 📚
    - Navigate to "📚 Index Documents"
    - Enter URLs (one per line) of legal documents
    - Click "🚀 Start Indexing"
    - Wait for indexing to complete
    - Review indexed documents
    
    #### Step 2: Flag Documents 🔍
    - Navigate to "🔍 Flag Documents"
    - Enter the law name (e.g., "Illinois Domestic Violence Act")
    - **Optional:** Describe what changed in the law
      - If provided: Get specific change suggestions
      - If not provided: Just flag documents that reference the law
    - Click "🔍 Start Flagging"
    
    #### Step 3: Review Results 📋
    - Navigate to "📋 View Results"
    - See flagged documents with:
      - Original text from document
      - Suggested changes (if "what changed" was provided)
      - Issue explanations
      - Confidence scores
    - Update status (Flagged → Reviewed → Updated)
    - Download results as JSON or CSV
    
    #### Features:
    - ✅ **Hybrid Search**: Combines semantic understanding + keyword matching
    - ✅ **AI Validation**: Removes false positives automatically
    - ✅ **Smart Suggestions**: Only when you provide "what changed"
    - ✅ **Side-by-Side View**: Original vs suggested text
    - ✅ **Status Tracking**: Flag → Review → Update workflow
    - ✅ **Export**: Download results in JSON/CSV format
    """)

# INDEX PAGE
elif page == "📚 Index Documents":
    st.markdown('<div class="main-header">📚 Index Documents</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Add legal documents to the system for analysis</div>', unsafe_allow_html=True)
    
    st.markdown("### 📝 Enter Document URLs")
    st.info("💡 Add one URL per line. Supports HTML webpages and PDF documents.")
    
    urls_input = st.text_area(
        "Document URLs",
        height=200,
        placeholder="https://www.example.com/legal-doc-1.html\nhttps://www.example.com/legal-doc-2.pdf\nhttps://www.example.com/legal-doc-3.html",
        label_visibility="collapsed",
        help="Enter URLs of legal documents to index. One URL per line."
    )
    
    # Show example
    with st.expander("📖 See Example URLs"):
        st.code("""https://www.illinoislegalaid.org/legal-information/getting-domestic-violence-order-protection
https://www.illinoislegalaid.org/legal-information/written-eviction-notices
https://www.example.com/legal-document.pdf""")
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        index_button = st.button("🚀 Start Indexing", type="primary", use_container_width=True)
    
    with col2:
        clear_button = st.button("🗑️ Clear All Data", use_container_width=True)
    
    with col3:
        if st.session_state.indexing_results:
            if st.button("🔄 Clear Results", use_container_width=True):
                st.session_state.indexing_results = []
                st.rerun()
    
    # Handle indexing
    # Handle indexing
    if index_button:
        urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
        
        if not urls:
            st.error("❌ Please enter at least one URL")
        else:
            st.markdown(f"### 🚀 Indexing {len(urls)} Documents")
            st.markdown("---")
            
            resp = api_call("POST", "/index/bulk", json={"urls": urls})
            
            # DEBUG: Show response details
            if resp:
                st.write(f"DEBUG - Status Code: {resp.status_code}")
                st.write(f"DEBUG - Response: {resp.text}")
            
            if resp and resp.status_code in [200, 202]:
                job_data = resp.json()
                job_id = job_data.get('job_id')
                
                st.markdown(f"""
                <div class="info-box">
                    <strong>Job Started</strong><br>
                    Job ID: <code>{job_id}</code>
                </div>
                """, unsafe_allow_html=True)
                
                # Poll job with detailed tracking
                result = poll_job_with_details(job_id, job_type="indexing", max_wait=600)
                
                if result:
                    st.session_state.last_job_result = result
            else:
                if resp:
                    st.error(f"❌ Failed to start indexing job - Status Code: {resp.status_code}")
                    st.error(f"Response: {resp.text}")
                else:
                    st.error("❌ Failed to start indexing job - No response from server")
    
    # Handle clear all
    if clear_button:
        if st.session_state.confirm_delete:
            with st.spinner("🗑️ Clearing all data..."):
                resp = api_call("DELETE", "/reset")
                if resp and resp.status_code == 200:
                    result = resp.json()
                    st.success("✅ All data cleared successfully!")
                    st.json(result)
                    st.session_state.confirm_delete = False
                    time.sleep(2)
                    st.rerun()
        else:
            st.session_state.confirm_delete = True
            st.warning("⚠️ **Are you sure?** This will delete ALL indexed documents and flags. Click 'Clear All Data' again to confirm.")
    
    # Show previously indexed documents
    if health and health.status_code == 200:
        stats = health.json().get('stats', {})
        if stats.get('total_documents', 0) > 0:
            st.markdown("---")
            st.markdown(f"### 📚 System Summary")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Total Documents", stats.get('total_documents', 0))
            with col2:
                st.metric("📦 Total Chunks", stats.get('total_chunks', 0))
            with col3:
                avg_chunks = stats.get('total_chunks', 0) / max(stats.get('total_documents', 1), 1)
                st.metric("📊 Avg Chunks/Doc", f"{avg_chunks:.1f}")

# FLAG PAGE
elif page == "🔍 Flag Documents":
    st.markdown('<div class="main-header">🔍 Flag Documents</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Identify documents affected by law changes</div>', unsafe_allow_html=True)
    
    st.markdown("### 1️⃣ Enter Law Name")
    law_name = st.text_input(
        "Law Name",
        placeholder="e.g., Illinois Domestic Violence Act",
        help="Enter the exact or partial name of the law that changed",
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 2️⃣ What Changed? (Optional)")
    
    st.markdown("""
    <div class="info-box">
        <strong>💡 Important:</strong><br>
        • <strong>If you provide details:</strong> System will generate specific suggestions for updating documents<br>
        • <strong>If you skip this:</strong> System will only flag documents that reference the law (no suggestions)
    </div>
    """, unsafe_allow_html=True)
    
    what_changed = st.text_area(
        "What Changed in the Law",
        height=150,
        placeholder="""Example:

Section 103(14) was amended to expand the definition of 'abuse' to explicitly include coercive control, defined as a pattern of behavior that unreasonably interferes with a person's free will and personal liberty.

Section 214(b)(1) now requires judges to specifically inquire about the presence of tracking devices during Order of Protection hearings.""",
        label_visibility="collapsed",
        help="Describe what changed in the law. Be specific about sections, definitions, or requirements."
    )
    
    st.markdown("---")
    st.markdown("### 3️⃣ Search Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        threshold = st.slider(
            "Semantic Search Threshold",
            min_value=0.1,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help="Lower = more results (less strict), Higher = fewer results (more strict)"
        )
    
    with col2:
        st.markdown(f"""
        <div class="info-box" style="margin-top: 1.5rem;">
            <strong>Current Setting:</strong> {threshold}<br>
            {"🔍 Strict - High precision" if threshold > 0.7 else "🎯 Balanced - Recommended" if threshold > 0.4 else "📡 Broad - High recall"}
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    if st.button("🔍 Start Flagging", type="primary", use_container_width=True):
        if not law_name:
            st.error("❌ Please enter a law name")
        else:
            st.markdown(f"### 🔍 Searching for '{law_name}'")
            st.markdown("---")
            
            payload = {
                "changed_law": law_name,
                "similarity_threshold": threshold
            }
            
            if what_changed.strip():
                payload["what_changed"] = what_changed.strip()
                st.info("📝 Analysis mode: Will generate change suggestions")
            else:
                st.info("🔍 Flag-only mode: Will identify referencing documents only")
            
            resp = api_call("POST", "/flag", json=payload)
            
            if resp and resp.status_code == 200:
                job_data = resp.json()
                job_id = job_data.get('job_id')
                
                st.markdown(f"""
                <div class="info-box">
                    <strong>Job Started</strong><br>
                    Job ID: <code>{job_id}</code>
                </div>
                """, unsafe_allow_html=True)
                
                # Poll job with detailed tracking
                result = poll_job_with_details(job_id, job_type="flagging", max_wait=600)
                
                if result and result.get('status') == 'completed':
                    st.balloons()
            else:
                st.error("❌ Failed to start flagging job")

# RESULTS PAGE
elif page == "📋 View Results":
    st.markdown('<div class="main-header">📋 View Results</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Review flagged documents and suggestions</div>', unsafe_allow_html=True)
    
    # Filters
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown("### 🔍 Filters")
    
    with col2:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "flagged", "reviewed", "updated"],
            label_visibility="collapsed"
        )
    
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # Fetch flagged documents
    endpoint = "/flagged" if status_filter == "All" else f"/flagged?status={status_filter}"
    resp = api_call("GET", endpoint)
    
    if resp and resp.status_code == 200:
        data = resp.json()
        docs = data.get('flagged_documents', [])
        
        st.markdown(f"### Found {len(docs)} Documents")
        
        if not docs:
            st.markdown("""
            <div class="info-box">
                <strong>No flagged documents found</strong><br>
                Go to '🔍 Flag Documents' to start flagging documents.
            </div>
            """, unsafe_allow_html=True)
        else:
            for idx, doc in enumerate(docs, 1):
                with st.expander(f"📄 {idx}. {doc.get('title', 'Untitled')}", expanded=(idx == 1)):
                    # Document header
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown(f"**Document ID:** `{doc.get('document_id', 'N/A')[:12]}...`")
                        st.markdown(f"**URL:** [{doc.get('url', 'N/A')}]({doc.get('url', '#')})")
                    
                    with col2:
                        status = doc.get('status', 'flagged')
                        status_color = {'flagged': '🟡', 'reviewed': '🔵', 'updated': '🟢'}
                        st.markdown(f"**Status:** {status_color.get(status, '⚪')} `{status.upper()}`")
                        st.markdown(f"**Confidence:** {doc.get('confidence', 0):.0%}")
                    
                    with col3:
                        st.markdown(f"**Flagged For:** {doc.get('flagged_for_law', 'N/A')}")
                        flagged_at = doc.get('flagged_at', '')
                        if flagged_at:
                            st.markdown(f"**Flagged At:** {flagged_at[:19].replace('T', ' ')}")
                    
                    st.markdown("---")
                    
                    # What changed section
                    what_changed = doc.get('what_changed')
                    if what_changed:
                        st.markdown("#### 📋 Law Change Details")
                        st.markdown(f"""
                        <div class="info-box">
                            {what_changed}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Suggestions section
                    suggestions = doc.get('change_suggestions', [])
                    
                    if suggestions:
                        st.markdown(f"#### 💡 Change Suggestions ({len(suggestions)})")
                        
                        for i, sug in enumerate(suggestions, 1):
                            st.markdown(f"##### 📝 Suggestion {i}")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**📖 Original Section from Document**")
                                st.markdown(
                                    f'<div class="original-text">{sug.get("section_text", "N/A")}</div>',
                                    unsafe_allow_html=True
                                )
                            
                            with col2:
                                st.markdown("**✅ Suggested Change**")
                                st.markdown(
                                    f'<div class="suggested-text">{sug.get("suggested_change", "N/A")}</div>',
                                    unsafe_allow_html=True
                                )
                            
                            st.markdown(f"""
                            <div class="warning-box">
                                <strong>⚠️ Issue Identified:</strong> {sug.get('issue', 'N/A')}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            st.markdown(f"**🎯 Confidence Score:** {sug.get('confidence', 0):.0%}")
                            
                            if i < len(suggestions):
                                st.markdown("---")
                    else:
                        if what_changed:
                            st.markdown("""
                            <div class="warning-box">
                                <strong>No suggestions generated</strong><br>
                                The AI analysis determined that this document may not require updates for this law change.
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown("""
                            <div class="info-box">
                                <strong>ℹ️ No analysis performed</strong><br>
                                This document was flagged as referencing the law, but no "what changed" details were provided, so no suggestions were generated.<br><br>
                                To get suggestions, flag the document again with "what changed" details.
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # Actions
                    st.markdown("---")
                    st.markdown("#### 🎯 Actions")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button(f"✅ Mark as Reviewed", key=f"review_{doc.get('document_id')}", use_container_width=True):
                            update_resp = api_call(
                                "POST",
                                "/flag/status",
                                json={
                                    "document_id": doc.get('document_id'),
                                    "status": "reviewed"
                                }
                            )
                            if update_resp and update_resp.status_code == 200:
                                st.success("✅ Marked as reviewed")
                                time.sleep(1)
                                st.rerun()
                    
                    with col2:
                        if st.button(f"🎉 Mark as Updated", key=f"update_{doc.get('document_id')}", use_container_width=True):
                            update_resp = api_call(
                                "POST",
                                "/flag/status",
                                json={
                                    "document_id": doc.get('document_id'),
                                    "status": "updated"
                                }
                            )
                            if update_resp and update_resp.status_code == 200:
                                st.success("✅ Marked as updated")
                                time.sleep(1)
                                st.rerun()
                    
                    with col3:
                        if st.button(f"🗑️ Unflag", key=f"unflag_{doc.get('document_id')}", use_container_width=True):
                            unflag_resp = api_call(
                                "POST",
                                "/unflag",
                                json={"document_ids": [doc.get('document_id')]}
                            )
                            if unflag_resp and unflag_resp.status_code == 200:
                                st.success("✅ Unflagged")
                                time.sleep(1)
                                st.rerun()
            
            # Download section
            st.markdown("---")
            st.markdown("### 📥 Download Results")
            
            col1, col2 = st.columns(2)
            
            with col1:
                json_data = json.dumps({"flagged_documents": docs}, indent=2)
                st.download_button(
                    label="📄 Download as JSON",
                    data=json_data,
                    file_name=f"flagged_documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            
            with col2:
                csv_rows = []
                for d in docs:
                    csv_rows.append({
                        'Title': d.get('title'),
                        'URL': d.get('url'),
                        'Status': d.get('status'),
                        'Law': d.get('flagged_for_law'),
                        'Suggestions': len(d.get('change_suggestions', [])),
                        'Confidence': f"{d.get('confidence', 0):.0%}"
                    })
                
                if csv_rows:
                    df = pd.DataFrame(csv_rows)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📊 Download as CSV",
                        data=csv,
                        file_name=f"flagged_documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

# STATISTICS PAGE
elif page == "📊 Statistics":
    st.markdown('<div class="main-header">📊 Statistics</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">System overview and analytics</div>', unsafe_allow_html=True)
    
    health_resp = api_call("GET", "/health")
    flagged_resp = api_call("GET", "/flagged")
    
    if health_resp and health_resp.status_code == 200:
        stats = health_resp.json().get('stats', {})
        
        # Key metrics
        st.markdown("### 📈 Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📦 Total Chunks", f"{stats.get('total_chunks', 0):,}")
        
        with col2:
            st.metric("📄 Total Documents", f"{stats.get('total_documents', 0):,}")
        
        with col3:
            st.metric("🚩 Flagged Documents", f"{stats.get('total_flagged', 0):,}")
        
        if flagged_resp and flagged_resp.status_code == 200:
            flagged_data = flagged_resp.json()
            flagged_docs = flagged_data.get('flagged_documents', [])
            
            total_suggestions = sum(len(doc.get('change_suggestions', [])) for doc in flagged_docs)
            
            with col4:
                st.metric("💡 Total Suggestions", f"{total_suggestions:,}")
            
            st.markdown("---")
            
            # Status breakdown
            st.markdown("### 📊 Status Breakdown")
            status_counts = {}
            for doc in flagged_docs:
                status = doc.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            if status_counts:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🟡 Flagged", status_counts.get('flagged', 0))
                with col2:
                    st.metric("🔵 Reviewed", status_counts.get('reviewed', 0))
                with col3:
                    st.metric("🟢 Updated", status_counts.get('updated', 0))
            
            st.markdown("---")
            
            # Law breakdown
            st.markdown("### ⚖️ Documents by Law")
            law_counts = {}
            for doc in flagged_docs:
                law = doc.get('flagged_for_law', 'Unknown')
                law_counts[law] = law_counts.get(law, 0) + 1
            
            if law_counts:
                df = pd.DataFrame(list(law_counts.items()), columns=['Law', 'Documents'])
                st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Confidence distribution
            st.markdown("### 🎯 Confidence Score Distribution")
            if flagged_docs:
                confidences = [doc.get('confidence', 0) for doc in flagged_docs]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📊 Average Confidence", f"{avg_conf:.0%}")
                with col2:
                    st.metric("⬆️ Highest", f"{max(confidences):.0%}")
                with col3:
                    st.metric("⬇️ Lowest", f"{min(confidences):.0%}")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #64748B; padding: 1rem;'>
        <strong>Legal Document Indexer v2.0</strong><br>
        Built with ❤️ using FastAPI + Streamlit<br>
        <small>Powered by OpenAI GPT-4o-mini & ChromaDB</small>
    </div>
    """,
    unsafe_allow_html=True
)