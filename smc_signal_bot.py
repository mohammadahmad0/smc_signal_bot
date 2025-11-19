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

# ============================================
# CONFIGURATION
# ============================================
class Config:
    # MT5 Connection
    MT5_LOGIN = 10008363736
    MT5_PASSWORD = "QyFmB-8o"
    MT5_SERVER = "MetaQuotes-Demo"
    
    EXCHANGE = 'mt5'
    SYMBOL = 'XAUUSD'
    
    # Notifications
    TELEGRAM_TOKEN = '7599271923:AAEzNIArzHHDhRAK42LC8XTGXN6ae-Eyj2w'
    TELEGRAM_CHAT_ID = 6859395938
    USE_TELEGRAM = False
    
    DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1438959957994242228/yXuxEBEn_re0R2YkG8VpgFJHauc25UCrHH99BCw2xHg-ISlyzxt03u6ZB-XEtog98Wgd"
    USE_DISCORD = True
    
    SAVE_SIGNALS_TO_FILE = True
    SIGNALS_LOG_FILE = "trading_signals.log"
    
    # Trading Settings
    AUTO_TRADE = True
    LOT_SIZE = 0.01
    MAX_OPEN_TRADES = 3
    
    # FIXED SL/TP
    FIXED_SL_PIPS = 25.0  # 25 pips = $2.50
    FIXED_TP_PIPS = 50.0  # 50 pips = $5.00
    
    # Strategy Settings
    OB_LOOKBACK_CANDLES = 50  # Look back 50 candles for 5min OB
    RETEST_ZONE_TOLERANCE = 0.003  # 0.3% tolerance for retest
    MIN_OB_BODY_SIZE = 0.0008  # 0.08% minimum body
    
    CHECK_INTERVAL = 60  # Check every 60 seconds
    
    PIP_SIZE = {
        'XAUUSD': 0.1,
        'BTCUSDT': 1.0,
        'EURUSD': 0.0001,
    }

# ============================================
# MT5 CONNECTION
# ============================================
def initialize_mt5(config: Config) -> bool:
    try:
        if not mt5.initialize():
            print("❌ MT5 init failed")
            return False
        
        authorized = mt5.login(config.MT5_LOGIN, password=config.MT5_PASSWORD, server=config.MT5_SERVER)
        
        if authorized:
            acc = mt5.account_info()
            print(f"✅ MT5 Connected | Acc: {acc.login} | Bal: ${acc.balance:.2f}")
            return True
        else:
            print(f"❌ Login failed: {mt5.last_error()}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ============================================
# ORDER EXECUTOR
# ============================================
class OrderExecutor:
    def __init__(self, symbol: str, lot_size: float):
        self.symbol = symbol
        self.lot_size = lot_size
        self.magic_number = 234000
    
    def place_order(self, signal_type: str, entry_price: float, sl: float, tp: float) -> bool:
        try:
            symbol_info = mt5.symbol_info(self.symbol)
            if not symbol_info or not symbol_info.visible:
                mt5.symbol_select(self.symbol, True)
            
            tick = mt5.symbol_info_tick(self.symbol)
            if not tick:
                return False
            
            order_type = mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL
            price = tick.ask if signal_type == "BUY" else tick.bid
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": order_type,
                "price": price,
                "sl": round(sl, 2),
                "tp": round(tp, 2),
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"SMC {signal_type}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"❌ Order failed: {result.comment}")
                return False
            
            print(f"✅ {signal_type} EXECUTED | Ticket: {result.order}")
            return True
        except:
            return False
    
    def get_open_positions(self) -> int:
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            return len(positions) if positions else 0
        except:
            return 0

# ============================================
# NOTIFICATION
# ============================================
class NotificationHandler:
    def __init__(self, discord_url, use_discord, save_to_file, log_file):
        self.discord_url = discord_url
        self.use_discord = use_discord
        self.save_to_file = save_to_file
        self.log_file = log_file
    
    def send_message(self, message: str):
        if self.use_discord and self.discord_url:
            try:
                msg = message.replace('<b>', '**').replace('</b>', '**')
                requests.post(self.discord_url, json={"embeds": [{"title": "🤖 Signal", "description": msg, "color": 3447003}]}, timeout=10)
                print("✅ Discord sent")
            except:
                pass
        
        if self.save_to_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*80}\n{datetime.now()}\n{'='*80}\n{message}\n")
                print(f"✅ Saved to {self.log_file}")
            except:
                pass

# ============================================
# DATA FETCHER
# ============================================
class DataFetcher:
    def __init__(self, symbol: str):
        self.symbol = symbol
    
    def get_ohlcv(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        try:
            tf_map = {
                '1m': mt5.TIMEFRAME_M1, 
                '5m': mt5.TIMEFRAME_M5,
                '1h': mt5.TIMEFRAME_H1  # Added 1h timeframe
            }
            rates = mt5.copy_rates_from_pos(self.symbol, tf_map[timeframe], 0, limit)
            
            if rates is None or len(rates) == 0:
                return pd.DataFrame()
            
            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            print(f"❌ Data error: {e}")
            return pd.DataFrame()

# ============================================
# PROPER SMC STRATEGY
# ============================================
class ProperSMCStrategy:
    def __init__(self, config: Config):
        self.config = config
    
    def detect_5min_order_blocks(self, df: pd.DataFrame) -> List[Dict]:
        """Detect PREVIOUS 5min Order Blocks (can be far back)
        
        BULLISH OB: RED candle BEFORE price goes UP
        BEARISH OB: GREEN candle BEFORE price goes DOWN
        """
        order_blocks = []
        
        # Look back through all available candles
        for i in range(5, len(df) - 2):
            candle = df.iloc[i]
            body_size = abs(candle['close'] - candle['open']) / candle['open']
            
            if body_size < self.config.MIN_OB_BODY_SIZE:
                continue
            
            # BULLISH OB - RED candle before UP move
            if candle['close'] < candle['open']:
                if df['close'].iloc[i+1] > df['high'].iloc[i-1]:
                    ob = {
                        'type': 'BULLISH',
                        'high': candle['high'],
                        'low': candle['low'],
                        'mid': (candle['high'] + candle['low']) / 2,
                        'wick_low': candle['low'],  # Entry at wick low
                        'wick_high': candle['high'],
                        'timestamp': candle['timestamp'],
                        'index': i,
                        'candle_close': candle['close'],
                        'candle_open': candle['open']
                    }
                    order_blocks.append(ob)
            
            # BEARISH OB - GREEN candle before DOWN move
            elif candle['close'] > candle['open']:
                if df['close'].iloc[i+1] < df['low'].iloc[i-1]:
                    ob = {
                        'type': 'BEARISH',
                        'high': candle['high'],
                        'low': candle['low'],
                        'mid': (candle['high'] + candle['low']) / 2,
                        'wick_low': candle['low'],
                        'wick_high': candle['high'],  # Entry at wick high
                        'timestamp': candle['timestamp'],
                        'index': i,
                        'candle_close': candle['close'],
                        'candle_open': candle['open']
                    }
                    order_blocks.append(ob)
        
        return order_blocks
    
    def is_price_retesting_ob(self, current_price: float, ob: Dict) -> bool:
        """Check if price is RETESTING the 5min OB zone"""
        tolerance = ob['mid'] * self.config.RETEST_ZONE_TOLERANCE
        
        # Price must be WITHIN the OB zone (with tolerance)
        if (ob['low'] - tolerance) <= current_price <= (ob['high'] + tolerance):
            return True
        
        return False
    
    def detect_1min_order_block_near_5min(self, df_1m: pd.DataFrame, ob_5m: Dict) -> Optional[Dict]:
        """Find 1min OB that is NEAR the 5min OB (confirmation)"""
        obs_1m = []
        
        # Detect 1min OBs
        for i in range(5, len(df_1m) - 1):
            candle = df_1m.iloc[i]
            next_candle = df_1m.iloc[i+1]
            
            body_size = abs(candle['close'] - candle['open']) / candle['open']
            if body_size < 0.0003:  # Very small body filter
                continue
            
            # BULLISH 1min OB
            if candle['close'] < candle['open']:
                if next_candle['close'] > candle['high']:
                    obs_1m.append({
                        'type': 'BULLISH',
                        'mid': (candle['high'] + candle['low']) / 2,
                        'timestamp': candle['timestamp']
                    })
            
            # BEARISH 1min OB
            elif candle['close'] > candle['open']:
                if next_candle['close'] < candle['low']:
                    obs_1m.append({
                        'type': 'BEARISH',
                        'mid': (candle['high'] + candle['low']) / 2,
                        'timestamp': candle['timestamp']
                    })
        
        # Find 1min OB that matches 5min OB type and is nearby
        for ob_1m in obs_1m[-20:]:  # Check last 20 1min OBs
            if ob_1m['type'] != ob_5m['type']:
                continue
            
            # Check proximity to 5min OB
            distance = abs(ob_1m['mid'] - ob_5m['mid'])
            tolerance = ob_5m['mid'] * 0.005  # 0.5% tolerance
            
            if distance <= tolerance:
                return ob_1m
        
        return None
    
    def calculate_entry_sl_tp(self, signal_type: str, ob_5m: Dict) -> Dict:
        """Calculate entry at 5min OB WICK level with FIXED SL/TP
        
        BUY: Entry at wick LOW of 5min OB
        SELL: Entry at wick HIGH of 5min OB
        """
        pip_size = self.config.PIP_SIZE.get(self.config.SYMBOL, 0.1)
        
        if signal_type == "BUY":
            entry = ob_5m['wick_low']  # Enter at wick low
            sl = entry - (self.config.FIXED_SL_PIPS * pip_size)
            tp = entry + (self.config.FIXED_TP_PIPS * pip_size)
        else:  # SELL
            entry = ob_5m['wick_high']  # Enter at wick high
            sl = entry + (self.config.FIXED_SL_PIPS * pip_size)
            tp = entry - (self.config.FIXED_TP_PIPS * pip_size)
        
        return {
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'risk_pips': self.config.FIXED_SL_PIPS,
            'reward_pips': self.config.FIXED_TP_PIPS
        }

# ============================================
# SIGNAL BOT
# ============================================
class ProperSignalBot:
    def __init__(self):
        self.config = Config()
        self.notifier = NotificationHandler(
            self.config.DISCORD_WEBHOOK_URL,
            self.config.USE_DISCORD,
            self.config.SAVE_SIGNALS_TO_FILE,
            self.config.SIGNALS_LOG_FILE
        )
        self.fetcher = DataFetcher(self.config.SYMBOL)
        self.strategy = ProperSMCStrategy(self.config)
        self.executor = OrderExecutor(self.config.SYMBOL, self.config.LOT_SIZE)
        self.last_signal_time = {}
        self.marked_obs = []  # Store marked 5min OBs
        self.last_market_update_time = 0  # Track market updates
    
    def generate_market_update(self) -> str:
        """Generate comprehensive market update every 30 minutes"""
        try:
            df_1h = self.fetcher.get_ohlcv('1h', limit=24)
            df_5m = self.fetcher.get_ohlcv('5m', limit=100)
            
            if df_1h.empty or df_5m.empty:
                return None
            
            # Current price
            current_price = df_5m['close'].iloc[-1]
            
            # 1-hour stats
            hour_open = df_1h['open'].iloc[-1]
            hour_high = df_1h['high'].iloc[-1]
            hour_low = df_1h['low'].iloc[-1]
            hour_close = df_1h['close'].iloc[-1]
            hour_change = ((hour_close - hour_open) / hour_open) * 100
            
            # 24-hour stats
            day_high = df_1h['high'].max()
            day_low = df_1h['low'].min()
            day_range = day_high - day_low
            
            # Volume analysis
            current_volume = df_5m['volume'].iloc[-1]
            avg_volume = df_5m['volume'].tail(20).mean()
            volume_ratio = current_volume / avg_volume
            
            if volume_ratio > 1.5:
                volume_status = "🔥 HIGH (Strong Activity)"
            elif volume_ratio > 1.0:
                volume_status = "⚡ NORMAL (Average)"
            else:
                volume_status = "😴 LOW (Quiet)"
            
            # Market bias/trend
            ma_20 = df_5m['close'].tail(20).mean()
            ma_50 = df_5m['close'].tail(50).mean() if len(df_5m) >= 50 else ma_20
            
            if current_price > ma_20 > ma_50:
                bias = "🟢 STRONG BULLISH"
                bias_emoji = "📈📈"
            elif current_price > ma_20:
                bias = "🟢 BULLISH"
                bias_emoji = "📈"
            elif current_price < ma_20 < ma_50:
                bias = "🔴 STRONG BEARISH"
                bias_emoji = "📉📉"
            elif current_price < ma_20:
                bias = "🔴 BEARISH"
                bias_emoji = "📉"
            else:
                bias = "🟡 NEUTRAL"
                bias_emoji = "↔️"
            
            # Price momentum (last 5 candles)
            price_5_ago = df_5m['close'].iloc[-6]
            price_momentum = ((current_price - price_5_ago) / price_5_ago) * 100
            
            if price_momentum > 0.1:
                momentum = "🚀 STRONG UP"
            elif price_momentum > 0:
                momentum = "⬆️ UP"
            elif price_momentum < -0.1:
                momentum = "💥 STRONG DOWN"
            elif price_momentum < 0:
                momentum = "⬇️ DOWN"
            else:
                momentum = "➡️ FLAT"
            
            # Support/Resistance
            recent_high = df_5m['high'].tail(20).max()
            recent_low = df_5m['low'].tail(20).min()
            
            # Volatility
            volatility = df_5m['close'].tail(20).std()
            avg_volatility = df_5m['close'].std()
            
            if volatility > avg_volatility * 1.2:
                vol_status = "🔥 HIGH VOLATILITY"
            elif volatility > avg_volatility * 0.8:
                vol_status = "⚡ NORMAL VOLATILITY"
            else:
                vol_status = "😴 LOW VOLATILITY"
            
            # Generate message
            msg = f"""
📊 <b>MARKET UPDATE - {self.config.SYMBOL}</b> 📊

💰 <b>CURRENT PRICE:</b> ${current_price:,.2f}

📈 <b>1-HOUR PERFORMANCE:</b>
   Open: ${hour_open:,.2f}
   High: ${hour_high:,.2f}
   Low: ${hour_low:,.2f}
   Close: ${hour_close:,.2f}
   Change: {hour_change:+.2f}%

🎯 <b>24-HOUR RANGE:</b>
   High: ${day_high:,.2f}
   Low: ${day_low:,.2f}
   Range: ${day_range:,.2f} ({(day_range/day_low)*100:.2f}%)

📊 <b>MARKET BIAS:</b>
   {bias} {bias_emoji}
   
💨 <b>MOMENTUM (5 candles):</b>
   {momentum} ({price_momentum:+.2f}%)

📉 <b>KEY LEVELS:</b>
   Resistance: ${recent_high:,.2f}
   Support: ${recent_low:,.2f}
   
📈 <b>MOVING AVERAGES:</b>
   MA20: ${ma_20:,.2f}
   MA50: ${ma_50:,.2f}

📊 <b>VOLUME:</b>
   {volume_status}
   Current: {current_volume:.0f}
   Average: {avg_volume:.0f}
   Ratio: {volume_ratio:.2f}x

💥 <b>VOLATILITY:</b>
   {vol_status}
   Value: {volatility:.2f}

⏰ <b>Update Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🤖 <b>Bot Status:</b> Active & Monitoring
            """
            return msg.strip()
        
        except Exception as e:
            print(f"❌ Market update error: {e}")
            return None
    
    def send_market_update_if_needed(self):
        """Send market update every 30 minutes (1800 seconds)"""
        current_time = time.time()
        
        # Check if 30 minutes passed
        if current_time - self.last_market_update_time >= 1800:
            print(f"\n📊 Generating 30-min market update...")
            
            message = self.generate_market_update()
            
            if message:
                self.notifier.send_message(message)
                self.last_market_update_time = current_time
                print(f"✅ Market update sent!")
            else:
                print(f"⚠️ Failed to generate market update")
    
    def check_signals(self):
        """PROPER STRATEGY FLOW:
        
        1. Detect and MARK previous 5min OBs (can be far back)
        2. Check if current price is RETESTING any marked OB
        3. Confirm with 1min OB nearby
        4. Enter at 5min OB WICK level with 25/50 pip SL/TP
        """
        try:
            df_5m = self.fetcher.get_ohlcv('5m', limit=self.config.OB_LOOKBACK_CANDLES)
            df_1m = self.fetcher.get_ohlcv('1m', limit=150)
            
            if df_5m.empty or df_1m.empty:
                print("⚠️ No data")
                return
            
            current_price = df_1m['close'].iloc[-1]
            
            # STEP 1: Detect and mark ALL previous 5min OBs
            obs_5m = self.strategy.detect_5min_order_blocks(df_5m)
            
            if not obs_5m:
                print("⏳ No 5min OBs detected")
                return
            
            print(f"\n📍 Found {len(obs_5m)} 5min OBs | Current Price: ${current_price:.2f}")
            
            # STEP 2: Check if price is RETESTING any marked OB
            for ob_5m in obs_5m:
                is_retesting = self.strategy.is_price_retesting_ob(current_price, ob_5m)
                
                if not is_retesting:
                    continue
                
                print(f"\n✅ RETEST DETECTED!")
                print(f"   5min OB: {ob_5m['type']} | ${ob_5m['low']:.2f}-${ob_5m['high']:.2f}")
                print(f"   OB from: {ob_5m['timestamp']}")
                print(f"   Current Price: ${current_price:.2f}")
                
                # STEP 3: Confirm with 1min OB nearby
                ob_1m = self.strategy.detect_1min_order_block_near_5min(df_1m, ob_5m)
                
                if not ob_1m:
                    print("❌ No 1min OB confirmation")
                    continue
                
                print(f"✅ 1min OB Confirmed!")
                print(f"   Type: {ob_1m['type']} | At: ${ob_1m['mid']:.2f}")
                
                # STEP 4: Generate signal
                signal_type = ob_5m['type'].replace('BULLISH', 'BUY').replace('BEARISH', 'SELL')
                
                # Avoid duplicate signals
                signal_key = f"{signal_type}_{ob_5m['timestamp']}"
                if signal_key in self.last_signal_time:
                    if time.time() - self.last_signal_time[signal_key] < 600:  # 10 min cooldown
                        print("⏸️ Signal cooldown")
                        continue
                
                # Check max trades
                if self.executor.get_open_positions() >= self.config.MAX_OPEN_TRADES:
                    print(f"⚠️ Max trades reached")
                    continue
                
                # Calculate entry at wick level with fixed SL/TP
                trade_levels = self.strategy.calculate_entry_sl_tp(signal_type, ob_5m)
                
                print(f"\n{'='*70}")
                print(f"🚨 {signal_type} SIGNAL GENERATED! 🚨")
                print(f"{'='*70}")
                print(f"Entry: ${trade_levels['entry']:.2f} (at 5min OB wick)")
                print(f"SL: ${trade_levels['sl']:.2f} (-25 pips)")
                print(f"TP: ${trade_levels['tp']:.2f} (+50 pips)")
                print(f"5min OB Zone: ${ob_5m['low']:.2f}-${ob_5m['high']:.2f}")
                print(f"{'='*70}\n")
                
                # Generate message
                message = f"""
{('🟢' if signal_type == 'BUY' else '🔴')} <b>{signal_type} SIGNAL</b>

💰 Pair: {self.config.SYMBOL}
💵 Entry: ${trade_levels['entry']:.2f} (5min OB wick)

📍 SL: ${trade_levels['sl']:.2f} (-25 pips)
🎯 TP: ${trade_levels['tp']:.2f} (+50 pips)

📈 5min OB: ${ob_5m['low']:.2f}-${ob_5m['high']:.2f}
⚡ 1min OB: Confirmed
✅ Retest: Confirmed

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                
                # Execute trade
                if self.config.AUTO_TRADE:
                    print("🤖 Executing trade...")
                    success = self.executor.place_order(
                        signal_type, trade_levels['entry'], trade_levels['sl'], trade_levels['tp']
                    )
                    
                    if success:
                        message = "🤖 <b>✅ TRADE EXECUTED!</b>\n\n" + message
                    else:
                        message = "⚠️ <b>TRADE FAILED</b>\n\n" + message
                else:
                    message = "📢 <b>SIGNAL ONLY</b>\n\n" + message
                
                # Send notification
                self.notifier.send_message(message)
                self.last_signal_time[signal_key] = time.time()
                
                # Exit after first valid signal
                return
        
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def run(self):
        print("=" * 70)
        print("🤖 PROPER SMC BOT - 5min OB Retest Strategy")
        print("=" * 70)
        print(f"📊 Symbol: {self.config.SYMBOL}")
        print(f"💰 Lot: {self.config.LOT_SIZE}")
        print(f"🎯 SL/TP: {self.config.FIXED_SL_PIPS}/{self.config.FIXED_TP_PIPS} pips")
        print(f"🤖 Auto: {'ON ✅' if self.config.AUTO_TRADE else 'OFF'}")
        print(f"📊 Market Updates: Every 30 minutes")
        print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        self.notifier.send_message(
            f"🤖 <b>SMC Bot Started!</b>\n\n"
            f"📊 {self.config.SYMBOL}\n"
            f"🎯 {self.config.FIXED_SL_PIPS}/{self.config.FIXED_TP_PIPS} pips\n"
            f"🤖 Auto: {'ON' if self.config.AUTO_TRADE else 'OFF'}\n"
            f"📊 Updates: Every 30 min"
        )
        
        while True:
            try:
                print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')}")
                self.check_signals()
                self.send_market_update_if_needed()  # Check for 30-min update
                time.sleep(self.config.CHECK_INTERVAL)
            except KeyboardInterrupt:
                print("\n👋 Stopped")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(self.config.CHECK_INTERVAL)

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    print("""
    🚀 PROPER SMC RETEST BOT
    
    ✅ Marks previous 5min OBs (can be far back)
    ✅ Waits for price RETEST
    ✅ Confirms with 1min OB nearby
    ✅ Enters at 5min OB WICK level
    ✅ Fixed 25 pip SL / 50 pip TP
    
    STRATEGY:
    1. Detect old 5min OBs
    2. Wait for retest
    3. Confirm 1min OB
    4. Enter at wick with fixed SL/TP
    
    """)
    
    input("Press Enter to start...\n")
    
    if not initialize_mt5(Config()):
        input("MT5 failed. Press Enter...")
        exit()
    
    print("\n✅ Ready!")
    input("Press Enter to START...\n")
    
    bot = ProperSignalBot()
    bot.run()
