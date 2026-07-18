# ============================================================
# APOB BOT — Automated Profit On Binary
# Professional Panel | Colourful Buttons | Clean Design
# ============================================================

import os, json, logging, threading, time, re, asyncio
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── Env Variables ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_USER_ID   = int(os.environ.get('TELEGRAM_USER_ID', 0) or 0)
PORT               = int(os.environ.get('PORT', 8080) or 8080)
PO_EMAIL           = os.environ.get('PO_EMAIL', '')
PO_PASSWORD        = os.environ.get('PO_PASSWORD', '')
CAPTCHA_KEY        = os.environ.get('CAPTCHA_KEY', '')

# ── Fix 409 conflict ───────────────────────────────────────────
try:
    import requests as _req
    _req.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    _req.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/close", timeout=10)
    time.sleep(3)
except: pass

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)

# ── User Storage ───────────────────────────────────────────────
USERS_FILE = 'apob_users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except: pass

users      = load_users()
user_state = {}

def get_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {
            'ssid':        '',
            'email':       '',
            'password':    '',
            'is_demo':     True,
            'amount':      1.0,
            'mg_levels':   2,
            'mg_multi':    2.0,
            'expiry':      1,
            'daily_limit': 20.0,
            'daily_loss':  0.0,
            'last_reset':  datetime.now().strftime('%Y-%m-%d'),
            'mode':        'auto',
            'connected':   False,
            'stats': {
                'total': 0, 'wins': 0,
                'losses': 0, 'profit': 0.0
            }
        }
        save_users(users)
    return users[uid]

# ── Keep Alive ─────────────────────────────────────────────────
keep_alive_started = False
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"APOB Bot alive!")
    def log_message(self, *args): pass

def start_keep_alive():
    global keep_alive_started
    if keep_alive_started: return
    try:
        s = HTTPServer(('0.0.0.0', PORT), KeepAliveHandler)
        t = threading.Thread(target=s.serve_forever)
        t.daemon = True
        t.start()
        keep_alive_started = True
        logger.info(f"✅ Keep alive on port {PORT}")
    except: pass

# ══════════════════════════════════════════════════════════════
# PANEL KEYBOARDS
# ══════════════════════════════════════════════════════════════

# ── Main Menu ──────────────────────────────────────────────────
def main_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🚀  Start Autotrade", callback_data="start_autotrade")
    )
    kb.add(
        InlineKeyboardButton("💰  Balance",          callback_data="balance"),
        InlineKeyboardButton("🔑  Login",            callback_data="login_menu")
    )
    kb.add(
        InlineKeyboardButton("📊  Trade Stats",      callback_data="stats"),
        InlineKeyboardButton("⚙️  Settings",         callback_data="settings_menu")
    )
    kb.add(
        InlineKeyboardButton("📖  FAQ / Help",       callback_data="help")
    )
    return kb

# ── Account Menu ───────────────────────────────────────────────
def account_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔄  Re-Login",         callback_data="relogin"),
        InlineKeyboardButton("🎮  Demo / Real",      callback_data="toggle_mode")
    )
    kb.add(
        InlineKeyboardButton("🏠  Main Menu",        callback_data="main_menu")
    )
    return kb

# ── Settings Menu ──────────────────────────────────────────────
def settings_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🎯  Autotrade Settings", callback_data="autotrade_settings")
    )
    kb.add(
        InlineKeyboardButton("⏳  Expiration Time",    callback_data="expiry_settings")
    )
    kb.add(
        InlineKeyboardButton("🤖  Manual / Auto",      callback_data="mode_settings")
    )
    kb.add(
        InlineKeyboardButton("🛑  Daily Loss Limit",   callback_data="loss_limit_settings")
    )
    kb.add(
        InlineKeyboardButton("🏠  Main Menu",          callback_data="main_menu")
    )
    return kb

# ── Autotrade Settings ─────────────────────────────────────────
def autotrade_settings_keyboard(user):
    amount  = user.get('amount', 1.0)
    mg_lvl  = user.get('mg_levels', 2)
    mg_mult = user.get('mg_multi', 2.0)
    kb = InlineKeyboardMarkup(row_width=3)
    # Base amount
    kb.add(
        InlineKeyboardButton("💵 $1",  callback_data="amt_1"),
        InlineKeyboardButton("💵 $2",  callback_data="amt_2"),
        InlineKeyboardButton("💵 $5",  callback_data="amt_5"),
    )
    kb.add(
        InlineKeyboardButton("💵 $10", callback_data="amt_10"),
        InlineKeyboardButton("💵 $20", callback_data="amt_20"),
        InlineKeyboardButton("✏️ Custom", callback_data="amt_custom"),
    )
    # Martingale levels
    kb.add(
        InlineKeyboardButton(f"{'✅' if mg_lvl==1 else '1️⃣'} MG Level 1", callback_data="mg_1"),
        InlineKeyboardButton(f"{'✅' if mg_lvl==2 else '2️⃣'} MG Level 2", callback_data="mg_2"),
    )
    kb.add(
        InlineKeyboardButton(f"{'✅' if mg_lvl==3 else '3️⃣'} MG Level 3", callback_data="mg_3"),
        InlineKeyboardButton(f"{'✅' if mg_lvl==4 else '4️⃣'} MG Level 4", callback_data="mg_4"),
    )
    # Multiplier
    kb.add(
        InlineKeyboardButton(f"{'✅' if mg_mult==2 else '✖️'} x2", callback_data="multi_2"),
        InlineKeyboardButton(f"{'✅' if mg_mult==3 else '✖️'} x3", callback_data="multi_3"),
        InlineKeyboardButton("✏️ Custom x", callback_data="multi_custom"),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="settings_menu"))
    return kb

# ── Expiry Settings ────────────────────────────────────────────
def expiry_settings_keyboard(user):
    expiry = user.get('expiry', 1)
    kb = InlineKeyboardMarkup(row_width=5)
    kb.add(
        InlineKeyboardButton(f"{'✅' if expiry==1 else '1️⃣'} 1m",  callback_data="exp_1"),
        InlineKeyboardButton(f"{'✅' if expiry==2 else '2️⃣'} 2m",  callback_data="exp_2"),
        InlineKeyboardButton(f"{'✅' if expiry==3 else '3️⃣'} 3m",  callback_data="exp_3"),
        InlineKeyboardButton(f"{'✅' if expiry==4 else '4️⃣'} 4m",  callback_data="exp_4"),
        InlineKeyboardButton(f"{'✅' if expiry==5 else '5️⃣'} 5m",  callback_data="exp_5"),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="settings_menu"))
    return kb

# ── Mode Settings ──────────────────────────────────────────────
def mode_settings_keyboard(user):
    mode = user.get('mode', 'auto')
    kb   = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            f"{'✅' if mode=='auto' else '🤖'} Auto Trade",
            callback_data="set_mode_auto"
        ),
        InlineKeyboardButton(
            f"{'✅' if mode=='manual' else '👤'} Manual Trade",
            callback_data="set_mode_manual"
        ),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="settings_menu"))
    return kb

# ── Loss Limit Settings ────────────────────────────────────────
def loss_limit_keyboard(user):
    limit = user.get('daily_limit', 20.0)
    kb    = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton(f"{'✅' if limit==10 else ''} $10",  callback_data="lim_10"),
        InlineKeyboardButton(f"{'✅' if limit==20 else ''} $20",  callback_data="lim_20"),
        InlineKeyboardButton(f"{'✅' if limit==50 else ''} $50",  callback_data="lim_50"),
    )
    kb.add(
        InlineKeyboardButton(f"{'✅' if limit==100 else ''} $100", callback_data="lim_100"),
        InlineKeyboardButton("✏️ Custom",                          callback_data="lim_custom"),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="settings_menu"))
    return kb

# ── Login Menu ─────────────────────────────────────────────────
def login_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📧  Login with Email & Password", callback_data="login_email"),
        InlineKeyboardButton("🔑  Login with SSID",             callback_data="login_ssid"),
        InlineKeyboardButton("🏠  Main Menu",                   callback_data="main_menu"),
    )
    return kb

# ── Manual Trade Menu ──────────────────────────────────────────
def manual_trade_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("EUR/USD OTC", callback_data="tr_EURUSD_otc"),
        InlineKeyboardButton("GBP/USD OTC", callback_data="tr_GBPUSD_otc"),
        InlineKeyboardButton("USD/JPY OTC", callback_data="tr_USDJPY_otc"),
        InlineKeyboardButton("AUD/USD OTC", callback_data="tr_AUDUSD_otc"),
        InlineKeyboardButton("NGN/USD OTC", callback_data="tr_NGNUSD_otc"),
        InlineKeyboardButton("EUR/GBP OTC", callback_data="tr_EURGBP_otc"),
        InlineKeyboardButton("GBP/JPY OTC", callback_data="tr_GBPJPY_otc"),
        InlineKeyboardButton("USD/CAD OTC", callback_data="tr_USDCAD_otc"),
    )
    kb.add(InlineKeyboardButton("🏠  Main Menu", callback_data="main_menu"))
    return kb

def direction_keyboard(asset):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🟢  BUY / CALL", callback_data=f"dir_{asset}_call"),
        InlineKeyboardButton("🔴  SELL / PUT",  callback_data=f"dir_{asset}_put"),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="manual_trade"))
    return kb

def expiry_trade_keyboard(asset, direction):
    kb = InlineKeyboardMarkup(row_width=5)
    kb.add(
        InlineKeyboardButton("1m", callback_data=f"texp_{asset}_{direction}_1"),
        InlineKeyboardButton("2m", callback_data=f"texp_{asset}_{direction}_2"),
        InlineKeyboardButton("3m", callback_data=f"texp_{asset}_{direction}_3"),
        InlineKeyboardButton("4m", callback_data=f"texp_{asset}_{direction}_4"),
        InlineKeyboardButton("5m", callback_data=f"texp_{asset}_{direction}_5"),
    )
    kb.add(InlineKeyboardButton("◀️  Back", callback_data="manual_trade"))
    return kb

# ══════════════════════════════════════════════════════════════
# MESSAGE BUILDERS
# ══════════════════════════════════════════════════════════════

def build_home_message(uid):
    user       = get_user(uid)
    is_demo    = user.get('is_demo', True)
    mode_text  = "🔵 DEMO" if is_demo else "🔴 REAL"
    trade_mode = "🤖 Auto" if user.get('mode') == 'auto' else "👤 Manual"
    connected  = "🟢 Connected" if user.get('connected') else "🔴 Not Connected"
    stats      = user.get('stats', {'total':0,'wins':0,'losses':0,'profit':0.0})
    wr         = (stats['wins']/stats['total']*100) if stats['total'] > 0 else 0
    daily_loss = user.get('daily_loss', 0.0)
    limit      = user.get('daily_limit', 20.0)

    return (
        f"🔴🔵 <b>APOB BOT</b> 🔴🔵\n"
        f"<i>Automated Profit On Binary</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📡 Status: {connected}\n"
        f"🎮 Trading Mode: <b>{mode_text}</b>\n"
        f"⚙️ Engine: <b>{trade_mode}</b>\n\n"
        f"💰 <b>Balance</b>\n"
        f"💵 Real Balance: <b>$0.00</b>\n"
        f"🎮 Demo Balance: <b>$0.00</b>\n\n"
        f"📊 <b>Today's Stats</b>\n"
        f"🔢 Trades: {stats['total']} | ✅ {stats['wins']} | ❌ {stats['losses']}\n"
        f"🎯 Win Rate: {wr:.1f}%\n"
        f"💰 P/L: ${stats['profit']:.2f}\n"
        f"🛑 Daily Loss: ${daily_loss:.2f} / ${limit:.2f}\n\n"
        f"⚙️ <b>Settings</b>\n"
        f"💵 Amount: ${user.get('amount',1.0)} | "
        f"📈 MG: {user.get('mg_levels',2)}x{user.get('mg_multi',2.0)}\n"
        f"⏱️ Expiry: {user.get('expiry',1)}min\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid  = str(message.from_user.id)
    name = message.from_user.first_name or "Trader"
    get_user(uid)
    user_state.pop(uid, None)
    bot.send_message(
        message.chat.id,
        f"🔴🔵 <b>APOB BOT</b> 🔴🔵\n"
        f"<i>Automated Profit On Binary</i>\n\n"
        f"👋 Welcome <b>{name}</b>!\n\n"
        f"Your professional binary options\n"
        f"trading assistant is ready.\n\n"
        f"🔑 Login to get started!\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode='HTML',
        reply_markup=main_menu_keyboard()
    )

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    uid  = str(call.from_user.id)
    user = get_user(uid)
    data = call.data
    bot.answer_callback_query(call.id)
    cid  = call.message.chat.id
    mid  = call.message.message_id

    # ── Main Menu ──────────────────────────────────────────────
    if data == 'main_menu':
        bot.edit_message_text(
            build_home_message(uid),
            cid, mid,
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )

    # ── Start Autotrade ────────────────────────────────────────
    elif data == 'start_autotrade':
        if not user.get('connected'):
            bot.edit_message_text(
                "🔴🔵 <b>APOB BOT</b>\n\n"
                "❌ Not connected to Pocket Option!\n\n"
                "Please login first using\n"
                "🔑 <b>Login</b> button.",
                cid, mid,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🔑 Login Now", callback_data="login_menu"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
                )
            )
            return
        mode_text = "🔵 DEMO" if user.get('is_demo', True) else "🔴 REAL"
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"🚀 <b>AUTOTRADE STARTED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Watching signal source\n"
            f"🎮 Mode: {mode_text}\n"
            f"💵 Amount: ${user.get('amount',1.0)}\n"
            f"📈 Martingale: {user.get('mg_levels',2)} levels x{user.get('mg_multi',2.0)}\n"
            f"⏱️ Expiry: {user.get('expiry',1)} min\n"
            f"🛑 Daily Limit: ${user.get('daily_limit',20.0)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"You will be notified of every trade!",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🛑 Stop Autotrade", callback_data="stop_autotrade"),
                InlineKeyboardButton("🏠 Main Menu",      callback_data="main_menu")
            )
        )

    # ── Stop Autotrade ─────────────────────────────────────────
    elif data == 'stop_autotrade':
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "🛑 <b>AUTOTRADE STOPPED!</b>\n\n"
            "No more trades will be placed.\n"
            "Click 🚀 Start Autotrade to resume.",
            cid, mid,
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )

    # ── Balance ────────────────────────────────────────────────
    elif data == 'balance':
        mode = "🔵 DEMO" if user.get('is_demo', True) else "🔴 REAL"
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"💰 <b>YOUR BALANCE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 Mode: {mode}\n"
            f"💵 Real Balance: $0.00 USD\n"
            f"🎮 Demo Balance: $0.00 USD\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Connect PO account to see\nyour real balance!",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔄 Refresh",   callback_data="balance"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
            )
        )

    # ── Login Menu ─────────────────────────────────────────────
    elif data == 'login_menu':
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "🔑 <b>LOGIN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Choose your login method:\n\n"
            "📧 <b>Email & Password</b>\n"
            "Auto fetches your SSID\n\n"
            "🔑 <b>SSID</b>\n"
            "Paste your session ID directly",
            cid, mid,
            parse_mode='HTML',
            reply_markup=login_menu_keyboard()
        )

    elif data == 'login_email':
        user_state[uid] = 'wait_email'
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "📧 <b>EMAIL LOGIN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please type your\n"
            "<b>Pocket Option Email:</b>",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Back", callback_data="login_menu")
            )
        )

    elif data == 'login_ssid':
        user_state[uid] = 'wait_ssid'
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "🔑 <b>SSID LOGIN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Paste your <b>Pocket Option SSID:</b>\n\n"
            "How to get SSID:\n"
            "1. Open pocketoption.com on PC\n"
            "2. Login → Press F12\n"
            "3. Application → Cookies\n"
            "4. Copy 'ssid' value",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Back", callback_data="login_menu")
            )
        )

    elif data == 'relogin':
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "🔄 <b>RE-LOGIN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Choose login method:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=login_menu_keyboard()
        )

    # ── Toggle Demo/Real ───────────────────────────────────────
    elif data == 'toggle_mode':
        user['is_demo'] = not user.get('is_demo', True)
        save_users(users)
        mode = "🔵 DEMO" if user['is_demo'] else "🔴 REAL"
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"✅ Switched to <b>{mode}</b> mode!\n\n"
            f"{'⚠️ You are now trading with real money!' if not user['is_demo'] else '✅ Safe demo mode active'}",
            cid, mid,
            parse_mode='HTML',
            reply_markup=account_menu_keyboard()
        )

    # ── Settings ───────────────────────────────────────────────
    elif data == 'settings_menu':
        user = get_user(uid)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"⚙️ <b>SETTINGS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 Autotrade Settings\n"
            f"Fine-tune the bot to match your style.\n\n"
            f"⏳ Expiration Time\n"
            f"Decide when your trades close.\n\n"
            f"🤖 Manual / Auto\n"
            f"Switch between Manual and Autotrade.\n\n"
            f"🛑 Daily Loss Limit\n"
            f"Protect your capital automatically.",
            cid, mid,
            parse_mode='HTML',
            reply_markup=settings_menu_keyboard()
        )

    elif data == 'autotrade_settings':
        user = get_user(uid)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"🎯 <b>AUTOTRADE SETTINGS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💵 Base Amount: <b>${user.get('amount',1.0)}</b>\n"
            f"📈 Martingale: <b>{user.get('mg_levels',2)} levels x{user.get('mg_multi',2.0)}</b>\n\n"
            f"Example sequence:\n"
            f"${user.get('amount',1.0)} → "
            f"${round(user.get('amount',1.0)*user.get('mg_multi',2.0),2)} → "
            f"${round(user.get('amount',1.0)*user.get('mg_multi',2.0)**2,2)}",
            cid, mid,
            parse_mode='HTML',
            reply_markup=autotrade_settings_keyboard(user)
        )

    elif data == 'expiry_settings':
        user = get_user(uid)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"⏳ <b>EXPIRATION TIME</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: <b>{user.get('expiry',1)} minute(s)</b>\n\n"
            f"Choose your expiry time:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=expiry_settings_keyboard(user)
        )

    elif data == 'mode_settings':
        user = get_user(uid)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"🤖 <b>TRADING MODE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: <b>{'🤖 Auto' if user.get('mode')=='auto' else '👤 Manual'}</b>\n\n"
            f"🤖 <b>Auto</b> — Bot trades signals automatically\n"
            f"👤 <b>Manual</b> — You control every trade",
            cid, mid,
            parse_mode='HTML',
            reply_markup=mode_settings_keyboard(user)
        )

    elif data == 'loss_limit_settings':
        user = get_user(uid)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"🛑 <b>DAILY LOSS LIMIT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current limit: <b>${user.get('daily_limit',20.0)}</b>\n"
            f"Today's loss: <b>${user.get('daily_loss',0.0):.2f}</b>\n\n"
            f"Bot stops trading when daily\nloss reaches this limit:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=loss_limit_keyboard(user)
        )

    # ── Amount Settings ────────────────────────────────────────
    elif data.startswith('amt_'):
        v = data.replace('amt_', '')
        if v == 'custom':
            user_state[uid] = 'wait_amount'
            bot.edit_message_text(
                "💵 Enter your base trade amount:\nExample: 3.5",
                cid, mid,
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("◀️ Back", callback_data="autotrade_settings")
                )
            )
        else:
            user['amount'] = float(v)
            save_users(users)
            bot.answer_callback_query(call.id, f"✅ Amount set to ${v}")
            bot.edit_message_reply_markup(cid, mid, reply_markup=autotrade_settings_keyboard(user))

    # ── Martingale Levels ──────────────────────────────────────
    elif data.startswith('mg_'):
        user['mg_levels'] = int(data.replace('mg_', ''))
        save_users(users)
        bot.answer_callback_query(call.id, f"✅ MG levels: {user['mg_levels']}")
        bot.edit_message_reply_markup(cid, mid, reply_markup=autotrade_settings_keyboard(user))

    # ── Multiplier ─────────────────────────────────────────────
    elif data.startswith('multi_'):
        v = data.replace('multi_', '')
        if v == 'custom':
            user_state[uid] = 'wait_multi'
            bot.edit_message_text(
                "✖️ Enter multiplier:\nExample: 2.5",
                cid, mid,
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("◀️ Back", callback_data="autotrade_settings")
                )
            )
        else:
            user['mg_multi'] = float(v)
            save_users(users)
            bot.answer_callback_query(call.id, f"✅ Multiplier: x{v}")
            bot.edit_message_reply_markup(cid, mid, reply_markup=autotrade_settings_keyboard(user))

    # ── Expiry ─────────────────────────────────────────────────
    elif data.startswith('exp_'):
        user['expiry'] = int(data.replace('exp_', ''))
        save_users(users)
        bot.answer_callback_query(call.id, f"✅ Expiry: {user['expiry']}min")
        bot.edit_message_reply_markup(cid, mid, reply_markup=expiry_settings_keyboard(user))

    # ── Mode ───────────────────────────────────────────────────
    elif data.startswith('set_mode_'):
        user['mode'] = data.replace('set_mode_', '')
        save_users(users)
        mode_name = "🤖 Auto" if user['mode'] == 'auto' else "👤 Manual"
        bot.answer_callback_query(call.id, f"✅ Mode: {mode_name}")
        bot.edit_message_reply_markup(cid, mid, reply_markup=mode_settings_keyboard(user))

    # ── Loss Limit ─────────────────────────────────────────────
    elif data.startswith('lim_'):
        v = data.replace('lim_', '')
        if v == 'custom':
            user_state[uid] = 'wait_limit'
            bot.edit_message_text(
                "🛑 Enter daily loss limit:\nExample: 30",
                cid, mid,
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("◀️ Back", callback_data="loss_limit_settings")
                )
            )
        else:
            user['daily_limit'] = float(v)
            save_users(users)
            bot.answer_callback_query(call.id, f"✅ Limit: ${v}")
            bot.edit_message_reply_markup(cid, mid, reply_markup=loss_limit_keyboard(user))

    # ── Stats ──────────────────────────────────────────────────
    elif data == 'stats':
        stats = user.get('stats', {'total':0,'wins':0,'losses':0,'profit':0.0})
        wr    = (stats['wins']/stats['total']*100) if stats['total'] > 0 else 0
        p     = stats['profit']
        sign  = '+' if p >= 0 else ''
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"📊 <b>TRADE STATS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔢 Total Trades: <b>{stats['total']}</b>\n"
            f"✅ Wins: <b>{stats['wins']}</b>\n"
            f"❌ Losses: <b>{stats['losses']}</b>\n"
            f"🎯 Win Rate: <b>{wr:.1f}%</b>\n"
            f"💰 Total P/L: <b>{sign}${p:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 Daily Loss: ${user.get('daily_loss',0):.2f}\n"
            f"📅 Limit: ${user.get('daily_limit',20):.2f}",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔄 Refresh",   callback_data="stats"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
            )
        )

    # ── Manual Trade ───────────────────────────────────────────
    elif data == 'manual_trade':
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "👤 <b>MANUAL TRADE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Select your asset:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=manual_trade_keyboard()
        )

    elif data.startswith('tr_'):
        asset = data.replace('tr_', '')
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"👤 <b>MANUAL TRADE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Asset: <b>{asset}</b>\n\n"
            f"Choose direction:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=direction_keyboard(asset)
        )

    elif data.startswith('dir_'):
        parts     = data.split('_')
        direction = parts[-1]
        asset     = '_'.join(parts[1:-1])
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"👤 <b>MANUAL TRADE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Asset: <b>{asset}</b>\n"
            f"Direction: <b>{'🟢 BUY/CALL' if direction=='call' else '🔴 SELL/PUT'}</b>\n\n"
            f"Choose expiry time:",
            cid, mid,
            parse_mode='HTML',
            reply_markup=expiry_trade_keyboard(asset, direction)
        )

    elif data.startswith('texp_'):
        parts     = data.split('_')
        expiry    = int(parts[-1])
        direction = parts[-2]
        asset     = '_'.join(parts[1:-2])
        amount    = user.get('amount', 1.0)
        bot.edit_message_text(
            f"🔴🔵 <b>APOB BOT</b>\n\n"
            f"⏳ <b>PLACING TRADE...</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Asset: <b>{asset}</b>\n"
            f"Direction: <b>{'🟢 BUY' if direction=='call' else '🔴 SELL'}</b>\n"
            f"Amount: <b>${amount}</b>\n"
            f"Expiry: <b>{expiry} min</b>\n\n"
            f"⏳ Executing trade...",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
            )
        )
        # Trade execution will be added when PO connection is ready

    # ── Help ───────────────────────────────────────────────────
    elif data == 'help':
        bot.edit_message_text(
            "🔴🔵 <b>APOB BOT</b>\n\n"
            "📖 <b>FAQ / HELP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 <b>Start Autotrade</b>\n"
            "Bot automatically trades signals\n\n"
            "🔑 <b>Login</b>\n"
            "Connect your Pocket Option account\n\n"
            "⚙️ <b>Settings</b>\n"
            "• Set base amount\n"
            "• Configure martingale levels\n"
            "• Choose expiry time (1-5 min)\n"
            "• Set daily loss limit\n\n"
            "👤 <b>Manual Trade</b>\n"
            "Place trades yourself manually\n\n"
            "📊 <b>Stats</b>\n"
            "View your win/loss record\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Always test on DEMO first!\n"
            "🛑 Set a daily limit to protect capital!",
            cid, mid,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
            )
        )

# ── Text Message Handler ───────────────────────────────────────
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid   = str(message.from_user.id)
    text  = message.text.strip()
    state = user_state.get(uid)
    user  = get_user(uid)

    if state == 'wait_email':
        user_state[uid]  = 'wait_password'
        user['_email']   = text
        save_users(users)
        bot.send_message(
            message.chat.id,
            "🔒 Now enter your <b>Password:</b>",
            parse_mode='HTML'
        )

    elif state == 'wait_password':
        user_state.pop(uid, None)
        email    = user.get('_email', '')
        password = text
        user['email']    = email
        user['password'] = password
        save_users(users)
        bot.send_message(
            message.chat.id,
            "⏳ <b>Logging in to Pocket Option...</b>\n"
            "Please wait...",
            parse_mode='HTML'
        )
        # Auto login will connect here
        bot.send_message(
            message.chat.id,
            "✅ <b>Credentials saved!</b>\n"
            "Connecting to Pocket Option...",
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )

    elif state == 'wait_ssid':
        user_state.pop(uid, None)
        user['ssid'] = text
        save_users(users)
        bot.send_message(
            message.chat.id,
            "✅ <b>SSID Saved!</b>\n"
            "Connecting to Pocket Option...",
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )

    elif state == 'wait_amount':
        user_state.pop(uid, None)
        try:
            amt = float(text)
            if amt < 0.5:
                bot.send_message(message.chat.id, "❌ Minimum is $0.50")
                return
            user['amount'] = amt
            save_users(users)
            bot.send_message(message.chat.id, f"✅ Amount set to ${amt:.2f}", reply_markup=main_menu_keyboard())
        except:
            bot.send_message(message.chat.id, "❌ Invalid amount. Enter a number like 3.5")

    elif state == 'wait_multi':
        user_state.pop(uid, None)
        try:
            multi = float(text)
            if multi < 1.5:
                bot.send_message(message.chat.id, "❌ Minimum multiplier is 1.5")
                return
            user['mg_multi'] = multi
            save_users(users)
            bot.send_message(message.chat.id, f"✅ Multiplier set to x{multi}", reply_markup=main_menu_keyboard())
        except:
            bot.send_message(message.chat.id, "❌ Invalid multiplier")

    elif state == 'wait_limit':
        user_state.pop(uid, None)
        try:
            lim = float(text)
            if lim < 1:
                bot.send_message(message.chat.id, "❌ Minimum limit is $1")
                return
            user['daily_limit'] = lim
            save_users(users)
            bot.send_message(message.chat.id, f"✅ Daily limit set to ${lim:.2f}", reply_markup=main_menu_keyboard())
        except:
            bot.send_message(message.chat.id, "❌ Invalid amount")
    else:
        # Show main menu for any other message
        bot.send_message(
            message.chat.id,
            build_home_message(uid),
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )

# ── Main ───────────────────────────────────────────────────────
def main():
    start_keep_alive()
    logger.info("🚀 Starting APOB Bot...")
    try:
        bot.send_message(
            TELEGRAM_USER_ID,
            "🔴🔵 <b>APOB BOT IS LIVE!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Panel ready\n"
            "✅ All settings available\n\n"
            "Type /start to open your panel!",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Startup msg error: {e}")

    logger.info("✅ APOB Bot polling started!")
    bot.infinity_polling(
        timeout=60,
        long_polling_timeout=60,
        skip_pending=True,
        allowed_updates=["message", "callback_query"]
    )

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"💥 Crash: {e}")
        logger.warning("🔄 Restarting in 30s...")
        time.sleep(30)
