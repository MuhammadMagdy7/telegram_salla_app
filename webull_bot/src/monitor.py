import asyncio
import logging
from datetime import datetime, date
from .api_client import MassiveAPIClient
from .database import Database
from .image_gen import ImageGenerator
from .config import Config
from .bot_handlers import get_template
from aiogram import Bot
# from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

logger = logging.getLogger(__name__)

class MonitorEngine:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.api = MassiveAPIClient()
        self.db = Database()
        self.image_gen = ImageGenerator()
        self.running = False
        # Memory
        self.last_notified = {}
        self.peak_prices = {} # {cmd_id: max_price}

    async def start(self):
        self.running = True
        logger.info("Monitoring engine started.")
        while self.running:
            await self.check_contracts()
            await asyncio.sleep(8)

    async def stop(self):
        self.running = False
        logger.info("Monitoring engine stopped.")

    async def check_contracts(self):
        commands = self.db.get_active_commands()
        if not commands:
            return

        today = date.today()
        import random # Jitter import

        # Group commands by Symbol + Expiration to use batch API calls
        # Anti-Ban Strategy: Fetch once per group instead of once per command
        groups = {}
        for cmd in commands:
            # Basic validation
            try:
                # Handle both string (SQLite legacy) and date object (PostgreSQL)
                exp_val = cmd['expiration']
                if isinstance(exp_val, date):
                    exp_date = exp_val
                elif isinstance(exp_val, datetime):
                    exp_date = exp_val.date()
                else:
                    exp_date = datetime.strptime(str(exp_val), "%Y-%m-%d").date()
                
                if exp_date < today:
                    logger.info(f"Command {cmd['id']} expired ({cmd['expiration']}). Stopping.")
                    self.db.update_command_status(cmd['id'], 'expired')
                    # Notify user... (Simplified for brevity, full logic below if needed or kept)
                    continue
            except ValueError:
                logger.error(f"Invalid expiration for {cmd['id']}")
                continue

            key = (cmd['symbol'], cmd['expiration'])
            if key not in groups: groups[key] = []
            groups[key].append(cmd)

        # Process Groups
        for key, group_cmds in groups.items():
            symbol, expiration = key
            
            # Anti-ban delay (Jitter)
            # Random delay 1-3s between underlying stats to look more human
            await asyncio.sleep(random.uniform(1.0, 3.0)) 

            # Batch Fetch
            try:
                # This runs synch request in executor to avoid blocking
                loop = asyncio.get_running_loop()
                chain_data = await loop.run_in_executor(None, self.api.get_batch_option_data, symbol, str(expiration))
            except Exception as e:
                logger.error(f"Batch fetch failed for {symbol}: {e}")
                continue

            # Process individual commands from cached data
            for cmd in group_cmds:
                try:
                    # Handle Decimal type from PostgreSQL
                    strike_val = cmd['strike']
                    target_strike = float(strike_val) if strike_val is not None else 0.0
                    contract_type = 'C' if str(cmd['contract_type']).upper().startswith('C') else 'P'
                    
                    # Load persisted price tracking from DB if not in memory
                    cmd_id = cmd['id']
                    if cmd_id not in self.last_notified:
                        db_last = float(cmd.get('last_notified_price', 0) or 0)
                        db_peak = float(cmd.get('peak_price', 0) or 0)
                        if db_last > 0:
                            self.last_notified[cmd_id] = db_last
                        if db_peak > 0:
                            self.peak_prices[cmd_id] = db_peak
                    
                    # Fuzzy match for strike (float precision issue)
                    # We look for closest strike in the chain data
                    # chain_data keys are (strike_float, type_str)
                    
                    # Find exact or closest match
                    match_key = None
                    min_diff = 0.05 # Tolerance
                    
                    found_data = None
                    
                    # Check exact first
                    if (target_strike, contract_type) in chain_data:
                        found_data = chain_data[(target_strike, contract_type)]
                    else:
                        # Scan for closest
                        for (s, t), d in chain_data.items():
                            if t == contract_type and abs(s - target_strike) < min_diff:
                                found_data = d
                                break
                    
                    if not found_data:
                        logger.warning(f"No data for cmd {cmd['id']} in batch")
                        continue

                    data = found_data
                    
                    # Round to 2 decimal places for comparison
                    last_price = data.get('last_price', 0)
                    bid = data.get('bid', 0)
                    ask = data.get('ask', 0)
                    mid_price = (bid + ask) / 2 if (bid and ask) else last_price
                    current_price = round(mid_price, 2)
                    
                    # --- Terminal Output ---
                    now_str = datetime.now().strftime("%H:%M:%S")
                    ch_pct = data.get('change_pct', 0)
                    direction = "🟢" if ch_pct >= 0 else "🔴"
                    try:
                        print(f"[{now_str}] {symbol} {cmd['strike']} {contract_type}: ${current_price} | {ch_pct}% | {direction}")
                    except:
                        pass
                    # -----------------------

                    mode = cmd.get('notification_mode', 'always')
                    
                    notification_needed = False
                    
                    # Update Peaks
                    initial_check = False
                    if cmd_id not in self.peak_prices:
                        self.peak_prices[cmd_id] = current_price
                        initial_check = True # Flag to notify on start
                    
                    is_new_peak = current_price > self.peak_prices[cmd_id]
                    if is_new_peak:
                        self.peak_prices[cmd_id] = current_price
                        # Persist peak to DB
                        self.db.update_price_tracking(
                            cmd_id, 
                            self.last_notified.get(cmd_id, 0), 
                            self.peak_prices[cmd_id]
                        )

                    # --- Logic based on Mode ---
                    if mode == 'peaks':
                        if is_new_peak or initial_check:
                            notification_needed = True
                    
                    elif mode == 'wait':
                        if cmd['target_price'] and current_price >= cmd['target_price']:
                            if cmd_id not in self.last_notified:
                                notification_needed = True
                            elif current_price > self.last_notified[cmd_id]:
                                notification_needed = True

                    elif mode == 'wait_down':
                        if cmd['target_price'] and current_price <= cmd['target_price']:
                            if cmd_id not in self.last_notified:
                                notification_needed = True
                            elif current_price < self.last_notified[cmd_id]:
                                notification_needed = True
                            
                    elif mode == 'enter':
                        if cmd['entry_price'] and current_price >= cmd['entry_price']:
                            if cmd_id not in self.last_notified:
                                notification_needed = True
                            elif current_price > self.last_notified[cmd_id]:
                                notification_needed = True

                    else: # Default 'always' - Only notify on price INCREASE
                        if cmd_id not in self.last_notified:
                            # Initialize with current price but DO NOT notify
                            self.last_notified[cmd_id] = current_price
                            notification_needed = False
                        elif current_price > self.last_notified[cmd_id]:
                            # Only notify if price is HIGHER than last notified price
                            notification_needed = True
                        else:
                            # Price is same or lower - do NOT notify
                            notification_needed = False
                    

                    if notification_needed:
                        is_first_notification = cmd_id not in self.last_notified
                        self.last_notified[cmd_id] = current_price
                        # Persist to DB after notification
                        self.db.update_price_tracking(
                            cmd_id,
                            self.last_notified[cmd_id],
                            self.peak_prices.get(cmd_id, current_price)
                        )
                        
                        img_data = {
                            'symbol': cmd['symbol'],
                            'strike': cmd['strike'],
                            'type': cmd['contract_type'],
                            'last_price': current_price,
                            'entry_price': cmd['entry_price'],
                            'expiration': cmd['expiration'],
                            'volume': data.get('volume'),
                            'openInterest': data.get('openInterest', 0),
                            'change_pct': data.get('change_pct', 0),
                            'change_abs': data.get('change_abs', 0),
                            'underlying_price': data.get('underlying_price', 0),
                            'bid': data.get('bid', 0),
                            'ask': data.get('ask', 0),
                            'impliedVolatility': data.get('impliedVolatility', 0)
                        }
                        
                        image_buf = self.image_gen.generate_status_image(img_data)
                        
                        from aiogram.types import BufferedInputFile
                        fname = f"{cmd['symbol']}_{cmd_id}.png"
                        photo = BufferedInputFile(image_buf.read(), filename=fname)
                        
                        target_chats = Config.TELEGRAM_GROUP_IDS if Config.TELEGRAM_GROUP_IDS else [cmd['chat_id']]
                        
                        bid = data.get('bid', 0) or 0
                        ask = data.get('ask', 0) or 0
                        mid_caption = (bid + ask) / 2 if (bid and ask) else current_price
                        if mid_caption == 0: mid_caption = last_price

                        type_ar = "🟢 كول 🟢" if cmd['contract_type'].upper().startswith('C') else "🔴 بوت 🔴"

                        template_vars = {
                            'symbol': cmd['symbol'],
                            'strike': cmd['strike'],
                            'expiration': cmd['expiration'],
                            'type_ar': type_ar,
                            'price': f"{mid_caption:.2f}",
                            'target_price': f"{(cmd.get('target_price') or 0):.2f}",
                            'entry_price': f"{(cmd.get('entry_price') or 0):.2f}"
                        }

                        caption = get_template('update').format(**template_vars)
                        
                        if mode == 'enter' and is_first_notification:
                            caption = get_template('enter_first').format(**template_vars)
                        elif (mode == 'wait' or mode == 'wait_down') and is_first_notification:
                            caption = get_template('wait_first').format(**template_vars)
                        elif (mode == 'always' or mode is None) and is_first_notification:
                            caption = get_template('select_first').format(**template_vars)

                        for chat_id in target_chats:
                            try:
                                await self.bot.send_photo(
                                    chat_id=chat_id, 
                                    photo=photo, 
                                    caption=caption,
                                    parse_mode="Markdown"
                                )
                            except Exception as send_err:
                                logger.error(f"Failed to send photo to {chat_id}: {send_err}")
                        
                except Exception as e:
                    logger.error(f"Error processing cmd {cmd['id']} in batch: {e}")
