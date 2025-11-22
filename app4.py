import streamlit as st
import requests
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
import cloudinary
import cloudinary.uploader
import time    
import re
import html as html_lib
from streamlit_autorefresh import st_autorefresh
import urllib.parse

st.set_page_config(layout="wide")


cloudinary.config(
  cloud_name = st.secrets["CLOUD_NAME"],
  api_key = st.secrets["API_KEY"],
  api_secret = st.secrets["API_SECRET"]
)


def upload_image_to_cloudinary(file_bytes, filename):
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=filename,
            resource_type="auto"  # <-- This allows both images and videos
        )
        return result['secure_url']
    except Exception as e:
        raise Exception("Upload to Cloudinary failed: " + str(e))


# ------------------ Session State ------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = {}

# ------------------ Airtable Functions ------------------

@st.cache_data(ttl=3600000000000000000000000000000) # 1 hour
def fetch_requests():
    url = f"https://api.airtable.com/v0/{BASE_ID}/Request"
    headers = {"Authorization": f"Bearer {AIRTABLE_PAT}", "Content-Type": "application/json"}
    res = requests.get(url, headers=headers)
    if res.ok:
        return res.json()["records"]
    return []


@st.cache_data(ttl=360000000000000000000000000000)  # Cache for 1 hour
def fetch_services():
    url = f"https://api.airtable.com/v0/{BASE_ID}/Talent"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }
    res = requests.get(url, headers=headers)
    if res.ok:
        return res.json()["records"]
    return []


@st.cache_data(ttl=360000000000000000)  # Cache for 1 hour
def fetch_users():
    res = requests.get(AIRTABLE_URL, headers=HEADERS)
    if res.ok:
        return res.json()["records"]
    st.error("❌ Couldn't load users.")
    return []

@st.cache_data(ttl=3600000000000000000000000000000000)  # Cache for 30 minutes
def get_users_dict():
    """Create a dictionary of users keyed by email for faster lookup"""
    users = fetch_users()
    users_dict = {}
    for u in users:
        f = u.get("fields", {})
        email = f.get("Email")
        if email:
            users_dict[email] = {"id": u["id"], **f}
    return users_dict

def find_user(email, password):
    # Check if user is already in session state
    if "user_cache" in st.session_state:
        cached_user = st.session_state.user_cache.get(email)
        if cached_user and cached_user.get("Password") == password:
            return cached_user
    
    # If not in session, fetch from Airtable
    users_dict = get_users_dict()
    user = users_dict.get(email)
    if user and user.get("Password") == password:
        # Cache in session state
        if "user_cache" not in st.session_state:
            st.session_state.user_cache = {}
        st.session_state.user_cache[email] = user
        return user
    return None

def format_time_ago(iso_time_str):
    msg_time = datetime.fromisoformat(iso_time_str.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    diff = now - msg_time

    seconds = int(diff.total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if seconds < 60:
        return f"{seconds} seconds ago"
    elif minutes < 60:
        return f"{minutes} minutes ago"
    elif hours < 24:
        return f"{hours} hours ago"
    else:
        return f"{days} days ago"
# ------------------ Config ------------------
AIRTABLE_PAT = st.secrets["AIRTABLE_PAT"]
BASE_ID = st.secrets["BASE_ID"]
TABLE_NAME = st.secrets["TABLE_NAME"]
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_PAT}", "Content-Type": "application/json"}

# ------------------ Session State ------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = {}
    

# ------------------ Airtable Functions ------------------
def fetch_users():
    res = requests.get(AIRTABLE_URL, headers=HEADERS)
    if res.ok:
        return res.json()["records"]
    st.error("❌ Couldn't load users.")
    return []

def find_user(email, password):
    users = fetch_users()
    for u in users:
        f = u.get("fields", {})
        if f.get("Email") == email and f.get("Password") == password:
            return {"id": u["id"], **f}
    return None

def upsert_user(data, record_id=None):
    payload = {"fields": data}
    if record_id:
        url = f"{AIRTABLE_URL}/{record_id}"
        res = requests.patch(url, headers=HEADERS, json=payload)
    else:
        res = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)
    # Debugging line
    if not res.ok:
        st.error(f"❌ Airtable Error: {res.status_code} - {res.text}")
    return res.ok

# chat section

def fetch_messages(user_name, contact_name):
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/Chats"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_PAT}",
            "Content-Type": "application/json"
        }
        filter_formula = (
        f"OR("
        f"AND(Sender='{user_name}', Recipient='{contact_name}'),"
        f"AND(Sender='{contact_name}', Recipient='{user_name}')"
        f")"
        )
        params = {
            "filterByFormula": filter_formula,
            "sort[0][field]": "Timestamp",
            "sort[0][direction]": "asc"
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise exception for bad status codes
        return response.json().get("records", [])

    except Exception as e:
        st.error("😕 Unable to load messages. Please check your internet connection and try again.")
        return []

def send_message(sender_name, recipient_name, message):
    url = f"https://api.airtable.com/v0/{BASE_ID}/Chats"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "Sender": sender_name,
            "Recipient": recipient_name,
            "Message": message,
            "Read" : False
            
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Raise error if status is not 2xx
        return True
    except requests.exceptions.RequestException as e:
        st.error("😔 Message couldn't be sent. Please check your connection and try again.")
        return False

def fetch_received_messages(current_user_name):
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/Chats"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_PAT}",
            "Content-Type": "application/json"
        }

        filter_formula = f"Recipient='{current_user_name}'"

        params = {
            "filterByFormula": filter_formula,
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("records", [])

    except Exception as e:
        st.error("😕 Unable to load your messages. Please check your connection and try again.")
        return []

# forgot password-chidi idea
def send_password_email(to_email, password):
    msg = EmailMessage()
    msg.set_content(f"Your LinkUp password is: {password}")
    msg["Subject"] = "LinkUp Password Reset"
    msg["From"] = st.secrets["EMAIL_ADDRESS"]
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_APP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False
# ------------------ Pages ------------------
# ------------------ LinkUp Homepage ------------------
def show_home():
    # Clean, modern CSS
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    /* Main Styles */
    .main-container {
        font-family: 'Inter', sans-serif;
        max-width: 1200px;
        margin: 0 auto;
        padding: 2rem;
    }
    
    /* Hero Section */
    .hero-section{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:3.5rem 2rem;border-radius:0 0 30px 30px;margin-bottom:3rem;position:relative;overflow:hidden}
    .hero-section::before{content:'';position:absolute;top:0;left:0;right:0;bottom:0;background:url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 120"><path d="M0,50 Q300,0 600,50 T1200,50 L1200,120 L0,120 Z" fill="rgba(255,255,255,0.1)"/></svg>') bottom/cover no-repeat;opacity:0.3}
    .hero-content{max-width:900px;margin:0 auto;text-align:center;position:relative;z-index:2}
    .hero-title{font-size:3rem;font-weight:800;color:#ffffff;margin-bottom:1rem;text-shadow:2px 4px 8px rgba(0,0,0,0.2)}
    .hero-subtitle{font-size:1.3rem;color:#f0f4ff;margin-bottom:1.5rem;font-weight:500}
    .hero-cta{background:rgba(255,255,255,0.95);color:#667eea;padding:0.8rem 2rem;border-radius:50px;font-weight:700;font-size:1.1rem;display:inline-block;margin-top:1rem;box-shadow:0 8px 20px rgba(0,0,0,0.15)}
    
    /* Eye-Catching Navigation Alert */
    .nav-alert-box {
        background: #ff3333;
        background: linear-gradient(135deg, #ff3333 0%, #ff6666 100%);
        padding: 1.8rem 2.5rem;
        border-radius: 20px;
        backdrop-filter: blur(10px);
        display: inline-block;
        margin: 2rem auto;
        border: 4px solid white;
        box-shadow: 0 10px 40px rgba(255,51,51,0.5);
        animation: pulse-attention 2s ease-in-out infinite;
        position: relative;
    }
    
    @keyframes pulse-attention {
        0%, 100% {
            transform: scale(1);
            box-shadow: 0 10px 40px rgba(255,51,51,0.5);
        }
        50% {
            transform: scale(1.03);
            box-shadow: 0 15px 50px rgba(255,51,51,0.7);
        }
    }
    
    .nav-alert-emoji {
        font-size: 2.5rem;
        display: inline-block;
        animation: wave 1s ease-in-out infinite;
    }
    
    @keyframes wave {
        0%, 100% { transform: rotate(0deg); }
        25% { transform: rotate(-15deg); }
        75% { transform: rotate(15deg); }
    }
    
    .nav-alert-text {
        color: white;
        font-size: 1.4rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        line-height: 1.8;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .nav-alert-text strong {
        font-size: 1.6rem;
        background: white;
        color: #ff3333;
        padding: 0.2rem 0.8rem;
        border-radius: 8px;
        display: inline-block;
        margin: 0 0.3rem;
    }
    
    .nav-alert-container {
        text-align: center;
        margin: 2rem 0;
    }
    
    /* Stats Bar */
    .stats-bar{background:white;padding:1.5rem;border-radius:20px;box-shadow:0 4px 15px rgba(0,0,0,0.08);margin:-2rem 2rem 3rem 2rem;position:relative;z-index:3;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:2rem;text-align:center}
    .stat-item{padding:0.5rem}
    .stat-number{font-size:2rem;font-weight:800;color:#667eea;margin-bottom:0.3rem}
    .stat-label{color:#718096;font-size:0.95rem;font-weight:500}
    
    /* Search Section */
    .search-section{max-width:800px;margin:0 auto 3rem auto;padding:0 2rem}
    .search-title{font-size:1.8rem;font-weight:700;color:#2d3748;text-align:center;margin-bottom:1.5rem}
    .search-box{background:white;padding:1rem;border-radius:15px;box-shadow:0 4px 15px rgba(0,0,0,0.08);display:flex;gap:1rem;align-items:center}
    .search-input{flex:1;padding:0.8rem 1.2rem;border:2px solid #e2e8f0;border-radius:10px;font-size:1rem}
    .search-btn{background:#667eea;color:white;padding:0.8rem 2rem;border-radius:10px;font-weight:600;border:none;cursor:pointer}
    
    /* Categories Grid */
    .categories-section{padding:0 2rem;margin-bottom:3rem}
    .section-header{font-size:2rem;font-weight:700;color:#2d3748;margin-bottom:2rem;text-align:center}
    .categories-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;max-width:1200px;margin:0 auto}
    .category-card{background:white;padding:2rem 1.5rem;border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,0.08);transition:all 0.3s ease;cursor:pointer;text-align:center;border:2px solid transparent}
    .category-card:hover{transform:translateY(-5px);box-shadow:0 8px 25px rgba(102,126,234,0.15);border-color:#667eea}
    .category-icon{font-size:3rem;margin-bottom:1rem;display:inline-block}
    .category-name{font-size:1.2rem;font-weight:700;color:#2d3748;margin-bottom:0.5rem}
    .category-count{color:#718096;font-size:0.9rem;font-weight:500}
    
    /* How It Works */
    .how-section{background:linear-gradient(135deg,#f7fafc 0%,#edf2f7 100%);padding:3rem 2rem;margin:3rem 0;border-radius:30px}
    .steps-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:2rem;max-width:1100px;margin:2rem auto 0 auto}
    .step-card{background:white;padding:2rem;border-radius:16px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.06)}
    .step-number{width:60px;height:60px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.8rem;font-weight:800;margin:0 auto 1rem auto}
    .step-title{font-size:1.2rem;font-weight:700;color:#2d3748;margin-bottom:0.8rem}
    .step-desc{color:#718096;font-size:0.95rem;line-height:1.6}
    
    /* Features */
    .features-section{padding:0 2rem;margin-bottom:3rem}
    .features-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem;max-width:1200px;margin:2rem auto 0 auto}
    .feature-card{background:linear-gradient(135deg,#ffffff,#f8f9ff);padding:2rem;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.06);border-left:4px solid #667eea}
    .feature-icon{font-size:2.5rem;margin-bottom:1rem}
    .feature-title{font-size:1.1rem;font-weight:700;color:#2d3748;margin-bottom:0.5rem}
    .feature-desc{color:#718096;font-size:0.9rem;line-height:1.5}
    
    /* CTA Section */
    .cta-section{background:linear-gradient(135deg,#48bb78 0%,#38a169 100%);padding:3rem 2rem;border-radius:25px;margin:3rem 2rem;text-align:center;color:white;box-shadow:0 8px 30px rgba(72,187,120,0.3)}
    .cta-title{font-size:2.2rem;font-weight:800;margin-bottom:1rem}
    .cta-subtitle{font-size:1.2rem;margin-bottom:2rem;opacity:0.95}
    .cta-buttons{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}
    .cta-btn{background:white;color:#38a169;padding:1rem 2.5rem;border-radius:50px;font-weight:700;font-size:1.1rem;box-shadow:0 4px 15px rgba(0,0,0,0.2);transition:all 0.3s ease}
    .cta-btn:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.25)}
    
    /* Footer */
    .footer{text-align:center;padding:2rem;color:#718096;font-size:0.95rem;margin-top:3rem}
    .footer-links{display:flex;gap:2rem;justify-content:center;margin-bottom:1rem;flex-wrap:wrap}
    .footer-link{color:#667eea;font-weight:600}
    </style>""", unsafe_allow_html=True)
    
    # Hero Section (without nav alert)
    st.markdown("""<div class="hero-section">
        <div class="hero-content">
            <div class="hero-title">🛍️ LinkUp Marketplace</div>
            <div class="hero-subtitle">Discover Local Student Businesses & Services</div>
            <div style="color:#f0f4ff;font-size:1.1rem;margin-bottom:1.5rem;">
                Post ads with photos & videos of your products • Browse services with real visuals • Connect directly with sellers<br>
                Your one-stop marketplace for everything student services
            </div>
        </div>
    </div>""", unsafe_allow_html=True)
    
    # CTA Section
    st.markdown('''<div class="cta-section">
        <div class="cta-title">Ready to Start?</div>
        <div class="cta-subtitle">Join hundreds of student entrepreneurs growing their businesses on LinkUp</div>
        <div style="background:rgba(255,255,255,0.2);padding:1.5rem;border-radius:15px;margin:2rem auto;max-width:600px;backdrop-filter:blur(10px);">
            <div style="font-size:1.2rem;font-weight:600;margin-bottom:1rem;">For Sellers</div>
            <div style="font-size:1rem;margin-bottom:0.5rem;">✅ Post unlimited ads for free</div>
            <div style="font-size:1rem;margin-bottom:0.5rem;">✅ Reach thousands of potential customers</div>
            <div style="font-size:1rem;">✅ Grow your business today</div>
        </div>
        <div style="background:rgba(255,255,255,0.2);padding:1.5rem;border-radius:15px;margin:2rem auto;max-width:600px;backdrop-filter:blur(10px);">
            <div style="font-size:1.2rem;font-weight:600;margin-bottom:1rem;">For Buyers</div>
            <div style="font-size:1rem;margin-bottom:0.5rem;">✅ Browse hundreds of verified services</div>
            <div style="font-size:1rem;margin-bottom:0.5rem;">✅ Compare prices and ratings</div>
            <div style="font-size:1rem;">✅ Connect instantly with providers</div>
        </div>
    </div>''', unsafe_allow_html=True)
    

    
    # Nav Alert Box (moved here)
    st.markdown("""<div class="nav-alert-container">
        <div class="nav-alert-box">
            <div class="nav-alert-text">
                <span class="nav-alert-emoji">👈</span> <strong>NEW HERE?</strong><br>
                Click the<strong>></strong>at the top left<br>
                to sign up & start exploring!
            </div>
        </div>
    </div>""", unsafe_allow_html=True)
        # Footer
    st.markdown('''<div class="footer">
        <div style="font-size:1.3rem;font-weight:700;color:#2d3748;margin-bottom:1rem;">🛍️ LinkUp Marketplace</div>
        <div style="margin-bottom:1.5rem;">The #1 student marketplace for local services and businesses</div>
        <div style="color:#a0aec0;font-size:0.85rem;">Built by students, for students • Connecting campus entrepreneurs since 2025</div>
    </div>''', unsafe_allow_html=True)

# upgrading the login to show forgot password
def show_login():
    # Modern CSS styling with dark mode compatibility
    st.markdown("""
    <style>
    .login-container {
        max-width: 500px;
        margin: 0 auto;
        padding: 2rem;
    }
    .login-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 3rem 2rem;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 15px 35px rgba(102, 126, 234, 0.2);
        position: relative;
        overflow: hidden;
    }
    .login-header::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent);
        transform: rotate(45deg);
        animation: shimmer 3s infinite;
    }
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    .login-header h1 {
        color: white;
        font-size: 2.8rem;
        margin: 0;
        font-weight: 700;
        text-shadow: 0 2px 10px rgba(0,0,0,0.3);
        position: relative;
        z-index: 1;
    }
    .login-header p {
        color: rgba(255,255,255,0.95);
        font-size: 1.2rem;
        margin: 1rem 0 0 0;
        font-weight: 300;
        position: relative;
        z-index: 1;
    }
    .login-card {
        background: white;
        padding: 2.5rem;
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(0,0,0,0.05);
        position: relative;
    }
    .login-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #667eea, #764ba2, #667eea);
        border-radius: 20px 20px 0 0;
    }
    .card-header {
        display: flex;
        align-items: center;
        margin-bottom: 2rem;
        padding-bottom: 1rem;
        border-bottom: 2px solid #f8f9fa;
    }
    .card-header h3 {
        margin: 0;
        color: #2c3e50;
        font-size: 1.5rem;
        font-weight: 600;
    }
    .card-icon {
        font-size: 1.8rem;
        margin-right: 0.8rem;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .admin-selector {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        border-left: 4px solid #f39c12;
    }
    
    /* Enhanced admin selector text for better dark mode readability */
    .admin-selector h4 {
        color: #8b6914 !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 2px rgba(255,255,255,0.8) !important;
        margin-bottom: 0.5rem !important;
    }
    
    .admin-selector p {
        color: #6c5416 !important;
        font-weight: 600 !important;
        text-shadow: 0 1px 2px rgba(255,255,255,0.8) !important;
        margin: 0 !important;
    }
    
    /* Enhanced text input styling for better visibility */
    .stTextInput > div > div > input {
        border: 2px solid #495057 !important;
        border-radius: 10px !important;
        padding: 0.75rem 1rem !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        background: #ffffff !important;
        color: #212529 !important;
        font-weight: 500 !important;
    }
    
    .stTextInput > div > div > input::placeholder {
        color: #6c757d !important;
        opacity: 0.8 !important;
        font-weight: 400 !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2) !important;
        background: #ffffff !important;
        color: #212529 !important;
        outline: none !important;
    }
    
    /* Radio button styling for better dark mode visibility */
    .stRadio > div {
        background: rgba(255, 255, 255, 0.95) !important;
        padding: 1rem !important;
        border-radius: 8px !important;
        border: 1px solid #dee2e6 !important;
    }
    
    .stRadio > div > label {
        color: #2c3e50 !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }
    
    .stRadio > div > label > div[data-testid="stMarkdownContainer"] {
        color: #2c3e50 !important;
    }
    
    /* Text input labels for better visibility */
    .stTextInput > label {
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        text-shadow: 0 1px 3px rgba(0,0,0,0.5) !important;
        margin-bottom: 0.5rem !important;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        padding: 1rem 2rem !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4) !important;
    }
    .welcome-back {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border: 1px solid #b8dacc;
        color: #155724;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        font-weight: 500;
    }
    .error-message {
        background: linear-gradient(135deg, #f8d7da 0%, #f1b0b7 100%);
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        font-weight: 500;
    }
    
    /* Forgot section styling */
    .forgot-section {
        background: rgba(255, 255, 255, 0.95);
        padding: 1.5rem;
        border-radius: 12px;
        margin-top: 2rem;
        border: 1px solid #dee2e6;
    }
    
    .forgot-header {
        display: flex;
        align-items: center;
        margin-bottom: 1rem;
    }
    
    .forgot-icon {
        font-size: 1.5rem;
        margin-right: 0.8rem;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .forgot-header h4 {
        margin: 0;
        color: #2c3e50;
        font-size: 1.3rem;
        font-weight: 600;
    }
    
    .info-text {
        color: #495057;
        font-weight: 500;
        margin: 0;
        line-height: 1.5;
    }
    
    .divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, #667eea, transparent);
        margin: 2rem 0;
        border-radius: 1px;
    }
    </style>
    """, unsafe_allow_html=True)
    # Main container
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    # Modern header with animation
    st.markdown("""
    <div class="login-header">
        <h1>Welcome Back</h1>
        <p>Sign in to connect with services around you</p>
    </div>
    """, unsafe_allow_html=True)

    # Login card
    st.markdown("""
    <div class="login-card">
        <div class="card-header">
            <span class="card-icon">👤</span>
            <h3>Account Login</h3>
        </div>
    </div>
    """, unsafe_allow_html=True)
    # Admin/User selector
    st.markdown("""
    <div class="admin-selector">
        <h4>⚙️ Login Type</h4>
        <p>Select your login type (Admin features will be available if your account has admin privileges)</p>
    </div>
    """, unsafe_allow_html=True)
    
    login_type = st.radio("", ["👤 Normal User", "⚙️ Admin"], horizontal=True)
    # Login form inputs
    email = st.text_input(
        "📧 Email Address (For security reasons manually input email address, dont use browser auto-fill here)",
        placeholder="yourname@gmail.com",
        help="Enter the email address you used to sign up",
        label_visibility="visible"
    )
    st.markdown('<style>.stTextInput label { color: #999 !important; font-weight: 600 !important; }</style>', unsafe_allow_html=True)

    password = st.text_input(
        "🔑 Password (For security reasons manually input password, dont use browser auto-fill here)",
        placeholder="Enter your password",
        type="password",
        help="Manually type your password. Avoid browser auto-fill here.",
        label_visibility="visible"
    )
    st.markdown('<style>.stTextInput label { color: #999 !important; font-weight: 600 !important; }</style>', unsafe_allow_html=True)

    # Login button
    login_col1, login_col2 = st.columns([1, 2])
    with login_col1:
        login_clicked = st.button("🚪 Sign In")

    # Login logic
    if login_clicked:
        # Force reading current values (helps with autofill issues)
        current_email = email.strip() if email else ""
        current_password = password.strip() if password else ""
        
        # Additional validation
        if not current_email or not current_password:
            st.markdown("""
            <div class="error-message">
                ❌ <strong>Missing Information</strong><br>
                Please enter both email and password.
            </div>
            """, unsafe_allow_html=True)
        else:
            user = find_user(current_email, current_password)
            if user:
                st.session_state.logged_in = True
                st.session_state.current_user = user
                st.session_state.selected_login_type = login_type

                st.markdown(f"""
                <div class="welcome-back">
                    ✅ <strong>Welcome back, {user['Name']}!</strong><br>
                    You're being redirected to your dashboard...
                </div>
                """, unsafe_allow_html=True)
                st.rerun()
            else:
                # First attempt failed - clear cache and try again (in case user just registered)
                with st.spinner("🔄 Refreshing user data..."):
                    st.cache_data.clear()
                    user = find_user(current_email, current_password)
                
                if user:
                    st.session_state.logged_in = True
                    st.session_state.current_user = user
                    st.session_state.selected_login_type = login_type

                    st.markdown(f"""
                    <div class="welcome-back">
                        ✅ <strong>Welcome back, {user['Name']}!</strong><br>
                        You're being redirected to your dashboard...
                    </div>
                    """, unsafe_allow_html=True)
                    st.rerun()
                else:
                    # Still failed after cache clear - credentials are actually wrong
                    st.markdown("""
                    <div class="error-message">
                        ❌ <strong>Invalid credentials</strong><br>
                        Please check your email and password and try again.
                    </div>
                    """, unsafe_allow_html=True)
    # Stylish divider
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    # Forgot password section
    st.markdown("""
    <div class="forgot-section">
        <div class="forgot-header">
            <span class="forgot-icon">🔄</span>
            <h4>Forgot Your Password?</h4>
        </div>
        <p class="info-text">
            No worries! Enter your email address below and we'll send your password to your inbox.
        </p>
    </div>
    """, unsafe_allow_html=True)

    forgot_email = st.text_input("📨 Email for password reset", 
                               key="forgot_email",
                               placeholder="Enter your registered email",
                               help="We'll send your password to this email address")
    
    if st.button("📬 Send My Password"):
        user = next((u["fields"] for u in fetch_users() if u["fields"].get("Email") == forgot_email), None)
        if user:
            sent = send_password_email(forgot_email, user["Password"])
            if sent:
                st.success("✅ Password sent! Please check your email inbox.")
            else:
                st.warning("⚠️ Could not send the email. Please try again later.")
        else:
            st.warning("⚠️ No account found with that email address.")

    st.markdown('</div>', unsafe_allow_html=True)

def show_sign_up_or_update():
    # Enhanced CSS for marketplace design
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    .main-header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:2rem;border-radius:15px;margin-bottom:2rem;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.1);font-family:'Poppins',sans-serif}
    .main-header h1{color:white;font-size:2.5rem;margin:0;font-weight:700;text-shadow:0 2px 4px rgba(0,0,0,0.3)}
    .main-header p{color:rgba(255,255,255,0.9);font-size:1.1rem;margin:0.5rem 0 0 0}
    .section-card{background:white;padding:2rem;border-radius:15px;box-shadow:0 5px 20px rgba(0,0,0,0.08);margin-bottom:1.5rem;border:1px solid rgba(0,0,0,0.05);font-family:'Poppins',sans-serif}
    .section-header{display:flex;align-items:center;margin-bottom:1.5rem;padding-bottom:0.5rem;border-bottom:2px solid #f0f2f6}
    .section-header h3{margin:0;color:#2c3e50;font-size:1.4rem;font-weight:600}
    .section-icon{font-size:1.5rem;margin-right:0.5rem}
    .form-section{background:white;padding:2rem;border-radius:15px;box-shadow:0 5px 20px rgba(0,0,0,0.08);margin-bottom:1.5rem;border:1px solid rgba(0,0,0,0.05);font-family:'Poppins',sans-serif}
    .form-section h3{color:#2c3e50;font-size:1.4rem;font-weight:600;margin-bottom:0.5rem;display:flex;align-items:center}
    .form-section p{color:#6b7280;font-size:1rem;margin-bottom:1.5rem}
    .account-type-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin:1.5rem 0}
    .type-card{background:white;padding:2rem;border:2px solid #e2e8f0;border-radius:15px;cursor:pointer;transition:all 0.3s ease;text-align:center;font-family:'Poppins',sans-serif}
    .type-card:hover{border-color:#667eea;box-shadow:0 8px 25px rgba(102,126,234,0.2);transform:translateY(-3px)}
    .type-card.selected{border-color:#667eea;background:linear-gradient(135deg,#667eea10,#764ba210);box-shadow:0 8px 25px rgba(102,126,234,0.3)}
    .type-icon{font-size:3rem;margin-bottom:1rem;display:block}
    .type-title{font-size:1.3rem;font-weight:600;color:#2c3e50;margin-bottom:0.5rem}
    .type-desc{color:#6b7280;font-size:0.95rem;line-height:1.4}
    .user-type-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin:1.5rem 0}
    .user-type-card{background:white;padding:2rem;border:2px solid #e2e8f0;border-radius:15px;cursor:pointer;transition:all 0.3s ease;text-align:center;font-family:'Poppins',sans-serif}
    .user-type-card:hover{border-color:#667eea;box-shadow:0 8px 25px rgba(102,126,234,0.2);transform:translateY(-3px)}
    .user-type-card.selected{border-color:#667eea;background:linear-gradient(135deg,#667eea10,#764ba210);box-shadow:0 8px 25px rgba(102,126,234,0.3)}
    .user-type-icon{font-size:3rem;margin-bottom:1rem;display:block}
    .user-type-title{font-size:1.3rem;font-weight:600;color:#2c3e50;margin-bottom:0.5rem}
    .user-type-desc{color:#6b7280;font-size:0.95rem;line-height:1.4}
    .info-box{background:linear-gradient(135deg,#e3f2fd 0%,#f3e5f5 100%);padding:1.5rem;border-radius:12px;margin-bottom:1.5rem;border-left:4px solid #2196f3;font-family:'Poppins',sans-serif}
    .stButton>button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:0.75rem 2rem;border-radius:25px;font-weight:600;font-size:1rem;box-shadow:0 4px 15px rgba(102,126,234,0.3);transition:all 0.3s ease;width:100%;font-family:'Poppins',sans-serif}
    .stButton>button:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(102,126,234,0.4)}
    </style>""", unsafe_allow_html=True)
    
    # Header
    is_update = st.session_state.logged_in
    st.markdown(f"""<div class="main-header">
        <h1>🛍️ {"Update Your Profile" if is_update else "Join LinkUp Marketplace"}</h1>
        <p>{"Keep your marketplace profile fresh and up-to-date!" if is_update else "Start posting your business ads and reaching thousands of students!"}</p>
    </div>""", unsafe_allow_html=True)
    
    # User Type Selection
    st.markdown("""
    <div class="section-card">
        <div class="section-header" style="color:#222;">
            <span class="section-icon">🎯</span>
            <h3 style="color:#222;">How will you use LinkUp?</h3>
        </div>
        <p style="color:#555;font-size:1.05rem;margin-bottom:1.5rem;">Choose your primary goal (you can always switch later!):</p>
        <div class="user-type-cards">
    """, unsafe_allow_html=True)
    
    # Create three columns for user type cards
    col1, col2, col3 = st.columns(3)
    
    # Initialize user_type in session state if not exists or reset old values
    if 'user_type' not in st.session_state or st.session_state.user_type not in ["Seller", "Buyer", "Both"]:
        st.session_state.user_type = "Seller"
    
    with col1:
        if st.button("📢 Post Ads", key="seller_btn", help="I want to post business ads and get customers"):
            st.session_state.user_type = "Seller"
    
    with col2:
        if st.button("🔍 Browse & Buy", key="buyer_btn", help="I want to browse ads and hire services"):
            st.session_state.user_type = "Buyer"
    
    with col3:
        if st.button("🔄 Both", key="both_btn", help="I want to post my ads AND browse others"):
            st.session_state.user_type = "Both"
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Show selected user type info
    user_type_info = {
        "Seller": {
            "icon": "📢", 
            "title": "Post Your Business Ads", 
            "desc": "You'll be able to create unlimited listings with photos & videos, showcase your products/services, set your own prices, and connect with customers who need what you offer."
        },
        "Buyer": {
            "icon": "🔍", 
            "title": "Browse & Hire", 
            "desc": "You'll be able to search through thousands of ads, view photos & videos of products/services, compare prices, and chat with sellers directly on WhatsApp or in-app."
        },
        "Both": {
            "icon": "🔄", 
            "title": "Full Marketplace Access", 
            "desc": "You'll be able to post your own business ads with photos & videos AND browse/hire from other students. The best of both worlds - grow your business while finding services you need!"
        }
    }

    selected_info = user_type_info[st.session_state.user_type]
    st.markdown(f"""<div class="info-box" style="background:linear-gradient(135deg,#48bb78 0%,#38a169 100%);color:#fff;border-left:4px solid #2f855a;">
        <h4 style="color:#fff;margin-bottom:0.8rem;font-size:1.2rem;">{selected_info['icon']} You selected: {selected_info['title']}</h4>
        <p style="margin:0;color:#f7fafc;font-size:0.98rem;line-height:1.6;">{selected_info['desc']}</p>
    </div>""", unsafe_allow_html=True)

    
    # Personal Information
    st.markdown("""
    <div class="section-card">
        <div class="section-header" style="color:#222;">
            <span class="section-icon">👤</span>
            <h3 style="color:#222;">Your Profile Information</h3>
        </div>
        <p style="color:#555;font-size:1.05rem;">Let buyers and sellers know who they're dealing with:</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Full Name *", st.session_state.current_user.get("Name", ""), 
                           help="Your real name - builds trust with other users")
    with col2:
        email = st.text_input("Email Address *", st.session_state.current_user.get("Email", ""),
                            help="For account security and important marketplace updates")
    
    password = st.text_input("Password *", type="password", 
                           help="Keep your account secure with a strong password")
    
    profile_image = st.file_uploader("📸 Upload Profile Photo (Recommended)", type=["png", "jpg", "jpeg"], 
                                   help="Ads with profile photos get 3x more responses!")
    
    # Bio section
    st.markdown("""
    <div class="section-card">
        <div class="section-header" style="color:#222;">
            <span class="section-icon">✍️</span>
            <h3 style="color:#222;">About You</h3>
        </div>
        <p style="color:#555;font-size:1.05rem;">Introduce yourself to the LinkUp community:</p>
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.user_type == "Seller":
        bio_placeholder = "Hey! I'm a student entrepreneur specializing in graphic design. I create stunning logos, flyers, and social media content. Check out my portfolio in my ads - let's work together! 🎨"
        bio_help = "Describe what you sell, your experience, and what makes your business special. This shows up on your profile!"
    elif st.session_state.user_type == "Buyer":
        bio_placeholder = "Hello! I'm always on the lookout for quality student services - from tutoring to design work. I believe in supporting young entrepreneurs and love discovering new talent on LinkUp! 🛍️"
        bio_help = "Tell sellers what kinds of services you typically look for and what you value in a seller"
    else:
        bio_placeholder = "Hi! I run a small design business and also hire other talented students for services I need. Love the LinkUp community and excited to connect with fellow student entrepreneurs! 💼🛍️"
        bio_help = "Describe both what you sell and what you look for when browsing the marketplace"
    
    bio = st.text_area("Short Bio (Optional)", st.session_state.current_user.get("Bio", ""), 
                      help=bio_help, placeholder=bio_placeholder, max_chars=500)
    
    # Submit button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 " + ("Update My Profile" if is_update else "Create My Account & Start Exploring")):
        if not name or not email or not password:
            st.warning("⚠️ Please fill in all required fields (Name, Email, Password).")
            return
        
        profile_image_url = st.session_state.current_user.get("Profile_Image", "")
        if profile_image:
            try:
                file_bytes = profile_image.read()
                profile_image_url = upload_image_to_cloudinary(file_bytes, profile_image.name)
                st.success("✅ Profile picture uploaded!")
            except Exception as e:
                st.error("😕 Could not upload your profile picture. Please try a different image or try again later.")
        
        # Prepare user data with simplified structure
        user_data = {
            "Name": name, 
            "Email": email, 
            "Password": password, 
            "User_Type": st.session_state.user_type,
            "Intent": "Business",  # Set to business since we're now marketplace-focused
            "What I know": "Marketplace Services",  # Generic value for backend compatibility
            "Looking For": "Marketplace Opportunities",  # Generic value for backend compatibility
            "Bio": bio, 
            "Profile_Image": profile_image_url 
        }
        
        record_id = st.session_state.current_user.get("id") if is_update else None
        success = upsert_user(user_data, record_id)
        
        if success:
            st.success("✅ Profile created successfully! Welcome to LinkUp Marketplace! 🎉")
            st.balloons()
            st.session_state.current_user = {**user_data, "id": record_id}
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("😔 We couldn't save your profile changes. Please check your connection and try again.")


# handle chat interface
def show_chats():
    # Automatically refresh the chat page every 90 seconds
    count = st_autorefresh(interval=90000, key="chatrefresh")  # 5000 ms = 5 seconds

    if "selected_contact" not in st.session_state:
        st.session_state.selected_contact = None

    # Enhanced header with better styling
    st.markdown("""
    <div style='text-align: center; padding: 20px 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                border-radius: 15px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);'>
        <h1 style='color: white; margin: 0; font-size: 2.5rem; font-weight: 700; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);'>
            💬 Messages
        </h1>
        <p style='color: rgba(255,255,255,0.8); margin: 5px 0 0 0; font-size: 1.1rem;'>
            Slide into DMs to hire or get hired 💼
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    current_user_name = st.session_state.current_user.get("Name")
    users = fetch_users()
    contacts = [user["fields"]["Name"] for user in users if user["fields"]["Name"] != current_user_name]

    all_msgs = fetch_received_messages(current_user_name)
    senders = set()

    for msg in all_msgs:
        fields = msg.get("fields", {})
        sender = fields.get("Sender")
        if fields.get("Recipient") == current_user_name:
            chat_history = fetch_messages(current_user_name, sender)
            has_unread = any(
                m["fields"]["Recipient"] == current_user_name and not m["fields"].get("Read", False)
                for m in chat_history
            )
            if has_unread:
                senders.add(sender)
    # Enhanced new messages section
    if senders:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #ff6b6b, #ffa726); padding: 20px; border-radius: 12px; 
                    margin-bottom: 25px; box-shadow: 0 4px 12px rgba(255,107,107,0.3);'>
            <h3 style='color: white; margin: 0 0 15px 0; font-size: 1.4rem; font-weight: 600;'>
                🔔 New Messages
            </h3>
        </div>
        """, unsafe_allow_html=True)
        
        for sender in senders:
            st.markdown(f"""
            <div style='background: white; border-left: 4px solid #ff6b6b; padding: 15px; margin: 10px 0; 
                        border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); 
                        transition: transform 0.2s ease, box-shadow 0.2s ease;'>
                <div style='display: flex; align-items: center; justify-content: space-between;'>
                    <div style='display: flex; align-items: center;'>
                        <div style='width: 40px; height: 40px; background: linear-gradient(135deg, #667eea, #764ba2); 
                                    border-radius: 50%; display: flex; align-items: center; justify-content: center; 
                                    margin-right: 12px; font-size: 1.2rem; color: white; font-weight: bold;'>
                            {sender[0].upper()}
                        </div>
                        <div>
                            <div style='font-weight: 600; color: #333; font-size: 1.1rem;'>{sender}</div>
                            <div style='color: #666; font-size: 0.9rem;'>sent you a new message</div>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                if st.button("💬 Open Chat", key=f"chat_{sender}", type="primary"):
                    st.session_state.selected_contact = sender
                    st.rerun()
    else:
        # Enhanced no messages state
        st.markdown("""
        <div style='text-align: center; padding: 40px 20px; background: linear-gradient(135deg, #f8f9fa, #e9ecef); 
                    border-radius: 15px; margin: 20px 0; border: 2px dashed #dee2e6;'>
            <div style='font-size: 4rem; margin-bottom: 15px; opacity: 0.5;'>📭</div>
            <h3 style='color: #6c757d; margin-bottom: 10px;'>No new messages</h3>
            <p style='color: #868e96; margin-bottom: 20px;'>Your inbox is all caught up!</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("📂 Show Chat History", type="secondary"):
            url = f"https://api.airtable.com/v0/{BASE_ID}/Chats"
            headers = {
                "Authorization": f"Bearer {AIRTABLE_PAT}",
                "Content-Type": "application/json"
            }
            params = {
                "filterByFormula": f"OR(Sender='{current_user_name}', Recipient='{current_user_name}')"
            }
            response = requests.get(url, headers=headers, params=params)
            if response.ok:
                records = response.json().get("records", [])
                unique_contacts = set()
                for r in records:
                    f = r["fields"]
                    if f.get("Sender") != current_user_name:
                        unique_contacts.add(f.get("Sender"))
                    elif f.get("Recipient") != current_user_name:
                        unique_contacts.add(f.get("Recipient"))
                if unique_contacts:
                    st.markdown("""
                    <div style='background: white; padding: 20px; border-radius: 12px; margin: 15px 0; 
                                box-shadow: 0 2px 10px rgba(0,0,0,0.1);'>
                        <h4 style='color: #495057; margin-bottom: 15px; font-size: 1.2rem;'>
                            💬 Previous Conversations
                        </h4>
                    </div>
                    """, unsafe_allow_html=True)
                    for contact in sorted(unique_contacts):
                        st.markdown(f"""
                        <div style='display: flex; align-items: center; padding: 10px; margin: 5px 0; 
                                    background: #f8f9fa; border-radius: 8px; border-left: 3px solid #28a745;'>
                            <div style='width: 30px; height: 30px; background: #28a745; border-radius: 50%; 
                                        display: flex; align-items: center; justify-content: center; 
                                        margin-right: 10px; color: white; font-weight: bold; font-size: 0.9rem;'>
                                {contact[0].upper()}
                            </div>
                            <span style='color: #495057; font-weight: 500;'>{contact}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("You haven't chatted with anyone yet.")
            else:
                st.error("😕 Unable to load chat history. Please check your connection and refresh the page.")

            # Enhanced contact selection
    st.markdown("### 👥 Start a Conversation")
    
    default_contact = st.session_state.selected_contact
    if default_contact not in contacts:
        default_contact = None

    selected_contact = st.selectbox("Select a contact to chat with", contacts, index=contacts.index(default_contact) if default_contact else 0)
    st.session_state.selected_contact = selected_contact

    # --- Enhanced Chat Interface ---
    if selected_contact:
        # Enhanced navigation buttons        
        colA, colB = st.columns(2)
        with colA:
            if st.button("⬅️ Back to Requests", type="secondary"):
                st.session_state.page = "post_request"
                st.rerun()
        with colB:
            if st.button("⬅️ Back to Explore Services", type="secondary"):
                st.session_state.page = "Talents"
                st.rerun()


        # Find the profile image URL for the selected contact
        contact_profile_url = ""
        for user in users:
            f = user.get("fields", {})
            if f.get("Name") == selected_contact:
                contact_profile_url = f.get("Profile_Image", "")
                break
        # Enhanced chat header with profile picture if available
        if contact_profile_url:
            avatar_html = f'<a href="{contact_profile_url}" target="_blank" title="Click to expand"><img src="{contact_profile_url}" alt="Profile" style="width:50px;height:50px;border-radius:50%;object-fit:cover;border:2px solid #764ba2;cursor:pointer; margin-right: 15px;"></a>'
        else:
            avatar_html = f'<div style="width: 50px; height: 50px; background: rgba(255,255,255,0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; color: white; font-weight: bold; font-size: 1.3rem; backdrop-filter: blur(10px);">{selected_contact[0].upper()}</div>'

        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 20px; 
                    border-radius: 12px; margin: 20px 0; box-shadow: 0 4px 12px rgba(79,172,254,0.3);'>
            <div style='display: flex; align-items: center;'>
                {avatar_html}
                <div>
                    <h2 style='color: white; margin: 0; font-size: 1.5rem; font-weight: 600;'>{selected_contact}</h2>
                    <p style='color: rgba(255,255,255,0.8); margin: 0; font-size: 0.9rem;'>Active conversation</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # Chat messages container with enhanced styling
        st.markdown("""
        <div style='background: #fafafa; padding: 20px; border-radius: 12px; margin: 20px 0; 
                    min-height: 400px; max-height: 500px; overflow-y: auto; 
                    box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);'>
        """, unsafe_allow_html=True)
        messages = fetch_messages(current_user_name, selected_contact)
        for msg in messages:
            fields = msg.get("fields", {})
            sender = fields.get("Sender")
            content = fields.get("Message")
            timestamp = fields.get("Timestamp", "")
            read = fields.get("Read", False)
            recipient = fields.get("Recipient")
            # Mark message as read if necessary
            if recipient == current_user_name and not read:
                msg_id = msg["id"]
                try:
                    requests.patch(
                        f"https://api.airtable.com/v0/{BASE_ID}/Chats/{msg_id}",
                        headers={
                            "Authorization": f"Bearer {AIRTABLE_PAT}",
                            "Content-Type": "application/json"
                        },
                        json={"fields": {"Read": True}}
                    )
                except Exception as e:
                    st.warning(f"Could not update read status: {e}")
            time_display = format_time_ago(timestamp) if timestamp else ""
            is_me = sender == current_user_name
            align = "right" if is_me else "left"
            # Enhanced message bubbles
            if is_me:
                bubble_bg = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
                text_color = "white"
                avatar_bg = "#667eea"
            else:
                bubble_bg = "white"
                text_color = "#333"
                avatar_bg = "#28a745"
            tick = "✔✔" if is_me and read else "✔" if is_me else ""
            tick_color = "#00ff88" if tick == "✔✔" else "rgba(255,255,255,0.7)" if is_me else "gray"
            st.markdown(
                f"""
                <div style='width: 100%; display: flex; justify-content: {"flex-end" if is_me else "flex-start"}; 
                            margin: 15px 0; animation: fadeIn 0.3s ease-in;'>
                    <div style='display: flex; align-items: flex-end; max-width: 70%; 
                                flex-direction: {"row-reverse" if is_me else "row"};'>
                        <div style='width: 35px; height: 35px; background: {avatar_bg}; border-radius: 50%; 
                                    display: flex; align-items: center; justify-content: center; 
                                    margin: {"0 0 0 10px" if is_me else "0 10px 0 0"}; color: white; 
                                    font-weight: bold; font-size: 0.9rem; flex-shrink: 0;'>
                            {sender[0].upper()}
                        </div>
                        <div style='background: {bubble_bg}; padding: 12px 16px; border-radius: 18px; 
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: relative;
                                    border-bottom-{"right" if is_me else "left"}-radius: 4px;'>
                            <div style='color: {text_color}; font-size: 0.95rem; line-height: 1.4; word-wrap: break-word;'>
                                {content}
                            </div>
                            <div style='font-size: 0.75rem; text-align: right; margin-top: 5px; 
                                        color: {"rgba(255,255,255,0.7)" if is_me else "#999"}; display: flex; 
                                        align-items: center; justify-content: flex-end; gap: 5px;'>
                                <span>{time_display}</span>
                                <span style='color: {tick_color}; font-weight: bold;'>{tick}</span>
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)
        # Auto scroll to bottom after all messages
        st.markdown(
            """
            <script>
            const chatContainer = window.parent.document.querySelector('section.main');
            if (chatContainer) {
                chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
            }
            </script>
            """,
            unsafe_allow_html=True
        )

        # Enhanced message input form
        with st.form(key="chat_form", clear_on_submit=True):
            st.markdown("**✍️ Type your message:**")
            message = st.text_area("", key="chat_input", placeholder="Write your message here...", height=100)
            
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                send_btn = st.form_submit_button("📤 Send Message", type="primary", use_container_width=True)

            if send_btn and message.strip():
                send_message(current_user_name, selected_contact, message.strip())
                st.session_state.last_sent = datetime.utcnow().isoformat()
                st.session_state.last_check = time.time()
                st.success("✅ Message sent successfully!")
                time.sleep(0.5)
                st.rerun()
                
        if st.session_state.get("last_sent"):
            st.markdown(f"""
            <div style='text-align: center; color: #6c757d; font-size: 0.85rem; margin-top: 10px;'>
                📤 Last sent: {st.session_state.last_sent}
            </div>
            """, unsafe_allow_html=True)

    # Add CSS animations
    st.markdown("""
    <style>
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    div[data-testid="stButton"] > button {
        transition: all 0.3s ease;
    }
    
    div[data-testid="stButton"] > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    .stSelectbox > div > div {
        border-radius: 8px;
        border: 2px solid #e9ecef;
        transition: border-color 0.3s ease;
    }
    
    .stSelectbox > div > div:hover {
        border-color: #667eea;
    }
    
    .stTextArea > div > div > textarea {
        border-radius: 8px;
        border: 2px solid #e9ecef;
        transition: border-color 0.3s ease;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)

    st.session_state.page = None
# Talent zone
# Enhanced Talent Zone with Chat Navigation Popup
def Talent_Zone():
    url = f"https://api.airtable.com/v0/{BASE_ID}/Talent"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }
    # Custom CSS for enhanced UI (keeping your existing styles + new marketplace styles)
    st.markdown("""
    <style>
    .talent-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
    }
    
    .talent-header h1 {
        font-size: 3rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .talent-header p {
        font-size: 1.2rem;
        opacity: 0.9;
        margin: 0;
    }
    
    .service-card {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        border-left: 5px solid #667eea;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .service-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 35px rgba(0,0,0,0.15);
    }
    
    .service-title {
        color: #2c3e50;
        font-size: 1.5rem;
        font-weight: 600;
        margin-bottom: 1rem;
        border-bottom: 2px solid #ecf0f1;
        padding-bottom: 0.5rem;
    }
    
    .service-info {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1rem;
    }
    
    .info-badge {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
        padding: 0.4rem 0.8rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
    }
    
    .price-badge {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 25px;
        font-size: 1.1rem;
        font-weight: 600;
        display: inline-block;
        margin: 0.5rem 0;
    }
    
    .contact-info {
        background: #e8f4fd;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #2c3e50;
        color: #2c3e50;
        font-weight: 500;
    }
    
    .section-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 2rem 0 1rem 0;
        text-align: center;
        font-size: 1.5rem;
        font-weight: 600;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    .search-container {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        margin: 1rem 0;
        border: 1px solid #e9ecef;
    }
    
    .form-container {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        margin: 1rem 0;
        border: 1px solid #e9ecef;
    }
    
    .form-header {
        text-align: center;
        color: #2c3e50;
        font-size: 1.8rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 3px solid #667eea;
    }
    
    .no-services {
        text-align: center;
        padding: 3rem;
        color: #6c757d;
        font-size: 1.2rem;
        background: #f8f9fa;
        border-radius: 12px;
        margin: 2rem 0;
    }
    
    .stats-container {
        display: flex;
        justify-content: space-around;
        margin: 1rem 0;
        flex-wrap: wrap;
        gap: 1rem;
    }
    
    .stat-card {
        background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        min-width: 120px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    .stat-number {
        font-size: 2rem;
        font-weight: 700;
        display: block;
    }
    
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    /* Rating and Review Styles */
    .rating-container {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.5rem 0;
    }
    
    .stars {
        color: #ffd700;
        font-size: 1.2rem;
    }
    
    .rating-text {
        color: #666;
        font-size: 0.9rem;
    }
    
    .review-section {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #28a745;
    }
    
    .review-item {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-left: 3px solid #667eea;
    }
    
    .review-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    
    .reviewer-name {
        font-weight: 600;
        color: #2c3e50;
    }
    
    .review-text {
        color: #555;
        line-height: 1.5;
        margin: 0.5rem 0;
    }
    
    .review-form {
        background: #e8f4fd;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border: 1px solid #bee5eb;
    }

    /* CHAT NAVIGATION POPUP STYLES */
    .navigation-popup {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        color: white;
        padding: 2rem;
        border-radius: 15px;
        margin: 1.5rem 0;
        text-align: center;
        box-shadow: 0 8px 25px rgba(79, 172, 254, 0.4);
        border: 3px solid #ffffff;
        animation: popup-bounce 0.6s ease-out;
    }
    
    @keyframes popup-bounce {
        0% { transform: scale(0.3) translateY(-50px); opacity: 0; }
        50% { transform: scale(1.05) translateY(-10px); opacity: 0.8; }
        100% { transform: scale(1) translateY(0); opacity: 1; }
    }
    
    .popup-header {
        font-size: 2.2rem;
        margin-bottom: 0.8rem;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    .popup-message {
        font-size: 1.1rem;
        line-height: 1.6;
        margin-bottom: 1.5rem;
        font-weight: 500;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
    }
    
    .popup-instructions {
        background: rgba(255, 255, 255, 0.15);
        padding: 1.2rem;
        border-radius: 10px;
        margin: 1rem 0;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .popup-instructions h4 {
        margin: 0 0 0.8rem 0;
        font-size: 1.2rem;
        color: #ffffff;
        font-weight: 600;
    }
    
    .popup-instructions p {
        margin: 0;
        font-size: 1rem;
        color: #ffffff;
        font-weight: 500;
    }
    
    .selected-user-info {
        background: rgba(255, 255, 255, 0.2);
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #ffffff;
    }
    
    .selected-user-info strong {
        color: #ffffff;
        font-size: 1.1rem;
    }

    /* UPDATED DISCLAIMER STYLES FOR MAXIMUM READABILITY */
    .disclaimer-banner {
        background: #000000;
        color: #ffffff;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        text-align: center;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
        animation: pulse-glow 3s infinite;
        border: 3px solid #ff0000;
    }
    
    @keyframes pulse-glow {
        0%, 100% { box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4); }
        50% { box-shadow: 0 8px 25px rgba(255, 0, 0, 0.6); }
    }
    
    .disclaimer-banner h3 {
        margin: 0 0 0.5rem 0;
        font-size: 1.4rem;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
    }
    
    .disclaimer-banner p {
        margin: 0;
        font-size: 1rem;
        color: #ffffff;
        font-weight: 600;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
    }
    
    .safety-modal-container {
        background: #000000;
        padding: 2.5rem;
        border-radius: 20px;
        margin: 2rem 0;
        color: #ffffff;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.5);
        border: 4px solid #ff0000;
    }
    
    .modal-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .modal-header h2 {
        font-size: 2.8rem;
        margin: 0 0 0.5rem 0;
        text-shadow: 3px 3px 6px rgba(0, 0, 0, 0.7);
        color: #ffffff;
        font-weight: 800;
    }
    
    .modal-header p {
        margin: 0;
        font-size: 1.3rem;
        color: #ffffff;
        font-weight: 600;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.5);
    }
    
    .safety-tips {
        background: #1a1a1a;
        border-radius: 12px;
        padding: 2rem;
        margin: 2rem 0;
        border-left: 6px solid #00ff00;
        border: 2px solid #333333;
    }
    
    .safety-tips h3 {
        color: #ffffff;
        margin: 0 0 1.5rem 0;
        font-size: 1.5rem;
        font-weight: 700;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
    }
    
    .safety-tips ul {
        margin: 0;
        padding-left: 1.5rem;
        line-height: 1.8;
    }
    
    .safety-tips li {
        margin: 0.8rem 0;
        color: #ffffff;
        font-weight: 600;
        font-size: 1rem;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
    }
    
    .warning-box {
        background: #cc0000;
        color: #ffffff;
        padding: 2rem;
        border-radius: 12px;
        margin: 2rem 0;
        text-align: center;
        box-shadow: 0 8px 25px rgba(204, 0, 0, 0.4);
        border: 3px solid #ffffff;
    }
    
    .warning-box h3 {
        margin: 0 0 0.8rem 0;
        font-size: 1.6rem;
        font-weight: 800;
        color: #ffffff;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
    }
    
    .warning-box p {
        margin: 0;
        font-size: 1.1rem;
        color: #ffffff;
        font-weight: 600;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
    }
    
    .pro-tip-box {
        background: #0066cc;
        padding: 1.5rem;
        border-radius: 8px;
        border-left: 6px solid #ffffff;
        margin: 1.5rem 0;
        border: 2px solid #ffffff;
    }
    
    .pro-tip-box p {
        margin: 0;
        color: #ffffff;
        font-weight: 600;
        font-size: 1rem;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
    }
        
    .verified-badge {
        background: linear-gradient(135deg, #1DA1F2 0%, #0084b4 100%);
        color: white;
        padding: 0.3rem 0.6rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        margin-left: 0.5rem;
        box-shadow: 0 2px 8px rgba(29, 161, 242, 0.3);
    }

    .service-title.verified {
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    /* JIJI-STYLE MARKETPLACE CARD LAYOUT */
    .marketplace-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 20px;
        margin: 20px 0;
    }
    
    @media (max-width: 1200px) {
        .marketplace-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    
    @media (max-width: 768px) {
        .marketplace-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
    }
    
    @media (max-width: 480px) {
        .marketplace-grid {
            grid-template-columns: 1fr;
        }
    }
    
    .marketplace-card {
        background: white;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e5e5e5;
        transition: all 0.3s ease;
        cursor: pointer;
        position: relative;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .marketplace-card:hover {
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        transform: translateY(-3px);
        border-color: #667eea;
    }
    
    .card-image-container {
        width: 100%;
        height: 200px;
        background: #f8f9fa;
        position: relative;
        overflow: hidden;
    }
    
    .card-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 0.3s ease;
    }
    
    .marketplace-card:hover .card-image {
        transform: scale(1.05);
    }
    
    .image-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #999;
        font-size: 3rem;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    .card-content {
        padding: 15px;
    }
    
    .card-price {
        font-size: 1.2rem;
        font-weight: 700;
        color: #e74c3c;
        margin-bottom: 8px;
    }
    
    .card-title {
        font-size: 1rem;
        font-weight: 600;
        color: #2c3e50;
        margin-bottom: 8px;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    
    .card-description {
        font-size: 0.85rem;
        color: #666;
        line-height: 1.4;
        margin-bottom: 12px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    
    .card-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
        font-size: 0.8rem;
        color: #777;
    }
    
    .seller-name {
        display: flex;
        align-items: center;
        gap: 5px;
    }
    
    .rating-stars {
        display: flex;
        align-items: center;
        gap: 3px;
        color: #ffd700;
        font-size: 0.9rem;
    }
    
    .view-profile-btn {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 10px;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .view-profile-btn:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    .verification-badge {
        position: absolute;
        top: 10px;
        right: 10px;
        background: #27ae60;
        color: white;
        padding: 4px 8px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(39, 174, 96, 0.3);
    }
    
    .unverified-warning {
        position: absolute;
        top: 10px;
        right: 10px;
        background: #e74c3c;
        color: white;
        padding: 4px 8px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(231, 76, 60, 0.3);
    }
    
    .popular-tag {
        position: absolute;
        top: 10px;
        left: 10px;
        background: #f39c12;
        color: white;
        padding: 4px 8px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(243, 156, 18, 0.3);
    }

    .grid-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 20px 0;
        padding: 0 10px;
    }
    
    .results-count {
        font-size: 1.1rem;
        color: #2c3e50;
        font-weight: 600;
    }
    
    .view-toggle {
        display: flex;
        gap: 10px;
        align-items: center;
    }
    
    .toggle-btn {
        padding: 8px 12px;
        border: 1px solid #ddd;
        background: white;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .toggle-btn.active {
        background: #667eea;
        color: white;
        border-color: #667eea;
    }
        </style>
    """, unsafe_allow_html=True)

    # Safety Modal - Show on first visit or when user wants to see it
    if 'talent_zone_disclaimer_accepted' not in st.session_state:
        st.session_state.talent_zone_disclaimer_accepted = False
    
    # Initialize chat popup state
    if 'show_chat_navigation_popup' not in st.session_state:
        st.session_state.show_chat_navigation_popup = False
    if 'selected_chat_user' not in st.session_state:
        st.session_state.selected_chat_user = None
    
    if not st.session_state.talent_zone_disclaimer_accepted:
        # Create the safety modal using Streamlit components
        st.markdown("""
        <div class="safety-modal-container">
            <div class="modal-header">
                <h2>🛡️ Safety First!</h2>
                <p>Important Information Before You Continue</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Warning box
        st.markdown("""
        <div class="warning-box">
            <h3>⚠️ PLATFORM LIABILITY DISCLAIMER</h3>
            <p>We are NOT liable for any scams, fraudulent activities, or disputes between users. Exercise caution in all transactions.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Safety tips
        st.markdown("""
        <div class="safety-tips">
            <h3>Smart Transaction Guidelines</h3>
            <ul>
                <li><strong>💳 Payment Protection:</strong> Always pay AFTER receiving satisfactory service delivery</li>
                <li><strong>🔍 Verify First:</strong> Check reviews, ratings, and previous work samples before engaging</li>
                <li><strong>📞 Communicate Clearly:</strong> Use the platform's chat feature for transparent communication</li>
                <li><strong>📋 Document Everything:</strong> Keep records of agreements, payments, and delivered work</li>
                <li><strong>🚨 Report Issues:</strong> Flag suspicious activities or disputes immediately</li>
                <li><strong>🤝 Meet Safely:</strong> If meeting in person, choose public locations</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Pro tip
        st.markdown("""
        <div class="pro-tip-box">
            <p><strong>💡 Pro Tip:</strong> Trust your instincts. If something feels too good to be true or seems suspicious, it probably is. Stay vigilant!</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Modal action buttons using Streamlit
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            col_accept, col_decline = st.columns(2)
            with col_accept:
                if st.button("✅ I Understand & Accept", key="accept_disclaimer", use_container_width=True):
                    st.session_state.talent_zone_disclaimer_accepted = True
                    st.rerun()
            with col_decline:
                if st.button("❌ Go Back", key="decline_disclaimer", use_container_width=True):
                    st.session_state.page = "dashboard"  # or wherever you want to redirect
                    st.rerun()
        
        return  # Don't show the rest of the page until disclaimer is accepted

    # Show Chat Navigation Popup if triggered
    if st.session_state.show_chat_navigation_popup and st.session_state.selected_chat_user:
        st.markdown(f"""
        <div class="navigation-popup">
            <div class="popup-header">💬 Chat Navigation</div>
            <div class="popup-message">
                <strong>Don't attempt to chat the user on this page!</strong><br>
                Navigate manually to the chat section by going to the navigation located on your left.
            </div>
            <div class="popup-instructions">
                <h4>📍 How to Access Chat:</h4>
                <p>1. Look at the navigation panel on your left sidebar<br>
                2. Click on "💬 Chats" from the navigation menu<br>
                3. Your selected contact will be automatically available</p>
            </div>
            <div class="selected-user-info">
                <strong>🎯 Selected Contact: {st.session_state.selected_chat_user}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Action buttons for the popup
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💬 Go to Chats Now", key="go_to_chats", use_container_width=True, type="primary"):
                st.session_state.selected_contact = st.session_state.selected_chat_user
                st.session_state.page = "chat"
                st.session_state.show_chat_navigation_popup = False
                st.rerun()
        with col2:
            if st.button("❌ Dismiss", key="dismiss_popup", use_container_width=True):
                st.session_state.show_chat_navigation_popup = False
                st.session_state.selected_chat_user = None
                st.rerun()
        with col3:
            if st.button("🔄 Select Different User", key="select_different", use_container_width=True):
                st.session_state.show_chat_navigation_popup = False
                st.session_state.selected_chat_user = None
                st.rerun()


    # Display Existing Services
    st.markdown('<div class="section-header">Explore Available Services</div>', unsafe_allow_html=True)

    try:
        records = fetch_services()

        # Stats Section (keeping your existing logic)
        if records:
            # total_services = len(records)
            # avg_price = sum([r["fields"].get("Price", 0) for r in records]) / len(records) if records else 0
            # unique_categories = len(set([r["fields"].get("Title", "Others") for r in records]))
            
            # st.markdown(f"""
            # <div class="stats-container">
            #     <div class="stat-card">
            #         <span class="stat-number">{total_services}</span>
            #         <span class="stat-label">Total Services</span>
            #     </div>
            #     <div class="stat-card">
            #         <span class="stat-number">₦{avg_price:,.0f}</span>
            #         <span class="stat-label">Avg Price</span>
            #     </div>
            #     <div class="stat-card">
            #         <span class="stat-number">{unique_categories}</span>
            #         <span class="stat-label">Categories</span>
            #     </div>
            # </div>
            # """, unsafe_allow_html=True)
            # --- Modern Search & Filter Bar (Streamlit-native, not markdown) ---
            with st.container():
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                    border-radius: 16px;
                    box-shadow: 0 4px 16px rgba(102,126,234,0.08);
                    padding: 1.5rem 2rem 1rem 2rem;
                    margin: 1.5rem 0 2.5rem 0;
                    border: 1.5px solid #e5e5e5;
                ">
                """, unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.markdown('<span style="font-weight:600; color:#2c3e50; font-size:1rem;">Search</span>', unsafe_allow_html=True)
                    search_query = st.text_input("", placeholder="e.g., design, development", key="search_query")
                with col2:
                    st.markdown('<span style="font-weight:600; color:#2c3e50; font-size:1rem;">Category</span>', unsafe_allow_html=True)
                    selected_title = st.selectbox(
                        "",
                        options=["All"] + sorted(set([r["fields"].get("Title", "Others") for r in records])),
                        key="selected_title"
                    )
                with col3:
                    st.markdown('<span style="font-weight:600; color:#2c3e50; font-size:1rem;">Sort</span>', unsafe_allow_html=True)
                    sort_order = st.selectbox(
                        "",
                        ["None", "Price: Low to High", "Price: High to Low", "Highest Rated"],
                        label_visibility="collapsed",
                        key="sort_order"
                    )
                with col4:
                    st.markdown('<span style="font-weight:600; color:#27ae60; font-size:1rem;">✓ Verified Only</span>', unsafe_allow_html=True)
                    show_verified_only = st.checkbox("", key="show_verified_only")
                st.markdown("</div>", unsafe_allow_html=True)

            # --- End Modern Search & Filter Bar ---
# After filtering/sorting, before showing results grid
            active_filters = []
            if search_query:
                active_filters.append(f"🔍 <b>Search:</b> <span style='color:#764ba2'>{search_query}</span>")
            if selected_title != "All":
                active_filters.append(f"🎯 <b>Category:</b> <span style='color:#764ba2'>{selected_title}</span>")
            if show_verified_only:
                active_filters.append("✅ <b>Verified Only</b>")
            if sort_order and sort_order != "None":
                active_filters.append(f"💰 <b>Sort:</b> <span style='color:#764ba2'>{sort_order}</span>")

            if active_filters:
                st.markdown(
                    f"""
                    <div style="margin: 1rem 0 0.5rem 0; padding: 0.7rem 1.2rem; background: #23272f; border-radius: 10px; border-left: 5px solid #667eea; font-size: 1.05rem; color: #fff;"">
                        <b>Showing results for:</b> {' | '.join(active_filters)}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"""
                    <div style="margin: 1rem 0 0.5rem 0; padding: 0.7rem 1.2rem; background: #23272f; border-radius: 10px; border-left: 5px solid #667eea; font-size: 1.05rem; color: #fff;">
                        <b>Showing all services</b>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            # (Keep your Python logic for filtering/sorting as before)
            if search_query:
                search_query_lower = search_query.lower()  # Convert search to lowercase
                records = [
                    r for r in records
                    if search_query_lower in r["fields"].get("Title", "").lower()
                    or search_query_lower in r["fields"].get("Description", "").lower()
                ]

            if selected_title != "All":
                records = [r for r in records if r["fields"].get("Title") == selected_title]
            if show_verified_only:
                records = [r for r in records if r["fields"].get("Verified", False)]
            if sort_order == "Price: Low to High":
                records.sort(key=lambda r: r["fields"].get("Price", 0))
            elif sort_order == "Price: High to Low":
                records.sort(key=lambda r: r["fields"].get("Price", 0), reverse=True)
            elif sort_order == "Highest Rated":
                records.sort(key=lambda r: calculate_average_rating(r["fields"]), reverse=True)

            if not records:
                st.markdown("""
                <div class="no-services">
                    <h3>🤷‍♂️ No Services Found</h3>
                    <p>Try adjusting your search criteria or be the first to post a service!</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Grid Header with Results Count
                st.markdown(f"""
                <div class="grid-header">
                """, unsafe_allow_html=True)
                        
            # Create marketplace grid using Streamlit columns
            # Display services in 4-column grid
            for i in range(0, len(records), 4):
                cols = st.columns(4)
                batch = records[i:i+4]
                
                for idx, record in enumerate(batch):
                    fields = record.get("fields", {})
                    requester = fields.get("Name", "Unknown")
                    # Add this block: read vendor price from the service (Talent) record, and lookup profile image from users
                    profile_image_url = ""
                    # Vendor price should live on the Talent/service record as a numeric field named one of:
                    # 'Vendor_Price', 'Vendor Price', or 'VendorPrice' (use one of these names in Airtable)
                    vendor_price_raw = fields.get("Vendor_Price") or fields.get("Vendor Price") or fields.get("VendorPrice")
                    for user in fetch_users():
                        user_fields = user.get("fields", {})
                        if user_fields.get("Name") == requester:
                            profile_image_url = user_fields.get("Profile_Image", "")
                            break
                    title = fields.get("Title", "No Title")
                    description = fields.get("Description", "No description")
                    price = fields.get("Price", 0)
                    # Try to parse vendor price (from talent/user record) safely into a number
                    vendor_price_num = None
                    try:
                        if vendor_price_raw is not None and str(vendor_price_raw).strip() != "":
                            vendor_price_num = float(str(vendor_price_raw).replace(",", ""))
                    except Exception:
                        vendor_price_num = None
                    record_id = record["id"]

                    # Calculate rating info
                    avg_rating = calculate_average_rating(fields)
                    review_count = fields.get("Review_Count", 0)
                    if avg_rating > 0:
                        stars = "⭐" * min(5, int(round(avg_rating)))
                        rating_text = f"{avg_rating:.1f}"
                    else:
                        stars = "☆☆☆☆☆"
                        rating_text = "No rating"

                    is_verified = fields.get("Verified", False)
                    is_popular = fields.get("Popular", False)

                    
                    
                    # Get image
                    works_raw = fields.get("Works", "")
                    image_url = ""
                    if works_raw:
                        urls = [u.strip() for u in works_raw.split("\n") if u.strip()]
                        if urls:
                            image_url = urls[0]

                    # Sanitize and truncate text for card display (remove any embedded HTML)
                    safe_desc = html_lib.unescape(str(description or ""))
                    safe_desc = re.sub(r'<[^>]+>', '', safe_desc)
                    short_description = safe_desc[:80] + "..." if len(safe_desc) > 80 else safe_desc
                    short_title = title[:40] + "..." if len(title) > 40 else title

                    with cols[idx]:
                        with st.container():
                            st.markdown(f"""
                            <div style="background: white; border-radius: 12px; overflow: hidden; border: 1px solid #e5e5e5; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: all 0.3s ease; margin-bottom: 20px; position: relative;">
                                <div style="width: 100%; height: 200px; background: #f8f9fa; position: relative; overflow: hidden;">
                                    {f'<img src="{image_url}" style="width: 100%; height: 100%; object-fit: cover;" alt="Service Image">' if image_url else '<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #999; font-size: 3rem; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);">📷</div>'}
                                    <div style="position: absolute; top: 10px; left: 10px; background: {('#27ae60' if is_verified else '#e74c3c')}; color: white; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.12);">
                                        {('✓ Verified' if is_verified else 'Unverified')}
                                    </div>
                                    <div style="position: absolute; top: 10px; right: 10px; background: {("#aea027" if is_popular else "#dbd1d0")}; color: white; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.12);">
                                        {('Popular 🔥' if is_popular else 'Seller')}
                                    </div>
                                </div>
                                <div style="padding: 15px;">
                                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                                        {f'<img src="{profile_image_url}" alt="Profile" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid #764ba2;">' if profile_image_url else '<div style="width:36px;height:36px;background:#eee;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.2rem;color:#aaa;">👤</div>'}
                                        <span style="font-weight:600;color:#2c3e50;font-size:1rem;">{requester}</span>
                                    </div>
                                    {f'<div style="font-size:0.95rem;color:#6c757d;margin-bottom:6px;"><s>Vendor price: ₦{int(vendor_price_num):,}</s></div>' if vendor_price_num else ''}
                                    <div style="font-size: 1.2rem; font-weight: 700; color: #000000; margin-bottom: 8px;">LinkUp price: ₦{price:,}</div>
                                    {f'<div style="font-size:0.95rem;color:#28a745;font-weight:700;margin-top:4px;">You save: ₦{max(0, int(vendor_price_num - float(price))):,}</div>' if vendor_price_num is not None else ''}
                                    <div style="font-size: 1rem; font-weight: 600; color: #2c3e50; margin-bottom: 8px; line-height: 1.3;">{short_title}</div>
                                    <div style="font-size: 0.85rem; color: #666; line-height: 1.4; margin-bottom: 12px;">{short_description}</div>
                                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 0.8rem; color: #777;">
                                        <div style="display: flex; align-items: center; gap: 5px;">
                                            <span>👤</span> {requester}
                                        </div>
                                        <div style="display: flex; align-items: center; gap: 3px; color: #ffd700; font-size: 0.9rem;">
                                            {stars} <span style="color: #666; font-size: 0.8rem;">({rating_text})</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        # Action buttons for each card
                        if st.button("👁 View Profile", key=f"profile_{record_id}", use_container_width=True):
                            st.session_state.selected_talent = record
                            st.session_state.page = "view_talent"
                            st.rerun()
                        # Review button and form
                        review_key = f"show_review_{record_id}"
                        if st.button("⭐ Review", key=f"review_{record_id}", use_container_width=True):
                            if review_key not in st.session_state:
                                st.session_state[review_key] = False
                            st.session_state[review_key] = not st.session_state[review_key]
                            st.rerun()
                        
                        # Show review form if toggled
                        if st.session_state.get(review_key, False):
                            with st.expander("📝 Leave a Review", expanded=True):
                                with st.form(f"review_form_{record_id}"):
                                    reviewer_name = st.text_input("Your Name", key=f"reviewer_{record_id}")
                                    rating = st.selectbox("Rating", [5, 4, 3, 2, 1], 
                                                        format_func=lambda x: "⭐" * x + f" ({x}/5)", 
                                                        key=f"rating_{record_id}")
                                    review_text = st.text_area("Your Review", key=f"review_text_{record_id}")
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.form_submit_button("Submit", use_container_width=True):
                                            if reviewer_name and review_text:
                                                success = add_review(record_id, reviewer_name, rating, review_text, headers, url)
                                                if success:
                                                    st.success("✅ Review submitted!")
                                                    st.session_state[review_key] = False
                                                    st.rerun()
                                                else:
                                                    st.error("😔 Unable to submit your review. Please try again in a moment.")
                                            else:
                                                st.error("🤔 Please fill in your rating and review before submitting.")
                                    with col2:
                                        if st.form_submit_button("Cancel", use_container_width=True):
                                            st.session_state[review_key] = False
                                            st.rerun()
                        
                        # Show existing reviews
                        reviews = get_reviews(fields)
                        if reviews:
                            with st.expander(f"💬 Reviews ({len(reviews)})", expanded=False):
                                for review in reviews:
                                    st.markdown(f"""
                                    <div class="review-item">
                                        <div class="review-header">
                                            <span class="reviewer-name">{review['name']}</span>
                                            <span style="color: #6c757d; font-size: 0.8rem;">{review['date']}</span>
                                        </div>
                                        <div class="stars">{"⭐" * review['rating']}</div>
                                        <div class="review-text">{review['text']}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                        
                        st.markdown("---")
                        

    except requests.exceptions.RequestException as e:
        st.error("😕 Unable to load services right now. Please check your connection and try again.")

    st.markdown("""
    <div style="margin: 3rem 0 2rem 0; padding: 1.5rem; background: #f8f9fa; border-radius: 10px; border-left: 5px solid #dc3545;">
        <h4 style="color: #dc3545; margin: 0 0 1rem 0; font-size: 1.1rem;">
            🚨 Final Safety Reminder
        </h4>
        <p style="margin: 0; color: #6c757d; line-height: 1.5;">
            <strong>Platform Disclaimer:</strong> This platform serves as a connection hub only. We do not guarantee service quality, 
            mediate disputes, or accept liability for transactions between users. Always exercise due diligence, verify credentials, 
            and prioritize your safety in all dealings.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Option to review safety guidelines again
    if st.button("🔄 Review Safety Guidelines Again", key="review_safety_again"):
        st.session_state.talent_zone_disclaimer_accepted = False
        st.rerun()

#Profile in talent zone
def view_talent_profile():
    
# --- Back Button with Custom CSS ---
    st.markdown("""
        <style>
        button[kind="secondary"] p {
            font-weight: 700 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("← Back to 🔎 Explore Services", type="secondary", use_container_width=True):
            st.session_state.page = "Talent zone"
            st.rerun()
    
    talent = st.session_state.get("selected_talent")
    fields = talent.get("fields", {})
    name = fields.get("Name", "No Name")
    record_id = talent.get("id", "")  # Get the record ID
    requester_name = fields.get("Name", "Unknown")
    if not talent:
        st.error("🔍 Please select a service provider from the explore section first.")
        return
    
    fields = talent.get("fields", {})
    name = fields.get("Name", "No Name")
    title = fields.get("Title", "No Title")
    description = fields.get("Description", "No description")
    price = fields.get("Price", 0)
    works_raw = fields.get("Works", "")
    whatsapp_number = fields.get("Contact", "")  # Make sure this is a valid WhatsApp number

    # --- Image Gallery (Jiji-style) ---
    image_urls = [u.strip() for u in works_raw.split("\n") if u.strip()]
    profile_key = f"profile_img_idx_{fields.get('Name','')}_{fields.get('Title','')}"
    if profile_key not in st.session_state:
        st.session_state[profile_key] = 0

    if image_urls:
        img_idx = st.session_state[profile_key]
        col_img, col_card = st.columns([2, 1])
        with col_img:
            # Show main image with reduced height and margin-bottom for spacing
            st.markdown(
                f'<img src="{image_urls[img_idx]}" style="width:100%;height:320px;object-fit:cover;border-radius:18px;box-shadow:0 2px 8px rgba(0,0,0,0.08);margin-bottom:24px;" />',
                unsafe_allow_html=True
            )
            # Show thumbnails with wrapping
            st.markdown("""
            <div style="display: flex; flex-wrap: wrap; gap: 16px; justify-content: flex-start; margin-bottom: 12px;">
            """, unsafe_allow_html=True)

            image_prices = fields.get("Image_Prices", "").split("\n")
            image_names = fields.get("Image_Names", "").split("\n")  # ADD THIS LINE

            for i, url in enumerate(image_urls):
                # Get price
                image_price = image_prices[i].strip() if i < len(image_prices) else ""
                if image_price and image_price.isdigit():
                    price_text = f"₦{int(image_price):,}"
                else:
                    price_text = f"₦{price:,}" if price > 0 else "Contact for price"
                
                # Get product name - ADD THIS
                product_name = image_names[i].strip() if i < len(image_names) and image_names[i].strip() else "Product"
                
                st.markdown(
                    f'''
                    <div style="flex: 0 1 auto; display: flex; align-items: center; gap: 12px;">
                        <a href="{url}" target="_blank" title="Click to expand">
                            <img src="{url}" style="width:180px;height:120px;object-fit:cover;border-radius:16px;border:2px solid #eee;box-shadow:0 2px 8px rgba(0,0,0,0.08);" />
                        </a>
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                            <div style="font-weight:700;color:#4a5568;font-size:1.1rem;">{product_name}</div>
                            <div style="font-weight:600;color:#4a5568;font-size:1.05rem;">{price_text}</div>
                        </div>
                    </div>
                    ''',
                    unsafe_allow_html=True
                )
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption(f"Image {img_idx+1} of {len(image_urls)}")



    else:
        col_img, col_card = st.columns([2, 1])
        with col_img:
            st.info("No images uploaded for this service.")

    # --- Video Gallery (always show if available) ---
    video_urls = [u.strip() for u in fields.get("Vids", "").split("\n") if u.strip()]
    if video_urls:
        st.markdown("#### 🎥 Service Videos")
        for url in video_urls:
            st.video(url)
    else:
        st.info("No videos uploaded for this service.")

    st.markdown(f"""
    <div style="
        background: white;
        border-radius: 18px;
        box-shadow: 0 4px 18px rgba(102,126,234,0.08);
        padding: 2.2rem 2rem 1.5rem 2rem;
        margin: 1.5rem 0 2.2rem 0;
        border: 1.5px solid #e5e5e5;
    ">
        <div style="font-size:2.1rem; font-weight:800; color:#23272f; margin-bottom:0.7rem; letter-spacing:-1px;">
            {title}
        </div>
        <div style="color:#636e72; font-size:1.15rem; line-height:1.7; margin-bottom:0.5rem;">
            {description}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- Right Card: Price & WhatsApp ---
    with col_card:
        image_prices = fields.get("Image_Prices", "").split("\n")
        valid_prices = [int(p.strip()) for p in image_prices if p.strip().isdigit()]
        if valid_prices:
            min_price = min(valid_prices)
            price_display = f"From ₦{min_price:,}"
        elif price > 0:
            price_display = f"₦{price:,}"
        else:
            price_display = "Contact for price"

        st.markdown(f"""
        <div style="background:white;padding:1.5rem 1.2rem 1.2rem 1.2rem;border-radius:15px;box-shadow:0 4px 20px rgba(0,0,0,0.08);margin-bottom:1.5rem;">
            <div style="font-size:2rem;font-weight:700;color:#27ae60;margin-bottom:0.5rem;">{price_display}</div>
            <div style="margin-bottom:1rem;">
                <span style="background:#e1f7e7;color:#27ae60;padding:0.3rem 0.8rem;border-radius:12px;font-size:0.95rem;font-weight:600;">Negotiable</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


        # WhatsApp Chat Button
        if whatsapp_number and whatsapp_number != "Not provided":
            wa_link = f"https://wa.me/{whatsapp_number}?text=Hi%20{name},%20I'm%20interested%20in%20your%20service%20on%20LinkUp!"
            st.markdown(
                f'<a href="{wa_link}" target="_blank" style="display:block;text-align:center;background:#25d366;color:white;padding:0.9rem 0;border:none;border-radius:8px;font-size:1.1rem;font-weight:700;margin-bottom:0.7rem;text-decoration:none;">💬 Chat on WhatsApp</a>',
                unsafe_allow_html=True
            )
            # --- Add Telegram Chat Button ---
            tg_text = f"Hi {name}, I'm interested in your service on LinkUp!"
            telegram_username = fields.get("Telegram_Username", "")
            if telegram_username:
                # Remove @ if present and create direct chat link
                telegram_username = telegram_username.lstrip('@')
                tg_link = f"https://t.me/{telegram_username}?text={urllib.parse.quote(tg_text)}"
            else:
                # Fallback to share URL if no username provided
                tg_link = f"https://t.me/share/url?url=https://linkupmarket.streamlit.app&text={urllib.parse.quote(tg_text)}"
            
            st.markdown(
                f'<a href="{tg_link}" target="_blank" style="display:block;text-align:center;background:#0088cc;color:white;padding:0.9rem 0;border:none;border-radius:8px;font-size:1.1rem;font-weight:700;margin-bottom:0.7rem;text-decoration:none;">💬 Chat on Telegram</a>',
                unsafe_allow_html=True
            )
        else:
            st.info("No WhatsApp contact provided.")

        # Fetch profile image for this talent
        profile_image_url = ""
        for user in fetch_users():
            user_fields = user.get("fields", {})
            if user_fields.get("Name") == name:
                profile_image_url = user_fields.get("Profile_Image", "")
                break

        # Show name and profile image
        st.markdown("<hr>", unsafe_allow_html=True)

        is_verified = fields.get("Verified", False)
        verified_badge = (
            '<span style="display:inline-block;vertical-align:middle;margin-left:7px;">'
            '<svg width="20" height="20" viewBox="0 0 20 20" style="vertical-align:middle;">'
            '<circle cx="10" cy="10" r="10" fill="#1DA1F2"/>'
            '<path d="M6 10.5l2.5 2.5 5-5" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
            '</span>'
            if is_verified else ""
        )

        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 1rem;">
            {f'<img src="{profile_image_url}" alt="Profile" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid #764ba2;">' if profile_image_url else '<div style="width:48px;height:48px;background:#eee;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.5rem;color:#aaa;">👤</div>'}
            <span style="font-weight:600;font-size:1.1rem;color:#444;">{name}{verified_badge}</span>
        </div>
        """, unsafe_allow_html=True)

        # st.markdown(f"""
        # <div style="
        #     background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        #     color: white;
        #     padding: 1.3rem 1rem;
        #     border-radius: 14px;
        #     margin-top: 1.2rem;
        #     box-shadow: 0 4px 18px rgba(102,126,234,0.13);
        #     text-align: center;
        #     font-size: 1.08rem;
        #     font-weight: 500;
        # ">
        #     <div style="font-size:1.7rem; margin-bottom:0.5rem;">💬</div>
        #     To chat in-app, go to the <b>💬 Chats</b> section in the navigation panel<br>
        #     and select <span style="color:#ffeaa7;font-weight:600;">{name}</span>.
        # </div>
        # """, unsafe_allow_html=True)

        st.markdown("""
        <div style="
            background: #fff;
            border-radius: 14px;
            box-shadow: 0 2px 10px rgba(102,126,234,0.07);
            padding: 1.3rem 1.1rem 1.1rem 1.1rem;
            margin-top: 1.2rem;
            border: 1.5px solid #e5e5e5;
        ">
            <div style="font-size:1.15rem; font-weight:700; color:#23272f; margin-bottom:0.7rem;">
                🛡️ Safety tips
            </div>
            <ul style="color:#444; font-size:1.02rem; line-height:1.7; margin:0 0 0 1.1rem; padding:0;">
                <li>Avoid sending any prepayments</li>
                <li>Meet with the seller at a safe public place</li>
                <li>Inspect what you're going to buy to make sure it's what you need</li>
                <li>Check all the docs and only pay if you're satisfied</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    # st.markdown("<hr>", unsafe_allow_html=True)
    # st.markdown("### 📢 Share Your LinkUp Profile")

    # share_message = f"""
    # <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:1.5rem;border-radius:14px;margin:1.2rem 0;text-align:center;box-shadow:0 4px 18px rgba(102,126,234,0.13);">
    #     <div style="font-size:1.3rem;font-weight:700;margin-bottom:0.7rem;">🔗 Find Me on LinkUp!</div>
    #     <div style="font-size:1.1rem;margin-bottom:0.5rem;">
    #         <b>{name} - {title}</b><br>
    #         <span style="color:#ffeaa7;">Price: ₦{price:,}</span>
    #     </div>
    #     <div style="margin-bottom:0.7rem;">
    #         <span style="background:#e1f7e7;color:#27ae60;padding:0.3rem 0.8rem;border-radius:12px;font-size:0.95rem;font-weight:600;">Contact: {whatsapp_number if whatsapp_number else "In-App Chat"}</span>
    #     </div>
    #     <div style="font-size:1rem;margin-bottom:0.7rem;">
    #         <b>How to find me:</b> Go to <span style="color:#ffeaa7;">🔎 Explore Services</span> and search for <b>{name} - {title}</b>
    #     </div>
    #     <div style="font-size:0.95rem;opacity:0.8;">
    #         <i>Download your profile image,Share this card on WhatsApp, Instagram, or anywhere!</i>
    #     </div>
    # </div>
    # """
    # st.markdown(share_message, unsafe_allow_html=True)

    # # WhatsApp share button
    # wa_text = f"Find me on LinkUp(linkupmarket.streamlit.app)! Go to 🔎 Explore Services and search for '{name} - {title}' (Price: ₦{price:,})"
    # wa_link = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"
    # st.markdown(f'<a href="{wa_link}" target="_blank" style="display:inline-block;background:#25d366;color:white;padding:0.7rem 1.2rem;border-radius:8px;font-size:1.08rem;font-weight:600;text-decoration:none;margin-top:0.7rem;">📤 Share on WhatsApp</a>', unsafe_allow_html=True)

    # telegram_username = fields.get("Telegram_Username", "")
    # if telegram_username:
    #     tg_link = f"https://t.me/{telegram_username.lstrip('@')}"
    #     st.markdown(
    #         f'<a href="{tg_link}" target="_blank" style="display:block;text-align:center;background:#0088cc;color:white;padding:0.9rem 0;border:none;border-radius:8px;font-size:1.1rem;font-weight:700;margin-bottom:0.7rem;text-decoration:none;">💬 Chat on Telegram</a>',
    #         unsafe_allow_html=True
    #     )
    # else:
    #     tg_text = f"Hi {name}, I'm interested in your service on LinkUp!"
    #     tg_link = f"https://t.me/share/url?url=https://linkupmarket.streamlit.app&text={urllib.parse.quote(tg_text)}"
    #     st.markdown(
    #         f'<a href="{tg_link}" target="_blank" style="display:block;text-align:center;background:#0088cc;color:white;padding:0.9rem 0;border:none;border-radius:8px;font-size:1.1rem;font-weight:700;margin-bottom:0.7rem;text-decoration:none;">💬 Chat on Telegram</a>',
    #         unsafe_allow_html=True
    #     )

    # import base64
    # from io import BytesIO
    # from PIL import Image
    # import requests

    # # Get images for card
    # profile_img_url = profile_image_url
    # service_img_url = image_urls[0] if image_urls else ""
    # rating = calculate_average_rating(fields)
    # stars = "⭐" * min(5, int(round(rating))) if rating > 0 else "☆☆☆☆☆"

    # # Download images for PIL (if available)
    # def get_image_bytes(url):
    #     try:
    #         response = requests.get(url)
    #         img = Image.open(BytesIO(response.content)).convert("RGB")
    #         return img
    #     except:
    #         return None

    # profile_img = get_image_bytes(profile_img_url) if profile_img_url else None
    # service_img = get_image_bytes(service_img_url) if service_img_url else None

    # # Generate a PIL card image (simple, but unique)
    # def generate_card(profile_img, service_img, name, title, price, stars):
    #     card = Image.new("RGB", (600, 340), (245, 245, 255))
    #     # Paste service image
    #     if service_img:
    #         service_img = service_img.resize((600, 180))
    #         card.paste(service_img, (0, 0))
    #     # Paste profile image
    #     if profile_img:
    #         profile_img = profile_img.resize((80, 80))
    #         card.paste(profile_img, (20, 200))
    #     # Add text
    #     from PIL import ImageDraw, ImageFont
    #     draw = ImageDraw.Draw(card)
    #     font = ImageFont.load_default()
    #     draw.text((120, 210), f"{name}", (40, 40, 80), font=font)
    #     draw.text((120, 235), f"{title}", (60, 60, 100), font=font)
    #     draw.text((120, 260), f"Price: ₦{price:,}", (27, 174, 96), font=font)
    #     draw.text((120, 285), f"Rating: {stars}", (255, 215, 0), font=font)
    #     draw.text((20, 320), "Find me on LinkUp!", (102, 126, 234), font=font)
    #     return card

    # card_img = generate_card(profile_img, service_img, name, title, price, stars)
    # # Convert to bytes for download
    # buffer = BytesIO()
    # card_img.save(buffer, format="PNG")
    # img_bytes = buffer.getvalue()
    # b64 = base64.b64encode(img_bytes).decode()

    # st.markdown("### 🖼️ Share Your LinkUp Card")
    # st.image(card_img, caption="Your Shareable LinkUp Card", use_container_width=True)
    # st.download_button(
    #     label="⬇️ Download Card Image",
    #     data=img_bytes,
    #     file_name=f"{name}_{title}_linkup_card.png",
    #     mime="image/png"
    # )

    # st.markdown("""
    # <div style="margin-top:1.2rem; background:#f8f9fa; border-radius:10px; padding:1rem 1.2rem; border-left:4px solid #667eea; color:#444;">
    #     <b>Pro Tip:</b> After clicking WhatsApp or Telegram share, <b>attach your LinkUp card image</b> for a more attractive post!<br>
    #     <i>Download your card above, then upload it in your chat or group.</i>
    # </div>
    # """, unsafe_allow_html=True)
    st.session_state.page = None





# Helper Functions
def calculate_average_rating(fields):
    """Calculate average rating from stored data"""
    total_rating = fields.get("Total_Rating", 0)
    review_count = fields.get("Review_Count", 0)
    if review_count > 0:
        return total_rating / review_count
    return 0
def get_reviews(fields):
    """Get reviews from stored JSON data"""
    import json
    try:
        reviews_data = fields.get("Reviews_Data", "[]")
        if not reviews_data:
            reviews_data = "[]"
        reviews = json.loads(reviews_data)
        return reviews
    except:
        return []
def add_review(record_id, reviewer_name, rating, review_text, headers, url):
    """Add a new review to the service"""
    import json
    from datetime import datetime
    try:
        # Get current record
        response = requests.get(f"{url}/{record_id}", headers=headers)
        response.raise_for_status()
        current_data = response.json()
        fields = current_data.get("fields", {})
        
        # Get current reviews
        current_reviews = get_reviews(fields)
        
        # Add new review
        new_review = {
            "name": reviewer_name,
            "rating": rating,
            "text": review_text,
            "date": datetime.now().strftime("%B %d, %Y")
        }
        current_reviews.append(new_review)
        
        # Update totals
        current_total = fields.get("Total_Rating", 0)
        current_count = fields.get("Review_Count", 0)
        
        new_total = current_total + rating
        new_count = current_count + 1
        
        # Update record
        update_data = {
            "fields": {
                "Reviews_Data": json.dumps(current_reviews),
                "Total_Rating": new_total,
                "Review_Count": new_count
            }
        }
        update_response = requests.patch(f"{url}/{record_id}", headers=headers, json=update_data)
        update_response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error adding review: {e}")
        return False


def update_profile():
    st.title("⚙️ Post/Update Your Business Profile")

    current_user = st.session_state.get("current_user")
    if not current_user:
        st.error("🔒 Please log in to update your profile.")
        return

    user_name = current_user.get("Name")

    url = f"https://api.airtable.com/v0/{BASE_ID}/Talent"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }

    # Check if user already has a profile
    response = requests.get(url, headers=headers, params={"filterByFormula": f"Name='{user_name}'"})
    
    is_update_mode = False
    record_id = None
    fields = {}
    
    if response.ok:
        records = response.json().get("records", [])
        if records:
            is_update_mode = True
            user_record = records[0]
            record_id = user_record["id"]
            fields = user_record.get("fields", {})

    # Display mode indicator
    if is_update_mode:
        st.success("📝 **Update Mode**: Editing existing profile")
    else:
        st.info("✨ **Post Mode**: Creating new profile")

    # Verification promotion banner
    st.markdown("""
    <div style="background: linear-gradient(135deg, #ffeaa7, #fab1a0); border: 3px solid #e17055; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; text-align: center; animation: subtle-pulse 2s infinite;">
        <h3 style="margin: 0 0 0.5rem 0; color: #2d3436;">🔒 Still Unverified? You're Missing Out!</h3>
        <p style="margin: 0; color: #636e72; font-weight: 600;">Verified professionals get 3x more clients. Join the elite circle! ✨</p>
    </div>
    <style>
    @keyframes subtle-pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.02); }
    }
    </style>
    """, unsafe_allow_html=True)

    # Combined form for both post and update
    with st.form("profile_form"):
        st.markdown("### 📝 Business Profile Information")
        
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input(
                "👤 Full Name", 
                value=fields.get("Name", ""),
                placeholder="Enter your full name (same as signup)" if not is_update_mode else ""
            )
            new_Title = st.text_input(
                "🎨 Service Title", 
                value=fields.get("Title", ""),
                placeholder="e.g., 'Logo Design', 'Web Development'" if not is_update_mode else ""
            )
            new_Price = st.number_input(
                "💸 Price (₦)", 
                min_value=0, 
                value=fields.get("Price", 0),
                help="Set your service price"
            )
        with col2:
            new_contact_pref = st.radio(
                "📞 Preferred Contact Method", 
                ["In-App Chat", "Phone/Email"],
                index=0 if fields.get("Contact_pref") == "In-App Chat" or not fields.get("Contact_pref") else 1
            )
            new_contact = st.text_input(
                "📞 Contact Info", 
                value=fields.get("Contact", ""),
                placeholder="Your whatsapp phone number (leave blank if you don't use whatsapp)" if not is_update_mode else ""
            )
            # Ask for Telegram username
            new_telegram_username = st.text_input(
                "📨 Telegram Username (Optional)", 
                value=fields.get("Telegram_Username", ""),
                placeholder="e.g. @yourusername",
                help="Enter your Telegram username for direct chat (leave blank if you don't use Telegram)"
            )
            new_uploaded_files = st.file_uploader(
                "📷 Upload Work Samples/Products", 
                accept_multiple_files=True, 
                type=["png", "jpg", "jpeg"],
                help="Upload images to showcase your work"
            )
            image_prices = st.text_area(
                "💸 Image Prices (one per line, matching each image above)",
                value=fields.get("Image_Prices", ""),
                placeholder="e.g.\n5000\n7000\n6000",
                help="Enter a price for each image above, one per line. Leave blank to use the general price."
            )
            image_names = st.text_area(
                "🏷️ Product Names (one per line, matching each image above)",
                value=fields.get("Image_Names", ""),
                placeholder="e.g.\nAirpods Pro\nSmart Watch\niPhone Case",
                help="Enter a product name for each image above, one per line."
            )
            new_uploaded_videos = st.file_uploader(
                "🎥 Upload Short Videos (Max 30 secs)", 
                accept_multiple_files=True, 
                type=["mp4", "mov", "avi"],
                help="Showcase your products/services with a short video!"
            )
            
            # Image handling options (only show in update mode)
            if is_update_mode:
                image_handling = st.radio("🖼️ What do you want to do with your work samples?", [
                    "Keep existing and add new",
                    "Replace all with new uploads",
                    "Remove all images"
                ])

        new_description = st.text_area(
            "🛠️ Describe Your Service", 
            value=fields.get("Description", ""),
            placeholder="Tell potential clients about your service, experience, and what makes you unique..." if not is_update_mode else ""
        )

        # Submit button text changes based on mode
        submit_text = "💾 Update Profile" if is_update_mode else "📤 Post Service"
        submitted = st.form_submit_button(submit_text, use_container_width=True)

        if submitted:
            # Step 1: Initialize image list and upload if any
            new_image_urls = []
            if new_uploaded_files:
                for file in new_uploaded_files:
                    try:
                        file_bytes = file.read()
                        image_url = upload_image_to_cloudinary(file_bytes, file.name)

                        if isinstance(image_url, str):
                            new_image_urls.append(image_url)
                            st.success(f"✅ Uploaded: {file.name}")
                        else:
                            st.warning(f"❌ Failed to get URL for {file.name}")
                    except Exception as e:
                        st.error(f"😕 Unable to upload {file.name}. Please try a different image or try again later.")
            # Step 1b: Upload videos
            new_video_urls = []
            if new_uploaded_videos:
                for file in new_uploaded_videos:
                    try:
                        file_bytes = file.read()
                        video_url = upload_image_to_cloudinary(file_bytes, file.name)
                        if isinstance(video_url, str):
                            new_video_urls.append(video_url)
                            st.success(f"✅ Uploaded video: {file.name}")
                        else:
                            st.warning(f"❌ Failed to get video URL for {file.name}")
                    except Exception as e:
                        st.error(f"😕 Unable to upload video {file.name}. Please try a different video or try again later.")


            # Step 2: Handle image logic based on mode and selected option
            if is_update_mode:
                if image_handling == "Keep existing and add new":
                    old_urls = fields.get("Works", "").split("\n") if fields.get("Works") else []
                    combined_urls = old_urls + new_image_urls
                elif image_handling == "Replace all with new uploads":
                    combined_urls = new_image_urls
                elif image_handling == "Remove all images":
                    combined_urls = []
            else:
                # Post mode - use new uploads only
                combined_urls = new_image_urls

            # Step 2b: Handle video logic
            if is_update_mode:
                old_vids = fields.get("Vids", "").split("\n") if fields.get("Vids") else []
                combined_vids = old_vids + new_video_urls
            else:
                combined_vids = new_video_urls

            # Step 3: Build data payload
            profile_data = {
                "fields": {
                    "Name": new_name,
                    "Title": new_Title,
                    "Description": new_description,
                    "Price": new_Price,
                    "Contact_pref": new_contact_pref,
                    "Contact": new_contact,
                    "Works": "\n".join(combined_urls) if combined_urls else None,
                    "Vids": "\n".join(combined_vids) if combined_vids else None,
                    "Image_Prices": image_prices,
                    "Image_Names": image_names,
                    "Telegram_Username": new_telegram_username
                }
            }

            # Add initial values for new profiles
            if not is_update_mode:
                profile_data["fields"].update({
                    "Reviews_Data": "[]",  # Initialize empty reviews
                    "Total_Rating": 0,
                    "Review_Count": 0
                })

            try:
                if is_update_mode:
                    # Update existing profile
                    update_url = f"{url}/{record_id}"
                    response = requests.patch(update_url, headers=headers, json=profile_data)
                    success_message = "🎉 Profile updated successfully!"
                else:
                    # Create new profile
                    response = requests.post(url, headers=headers, json=profile_data)
                    success_message = "🎉 Your service has been posted successfully!"

                if response.ok:
                    st.success(success_message)
                    st.session_state.current_user = response.json().get("fields", {})
                    st.balloons()
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to save profile.")
                    st.write(response.text)
                    
            except requests.exceptions.RequestException as e:
                st.error("❌ Failed to save profile.")
                st.exception(e)
                st.code(response.text if 'response' in locals() else 'No response body')
# post requests
def post_request():
    url = f"https://api.airtable.com/v0/{BASE_ID}/Request"
    headers = {"Authorization": f"Bearer {AIRTABLE_PAT}", "Content-Type": "application/json"}
    
    # Compact CSS with all original styles
    st.markdown("""<style>
    .request-hero{background:linear-gradient(135deg,#ff9a9e 0%,#fecfef 50%,#fecfef 100%);padding:3rem 2rem;border-radius:20px;margin-bottom:2rem;text-align:center;color:white;position:relative;overflow:hidden;box-shadow:0 15px 35px rgba(255,154,158,0.3)}
    .request-hero::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle,rgba(255,255,255,0.1) 0%,transparent 70%);animation:float 6s ease-in-out infinite}
    @keyframes float{0%,100%{transform:translateY(0px) rotate(0deg)}50%{transform:translateY(-20px) rotate(180deg)}}
    .request-hero h1{font-size:2.8rem;font-weight:800;margin-bottom:0.5rem;text-shadow:2px 2px 4px rgba(0,0,0,0.2);position:relative;z-index:2}
    .request-hero p{font-size:1.3rem;opacity:0.95;margin:0;position:relative;z-index:2}
    .info-card{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:15px;padding:2rem;margin:2rem 0;color:white;box-shadow:0 10px 30px rgba(102,126,234,0.3)}
    .info-card ul{list-style:none;padding:0;margin:0}
    .info-card li{padding:0.8rem 0;font-size:1.1rem;border-bottom:1px solid rgba(255,255,255,0.2);display:flex;align-items:center;gap:0.5rem}
    .info-card li:last-child{border-bottom:none}
    .request-form-container{background:white;border-radius:20px;padding:2.5rem;margin:2rem 0;box-shadow:0 20px 40px rgba(0,0,0,0.1);border:1px solid #f0f2f5;position:relative}
    .request-form-container::before{content:'';position:absolute;top:0;left:0;right:0;height:5px;background:linear-gradient(90deg,#ff9a9e,#fecfef,#667eea,#764ba2);border-radius:20px 20px 0 0}
    .form-title{text-align:center;color:#2c3e50;font-size:2rem;font-weight:700;margin-bottom:2rem;position:relative}
    .form-title::after{content:'';position:absolute;bottom:-10px;left:50%;transform:translateX(-50%);width:80px;height:4px;background:linear-gradient(90deg,#ff9a9e,#fecfef);border-radius:2px}
    .request-card{background:white;border-radius:15px;padding:2rem;margin:1.5rem 0;box-shadow:0 8px 25px rgba(0,0,0,0.08);border-left:6px solid #ff9a9e;transition:all 0.3s ease;position:relative;overflow:hidden}
    .request-card::before{content:'';position:absolute;top:0;right:0;width:100px;height:100px;background:linear-gradient(135deg,rgba(255,154,158,0.1) 0%,transparent 100%);border-radius:0 0 0 100px}
    .request-card:hover{transform:translateY(-3px);box-shadow:0 15px 35px rgba(0,0,0,0.12);border-left-color:#667eea}
    .request-title{color:#2c3e50;font-size:1.6rem;font-weight:700;margin-bottom:1.5rem;position:relative;z-index:2}
    .request-details{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem;margin:1.5rem 0}
    .detail-item{background:#f8f9fa;padding:1rem;border-radius:10px;border-left:4px solid #ff9a9e;position:relative;z-index:2}
    .detail-label{font-weight:600;color:#495057;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5rem}
    .detail-value{color:#2c3e50;font-size:1.1rem;font-weight:500}
    .budget-highlight{background:linear-gradient(135deg,#11998e 0%,#38ef7d 100%);color:white;padding:0.8rem 1.5rem;border-radius:25px;font-size:1.2rem;font-weight:700;display:inline-block;margin:1rem 0;box-shadow:0 5px 15px rgba(17,153,142,0.3)}
    .contact-section{background:linear-gradient(135deg,#ffeaa7 0%,#fab1a0 100%);padding:1.5rem;border-radius:12px;margin:1.5rem 0;color:#2d3436;position:relative;z-index:2}
    .contact-section h4{margin:0 0 1rem 0;font-weight:600}
    .section-header{background:linear-gradient(135deg,#a8edea 0%,#fed6e3 100%);color:#2c3e50;padding:2rem;border-radius:15px;margin:3rem 0 2rem 0;text-align:center;font-size:1.8rem;font-weight:700;box-shadow:0 10px 25px rgba(168,237,234,0.3);position:relative}
    .section-header::after{content:'';position:absolute;bottom:-10px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:15px solid transparent;border-right:15px solid transparent;border-top:15px solid #fed6e3}
    .no-requests{text-align:center;padding:4rem 2rem;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:15px;color:white;margin:2rem 0}
    .no-requests h3{font-size:2rem;margin-bottom:1rem}
    .no-requests p{font-size:1.2rem;opacity:0.9}
    .chat-button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:0.8rem 2rem;border-radius:25px;font-weight:600;font-size:1rem;cursor:pointer;transition:all 0.3s ease;box-shadow:0 5px 15px rgba(102,126,234,0.4);position:relative;z-index:2}
    .chat-button:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(102,126,234,0.6)}
    .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.5rem;margin:2rem 0}
    .stat-item{background:linear-gradient(135deg,#74b9ff 0%,#0984e3 100%);color:white;padding:1.5rem;border-radius:12px;text-align:center;box-shadow:0 8px 20px rgba(116,185,255,0.3)}
    .stat-number{font-size:2.5rem;font-weight:800;display:block;margin-bottom:0.5rem}
    .stat-label{font-size:1rem;opacity:0.9;font-weight:500}
    </style>""", unsafe_allow_html=True)
    
    # Hero and Info sections
    st.markdown('<div class="request-hero"><h1>✨ Request Zone</h1><p>Need help? Post your request and connect with talented people!</p></div><div class="info-card"><ul><li>🙆‍♂️ <b>Need help in a task</b> – Find people who are skilled at the task</li><li>🖊 <b>Just fill the form</b> – Wait for users to respond</li><li>🔍 <b>Explore Services</b> – You can manually look for people with skills by going to the 🔎 Explore Services zone</li></ul></div>', unsafe_allow_html=True)
    
    # Request Form
    st.markdown('<div class="request-form-container"><div class="form-title">📝 Post Your Request</div>', unsafe_allow_html=True)
    with st.form("post_request_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("👤 Full Name", placeholder="Make sure it's the same name you used to signup")
            request_title = st.text_input("🎯 What do you need?", placeholder="e.g., 'Help with video editing', 'Logo design needed'")
            budget = st.number_input("💸 Budget (₦)", min_value=0, help="How much are you willing to pay?")
        with col2:
            deadline = st.text_input("⏰ Deadline", placeholder="e.g., 'Next week', '3 days', 'ASAP'")
            contact_method = st.radio("📞 Preferred Contact Method", ["In-App Chat", "Phone/Email"])
            contact_info = st.text_input("📧 Contact Details", placeholder="Phone number or email (optional)")
        details = st.text_area("📋 Request Details", placeholder="Describe what you need in detail. Be specific about requirements, expectations, and any important information...")
        submit_request = st.form_submit_button("🚀 Post Request", use_container_width=True)
        
        if submit_request:
            user_data = {"fields": {"Name": name, "Request": request_title, "Details": details, "Budget": budget, "Deadline": deadline, "Contact_pref": contact_method, "Contact": contact_info}}
            try:
                response = requests.post(url, headers=headers, json=user_data)
                response.raise_for_status()
                st.success("✅ Your Request has been posted successfully!")
                st.balloons()
                st.cache_data.clear()
            except requests.exceptions.RequestException as e:
                st.error("❌ Failed to post Request.")
                st.exception(e)
                st.code(response.text if 'response' in locals() else 'No response body')
    st.markdown('</div>', unsafe_allow_html=True)

    # Browse Requests Section
    st.markdown('<div class="section-header">🔎 Browse Open Requests</div>', unsafe_allow_html=True)
    
    try:
        records = fetch_requests()

        if not records:
            st.markdown('<div class="no-requests"><h3>📭 No Requests Yet</h3><p>Be the first to post a request and find the help you need!</p></div>', unsafe_allow_html=True)
        else:
            # Stats Section
            total_requests = len(records)
            total_budget = sum([r["fields"].get("Budget", 0) for r in records])
            avg_budget = total_budget / len(records) if records else 0
            urgent_requests = len([r for r in records if "asap" in r["fields"].get("Deadline", "").lower() or "urgent" in r["fields"].get("Details", "").lower()])
            
            st.markdown(f'<div class="stats-grid"><div class="stat-item"><span class="stat-number">{total_requests}</span><span class="stat-label">Active Requests</span></div><div class="stat-item"><span class="stat-number">₦{avg_budget:,.0f}</span><span class="stat-label">Average Budget</span></div><div class="stat-item"><span class="stat-number">{urgent_requests}</span><span class="stat-label">Urgent Requests</span></div></div>', unsafe_allow_html=True)
            
            for record in records:
                fields = record.get("fields", {})
                requester_name = fields.get("Name", "Unknown")
                request_title = fields.get('Request', 'No Title')
                details = fields.get('Details', 'No details')
                budget = fields.get('Budget', 0)
                deadline = fields.get('Deadline', 'Not specified')
                contact_pref = fields.get('Contact_pref', 'Not specified')
                contact = fields.get('Contact', 'N/A')

                st.markdown(f'''<div class="request-card"><div class="request-title">{request_title}</div><div class="request-details"><div class="detail-item"><div class="detail-label">👤 Requester</div><div class="detail-value">{requester_name}</div></div><div class="detail-item"><div class="detail-label">📆 Deadline</div><div class="detail-value">{deadline}</div></div><div class="detail-item"><div class="detail-label">📞 Contact Method</div><div class="detail-value">{contact_pref}</div></div></div><div class="budget-highlight">💰 Budget: ₦{budget:,}</div><p style="color:#555;line-height:1.7;margin:1.5rem 0;font-size:1.1rem;"><b>📝 Details:</b> {details}</p><div class="contact-section"><h4>📱 Contact Information</h4><p><strong>Method:</strong> {contact_pref}</p><p><strong>Details:</strong> {contact if contact != 'N/A' else 'Available via ' + contact_pref}</p></div></div>''', unsafe_allow_html=True)

                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("💬 Start Chat", key=f"chat_{record['id']}", use_container_width=True):
                        st.session_state.selected_contact = requester_name
                        st.session_state.page = "chat"
                        st.rerun()

    except requests.exceptions.RequestException as e:
        st.error("❌ Could not fetch requests.")
        st.exception(e)
# Add these functions to your code
def is_admin_user():
    """Check if current user is admin"""
    if not st.session_state.logged_in:
        return False
    current_user = st.session_state.current_user
    return current_user.get("Is_Admin", False) and st.session_state.get("selected_login_type") == "⚙️ Admin"
def create_announcement(title, message, admin_name, image_url=None):
    """Create a new announcement with optional image"""
    try:
        from datetime import datetime
        data = {
            "fields": {
                "Title": title,
                "Message": message,
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Posted_By": admin_name,
                "Active": True
            }
        }
        # Add image URL if provided
        if image_url:
            data["fields"]["Image_URL"] = image_url
        
        url = f"https://api.airtable.com/v0/{BASE_ID}/Announcements"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_PAT}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error creating announcement: {e}")
        return False
def delete_announcement(record_id):
    """Delete an announcement by record ID"""
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/Announcements/{record_id}"
        headers = {"Authorization": f"Bearer {AIRTABLE_PAT}"}
        
        response = requests.delete(url, headers=headers)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting announcement: {e}")
        return False
def fetch_announcements():
    """Fetch all active announcements"""
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/Announcements"
        headers = {"Authorization": f"Bearer {AIRTABLE_PAT}"}
        params = {
            "filterByFormula": "Active = TRUE()",
            "sort[0][field]": "Date",
            "sort[0][direction]": "desc"
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get("records", [])
        return []
    except Exception as e:
        st.error(f"Error fetching announcements: {e}")
        return []
def show_admin_announcements():
    """Admin page to manage announcements"""
    st.markdown("""
    <style>
    .admin-header {
        background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        color: white;
        box-shadow: 0 8px 25px rgba(231, 76, 60, 0.3);
    }
    .admin-card {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
        border-top: 4px solid #e74c3c;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="admin-header">
        <h1>⚙️ Admin Dashboard</h1>
        <p>Manage School Announcements</p>
    </div>
    """, unsafe_allow_html=True)
# Create new announcement
    st.markdown("""
    <div class="admin-card">
        <h3>📢 Create New Announcement</h3>
    </div>
    """, unsafe_allow_html=True)

    with st.form("new_announcement"):
        admin_name = st.text_input("👤 Your Name", placeholder="Enter your name (e.g., Principal Smith)")
        title = st.text_input("📝 Announcement Title", placeholder="Enter announcement title")
        message = st.text_area("💬 Message", placeholder="Write your announcement message here...", height=150)
    
        # Image upload
        uploaded_image = st.file_uploader("🖼️ Upload Poster/Image (Optional)", 
                                        type=["png", "jpg", "jpeg"], 
                                        help="Upload a poster or image for your announcement")
        if st.form_submit_button("📤 Post Announcement", type="primary"):
            if title and message and admin_name:
                image_url = None
            
                # Handle image upload
                if uploaded_image:
                    try:
                        file_bytes = uploaded_image.read()
                        image_url = upload_image_to_cloudinary(file_bytes, uploaded_image.name)
                        st.success(f"✅ Image uploaded: {uploaded_image.name}")
                    except Exception as e:
                        st.error(f"❌ Failed to upload image: {uploaded_image.name}")
                        st.exception(e)
            
            # Create announcement
            if create_announcement(title, message, admin_name, image_url):
                st.success("✅ Announcement posted successfully!")
                
                st.rerun()
                st.toast(f"📢 New Announcement: {title} ({datetime.now().strftime('%Y-%m-%d')})")
            else:
                st.error("❌ Failed to post announcement")
        else:
            st.warning("⚠️ Please fill in all required fields (Name, Title, Message)")
    
    
    # Show existing announcements
    st.markdown("""
    <div class="admin-card">
        <h3>📋 Existing Announcements</h3>
    </div>
    """, unsafe_allow_html=True)

    announcements = fetch_announcements()
    if announcements:
        for announcement in announcements:
            fields = announcement["fields"]
            record_id = announcement["id"]
            image_url = fields.get('Image_URL', '')
        
            col1, col2 = st.columns([4, 1])
        
            with col1:
                if image_url:
                    # Show image preview
                    st.image(image_url, width=200)
            
                st.markdown(f"""
                <div style="background: #f8f9fa; padding: 1rem; border-radius: 10px; margin-bottom: 1rem; border-left: 4px solid #007bff;">
                    <h4 style="margin: 0; color: #2c3e50;">{fields.get('Title', 'No Title')}</h4>
                    <p style="margin: 0.5rem 0; color: #6c757d;">{fields.get('Message', 'No Message')}</p>
                    <small style="color: #6c757d;">Posted on: {fields.get('Date', 'Unknown Date')} • By {fields.get('Posted_By', 'Admin')}</small>
                    {f'<br><small style="color: #28a745;">📷 Image attached</small>' if image_url else ''}
                </div>
                """, unsafe_allow_html=True)
        
            with col2:
                if st.button("🗑️ Delete", key=f"delete_{record_id}", type="secondary"):
                    if delete_announcement(record_id):
                        st.success("✅ Announcement deleted!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete announcement")
    else:
        st.info("📭 No announcements yet")
def show_student_dashboard():
    """Student dashboard with announcements"""
    st.markdown("""
    <style>
    .dashboard-header {
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        color: white;
        box-shadow: 0 8px 25px rgba(52, 152, 219, 0.3);
    }
    .announcement-card {
        background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border-left: 5px solid #007bff;
        box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
    }
    .announcement-card:hover {
        transform: translateY(-2px);
    }
    .announcement-title {
        color: #2c3e50;
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .announcement-message {
        color: #5a6c7d;
        line-height: 1.5;
        margin-bottom: 0.5rem;
    }
    .announcement-date {
        color: #95a5a6;
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="dashboard-header">
        <h1>🏫 School Dashboard</h1>
        <p>Stay updated with the latest announcements</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show announcements
    st.markdown("### 📢 Latest Announcements")

    announcements = fetch_announcements()
    if announcements:
        for announcement in announcements:
            fields = announcement["fields"]
            image_url = fields.get('Image_URL', '')
        
            # Clean the HTML tags from title and message
            title = fields.get('Title', 'No Title')
            message = fields.get('Message', 'No Message')
        
            # Remove HTML tags
            import re
            title = re.sub(r'<[^>]+>', '', title).strip()
            message = re.sub(r'<[^>]+>', '', message).strip()

            if image_url:
                # Announcement with image - Image on top, text below, click to expand
                st.markdown(f"""
                <div class="announcement-card" style="overflow: hidden; margin-bottom: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <a href="{image_url}" target="_blank" title="Click to expand">
                        <div style="width: 100%; height: 280px; background-image: url('{image_url}'); 
                            background-size: contain; background-repeat: no-repeat; background-position: center; 
                            background-color: #f8f9fa; border-radius: 12px 12px 0 0; position: relative; cursor: pointer;">
                            <div style="position: absolute; top: 15px; right: 15px; background: rgba(0,0,0,0.7); 
                                color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.8rem;">
                                📅 {fields.get('Date', 'Unknown Date')}
                            </div>
                            <div style="position: absolute; bottom: 15px; right: 15px; background: rgba(0,0,0,0.7); 
                                color: white; padding: 8px 12px; border-radius: 20px; font-size: 0.8rem;">
                                🔍 Click to expand
                            </div>
                        </div>
                    </a>
                    <div style="padding: 1.5rem; background: white; border-radius: 0 0 12px 12px;">
                        <div style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.8rem; color: #2c3e50;">
                            📌 {title}
                        </div>
                        <div style="font-size: 1.1rem; line-height: 1.6; color: #34495e; margin-bottom: 1rem;">
                            {message}
                        </div>
                        <div style="font-size: 0.9rem; color: #7f8c8d; display: flex; align-items: center; gap: 10px;">
                            <span>👤 {fields.get('Posted_By', 'Admin')}</span>
                            <span>•</span>
                            <span>📢 Announcement</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Regular announcement without image
                st.markdown(f"""
                <div class="announcement-card">
                    <div class="announcement-title">📌 {title}</div>
                    <div class="announcement-message">{message}</div>
                    <div class="announcement-date">📅 {fields.get('Date', 'Unknown Date')} • By {fields.get('Posted_By', 'Admin')}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("📭 No announcements at the moment. Check back later!")

    # Add some spacing
    st.markdown("<br>", unsafe_allow_html=True)

    # Test notification button
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📢 Announcements", len(announcements))
    with col2:
        st.metric("📅 Today", "Active")
    with col3:
        st.metric("👥 Community", "Online")
    with col4:
        if st.button("🔔 Test Notification"):
            st.toast("🎉 TEST NOTIFICATION 🎉\nThis is a test notification to show how awesome this feature is!")
def show_verification_page():
    """Display the account verification page for business users"""
    
    # Consolidated CSS
    st.markdown("""<style>
    .verification-header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:2rem;border-radius:15px;margin-bottom:2rem;text-align:center;color:white;box-shadow:0 10px 30px rgba(0,0,0,0.1)}
    .verification-header h1{font-size:2.5rem;font-weight:700;margin-bottom:0.5rem;text-shadow:2px 2px 4px rgba(0,0,0,0.3)}
    .benefit-card{background:white;border-radius:12px;padding:1.5rem;margin:1rem 0;box-shadow:0 5px 15px rgba(0,0,0,0.08);border-left:5px solid #28a745;transition:transform 0.3s ease}
    .benefit-card:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(0,0,0,0.12)}
    .benefit-icon{font-size:2rem;margin-bottom:1rem;display:block}
    .benefit-title{color:#2c3e50;font-size:1.3rem;font-weight:600;margin-bottom:0.5rem}
    .benefit-description{color:#6c757d;line-height:1.6;margin:0}
    .verification-cta{background:linear-gradient(135deg,#28a745 0%,#20c997 100%);color:white;padding:2rem;border-radius:15px;text-align:center;margin:2rem 0;box-shadow:0 8px 25px rgba(40,167,69,0.3)}
    .verification-cta h2{margin:0 0 1rem 0;font-size:1.8rem;font-weight:700}
    .verification-cta p{margin:0 0 1.5rem 0;font-size:1.1rem;opacity:0.9}
    .price-info{background:#e8f5e8;border:2px solid #28a745;border-radius:10px;padding:1.5rem;margin:1.5rem 0;text-align:center}
    .price-amount{color:#28a745;font-size:2.5rem;font-weight:800;margin:0}
    .price-period{color:#6c757d;font-size:1rem;margin:0}
    .whatsapp-button{background:linear-gradient(135deg,#25D366 0%,#128C7E 100%);color:white;padding:1rem 2rem;border-radius:50px;font-size:1.2rem;font-weight:600;text-decoration:none;display:inline-flex;align-items:center;gap:0.5rem;box-shadow:0 5px 15px rgba(37,211,102,0.4);transition:all 0.3s ease}
    .whatsapp-button:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(37,211,102,0.6);text-decoration:none;color:white}
    .already-verified{background:linear-gradient(135deg,#17a2b8 0%,#138496 100%);color:white;padding:1.5rem;border-radius:12px;text-align:center;margin:2rem 0}
    .verification-steps{background:#f8f9fa;border-radius:12px;padding:1.5rem;margin:2rem 0;border-left:5px solid #667eea}
    .step-item{display:flex;align-items:flex-start;margin:1rem 0;gap:1rem}
    .step-number{background:#667eea;color:white;width:2rem;height:2rem;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;flex-shrink:0}
    .step-content{flex:1}
    .step-title{font-weight:600;color:#2c3e50;margin-bottom:0.25rem}
    .step-description{color:#6c757d;font-size:0.9rem;margin:0}
    </style>""", unsafe_allow_html=True)
    
    current_user = st.session_state.get("current_user", {})
    is_verified = current_user.get("Verified", False)
    user_name = current_user.get("Name", "")
    
    # Header
    st.markdown('<div class="verification-header"><h1>✅ Get Verified</h1><p>Stand out from the crowd and build trust with clients</p></div>', unsafe_allow_html=True)
    
    # Already verified check
    if is_verified:
        st.markdown('<div class="already-verified"><h2>🎉 Congratulations!</h2><p>Your account is already verified. You now enjoy all the premium benefits of a verified business account.</p></div>', unsafe_allow_html=True)
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state.page = "🏠 Home"
            st.rerun()
        return
    
    # Benefits section
    st.markdown("## 🌟 Why Get Verified?")
    col1, col2 = st.columns(2)
    
    benefits = [
        ("🛡️", "Build Trust & Credibility", "Display a verified badge that shows clients you're a legitimate business, increasing your chances of getting hired by up to 70%."),
        ("📈", "Boost Your Visibility", "Verified accounts appear and get featured in our \"Verified Professionals\" section."),
        ("⭐", "Verified Profile Features", "Access advanced profile customization, priority support, and detailed analytics about your service performance."),
        ("💼", "Professional Recognition", "Join our exclusive network of verified professionals and get access to premium client opportunities.")
    ]
    
    for i, (icon, title, desc) in enumerate(benefits):
        col = col1 if i % 2 == 0 else col2
        col.markdown(f'<div class="benefit-card"><span class="benefit-icon">{icon}</span><div class="benefit-title">{title}</div><div class="benefit-description">{desc}</div></div>', unsafe_allow_html=True)
    
    # Pricing
    st.markdown('<div class="price-info"><div class="price-amount">₦2,950</div><div class="price-period">Per semester verification fee</div></div>', unsafe_allow_html=True)
    
    # Steps
    st.markdown("## 📋 How It Works")
    steps = [
        ("Click \"Get Verified Now\"", "This will open WhatsApp with a pre-filled message"),
        ("Send the Message", "Send the verification request via WhatsApp"),
        ("Make Payment", "Complete the ₦2,950 verification fee via bank transfer or mobile money"),
        ("Get Verified", "My team would come to you to make sure your business is legal\nYour account will be verified within 24 hours of payment confirmation"),
        ("When Verified", "If your business is legal you would be verfied\nYou would see a blue check-mark on your service")
    ]
    
    steps_html = '<div class="verification-steps">'
    for i, (title, desc) in enumerate(steps, 1):
        steps_html += f'<div class="step-item"><div class="step-number">{i}</div><div class="step-content"><div class="step-title">{title}</div>'
        for line in desc.strip().split('\n'):
            steps_html += f'<div class="step-description">{line}</div>'
        steps_html += '</div></div>'
    steps_html += '</div>'
    st.markdown(steps_html, unsafe_allow_html=True)
    
    # CTA
    st.markdown('<div class="verification-cta"><h2>🚀 Ready to Get Verified?</h2><p>Join thousands of verified professionals and take your business to the next level!</p></div>', unsafe_allow_html=True)
    
    # WhatsApp link generation
    def generate_whatsapp_link(user_name):
        phone_number = "2349130622391"
        current_time = datetime.now().strftime("%H:%M")
        message = f"""👋Hello Joel! 

I would like to verify my business account on your platform.

📋 My Details:
• Name: {user_name}
• Request: Account Verification
• Time: {current_time}
• Verification Fee: ₦2,950

Please guide me through the payment process to get my account verified.

Thank you! 🙏"""
        return f"https://wa.me/{phone_number}?text={urllib.parse.quote(message)}"
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        whatsapp_link = generate_whatsapp_link(user_name)
        st.markdown(f'<div style="text-align: center;"><a href="{whatsapp_link}" target="_blank" class="whatsapp-button">📱 Get Verified Now</a></div><br>', unsafe_allow_html=True)
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state.page = "🏠 Home"
            st.rerun()
    
    # FAQ Section
    st.markdown("---\n## ❓ Frequently Asked Questions")
    
    faqs = [
        ("What happens after I make payment?", "After payment confirmation:\n1. We come and make sure your business is legal\n2. Your account will be marked as verified within 24 hours\n3. You'll receive a confirmation message\n4. The verified badge will appear on your profile\n5. You'll gain access to all verified features"),
        ("Is the verification permanent?", "Yes for one semester! Once verified, your account remains verified for one full semester. This is a per semester fee."),
        ("What payment methods do you accept?", "We accept:\n- Bank Transfer\n- Mobile Money (MTN, Airtel, etc.)\n- USSD payments\n\nPayment details will be provided via WhatsApp."),
        ("Can I get a refund if I'm not satisfied?", "Verification is a service that's completed upon account approval. However, if there are any technical issues with the verification process, we'll work to resolve them or provide appropriate compensation.")
    ]
    
    for question, answer in faqs:
        with st.expander(question):
            st.write(answer)
    
    st.session_state.page = None
# ------------------ Navigation ------------------
# ------------------ Navigation ------------------
# Enhanced Navigation with improved UI/UX and Mobile Responsiveness

# Custom CSS for enhanced styling with mobile optimization
st.markdown("""
<style>
    /* Base Navigation Styles */
    .nav-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
        color: white;
        font-weight: bold;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        position: relative;
    }
    
    .nav-logo-container {
        background: white;
        padding: 0.8rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* Mobile-friendly close button */
    .nav-close-btn {
        position: absolute;
        top: 8px;
        right: 12px;
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: white;
        font-size: 20px;
        padding: 8px 12px;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        z-index: 1000;
    }
    
    .nav-close-btn:hover {
        background: rgba(255, 255, 255, 0.3);
        transform: scale(1.1);
    }
    
    /* Mobile navigation overlay */
    .mobile-nav-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 999;
        display: none;
    }
    
    /* Sidebar improvements for mobile */
    .css-1d391kg {
        padding-top: 1rem !important;
    }
    
    .user-info {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 0.8rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        text-align: center;
        color: white;
        font-weight: 500;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .nav-section {
        margin-bottom: 1rem;
    }
    
    .nav-section-title {
        color: #4a5568;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
        padding: 0.5rem;
        border-left: 3px solid #667eea;
        background: rgba(102, 126, 234, 0.05);
        border-radius: 0 6px 6px 0;
    }
    
    .logout-warning {
        background-color: #fed7d7;
        border: 1px solid #fc8181;
        border-radius: 6px;
        padding: 0.75rem;
        margin: 0.5rem 0;
        color: #742a2a;
        font-size: 0.9rem;
    }
    
    /* Enhanced Radio Button Styles */
    .stRadio > div {
        gap: 0.4rem;
    }
    
    .stRadio > div > label {
        background-color: #2d3748 !important;
        color: #e2e8f0 !important;
        padding: 0.7rem 0.9rem !important;
        border-radius: 8px !important;
        border: 1px solid #4a5568 !important;
        transition: all 0.3s ease !important;
        margin-bottom: 0.3rem !important;
        display: flex !important;
        align-items: center !important;
        cursor: pointer !important;
        min-height: 44px !important; /* Better touch target */
    }
    
    .stRadio > div > label:hover {
        background-color: #4a5568 !important;
        border-color: #667eea !important;
        color: #ffffff !important;
        transform: translateX(4px) !important;
        box-shadow: 0 3px 8px rgba(102, 126, 234, 0.3) !important;
    }
    
    .stRadio > div > label > div {
        color: #e2e8f0 !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
    }
    
    .stRadio > div > label:hover > div {
        color: #ffffff !important;
    }
    
    /* Selected state */
    .stRadio > div > label[data-checked="true"] {
        background-color: #667eea !important;
        border-color: #764ba2 !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
    
    .stRadio > div > label[data-checked="true"] > div {
        color: white !important;
        font-weight: 600 !important;
    }
    
    /* Mobile Responsive Design */
    @media (max-width: 768px) {
        /* Sidebar width adjustments */
        .css-1d391kg {
            width: 280px !important;
            max-width: 85vw !important;
        }
        
        .nav-header {
            padding: 0.8rem;
            font-size: 0.9rem;
        }
        
        .nav-close-btn {
            top: 6px;
            right: 8px;
            font-size: 18px;
            padding: 6px 10px;
        }
        
        .user-info {
            padding: 0.6rem;
            flex-direction: column !important;
            gap: 0.5rem !important;
        }
        
        .user-info img {
            width: 40px !important;
            height: 40px !important;
        }
        
        .nav-section-title {
            font-size: 0.7rem;
            padding: 0.4rem;
        }
        
        .stRadio > div > label {
            padding: 0.8rem !important;
            font-size: 0.85rem !important;
            min-height: 48px !important; /* Better touch on mobile */
        }
        
        .logout-warning {
            font-size: 0.8rem;
            padding: 0.6rem;
        }
    }
    
    @media (max-width: 480px) {
        .css-1d391kg {
            width: 260px !important;
            max-width: 90vw !important;
        }
        
        .nav-header {
            padding: 0.6rem;
            font-size: 0.85rem;
        }
        
        .stRadio > div > label {
            padding: 0.9rem !important;
            min-height: 52px !important; /* Even better touch on small phones */
        }
    }
    
    /* Tablet specific adjustments */
    @media (min-width: 769px) and (max-width: 1024px) {
        .css-1d391kg {
            width: 300px !important;
        }
        
        .stRadio > div > label {
            min-height: 46px !important;
        }
    }
    
    /* Better scrolling for long navigation lists */
    .css-1d391kg {
        overflow-y: auto !important;
        max-height: 100vh !important;
    }
    
    /* Improved button styling */
    .stButton > button {
        width: 100% !important;
        min-height: 44px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    
    /* Add visual feedback for navigation actions */
    .nav-section:hover {
        background: rgba(102, 126, 234, 0.02);
        border-radius: 8px;
        transition: all 0.3s ease;
    }
</style>
""", unsafe_allow_html=True)

# Add JavaScript for better mobile interaction
st.markdown("""
<script>
// Auto-close sidebar on mobile after selection
function autoCloseSidebar() {
    if (window.innerWidth <= 768) {
        // Find and click the sidebar close button if it exists
        const sidebarClose = document.querySelector('[data-testid="collapsedControl"]');
        if (sidebarClose) {
            setTimeout(() => {
                sidebarClose.click();
            }, 500);
        }
    }
}

// Listen for radio button changes
document.addEventListener('change', function(e) {
    if (e.target.type === 'radio' && e.target.name.includes('nav_')) {
        autoCloseSidebar();
    }
});

// Add touch-friendly interactions
document.addEventListener('DOMContentLoaded', function() {
    // Add visual feedback for touch events
    const labels = document.querySelectorAll('.stRadio label');
    labels.forEach(label => {
        label.addEventListener('touchstart', function() {
            this.style.transform = 'scale(0.98)';
        });
        
        label.addEventListener('touchend', function() {
            setTimeout(() => {
                this.style.transform = '';
            }, 150);
        });
    });
});
</script>
""", unsafe_allow_html=True)

# Logo Display - Replace Navigation Header
try:
    st.sidebar.image("linkup_logo.png", use_container_width=True)
except:
    # Fallback if logo doesn't exist
    st.sidebar.markdown("""
    <div class="nav-header">
        <div style="font-size: 1.3rem; margin-bottom: 0.5rem;">🔗 LinkUp</div>
        <div style="font-size: 0.8rem; opacity: 0.9;">
            📱 Swipe left or tap outside to close
        </div>
    </div>
    """, unsafe_allow_html=True)

# Sidebar close instruction
st.sidebar.markdown("""
<div style="text-align:center; margin:1rem 0;">
    <span style="font-size:1.2rem;">✕</span>
    <div style="font-size:0.95rem; color:#666;">
        To close this menu, tap the arrow at the top right.
    </div>
</div>
""", unsafe_allow_html=True)

# Enhanced User Info Display with mobile optimization
if st.session_state.logged_in:
    user = st.session_state.current_user
    user_name = user.get("Name", "Guest")
    user_type = user.get("User_Type", "Student")
    profile_image_url = user.get("Profile_Image", "")

    if profile_image_url:
        st.sidebar.markdown(f"""
        <div class="user-info" style="display: flex; align-items: center; gap: 0.75rem; justify-content: center; flex-wrap: wrap;">
            <a href="{profile_image_url}" target="_blank" title="Click to expand">
                <img src="{profile_image_url}" alt="Profile" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid #764ba2;cursor:pointer;">
            </a>
            <div style="text-align:center; flex: 1; min-width: 140px;">
                <div style="font-weight:600;font-size:1rem; line-height: 1.2;">Welcome, {user_name}!</div>
                <small style="opacity: 0.9;">{user_type} Account</small>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"""
        <div class="user-info" style="display: flex; align-items: center; gap: 0.75rem; justify-content: center; flex-wrap: wrap;">
            <span style="font-size:2.2rem;">👤</span>
            <div style="text-align:center; flex: 1; min-width: 140px;">
                <div style="font-weight:600;font-size:1rem; line-height: 1.2;">Welcome, {user_name}!</div>
                <small style="opacity: 0.9;">{user_type} Account</small>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div class="user-info">
        👋 Welcome, Guest!
        <div style="font-size: 0.8rem; margin-top: 0.3rem; opacity: 0.9;">
            Join our community today!
        </div>
    </div>
    """, unsafe_allow_html=True)

# Navigation Logic with Enhanced Organization
if not st.session_state.logged_in:
    # Guest Navigation 
    st.sidebar.markdown('<div class="nav-section-title">🌟 Get Started</div>', unsafe_allow_html=True)
    page = st.sidebar.radio("Choose your path:", ["Home", "Login", "Sign Up"], key="nav_guest")
else:
    # Check if user is admin
    is_admin = is_admin_user()
    user_type = st.session_state.current_user.get("User_Type", "Student")
    
    if is_admin:
        # Admin Navigation
        st.sidebar.markdown('<div class="nav-section-title">⚙️ Admin Panel</div>', unsafe_allow_html=True)
        admin_options = ["Home", "Manage Announcements"]
        
        st.sidebar.markdown('<div class="nav-section-title">👤 Account</div>', unsafe_allow_html=True)
        account_options = ["Logout"]

        all_options = admin_options + account_options
        page = st.sidebar.radio("Navigate to:", all_options, key="nav_admin")
        
    elif user_type == "Business":
        # Business User Navigation with Verification
        st.sidebar.markdown('<div class="nav-section-title">💼 Business Hub</div>', unsafe_allow_html=True)
        main_options = [ "Explore Services", "Update Profile", "Chats", "Post/Update Your Business/Service profile"]
    
        all_options = main_options + ["Logout"]
        page = st.sidebar.radio("Navigate to:", all_options, key="nav_business")
        
    elif user_type == "Student":
        # Student User Navigation with Dashboard
        st.sidebar.markdown('<div class="nav-section-title">🎯 Main Hub</div>', unsafe_allow_html=True)
        main_options = ["Explore Services", "Update Profile", "Post/Update Your Business/Service profile"]
        
        all_options = main_options + ["Logout"]
        page = st.sidebar.radio("Navigate to:", all_options, key="nav_student")
        
    else:  # user_type == "Both"
        # Both User Navigation with Verification
        st.sidebar.markdown('<div class="nav-section-title">🎯 Main Hub</div>', unsafe_allow_html=True)
        main_options = [ "Explore Services", "Update Profile", "Post/Update Your Business/Service profile"]
  
        all_options = main_options + ["Logout"]
        page = st.sidebar.radio("Navigate to:", all_options, key="nav_both")
        
    # Handle special page redirects from session state
    if st.session_state.get("page") == "view_talent":
        page = "View Talent"
    elif st.session_state.get("page") == "chat":
        page = "Chats"
    elif st.session_state.get("page") == "post_request":
        page = "post_request"
    elif st.session_state.get("page") == "Talents":
        page = "Talents"
    elif st.session_state.get("page") == "Talent zone":
        page = "Talent zone"
    elif st.session_state.get("page") == "verification":
        page = "Get Verified"

# Page Routing Logic
if page == "Home":
    show_home()
elif page == "Login":
    show_login()
elif page == "Sign Up":
    show_sign_up_or_update()
elif page == "Update Profile":
    show_sign_up_or_update()
elif page == "Logout":
    # Enhanced logout confirmation
    st.sidebar.markdown("""
    <div class="logout-warning">
        ⚠️ <strong>Logout Confirmation</strong><br>
        You're about to end your session.
    </div>
    """, unsafe_allow_html=True)
    if st.sidebar.button("🔓 Confirm Logout", type="primary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.current_user = {}
        st.success("✅ Successfully logged out!")
        st.rerun()
elif page == "Chats":
    show_chats()
elif page == "Talent Zone":
    Talent_Zone()
elif page == "Service Requests":
    post_request()
elif page == "View Talent":
    view_talent_profile()
elif page == "post_request":
    post_request()
elif page == "Talents":
    Talent_Zone()
elif page == "Explore Services":
    Talent_Zone()
elif page == "Post/Update Your Business/Service profile":
    update_profile()
elif page == "Manage Announcements":
    if is_admin_user():
        show_admin_announcements()
    else:
        st.error("⚠️ Access denied. Admin privileges required.")
elif page == "School Dashboard":
    show_student_dashboard()
elif page == "Get Verified":
    show_verification_page()
