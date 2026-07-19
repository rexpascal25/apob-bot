# ============================================================
# APOB Bot — PO Login Module
# Simple HTTP login — no Playwright/Selenium needed
# ============================================================

import os, json, logging, requests, re, time
logger = logging.getLogger(__name__)

PO_EMAIL    = os.environ.get('PO_EMAIL', '')
PO_PASSWORD = os.environ.get('PO_PASSWORD', '')

def auto_login_and_get_ssid(email=None, password=None):
    """
    Login to Pocket Option via HTTP
    Returns SSID if successful, None if failed
    """
    email    = email    or PO_EMAIL
    password = password or PO_PASSWORD

    if not email or not password:
        logger.error("No email/password provided!")
        return None

    logger.info(f"🔐 Attempting login for {email}...")

    session = requests.Session()
    session.headers.update({
        'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept':          'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin':          'https://pocketoption.com',
        'Referer':         'https://pocketoption.com/en/login/',
    })

    try:
        # Step 1 — Get login page to get cookies/tokens
        logger.info("Getting login page...")
        resp = session.get('https://pocketoption.com/en/login/', timeout=15)
        logger.info(f"Login page status: {resp.status_code}")

        # Step 2 — Try JSON API login
        logger.info("Attempting API login...")
        login_resp = session.post(
            'https://pocketoption.com/en/login/',
            data={
                'email':    email,
                'password': password,
                'remember': '1',
            },
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
            },
            timeout=20,
            allow_redirects=True
        )
        logger.info(f"Login response: {login_resp.status_code}")

        # Step 3 — Check cookies for SSID
        cookies = session.cookies.get_dict()
        logger.info(f"Cookies received: {list(cookies.keys())}")

        for key in ['ssid', 'SSID', 'session', 'SESSION']:
            if key in cookies:
                ssid = cookies[key]
                logger.info(f"✅ Got SSID from cookie '{key}'")
                return ssid

        # Step 4 — Try to extract from response
        try:
            data = login_resp.json()
            for key in ['ssid', 'session', 'token', 'sid']:
                if key in data:
                    logger.info(f"✅ Got SSID from response '{key}'")
                    return data[key]
        except: pass

        # Step 5 — Check if logged in by visiting dashboard
        dash = session.get('https://pocketoption.com/en/cabinet/', timeout=15)
        cookies = session.cookies.get_dict()
        logger.info(f"Dashboard cookies: {list(cookies.keys())}")

        for key in ['ssid', 'SSID', 'session', 'ci_session']:
            if key in cookies and len(cookies[key]) > 10:
                logger.info(f"✅ Got SSID from dashboard cookie '{key}'")
                return cookies[key]

        logger.error("❌ Login failed - no SSID found in cookies")
        logger.info(f"Available cookies: {cookies}")
        return None

    except Exception as e:
        logger.error(f"Login error: {e}")
        return None
