import ccxt
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import MetaTrader5 as mt5

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# MT5 initialization will happen in initialize_mt5() function

# ============================================
# CONFIGURATION
# ============================================
class Config:
    # MT5 Connection Details
    MT5_LOGIN = 10008363736
    MT5_PASSWORD = "QyFmB-8o"
    MT5_SERVER = "MetaQuotes-Demo"
    
    # Exchange settings
    EXCHANGE = 'mt5'
    SYMBOL = 'XAUUSD'
    
    # Telegram Bot (Blocked in Pakistan)
    TELEGRAM_TOKEN = '7599271923:AAEzNIArzHHDhRAK42LC8XTGXN6ae-Eyj2w'
    TELEGRAM_CHAT_ID = 6859395938
    USE_TELEGRAM = False  # Disabled - blocked in Pakistan
    
    # Discord Webhook (Recommended)
    DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1438959957994242228/yXuxEBEn_re0R2YkG8VpgFJHauc25UCrHH99BCw2xHg-ISlyzxt03u6ZB-XEtog98Wgd"
    USE_DISCORD = True  # Enable Discord notifications
    
    # Proxy Settings (if needed)
    USE_PROXY = False
    PROXY_URL = "socks5://127.0.0.1:1080"
    
    # Fallback: Save signals to file
    SAVE_SIGNALS_TO_FILE = True  # Backup to file
    SIGNALS_LOG_FILE = "trading_signals.log"
    
    # AUTO TRADING SETTINGS
    AUTO_TRADE = True  # True = Auto execute trades, False = Signals only
    LOT_SIZE = 0.01  # 0.01 = micro lot (safe for demo)
    MAX_OPEN_TRADES = 3  # Maximum simultaneous trades
    
    # Strategy parameters - Enhanced for accuracy
    OB_ZONE_TOLERANCE = 0.003  # 0.3% tighter tolerance for better accuracy
    LIQUIDITY_WICK_RATIO = 2.0  # Stronger wick requirement (2x body)
    MIN_OB_BODY_SIZE = 0.0015  # Minimum 0.15% body size for valid OB
    CONFIRMATION_CANDLES = 2  # Wait for 2 candles confirmation
    
    # Risk Management
    DEFAULT_RR_RATIO = 1.5  # Default Risk:Reward 1:1.5
    AGGRESSIVE_RR_RATIO = 2.0  # For high confidence trades 1:2
    CONSERVATIVE_RR_RATIO = 1.0  # For lower confidence 1:1
    
    # Accuracy filters
    MIN_VOLUME_INCREASE = 1.2  # OB candle must have 20% more volume
    REQUIRE_TREND_ALIGNMENT = True  # Only trade in direction of trend
    
    CHECK_INTERVAL = 60  # Check every 60 seconds
    
    # Pip calculation
    PIP_SIZE = {
        'XAUUSD': 0.1,  # Gold: 0.1 = 1 pip
        'BTCUSDT': 1.0,
        'EURUSD': 0.0001,
    }

# ============================================
# MT5 CONNECTION
# ============================================
def initialize_mt5(config: Config) -> bool:
    """Initialize MT5 and login to account"""
    try:
        # Try to initialize without path (uses already running MT5)
        init_result = mt5.initialize()
        print(f"🔍 MT5 Initialize Result: {init_result}")
        print(f"🔍 MT5 Last Error: {mt5.last_error()}")
        
        if not init_result:
            print("❌ MT5 initialization failed")
            print("   Make sure MT5 is running and accessible")
            return False
        
        # Login to account
        print(f"\n🔐 Attempting login...")
        print(f"   Login: {config.MT5_LOGIN}")
        print(f"   Server: {config.MT5_SERVER}")
        
        authorized = mt5.login(config.MT5_LOGIN, password=config.MT5_PASSWORD, server=config.MT5_SERVER)
        print(f"🔍 Login Result: {authorized}")
        print(f"🔍 Login Error: {mt5.last_error()}")
        
        if authorized:
            account_info = mt5.account_info()
            print(f"\n✅ MT5 Connected Successfully!")
            print(f"   Account: {account_info.login}")
            print(f"   Balance: ${account_info.balance:.2f}")
            print(f"   Server: {account_info.server}")
            print(f"   Currency: {account_info.currency}")
            return True
        else:
            error = mt5.last_error()
            print(f"\n❌ MT5 Login Failed: {error}")
            mt5.shutdown()
            return False
    
    except Exception as e:
        print(f"❌ Exception during MT5 initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================
# ORDER EXECUTION CLASS
# ============================================
class OrderExecutor:
    def __init__(self, symbol: str, lot_size: float = 0.01):
        self.symbol = symbol
        self.lot_size = lot_size
        self.magic_number = 234000  # Unique ID for bot trades
    
    def place_order(self, signal_type: str, entry_price: float, sl: float, tp: float) -> bool:
        """Execute trade on MT5 with SL/TP"""
        try:
            # Get symbol info
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                print(f"❌ Symbol {self.symbol} not found")
                return False
            
            if not symbol_info.visible:
                if not mt5.symbol_select(self.symbol, True):
                    print(f"❌ Failed to select {self.symbol}")
                    return False
            
            # Get current price
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                print(f"❌ Failed to get tick for {self.symbol}")
                return False
            
            # Determine order type and price
            if signal_type == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
                sl_price = sl
                tp_price = tp
            else:  # SELL
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid
                sl_price = sl
                tp_price = tp
            
            # Prepare request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"SMC Bot {signal_type}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"❌ Order failed: {result.comment} (Code: {result.retcode})")
                return False
            
            print(f"\n✅ ✅ {signal_type} ORDER EXECUTED! ✅ ✅")
            print(f"   Ticket: {result.order}")
            print(f"   Entry: ${price:.2f}")
            print(f"   SL: ${sl_price:.2f}")
            print(f"   TP: ${tp_price:.2f}")
            print(f"   Volume: {self.lot_size} lot\n")
            return True
            
        except Exception as e:
            print(f"❌ Order execution error: {e}")
            return False
    
    def get_open_positions(self) -> int:
        """Get number of open positions for this symbol"""
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            return len(positions) if positions else 0
        except:
            return 0

# ============================================
# TELEGRAM NOTIFIER
# ============================================
class NotificationHandler:
    def __init__(self, discord_url: str = None, use_discord: bool = False,
                 telegram_token: str = None, telegram_chat_id: str = None,
                 save_to_file: bool = False, log_file: str = None):
        self.discord_url = discord_url
        self.use_discord = use_discord
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.save_to_file = save_to_file
        self.log_file = log_file or "signals.log"
    
    def save_signal_to_file(self, message: str):
        """Save signal to local file as fallback"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*80}\n")
                f.write(message)
                f.write(f"\n{'='*80}\n")
            print(f"✅ Signal saved to: {self.log_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to save signal to file: {e}")
            return False
    
    def send_message(self, message: str):
        """Send message to Discord or Telegram"""
        
        # Method 1: Discord (Recommended - No blocking)
        if self.use_discord and self.discord_url:
            try:
                print(f"📤 Sending to Discord...")
                
                # Convert HTML to Discord markdown
                msg_clean = message.replace('<b>', '**').replace('</b>', '**')
                msg_clean = msg_clean.replace('<i>', '*').replace('</i>', '*')
                
                embed = {
                    "title": "🤖 Trading Signal",
                    "description": msg_clean,
                    "color": 3447003
                }
                
                payload = {"embeds": [embed]}
                
                response = requests.post(
                    self.discord_url,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 204:
                    print(f"✅ Discord message sent successfully!")
                    return {"discord": "success"}
                else:
                    print(f"   ⚠️ Discord status: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Discord failed: {str(e)[:50]}")
        
        # Method 2: Telegram (if enabled)
        if self.telegram_token and self.telegram_chat_id:
            try:
                print(f"📤 Trying Telegram...")
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                data = {
                    'chat_id': self.telegram_chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                
                response = requests.post(url, data=data, timeout=30, verify=False)
                
                if response.status_code == 200:
                    print(f"✅ Telegram message sent!")
                    return {"telegram": "success"}
                    
            except Exception as e:
                print(f"   ❌ Telegram failed: {str(e)[:30]}")
        
        # Fallback: Save to file
        if self.save_to_file:
            print("\n📁 Saving signal to file...")
            self.save_signal_to_file(message)
            return {"file": "saved"}
        
        print("\n❌ All notification methods failed")
        return None

# ============================================
# MARKET DATA HANDLER
# ============================================
class DataFetcher:
    def __init__(self, exchange_name: str, symbol: str):
        self.symbol = symbol
    
    def get_ohlcv(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV data from MT5"""
        try:
            tf_map = {
                '1m': mt5.TIMEFRAME_M1, 
                '5m': mt5.TIMEFRAME_M5,
                '15m': mt5.TIMEFRAME_M15,
                '1h': mt5.TIMEFRAME_H1
            }
            
            if timeframe not in tf_map:
                return pd.DataFrame()
            
            rates = mt5.copy_rates_from_pos(self.symbol, tf_map[timeframe], 0, limit)
            
            if rates is None or len(rates) == 0:
                return pd.DataFrame()
            
            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            print(f"❌ MT5 data error: {e}")
            return pd.DataFrame()

# ============================================
# ENHANCED SMART MONEY CONCEPTS STRATEGY
# ============================================
class EnhancedSMCStrategy:
    def __init__(self, config: Config):
        self.config = config
    
    def detect_market_structure(self, df: pd.DataFrame) -> str:
        """Enhanced market structure detection - more reliable"""
        if len(df) < 20:
            return "RANGING"
        
        # Use recent data (last 50 candles)
        recent_df = df.tail(50)
        highs = recent_df['high'].values
        lows = recent_df['low'].values
        closes = recent_df['close'].values
        
        # Method 1: Simple trend using close prices
        recent_close = closes[-1]
        ma_20 = closes.mean()
        ma_10 = closes[-10:].mean()
        
        # Method 2: Find swing points (less strict)
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(recent_df) - 2):
            # Swing high (less strict - only 2 bars on each side)
            if highs[i] > highs[i-1] and highs[i] > highs[i+1] and highs[i] > highs[i-2] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))
            
            # Swing low (less strict - only 2 bars on each side)
            if lows[i] < lows[i-1] and lows[i] < lows[i+1] and lows[i] < lows[i-2] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))
        
        # Determine trend
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            # Check if making higher highs and higher lows (BULLISH)
            if swing_highs[-1][1] > swing_highs[-2][1] and swing_lows[-1][1] > swing_lows[-2][1]:
                return "BULLISH"
            # Check if making lower highs and lower lows (BEARISH)
            elif swing_highs[-1][1] < swing_highs[-2][1] and swing_lows[-1][1] < swing_lows[-2][1]:
                return "BEARISH"
        
        # Fallback: Use moving average crossover
        if recent_close > ma_10 > ma_20:
            return "BULLISH"
        elif recent_close < ma_10 < ma_20:
            return "BEARISH"
        elif recent_close > ma_20:
            return "BULLISH"
        elif recent_close < ma_20:
            return "BEARISH"
        
        return "RANGING"
    
    def calculate_confidence_score(self, ob: Dict, df: pd.DataFrame, trend: str) -> float:
        """Calculate trade confidence (0-100)"""
        score = 50  # Base score
        
        candle_idx = ob['index']
        candle = df.iloc[candle_idx]
        
        # 1. Volume check (+15 points)
        avg_volume = df['volume'].iloc[candle_idx-10:candle_idx].mean()
        if candle['volume'] > avg_volume * self.config.MIN_VOLUME_INCREASE:
            score += 15
        
        # 2. Body size check (+10 points)
        body_size = abs(candle['close'] - candle['open']) / candle['open']
        if body_size > self.config.MIN_OB_BODY_SIZE:
            score += 10
        
        # 3. Trend alignment (+20 points)
        if self.config.REQUIRE_TREND_ALIGNMENT:
            if (ob['type'] == 'BULLISH' and trend == 'BULLISH') or \
               (ob['type'] == 'BEARISH' and trend == 'BEARISH'):
                score += 20
        
        # 4. Clean rejection (+5 points for each clean wick)
        total_range = candle['high'] - candle['low']
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        if ob['type'] == 'BULLISH' and lower_wick > total_range * 0.3:
            score += 5
        elif ob['type'] == 'BEARISH' and upper_wick > total_range * 0.3:
            score += 5
        
        return min(score, 100)
    
    def detect_enhanced_order_blocks(self, df: pd.DataFrame, trend: str) -> List[Dict]:
        """Enhanced Order Block detection with quality filters
        
        STRATEGY:
        - BULLISH OB (Support): Green candle (close > open) at bottom = BUY signal
        - BEARISH OB (Resistance): Red candle (close < open) at top = SELL signal
        """
        order_blocks = []
        
        for i in range(5, len(df) - 2):
            candle = df.iloc[i]
            body_size = abs(candle['close'] - candle['open']) / candle['open']
            
            # Skip weak candles
            if body_size < self.config.MIN_OB_BODY_SIZE:
                continue
            
            # BULLISH Order Block (Support) - Green candle at bottom
            if candle['close'] > candle['open']:  # Green/Bullish candle
                # Check for strong bullish rejection (price bounces up)
                if i + 2 < len(df):
                    if df['close'].iloc[i+1] > candle['high'] and \
                       df['close'].iloc[i+2] > df['close'].iloc[i+1]:  # Confirmation
                        
                        confidence = self.calculate_confidence_score(
                            {'type': 'BULLISH', 'index': i}, df, trend
                        )
                        
                        # Only add high-quality OBs
                        if confidence >= 60:
                            ob = {
                                'type': 'BULLISH',
                                'high': candle['high'],
                                'low': candle['low'],
                                'timestamp': candle['timestamp'],
                                'index': i,
                                'confidence': confidence
                            }
                            order_blocks.append(ob)
            
            # BEARISH Order Block (Resistance) - Red candle at top
            if candle['close'] < candle['open']:  # Red/Bearish candle
                # Check for strong bearish rejection (price bounces down)
                if i + 2 < len(df):
                    if df['close'].iloc[i+1] < candle['low'] and \
                       df['close'].iloc[i+2] < df['close'].iloc[i+1]:  # Confirmation
                        
                        confidence = self.calculate_confidence_score(
                            {'type': 'BEARISH', 'index': i}, df, trend
                        )
                        
                        # Only add high-quality OBs
                        if confidence >= 60:
                            ob = {
                                'type': 'BEARISH',
                                'high': candle['high'],
                                'low': candle['low'],
                                'timestamp': candle['timestamp'],
                                'index': i,
                                'confidence': confidence
                            }
                            order_blocks.append(ob)
        
        return order_blocks
    
    def detect_liquidity_grab(self, candle: pd.Series) -> Optional[str]:
        """Enhanced liquidity grab detection"""
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        # Stronger wick requirements
        if lower_wick > body * self.config.LIQUIDITY_WICK_RATIO:
            return "BULLISH_GRAB"
        
        if upper_wick > body * self.config.LIQUIDITY_WICK_RATIO:
            return "BEARISH_GRAB"
        
        return None
    
    def check_ob_proximity(self, ob1: Dict, ob2: Dict) -> bool:
        """Check if two OBs overlap or are very close"""
        # Check for actual overlap first (best case)
        if (ob1['low'] <= ob2['high'] and ob1['high'] >= ob2['low']):
            return True
        
        # Check proximity
        mid1 = (ob1['high'] + ob1['low']) / 2
        mid2 = (ob2['high'] + ob2['low']) / 2
        diff = abs(mid1 - mid2) / mid1
        
        return diff <= self.config.OB_ZONE_TOLERANCE
    
    def calculate_sl_tp(self, signal_type: str, entry_price: float, 
                       ob_zone: Dict, confidence: float) -> Dict:
        """Calculate Stop Loss and Take Profit based on OB zone and confidence"""
        
        # Determine RR ratio based on confidence
        if confidence >= 80:
            rr_ratio = self.config.AGGRESSIVE_RR_RATIO  # 1:2
        elif confidence >= 70:
            rr_ratio = self.config.DEFAULT_RR_RATIO  # 1:1.5
        else:
            rr_ratio = self.config.CONSERVATIVE_RR_RATIO  # 1:1
        
        if signal_type == "BUY":
            # SL below OB zone
            sl = ob_zone['low'] - (ob_zone['high'] - ob_zone['low']) * 0.1
            risk = entry_price - sl
            tp = entry_price + (risk * rr_ratio)
            
        else:  # SELL
            # SL above OB zone
            sl = ob_zone['high'] + (ob_zone['high'] - ob_zone['low']) * 0.1
            risk = sl - entry_price
            tp = entry_price - (risk * rr_ratio)
        
        # Calculate pips
        pip_size = self.config.PIP_SIZE.get(self.config.SYMBOL, 1.0)
        risk_pips = abs(entry_price - sl) / pip_size
        reward_pips = abs(tp - entry_price) / pip_size
        
        return {
            'sl': sl,
            'tp': tp,
            'risk_pips': risk_pips,
            'reward_pips': reward_pips,
            'rr_ratio': rr_ratio
        }

# ============================================
# ADVANCED SIGNAL BOT
# ============================================
class AdvancedSignalBot:
    def __init__(self):
        self.config = Config()
        self.notifier = NotificationHandler(
            discord_url=self.config.DISCORD_WEBHOOK_URL,
            use_discord=self.config.USE_DISCORD,
            telegram_token=self.config.TELEGRAM_TOKEN,
            telegram_chat_id=self.config.TELEGRAM_CHAT_ID,
            save_to_file=self.config.SAVE_SIGNALS_TO_FILE,
            log_file=self.config.SIGNALS_LOG_FILE
        )
        self.fetcher = DataFetcher(self.config.EXCHANGE, self.config.SYMBOL)
        self.strategy = EnhancedSMCStrategy(self.config)
        self.executor = OrderExecutor(self.config.SYMBOL, self.config.LOT_SIZE)
        self.last_signal_time = {}
        self.last_market_update_time = 0  # Track last market update
    
    def generate_signal_message(self, signal_type: str, price: float, 
                                ob_5m: Dict, ob_1m: Dict, sl_tp: Dict) -> str:
        """Generate enhanced signal message with SL/TP"""
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        confidence = (ob_5m['confidence'] + ob_1m['confidence']) / 2
        
        # Determine quality badge
        if confidence >= 80:
            quality = "🌟 PREMIUM SETUP"
        elif confidence >= 70:
            quality = "⭐ HIGH QUALITY"
        else:
            quality = "✅ GOOD SETUP"
        
        msg = f"""
{emoji} <b>{signal_type} SIGNAL</b> {emoji}
{quality}

💰 <b>Pair:</b> {self.config.SYMBOL}
💵 <b>Entry Price:</b> ${price:,.2f}

📍 <b>STOP LOSS:</b> ${sl_tp['sl']:,.2f}
🎯 <b>TAKE PROFIT:</b> ${sl_tp['tp']:,.2f}

📊 <b>Risk/Reward:</b> 1:{sl_tp['rr_ratio']}
📏 <b>Risk:</b> {sl_tp['risk_pips']:.1f} pips
💎 <b>Reward:</b> {sl_tp['reward_pips']:.1f} pips

🔥 <b>Confidence Score:</b> {confidence:.0f}%

📈 <b>5min Order Block:</b>
   High: ${ob_5m['high']:,.2f}
   Low: ${ob_5m['low']:,.2f}
   Quality: {ob_5m['confidence']:.0f}%

⚡ <b>1min Order Block:</b>
   High: ${ob_1m['high']:,.2f}
   Low: ${ob_1m['low']:,.2f}
   Quality: {ob_1m['confidence']:.0f}%

🕐 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ <b>Strategy:</b> Enhanced Smart Money Concepts
🎯 Target Accuracy: 70%+
        """
        return msg.strip()
    
    def generate_market_update_message(self) -> str:
        """Generate market update with price, bias, and technical info"""
        try:
            # Fetch data for analysis
            df_1h = self.fetcher.get_ohlcv('1h', limit=50)
            df_5m = self.fetcher.get_ohlcv('5m', limit=100)
            
            if df_1h.empty or df_5m.empty:
                return None
            
            # Get current price
            current_price = df_5m['close'].iloc[-1]
            
            # Calculate 1-hour stats
            hour_open = df_1h['open'].iloc[-1]
            hour_high = df_1h['high'].iloc[-1]
            hour_low = df_1h['low'].iloc[-1]
            hour_close = df_1h['close'].iloc[-1]
            hour_change = ((hour_close - hour_open) / hour_open) * 100
            
            # Calculate 24-hour stats (approximate with available data)
            day_high = df_1h['high'].max()
            day_low = df_1h['low'].min()
            day_range = day_high - day_low
            
            # Detect market bias/trend
            trend = self.strategy.detect_market_structure(df_5m)
            
            # Calculate moving averages for bias
            ma_20 = df_5m['close'].tail(20).mean()
            ma_50 = df_5m['close'].tail(50).mean() if len(df_5m) >= 50 else df_5m['close'].mean()
            
            # Determine bias
            if current_price > ma_20 > ma_50:
                bias = "🟢 BULLISH (Strong)"
                bias_emoji = "📈"
            elif current_price > ma_20:
                bias = "🟢 BULLISH (Moderate)"
                bias_emoji = "📈"
            elif current_price < ma_20 < ma_50:
                bias = "🔴 BEARISH (Strong)"
                bias_emoji = "📉"
            elif current_price < ma_20:
                bias = "🔴 BEARISH (Moderate)"
                bias_emoji = "📉"
            else:
                bias = "🟡 NEUTRAL"
                bias_emoji = "↔️"
            
            # Calculate volatility
            volatility = df_5m['close'].tail(20).std()
            volatility_level = "🔥 HIGH" if volatility > df_5m['close'].std() * 1.2 else "⚡ NORMAL" if volatility > df_5m['close'].std() * 0.8 else "😴 LOW"
            
            # Support and Resistance (from recent data)
            recent_high = df_5m['high'].tail(20).max()
            recent_low = df_5m['low'].tail(20).min()
            
            # Generate message
            msg = f"""
📊 <b>MARKET UPDATE - {self.config.SYMBOL}</b> 📊

💰 <b>CURRENT PRICE:</b> ${current_price:,.2f}

📈 <b>1-HOUR ANALYSIS:</b>
   Open: ${hour_open:,.2f}
   High: ${hour_high:,.2f}
   Low: ${hour_low:,.2f}
   Close: ${hour_close:,.2f}
   Change: {hour_change:+.2f}%

📊 <b>MARKET STRUCTURE:</b>
   Trend: {trend}
   Bias: {bias}
   {bias_emoji}

🎯 <b>TECHNICAL LEVELS:</b>
   24h High: ${day_high:,.2f}
   24h Low: ${day_low:,.2f}
   Range: ${day_range:,.2f}
   
   Resistance: ${recent_high:,.2f}
   Support: ${recent_low:,.2f}

📉 <b>MOVING AVERAGES:</b>
   MA20: ${ma_20:,.2f}
   MA50: ${ma_50:,.2f}

💨 <b>VOLATILITY:</b> {volatility_level}
   Value: {volatility:.4f}

⏰ <b>Update Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            return msg.strip()
        
        except Exception as e:
            print(f"❌ Error generating market update: {e}")
            return None
    
    def send_market_update(self):
        """Send market update every 30 minutes"""
        current_time = time.time()
        
        # Check if 30 minutes (1800 seconds) have passed
        if current_time - self.last_market_update_time >= 1800:
            print(f"\n📊 Sending market update...")
            message = self.generate_market_update_message()
            
            if message:
                self.notifier.send_message(message)
                self.last_market_update_time = current_time
                print(f"✅ Market update sent!")
            else:
                print(f"⚠️ Failed to generate market update")
    
    def check_signals(self):
        """Enhanced signal checking with strict filters"""
        try:
            # Fetch data
            df_5m = self.fetcher.get_ohlcv('5m', limit=100)
            df_1m = self.fetcher.get_ohlcv('1m', limit=150)
            
            if df_5m.empty or df_1m.empty:
                print("⚠️ No data received")
                return
            
            # Detect market structure
            trend = self.strategy.detect_market_structure(df_5m)
            print(f"📊 Market Trend: {trend}")
            
            # Note: Allow ranging markets too - they can have valid order blocks
            # Only skip if we can't detect any structure at all
            if trend is None:
                print("⏳ Cannot detect market structure - waiting...")
                return
            
            # Detect enhanced Order Blocks on 5min
            obs_5m = self.strategy.detect_enhanced_order_blocks(df_5m, trend)
            if not obs_5m:
                print("⏳ No high-quality 5min Order Blocks found")
                return
            
            # Get most recent high-confidence 5min OB
            recent_ob_5m = obs_5m[-1]
            print(f"✅ 5min OB: {recent_ob_5m['type']} | Confidence: {recent_ob_5m['confidence']:.0f}% | ${recent_ob_5m['low']:.2f}-${recent_ob_5m['high']:.2f}")
            
            # Detect Order Blocks on 1min
            obs_1m = self.strategy.detect_enhanced_order_blocks(df_1m, trend)
            if not obs_1m:
                print("⏳ No high-quality 1min Order Blocks found")
                return
            
            # Check for matching high-quality OBs
            for ob_1m in obs_1m[-10:]:  # Check last 10 OBs
                # Must be same type
                if ob_1m['type'] != recent_ob_5m['type']:
                    continue
                
                # Check proximity
                if not self.strategy.check_ob_proximity(recent_ob_5m, ob_1m):
                    continue
                
                print(f"✅ 1min OB matches: {ob_1m['type']} | Confidence: {ob_1m['confidence']:.0f}%")
                
                # Check for liquidity grab on recent 1min candles
                for i in range(-3, -1):  # Check last 2 candles
                    recent_candle = df_1m.iloc[i]
                    liquidity = self.strategy.detect_liquidity_grab(recent_candle)
                    
                    if liquidity:
                        print(f"💧 Liquidity grab detected: {liquidity}")
                        
                        # Generate signal only if everything aligns
                        signal_type = None
                        if recent_ob_5m['type'] == 'BULLISH' and liquidity == 'BULLISH_GRAB':
                            signal_type = "BUY"
                        elif recent_ob_5m['type'] == 'BEARISH' and liquidity == 'BEARISH_GRAB':
                            signal_type = "SELL"
                        
                        if signal_type:
                            # Calculate combined confidence
                            avg_confidence = (recent_ob_5m['confidence'] + ob_1m['confidence']) / 2
                            
                            # Only send high-confidence signals (65%+)
                            if avg_confidence >= 65:
                                signal_key = f"{signal_type}_{recent_ob_5m['timestamp']}"
                                if signal_key not in self.last_signal_time:
                                    current_price = df_1m['close'].iloc[-1]
                                    
                                    # Calculate SL/TP
                                    sl_tp = self.strategy.calculate_sl_tp(
                                        signal_type, current_price, recent_ob_5m, avg_confidence
                                    )
                                    
                                    # Check max trades limit
                                    open_trades = self.executor.get_open_positions()
                                    if open_trades >= self.config.MAX_OPEN_TRADES:
                                        print(f"⚠️ Max trades limit reached ({open_trades}/{self.config.MAX_OPEN_TRADES})")
                                        continue
                                    
                                    print(f"\n🚨 🚨 {signal_type} SIGNAL DETECTED! 🚨 🚨")
                                    print(f"Confidence: {avg_confidence:.0f}%")
                                    print(f"Entry: ${current_price:.2f}")
                                    print(f"SL: ${sl_tp['sl']:.2f} ({sl_tp['risk_pips']:.1f} pips)")
                                    print(f"TP: ${sl_tp['tp']:.2f} ({sl_tp['reward_pips']:.1f} pips)")
                                    print(f"RR: 1:{sl_tp['rr_ratio']}")
                                    
                                    # Generate message
                                    message = self.generate_signal_message(
                                        signal_type, current_price, recent_ob_5m, ob_1m, sl_tp
                                    )
                                    
                                    # AUTO TRADE EXECUTION
                                    if self.config.AUTO_TRADE:
                                        print("\n🤖 EXECUTING TRADE ON MT5...")
                                        trade_success = self.executor.place_order(
                                            signal_type, current_price, sl_tp['sl'], sl_tp['tp']
                                        )
                                        
                                        if trade_success:
                                            message = "🤖 <b>✅ TRADE EXECUTED ON MT5!</b>\n\n" + message
                                        else:
                                            message = "⚠️ <b>SIGNAL ONLY (Trade execution failed)</b>\n\n" + message
                                    else:
                                        message = "📢 <b>SIGNAL ONLY (Auto-trade OFF)</b>\n\n" + message
                                    
                                    # Send to Telegram
                                    self.notifier.send_message(message)
                                    self.last_signal_time[signal_key] = time.time()
                            else:
                                print(f"⚠️ Signal confidence too low ({avg_confidence:.0f}%) - skipped")
        
        except Exception as e:
            print(f"❌ Error in check_signals: {e}")
    
    def run(self):
        """Main bot loop"""
        print("=" * 70)
        print("🤖 ADVANCED SMC BOT - AUTO TRADING + SIGNALS")
        print("=" * 70)
        print(f"📊 Symbol: {self.config.SYMBOL}")
        print(f"🎯 Target Accuracy: 70%+")
        print(f"📏 Default RR: 1:{self.config.DEFAULT_RR_RATIO}")
        print(f"💰 Lot Size: {self.config.LOT_SIZE}")
        print(f"🤖 Auto Trade: {'✅ ON (Will execute trades)' if self.config.AUTO_TRADE else '❌ OFF (Signals only)'}")
        print(f"🔢 Max Trades: {self.config.MAX_OPEN_TRADES}")
        print(f"🔄 Check Interval: {self.config.CHECK_INTERVAL}s")
        print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Send startup message
        auto_status = "🤖 AUTO TRADING ENABLED ✅" if self.config.AUTO_TRADE else "📢 SIGNALS ONLY MODE"
        self.notifier.send_message(
            f"🤖 <b>Advanced SMC Bot Started!</b>\n\n"
            f"📊 Symbol: {self.config.SYMBOL}\n"
            f"🎯 Target: 70%+ Accuracy\n"
            f"💎 Auto SL/TP: 1:1 / 1:1.5 / 1:2\n"
            f"💰 Lot Size: {self.config.LOT_SIZE}\n"
            f"🔢 Max Trades: {self.config.MAX_OPEN_TRADES}\n"
            f"{auto_status}\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        while True:
            try:
                print(f"\n⏰ Checking at {datetime.now().strftime('%H:%M:%S')}...")
                self.check_signals()
                self.send_market_update()  # Send market update every 30 minutes
                time.sleep(self.config.CHECK_INTERVAL)
            
            except KeyboardInterrupt:
                print("\n\n👋 Bot stopped by user")
                self.notifier.send_message("🛑 <b>Bot Stopped</b>")
                break
            except Exception as e:
                print(f"❌ Main loop error: {e}")
                time.sleep(self.config.CHECK_INTERVAL)

# ============================================
# RUN BOT
# ============================================
if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║   
    ║   🚀 ADVANCED SMC AUTO TRADING BOT 🚀               ║
    ╚═══════════════════════════════════════════════════════╝
    
    ✅ Features:
    • Auto trade execution on MT5
    • Smart SL/TP (1:1, 1:1.5, 1:2 based on confidence)
    • 70%+ target accuracy with strict filters
    • Enhanced Order Block detection (5min + 1min)
    • Liquidity grab confirmation
    • Real-time Telegram signals
    • Risk management (max trades limit)
    
    📊 Current Setup:
    • Symbol: XAUUSD (Gold)
    • Lot Size: 0.01 (Micro lot)
    • Auto Trade: ON ✅
    • Max Trades: 3
    
    ⚠️ IMPORTANT:
    • Make sure MT5 is OPEN and LOGGED IN
    • VPN must be ON for Telegram
    • Demo account recommended for testing
    
    """)
    
    input("✅ Press Enter to connect to MT5 and start bot...\n")
    
    # Initialize MT5 Connection
    config = Config()
    if not initialize_mt5(config):
        print("\n❌ Failed to connect to MT5. Please check:")
        print("   1. MT5 is running")
        print("   2. Login credentials are correct")
        print("   3. Account is Demo (MetaQuotes-Demo server)")
        input("\nPress Enter to exit...")
        exit()
    
    print("\n" + "="*70)
    input("✅ MT5 Connected! Press Enter to start the trading bot...\n")
    
    # Start Bot
    bot = AdvancedSignalBot()
    bot.run()