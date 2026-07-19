# ============================================================
# APOB Bot — Strategy Engine
# Double SMA + Fractal Strategy
# SMA 2 (orange) + SMA 5 (green) + Fractal (period 2)
# Timeframe: 2 minute candles | Expiry: 5 seconds
# OTC pairs only!
# ============================================================

import asyncio
import logging
import time
import json
import websockets
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ── OTC Assets To Trade ────────────────────────────────────────
OTC_ASSETS = [
    "EURUSD_otc",
    "GBPUSD_otc",
    "USDJPY_otc",
    "AUDUSD_otc",
    "EURGBP_otc",
    "USDCAD_otc",
    "GBPJPY_otc",
    "NGNUSD_otc",
]

# ── Candle Data Store ──────────────────────────────────────────
# Stores last 10 candles per asset
candle_store = {}  # {asset: [candle1, candle2, ...]}
# Each candle = {open, high, low, close, time}

# ══════════════════════════════════════════════════════════════
# INDICATOR CALCULATIONS
# ══════════════════════════════════════════════════════════════

def calculate_sma(candles, period):
    """Calculate Simple Moving Average"""
    if len(candles) < period:
        return None
    closes = [c['close'] for c in candles[-period:]]
    return sum(closes) / period

def calculate_fractal_up(candles, period=2):
    """
    Fractal UP (sell signal) — high point surrounded by lower highs
    Middle candle has highest high of the group
    """
    if len(candles) < (period * 2 + 1):
        return False
    mid   = len(candles) - period - 1
    highs = [c['high'] for c in candles]
    mid_high = highs[mid]
    # Check all surrounding candles have lower highs
    for i in range(mid - period, mid + period + 1):
        if i != mid and highs[i] >= mid_high:
            return False
    return True

def calculate_fractal_down(candles, period=2):
    """
    Fractal DOWN (buy signal) — low point surrounded by higher lows
    Middle candle has lowest low of the group
    """
    if len(candles) < (period * 2 + 1):
        return False
    mid  = len(candles) - period - 1
    lows = [c['low'] for c in candles]
    mid_low = lows[mid]
    # Check all surrounding candles have higher lows
    for i in range(mid - period, mid + period + 1):
        if i != mid and lows[i] <= mid_low:
            return False
    return True

def get_candle_close_position(candle):
    """
    Determine where candle closed relative to its range
    Returns: 'top', 'middle', 'bottom'
    TOP    = close in upper 33% = SELL signal
    MIDDLE = close in middle 34% = BUY signal
    BOTTOM = close in lower 33% = potential BUY
    """
    high  = candle['high']
    low   = candle['low']
    close = candle['close']
    
    if high == low:
        return 'middle'
    
    position = (close - low) / (high - low)
    
    if position >= 0.67:
        return 'top'       # Close at top = SELL
    elif position >= 0.33:
        return 'middle'    # Close at middle = BUY
    else:
        return 'bottom'    # Close at bottom = BUY

def is_market_jumping(candles, threshold=3.0):
    """
    Detect if market is jumping/choppy
    Returns True if market is unstable (skip trade)
    """
    if len(candles) < 3:
        return False
    # Check last 3 candles for excessive volatility
    recent = candles[-3:]
    ranges = [(c['high'] - c['low']) for c in recent]
    avg_range = sum(ranges) / len(ranges)
    # If any candle range is 3x the average, market is jumping
    for r in ranges:
        if r > avg_range * threshold:
            return True
    return False

def check_sma_crossover(candles):
    """
    Check if SMA 2 and SMA 5 have crossed
    Returns: 'bullish' (buy), 'bearish' (sell), or None
    """
    if len(candles) < 6:
        return None
    
    # Current values
    sma2_now = calculate_sma(candles, 2)
    sma5_now = calculate_sma(candles, 5)
    
    # Previous values (one candle ago)
    sma2_prev = calculate_sma(candles[:-1], 2)
    sma5_prev = calculate_sma(candles[:-1], 5)
    
    if None in [sma2_now, sma5_now, sma2_prev, sma5_prev]:
        return None
    
    # Bullish crossover: SMA2 crossed above SMA5
    if sma2_prev <= sma5_prev and sma2_now > sma5_now:
        return 'bullish'
    
    # Bearish crossover: SMA2 crossed below SMA5
    if sma2_prev >= sma5_prev and sma2_now < sma5_now:
        return 'bearish'
    
    return None

def confirm_next_candle_direction(candles):
    """
    Check direction of the latest forming candle
    Returns: 'up', 'down', or 'unclear'
    """
    if len(candles) < 2:
        return 'unclear'
    
    latest = candles[-1]
    body = latest['close'] - latest['open']
    
    if body > 0:
        return 'up'
    elif body < 0:
        return 'down'
    return 'unclear'

# ══════════════════════════════════════════════════════════════
# MAIN STRATEGY LOGIC
# ══════════════════════════════════════════════════════════════

def analyze_signal(asset, candles):
    """
    Main strategy analysis
    Returns signal dict or None
    
    Strategy Rules:
    1. Wait for SMA 2 and SMA 5 to cross
    2. At the crossover candle close:
       - Close at TOP (67-100%) = SELL
       - Close at MIDDLE (33-67%) = BUY
    3. Confirm with next candle direction
    4. Skip if market is jumping
    5. Enter with 5 second expiry on OTC only
    """
    if len(candles) < 7:
        return None
    
    # Rule 1: Skip jumping markets
    if is_market_jumping(candles):
        logger.info(f"{asset}: Market jumping — skipping")
        return None
    
    # Rule 2: Check for SMA crossover
    crossover = check_sma_crossover(candles)
    if not crossover:
        return None
    
    logger.info(f"{asset}: SMA crossover detected — {crossover}")
    
    # Rule 3: Check candle close position
    last_candle   = candles[-1]
    close_position = get_candle_close_position(last_candle)
    
    logger.info(f"{asset}: Candle close position — {close_position}")
    
    # Rule 4: Check fractal confirmation
    fractal_up   = calculate_fractal_up(candles)
    fractal_down = calculate_fractal_down(candles)
    
    # Rule 5: Determine direction
    direction = None
    confidence = 0
    
    if crossover == 'bullish':
        if close_position in ['middle', 'bottom']:
            direction  = 'call'  # BUY
            confidence = 80
            if fractal_down:
                confidence = 90  # Extra confirmation from fractal
    
    elif crossover == 'bearish':
        if close_position == 'top':
            direction  = 'put'   # SELL
            confidence = 80
            if fractal_up:
                confidence = 90  # Extra confirmation from fractal
    
    if not direction:
        logger.info(f"{asset}: No valid entry — crossover={crossover}, close={close_position}")
        return None
    
    # Rule 6: Confirm next candle direction
    next_dir = confirm_next_candle_direction(candles)
    if direction == 'call' and next_dir == 'down':
        logger.info(f"{asset}: Next candle going down — skip BUY")
        return None
    if direction == 'put' and next_dir == 'up':
        logger.info(f"{asset}: Next candle going up — skip SELL")
        return None
    
    # ✅ Valid signal!
    signal = {
        'asset':      asset,
        'direction':  direction,
        'expiry':     5,        # 5 seconds
        'confidence': confidence,
        'crossover':  crossover,
        'close_pos':  close_position,
        'fractal_up': fractal_up,
        'fractal_dn': fractal_down,
        'time':       datetime.now().strftime('%H:%M:%S'),
        'sma2':       calculate_sma(candles, 2),
        'sma5':       calculate_sma(candles, 5),
    }
    
    logger.info(
        f"✅ SIGNAL: {asset} {direction.upper()} "
        f"| Confidence: {confidence}% "
        f"| Crossover: {crossover} "
        f"| Close: {close_position}"
    )
    
    return signal

# ══════════════════════════════════════════════════════════════
# CANDLE DATA MANAGER
# ══════════════════════════════════════════════════════════════

class CandleManager:
    def __init__(self):
        self.candles    = {}  # {asset: [candles]}
        self.max_candles = 20
    
    def add_candle(self, asset, candle):
        """Add a new completed candle"""
        if asset not in self.candles:
            self.candles[asset] = []
        self.candles[asset].append(candle)
        # Keep only last 20 candles
        if len(self.candles[asset]) > self.max_candles:
            self.candles[asset] = self.candles[asset][-self.max_candles:]
    
    def update_current_candle(self, asset, price, timestamp):
        """Update the current forming candle"""
        if asset not in self.candles:
            self.candles[asset] = []
        
        # 2-minute candle period
        candle_period = 120  # seconds
        candle_time   = (timestamp // candle_period) * candle_period
        
        if self.candles[asset] and self.candles[asset][-1].get('time') == candle_time:
            # Update existing candle
            c = self.candles[asset][-1]
            c['close'] = price
            c['high']  = max(c['high'], price)
            c['low']   = min(c['low'],  price)
        else:
            # New candle
            new_candle = {
                'time':  candle_time,
                'open':  price,
                'high':  price,
                'low':   price,
                'close': price
            }
            self.candles[asset].append(new_candle)
            if len(self.candles[asset]) > self.max_candles:
                self.candles[asset] = self.candles[asset][-self.max_candles:]
    
    def get_candles(self, asset):
        return self.candles.get(asset, [])
    
    def has_enough_candles(self, asset):
        return len(self.candles.get(asset, [])) >= 7

# ══════════════════════════════════════════════════════════════
# STRATEGY RUNNER
# ══════════════════════════════════════════════════════════════

class StrategyRunner:
    def __init__(self, po_client, bot, user_id, user_settings):
        self.po_client     = po_client
        self.bot           = bot
        self.user_id       = user_id
        self.settings      = user_settings
        self.candle_mgr    = CandleManager()
        self.running       = False
        self.last_signal   = {}  # Prevent duplicate signals
        self.active_trade  = False
    
    def start(self):
        self.running = True
        logger.info(f"🚀 Strategy runner started for user {self.user_id}")
    
    def stop(self):
        self.running = False
        logger.info(f"🛑 Strategy runner stopped for user {self.user_id}")
    
    def on_price_update(self, asset, price, timestamp):
        """Called when new price data arrives"""
        if not self.running:
            return
        if asset not in OTC_ASSETS:
            return
        
        # Update candle
        self.candle_mgr.update_current_candle(asset, price, timestamp)
        
        # Only analyze on candle close (every 2 minutes)
        candles = self.candle_mgr.get_candles(asset)
        if not self.candle_mgr.has_enough_candles(asset):
            return
        
        # Check if this is a new candle (previous one just closed)
        if len(candles) < 2:
            return
        
        # Analyze for signal
        signal = analyze_signal(asset, candles[:-1])  # Use closed candles
        if not signal:
            return
        
        # Prevent duplicate signals (same asset within 30 seconds)
        last = self.last_signal.get(asset, 0)
        if time.time() - last < 30:
            return
        
        self.last_signal[asset] = time.time()
        
        # Skip if already in a trade
        if self.active_trade:
            logger.info(f"Already in a trade — skipping {asset} signal")
            return
        
        # Execute the signal
        asyncio.create_task(self.execute_signal(signal))
    
    async def execute_signal(self, signal):
        """Execute trade based on signal"""
        self.active_trade = True
        asset     = signal['asset']
        direction = signal['direction']
        expiry    = signal['expiry']  # 5 seconds
        amount    = self.settings.get('amount', 1.0)
        mg_levels = self.settings.get('mg_levels', 2)
        mg_multi  = self.settings.get('mg_multi', 2.0)
        
        # Notify user
        self.bot.send_message(
            self.user_id,
            f"🎯 <b>APOB SIGNAL!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Asset: <b>{asset}</b>\n"
            f"Direction: <b>{'🟢 BUY/CALL' if direction=='call' else '🔴 SELL/PUT'}</b>\n"
            f"Expiry: <b>{expiry} seconds</b>\n"
            f"Amount: <b>${amount}</b>\n"
            f"Confidence: <b>{signal['confidence']}%</b>\n"
            f"SMA Cross: {signal['crossover']}\n"
            f"Candle Close: {signal['close_pos']}\n"
            f"━━━━━━━━━━━━━━━━━━",
            parse_mode='HTML'
        )
        
        # Build martingale sequence
        mg_amounts = [amount]
        current    = amount
        for _ in range(mg_levels):
            current = round(current * mg_multi, 2)
            mg_amounts.append(current)
        
        # Execute with martingale
        for level, mg_amt in enumerate(mg_amounts):
            # Check daily loss limit
            daily_loss  = self.settings.get('daily_loss', 0)
            daily_limit = self.settings.get('daily_limit', 20)
            if daily_loss >= daily_limit:
                self.bot.send_message(
                    self.user_id,
                    f"🛑 <b>Daily Loss Limit Reached!</b>\n"
                    f"Lost ${daily_loss:.2f} today.\n"
                    f"Trading stopped for today!",
                    parse_mode='HTML'
                )
                break
            
            level_name = "ENTRY" if level == 0 else f"M{level}"
            
            # Place order
            try:
                order = await self.po_client.place_order(
                    asset=asset,
                    amount=mg_amt,
                    direction=direction,
                    duration=expiry
                )
                
                if not order:
                    self.bot.send_message(
                        self.user_id,
                        f"❌ {level_name} trade failed!"
                    )
                    break
                
                self.bot.send_message(
                    self.user_id,
                    f"✅ <b>{level_name} Placed!</b> "
                    f"{'🟢' if direction=='call' else '🔴'} ${mg_amt:.2f}"
                )
                
                # Wait for result (5 seconds + 2 buffer)
                await asyncio.sleep(expiry + 2)
                
                # Get result
                result = await self.po_client.get_order_result(
                    order.order_id, timeout=30
                )
                
                if result and result.profit > 0:
                    # WIN!
                    self.bot.send_message(
                        self.user_id,
                        f"🎉 <b>WIN on {level_name}!</b>\n"
                        f"+${result.profit:.2f} 💰",
                        parse_mode='HTML'
                    )
                    self.update_stats('win', result.profit, mg_amt)
                    break
                
                else:
                    # LOSS
                    self.update_stats('loss', 0, mg_amt)
                    if level < len(mg_amounts) - 1:
                        next_amt = mg_amounts[level + 1]
                        self.bot.send_message(
                            self.user_id,
                            f"❌ Loss on {level_name} → "
                            f"Next: ${next_amt:.2f}"
                        )
                    else:
                        self.bot.send_message(
                            self.user_id,
                            f"❌ <b>All levels lost!</b>\n"
                            f"Reset to ${amount:.2f}",
                            parse_mode='HTML'
                        )
            
            except Exception as e:
                logger.error(f"Trade execution error: {e}")
                self.bot.send_message(
                    self.user_id,
                    f"❌ Trade error: {e}"
                )
                break
        
        self.active_trade = False
    
    def update_stats(self, outcome, profit, amount):
        """Update user trading statistics"""
        stats = self.settings.get('stats', {
            'total': 0, 'wins': 0, 'losses': 0, 'profit': 0.0
        })
        stats['total'] += 1
        if outcome == 'win':
            stats['wins']   += 1
            stats['profit'] += profit
        else:
            stats['losses'] += 1
            stats['profit'] -= amount
            self.settings['daily_loss'] = \
                self.settings.get('daily_loss', 0) + amount
        
        self.settings['stats'] = stats
        
        wr   = (stats['wins']/stats['total']*100) if stats['total'] > 0 else 0
        p    = stats['profit']
        sign = '+' if p >= 0 else ''
        
        self.bot.send_message(
            self.user_id,
            f"📊 {stats['total']} trades | "
            f"✅{stats['wins']} ❌{stats['losses']} | "
            f"{wr:.1f}% | {sign}${p:.2f}"
        )

# ══════════════════════════════════════════════════════════════
# PRICE FEED (connects to PO WebSocket for live prices)
# ══════════════════════════════════════════════════════════════

class PriceFeed:
    def __init__(self, ssid, strategy_runners):
        self.ssid             = ssid
        self.strategy_runners = strategy_runners  # list of StrategyRunner
        self.ws               = None
        self.running          = False
    
    async def connect(self):
        headers = {
            "Origin":     "https://pocketoption.com",
            "User-Agent": "Mozilla/5.0"
        }
        urls = [
            "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
            "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
        ]
        for url in urls:
            try:
                self.ws = await websockets.connect(
                    url,
                    extra_headers=headers,
                    ping_interval=20,
                    ping_timeout=10
                )
                # Auth
                await self.ws.recv()
                auth = json.dumps(["auth", {
                    "session": self.ssid,
                    "isDemo":  1,
                    "uid":     0,
                    "platform": 2
                }])
                await self.ws.send(f"42{auth}")
                logger.info("✅ Price feed connected!")
                self.running = True
                return True
            except Exception as e:
                logger.warning(f"Price feed URL failed: {e}")
                continue
        return False
    
    async def run(self):
        """Main price feed loop"""
        if not await self.connect():
            logger.error("❌ Price feed connection failed!")
            return
        
        try:
            async for msg in self.ws:
                if not self.running:
                    break
                try:
                    if msg == '2':
                        await self.ws.send('3')
                        continue
                    
                    if not msg.startswith('42'):
                        continue
                    
                    data = json.loads(msg[2:])
                    if not isinstance(data, list) or len(data) < 2:
                        continue
                    
                    event   = data[0]
                    payload = data[1]
                    
                    # Handle price updates
                    if event in ['updateStream', 'candles', 'price']:
                        if isinstance(payload, dict):
                            asset = payload.get('asset') or payload.get('symbol')
                            price = payload.get('price') or payload.get('close')
                            ts    = payload.get('time') or int(time.time())
                            
                            if asset and price and asset in OTC_ASSETS:
                                for runner in self.strategy_runners:
                                    runner.on_price_update(
                                        asset, float(price), int(ts)
                                    )
                
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.error(f"Price feed error: {e}")
        
        except Exception as e:
            logger.error(f"Price feed disconnected: {e}")
            self.running = False
    
    def stop(self):
        self.running = False
