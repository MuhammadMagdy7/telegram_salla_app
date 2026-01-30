from aiogram import Router, types
from aiogram.filters import Command
from aiogram import F
from .database import Database
from .api_client import MassiveAPIClient
from .image_gen import ImageGenerator
from .contract_card_gen import ContractCardGenerator
from .postgres_client import PostgresClient
from .config import Config
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import json
import asyncio
import os
from datetime import date
import logging

logger = logging.getLogger(__name__)

router = Router()
db = Database()
api = MassiveAPIClient()
image_gen = ImageGenerator()
contract_card = ContractCardGenerator()
pg_client = PostgresClient()

# Helper to default date to today
def validate_or_default_date(expiration_str):
    if not expiration_str:
        return date.today().strftime("%Y-%m-%d")
    return expiration_str

# Path to favorites file
FAVORITES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "favorites.json")

def load_favorites():
    """Load favorites from JSON file."""
    try:
        with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            raw = data.get('symbols', [])
            normalized = []
            for item in raw:
                if isinstance(item, str):
                    normalized.append({'symbol': item, 'type': 'fund'})
                else:
                    normalized.append(item)
            return normalized
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_favorites(symbols):
    """Save favorites to JSON file."""
    with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
        json.dump({'symbols': symbols}, f, ensure_ascii=False, indent=4)

# Path to templates file
TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates.json")

# Default templates
DEFAULT_TEMPLATES = {
    "select_first": "📢 دخول العقد {type_ar}\n\n🔹 الرمز: {symbol}\n📅 التاريخ: {expiration}\n🎯 السترايك: {strike}\n📊 النوع: {type_ar}\n💰 السعر الحالي: ${price}",
    
    "wait_announce": "⏳ *توصية انتظار*\n\nيرجى مراقبة العقد التالي وانتظار السعر المحدد:\n🔹 *الرمز:* {symbol}\n📅 *التاريخ:* {expiration}\n🎯 *السترايك:* {strike}\n📊 *النوع:* {type_ar}\n\n💰 *السعر المستهدف للانتظار:* {target_price}",
    
    "wait_first": "⏳ *تم الوصول لسعر الانتظار*\n\n🔹 *الرمز:* {symbol}\n📅 *التاريخ:* {expiration}\n🎯 *السترايك:* {strike}\n📊 *النوع:* {type_ar}\n\n💰 *السعر المستهدف:* ${target_price}\n📈 *السعر الحالي:* ${price}",
    
    "enter_first": "🚀 *توصية دخول*\n\n*تم الوصول لنقطة الدخول المحددة:*\n🔹 *الرمز:* {symbol}\n📅 *التاريخ:* {expiration}\n🎯 *السترايك:* {strike}\n📊 *النوع:* {type_ar}\n\n💰 *سعر الدخول المستهدف:* ${entry_price}\n📈 *السعر الحالي:* ${price}",
    
    "update": "صعود السعر 🚀🚀\nالطمع يسحق ماجمع ⚡📌\nالإنسان بدون مخاطر يمشي للمجهول ✋🏻",
    
    "exit_contract": "🚨 *تنبيه خروج من العقد*\n\n🔹 *الرمز:* {symbol}\n📅 *التاريخ:* {expiration}\n🎯 *السترايك:* {strike}\n📊 *النوع:* {type_ar}\n\n💰 *سعر الخروج:* ${price}\n\n⚠️ *يرجى الخروج من العقد فوراً*"
}

def load_templates():
    """Load templates from JSON file."""
    try:
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            merged = DEFAULT_TEMPLATES.copy()
            merged.update(data)
            return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_TEMPLATES.copy()

def save_templates(templates):
    """Save templates to JSON file."""
    with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, ensure_ascii=False, indent=4)

def get_template(key):
    """Get a specific template by key."""
    templates = load_templates()
    return templates.get(key, DEFAULT_TEMPLATES.get(key, ""))

# Store last Gso result: maps simple 3-digit ID to full contract info
# This is cleared and replaced every time 'g' command is used
last_gso_contracts = {}

# --- Main Keyboard ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 عرض القائمة"), KeyboardButton(text="❓ عرض الأوامر")],
    ],
    resize_keyboard=True
)

@router.message(Command("id", "i"))
@router.channel_post(Command("id", "i"))
async def get_chat_id(message: types.Message):
    """Returns the chat ID, useful for getting Group IDs."""
    await message.reply(f"Chat ID: `{message.chat.id}`", parse_mode="Markdown")

@router.callback_query(F.data.startswith("remove_"))
async def handle_remove_callback(callback: types.CallbackQuery):
    if Config.ADMIN_USER_IDS and str(callback.from_user.id) not in Config.ADMIN_USER_IDS:
        await callback.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    try:
        cmd_id = int(callback.data.split("_")[1])

        # Postgres Logic: Close contract log
        cmd = db.get_command(cmd_id)
        if not cmd:
            await callback.answer("❌ لم يتم العثور على الأمر", show_alert=True)
            return
            
        price = 0
        if cmd.get('postgres_id'):
             try:
                 # Use get_batch_option_data like monitor does (more reliable)
                 loop = asyncio.get_running_loop()
                 chain_data = await loop.run_in_executor(None, api.get_batch_option_data, cmd['symbol'], str(cmd['expiration']))
                 
                 # Find our contract in the chain
                 contract_type = 'C' if str(cmd['contract_type']).upper().startswith('C') else 'P'
                 target_strike = float(cmd['strike'])
                 
                 data = chain_data.get((target_strike, contract_type))
                 if not data:
                     # Try fuzzy match
                     for (s, t), d in chain_data.items():
                         if t == contract_type and abs(s - target_strike) < 0.05:
                             data = d
                             break
                 
                 if data:
                     bid = data.get('bid', 0) or 0
                     ask = data.get('ask', 0) or 0
                     mid = (bid + ask) / 2
                     price = mid if mid > 0 else (data.get('last_price', 0) or 0)
                 else:
                     price = 0
                 await asyncio.to_thread(pg_client.update_close_price, cmd['postgres_id'], price, data)
             except Exception as e:
                 print(f"Postgres update error: {e}")

        if db.remove_command(cmd_id):
            await callback.answer("🗑 تم الحذف")
            await callback.message.edit_text(f"🗑 تم حذف المراقبة رقم {cmd_id}.")
            
            # Send exit notification to group
            if Config.TELEGRAM_GROUP_IDS:
                try:
                    type_ar = "🟢 كول 🟢" if str(cmd['contract_type']).upper().startswith('C') else "🔴 بوت 🔴"
                    template_vars = {
                        'symbol': cmd['symbol'],
                        'strike': cmd['strike'],
                        'expiration': cmd['expiration'],
                        'type_ar': type_ar,
                        'price': f"{price:.2f}"
                    }
                    exit_msg = get_template('exit_contract').format(**template_vars)
                    
                    for chat_id in Config.TELEGRAM_GROUP_IDS:
                        try:
                            await callback.bot.send_message(
                                chat_id=chat_id,
                                text=exit_msg,
                                parse_mode="Markdown"
                            )
                        except Exception as inner_e:
                            print(f"Failed to send exit notification to group {chat_id}: {inner_e}")
                except Exception as e:
                    print(f"Failed to send exit notification: {e}")
        else:
            await callback.answer("❌ لم يتم العثور على الأمر", show_alert=True)
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)

@router.callback_query(F.data.startswith("stop_"))
async def handle_stop_callback(callback: types.CallbackQuery):
    if Config.ADMIN_USER_IDS and str(callback.from_user.id) not in Config.ADMIN_USER_IDS:
        await callback.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    try:
        cmd_id = int(callback.data.split("_")[1])
        if db.update_command_status(cmd_id, 'paused'):
            await callback.answer("⏸ تم الإيقاف المؤقت")
            await callback.message.answer(f"⏸ تم إيقاف العملية رقم {cmd_id} مؤقتاً.")
            # Refresh the list to show the new status
            await cmd_list(callback.message, from_callback=True)
        else:
            await callback.answer("❌ لم يتم العثور على الأمر", show_alert=True)
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)

@router.callback_query(F.data.startswith("run_"))
async def handle_run_callback(callback: types.CallbackQuery):
    if Config.ADMIN_USER_IDS and str(callback.from_user.id) not in Config.ADMIN_USER_IDS:
        await callback.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    try:
        cmd_id = int(callback.data.split("_")[1])
        if db.update_command_status(cmd_id, 'active'):
            await callback.answer("▶ تم التشغيل")
            await callback.message.answer(f"▶ تم استئناف العملية رقم {cmd_id}.")
            # Refresh the list to show the new status
            await cmd_list(callback.message, from_callback=True)
        else:
            await callback.answer("❌ لم يتم العثور على الأمر", show_alert=True)
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)


@router.callback_query(F.data.startswith("del_"))
async def handle_delete_callback(callback: types.CallbackQuery):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(callback.from_user.id) not in Config.ADMIN_USER_IDS:
        await callback.answer("⛔ ليس لديك صلاحية لهذا الإجراء.", show_alert=True)
        return

    try:
        cmd_id = int(callback.data.split("_")[1])
        
        # Postgres Logic: Close contract log
        cmd = db.get_command(cmd_id)
        if not cmd:
            await callback.answer("❌ لم يتم العثور على الأمر", show_alert=True)
            return
            
        price = 0
        if cmd.get('postgres_id'):
             try:
                 # Use get_batch_option_data like monitor does (more reliable)
                 loop = asyncio.get_running_loop()
                 chain_data = await loop.run_in_executor(None, api.get_batch_option_data, cmd['symbol'], str(cmd['expiration']))
                 
                 # Find our contract in the chain
                 contract_type = 'C' if str(cmd['contract_type']).upper().startswith('C') else 'P'
                 target_strike = float(cmd['strike'])
                 
                 data = chain_data.get((target_strike, contract_type))
                 if not data:
                     # Try fuzzy match
                     for (s, t), d in chain_data.items():
                         if t == contract_type and abs(s - target_strike) < 0.05:
                             data = d
                             break
                 
                 if data:
                     bid = data.get('bid', 0) or 0
                     ask = data.get('ask', 0) or 0
                     mid = (bid + ask) / 2
                     price = mid if mid > 0 else (data.get('last_price', 0) or 0)
                     logger.info(f"Delete Callback: Updating CMD {cmd_id} with exit price {price}")
                 else:
                     logger.warning(f"Delete Callback: No market data found for CMD {cmd_id}")
                     price = 0
                 await asyncio.to_thread(pg_client.update_close_price, cmd['postgres_id'], price, data)
             except Exception as e:
                 print(f"Postgres update error: {e}")

        db.remove_command(cmd_id)
        await callback.answer("تم حذف المراقبة.")
        await callback.message.reply(f"🛑 تم إيقاف عملية المراقبة رقم {cmd_id} بنجاح.")
        
        # Send exit notification to group
        if Config.TELEGRAM_GROUP_IDS:
            try:
                type_ar = "🟢 كول 🟢" if str(cmd['contract_type']).upper().startswith('C') else "🔴 بوت 🔴"
                template_vars = {
                    'symbol': cmd['symbol'],
                    'strike': cmd['strike'],
                    'expiration': cmd['expiration'],
                    'type_ar': type_ar,
                    'price': f"{price:.2f}"
                }
                exit_msg = get_template('exit_contract').format(**template_vars)
                
                for chat_id in Config.TELEGRAM_GROUP_IDS:
                    try:
                        await callback.bot.send_message(
                            chat_id=chat_id,
                            text=exit_msg,
                            parse_mode="Markdown"
                        )
                    except Exception as inner_e:
                        print(f"Failed to send exit notification to group {chat_id}: {inner_e}")
            except Exception as e:
                print(f"Failed to send exit notification: {e}")
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)

# --- Favorites Callback Handler ---
@router.callback_query(F.data.startswith("fav_"))
async def handle_fav_callback(callback: types.CallbackQuery):
    """Handle favorite symbol selection - execute g command or prompt expiry."""
    if Config.ADMIN_USER_IDS and str(callback.from_user.id) not in Config.ADMIN_USER_IDS:
        await callback.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    
    try:
        symbol = callback.data.split("_")[1].upper()
        
        # Check type
        favorites = load_favorites()
        fav_item = next((f for f in favorites if f['symbol'] == symbol), None)
        
        if fav_item and fav_item.get('type') == 'company':
             await prompt_fav_expirations(callback, symbol)
             return

        # If fund or default, show chain directly (no expiry days filter)
        await show_chain_view(callback, symbol)
        
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)

@router.message(F.text.lower().startswith("gso") | F.text.lower().startswith("g "))
async def handle_gso_command(message: types.Message):
    global last_gso_contracts
    
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: Gso <symbol>
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("طريقة الاستخدام: g <رمز_السهم>")
            return
        
        symbol = parts[1].upper()
        
        # 1. Acknowledgement
        await message.answer("⌛ جاري جلب البيانات...")
        
        # 2. Fetch Option Chain
        chain_result = await api.get_option_chain(symbol)
        
        if not chain_result:
             await message.answer("لم يتم العثور على بيانات لهذا الرمز.")
             return

        chain_data = chain_result['contracts']
        entry_call = chain_result['entry_call']
        entry_put = chain_result['entry_put']

        # 3. Clear previous list and assign new simple IDs (1, 2, 3...)
        last_gso_contracts = {}
        simple_id = 1
        for c in chain_data:
            c['simple_id'] = simple_id
            last_gso_contracts[simple_id] = c
            simple_id += 1

        # Get all calls and puts first
        all_calls = [c for c in chain_data if c['type'] == 'C']
        all_puts = [c for c in chain_data if c['type'] == 'P']
        
        # Apply filter only if list has more than 10 items
        if len(all_calls) > 10:
            # Filter: Ask between 2 and 10
            filtered_calls = [c for c in all_calls if 2 <= c.get('ask', 0) <= 10]
            # Fallback: if filter returns empty, show all
            calls = filtered_calls if filtered_calls else all_calls
        else:
            calls = all_calls
            
        if len(all_puts) > 10:
            # Filter: Ask between 2 and 10
            filtered_puts = [c for c in all_puts if 2 <= c.get('ask', 0) <= 10]
            # Fallback: if filter returns empty, show all
            puts = filtered_puts if filtered_puts else all_puts
        else:
            puts = all_puts
        
        # Sort by strike
        calls.sort(key=lambda x: x['strike'])
        puts.sort(key=lambda x: x['strike'])
        
        # Limit to 10 rows: first 10 calls, first 10 puts
        calls = calls[:10]
        puts = puts[:10]
        
        # Format Call Table with simple 3-digit ID
        call_table = "عقود الكول:\n"
        call_table += "ID   Strike    Bid    Ask    Last   Vol\n"
        call_table += "────────────────────────────────────\n"
        for c in calls:
             call_table += f"{c['simple_id']:<3}  {c['strike']:<8.0f} {c['bid']:<6.2f} {c['ask']:<6.2f} {c['last']:<6.2f} {c['volume']:,}\n"

        # Format Put Table with simple 3-digit ID
        put_table = "عقود البوت:\n"
        put_table += "ID   Strike    Bid    Ask    Last   Vol\n"
        put_table += "────────────────────────────────────\n"
        for c in puts:
             put_table += f"{c['simple_id']:<3}  {c['strike']:<8.0f} {c['bid']:<6.2f} {c['ask']:<6.2f} {c['last']:<6.2f} {c['volume']:,}\n"

        entry_msg = f"🟢 دخول الكول : {entry_call:.2f}\n🔴 دخول البوت : {entry_put:.2f}"
        summary_msg = f"📊 *{symbol}* - استخدم `/x <ID>` للمراقبة"

        # Send Tables
        msg_calls = f"```{call_table}```"
        msg_puts = f"```{put_table}```"
        
        await message.answer(entry_msg, parse_mode="Markdown")
        await message.answer(summary_msg + "\n" + msg_calls + "\n" + msg_puts, parse_mode="Markdown")

    except Exception as e:
        await message.answer(f"حدث خطأ غير متوقع: {str(e)}")

# --- Helper to get keyboard ---
def get_user_keyboard(user_id):
    if Config.ADMIN_USER_IDS and str(user_id) in Config.ADMIN_USER_IDS:
        return main_keyboard
    return types.ReplyKeyboardRemove()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = get_user_keyboard(message.from_user.id)
    await message.answer("أهلاً بك! استخدم الأزرار بالأسفل للتحكم.", reply_markup=kb)

@router.message(F.text == "❓ عرض الأوامر")
@router.message(Command("h", "help"))
async def cmd_help(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لعرض الأوامر.")
        return


# /peaks SPX 6900 C 2026-01-20 - القمم فقط
    help_text = """
📌 الأوامر الأساسية:

/m SPX 6900 C 2026-01-20 - مراقبة عقد
/l - عرض القائمة

Gso SPX - عرض سلسلة العقود (أو g SPX)
/x ID - مراقبة عقد من القائمة

📌 المفضلة:
/f - عرض قائمة الرموز المفضلة
/fa SPX - إضافة رمز للمفضلة
/fd 1 - حذف رمز من المفضلة

📌 أوامر متقدمة:
/wait SPX 6900 C 2026-01-20 5.50 - انتظار سعر
/enter SPX 6900 C 2026-01-20 4.20 - انتظار نقطة دخول

📌 إدارة القوالب:
/tmp - عرض القوالب الحالية
/tset <رقم> <النص> - تعديل قالب
/treset - إعادة تعيين القوالب -- خطر !
/treset <رقم> - إعادة تعيين قالب محدد   

ملاحظة: جميع الأوامر تدعم الاختصارات (m, l, x, pk, wt, en, h, g).
"""
    kb = get_user_keyboard(message.from_user.id)
    await message.answer(help_text, reply_markup=kb)


@router.message(Command("monitor", "m"))
async def cmd_monitor(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: /m SPX 6900 C [2026-01-20]
    try:
        parts = message.text.split()[1:]
        if len(parts) < 3:
            await message.answer("طريقة الاستخدام: /m SPX 6900 C [2026-01-20]")
            return
        
        symbol = parts[0]
        strike = parts[1]
        c_type = parts[2]
        expiration = parts[3] if len(parts) > 3 else date.today().strftime("%Y-%m-%d")

        # Fetch fresh data for Postgres log and Image
        data = await api.get_market_data(symbol.upper(), c_type.upper(), expiration, strike)
        if not data:
            data = {'last_price': 0, 'bid': 0, 'ask': 0}

        # Calculate mid price
        bid = data.get('bid', 0) or 0
        ask = data.get('ask', 0) or 0
        current_price = (bid + ask) / 2 if (bid and ask) else (data.get('last_price', 0) or 0)

        # Log to Postgres with entry market data
        pg_id = await asyncio.to_thread(
            pg_client.add_contract_log, 
            symbol.upper(), c_type.upper(), float(strike), expiration, current_price,
            None, data  # auction_day=None, market_data=data
        )

        cmd_id = db.add_command(message.chat.id, symbol.upper(), float(strike), c_type.upper(), expiration, postgres_id=pg_id)
        await message.answer(f"✅ بدأت المراقبة لـ {symbol} {strike} {c_type} {expiration}.\nرقم: {cmd_id}")

        # Notify Group using template (Same as /x command)
        if Config.TELEGRAM_GROUP_IDS:
            try:
                # Type translation
                type_ar = "🟢 كول 🟢" if c_type.upper().startswith('C') else "🔴 بوت 🔴"
                
                # Fetch fresh data for image (Already fetched above)
                # data = await api.get_market_data(...) - Removed duplicate call

                # Prepare Image Data
                img_data = {
                    'symbol': symbol.upper(),
                    'strike': float(strike),
                    'type': c_type.upper(),
                    'last_price': current_price,
                    'entry_price': 0,
                    'expiration': expiration,
                    'volume': data.get('volume', 0),
                    'openInterest': data.get('openInterest', 0),
                    'change_pct': data.get('change_pct', 0),
                    'change_abs': data.get('change_abs', 0),
                    'underlying_price': data.get('underlying_price', 0),
                    'bid': bid,
                    'ask': ask,
                    'impliedVolatility': data.get('impliedVolatility', 0)
                }

                # Generate Image
                image_buf = image_gen.generate_status_image(img_data)
                
                from aiogram.types import BufferedInputFile
                fname = f"{symbol}_{cmd_id}.png"
                photo = BufferedInputFile(image_buf.read(), filename=fname)

                # Prepare Caption using Template
                template_vars = {
                    'symbol': symbol.upper(),
                    'strike': strike,
                    'expiration': expiration,
                    'type_ar': type_ar,
                    'price': f"{current_price:.2f}",
                    'target_price': "0.00",
                    'entry_price': "0.00"
                }

                caption = get_template('select_first').format(**template_vars)
                
                for chat_id in Config.TELEGRAM_GROUP_IDS:
                    try:
                        image_buf.seek(0)
                        photo_reuse = BufferedInputFile(image_buf.read(), filename=fname)
                        
                        await message.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_reuse,
                            caption=caption,
                            parse_mode="Markdown"
                        )
                    except Exception as inner_e:
                        print(f"Failed to send monitor notification to group {chat_id}: {inner_e}")
            except Exception as e:
                print(f"Failed to send notification to group: {e}")

    except (IndexError, ValueError):
        await message.answer("طريقة الاستخدام: /m SPX 6900 C [2026-01-20]")

@router.message(F.text == "📋 عرض القائمة")
@router.message(Command("list", "l"))
async def cmd_list(message: types.Message, from_callback: bool = False):
    # Skip admin check if called from a callback (already checked there)
    if not from_callback:
        if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
            await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
            return

    my_commands = db.get_chat_commands(message.chat.id)
    
    if not my_commands:
        kb = get_user_keyboard(message.from_user.id)
        await message.answer("لا توجد عمليات مراقبة حالياً.", reply_markup=kb)
        return

    # For callbacks, we edit the message. For commands, we send a new one.
    send_func = message.edit_text if from_callback else message.answer

    for c in my_commands:
        status_icon = "✅" if c['status'] == 'active' else "⏸️"
        text = (
            f"{status_icon} *رقم: {c['id']}* | {c['symbol']} {c['strike']} {c['contract_type']} {c['expiration']}\n"
            f"📈 الوضع: `{c['notification_mode']}`"
        )
        
        # --- Inline Keyboard for each item ---
        buttons = []
        if c['status'] == 'active':
            buttons.append(InlineKeyboardButton(text="⏸ إيقاف مؤقت", callback_data=f"stop_{c['id']}"))
        else:
            buttons.append(InlineKeyboardButton(text="▶️ تشغيل", callback_data=f"run_{c['id']}"))
        
        buttons.append(InlineKeyboardButton(text="🗑 حذف", callback_data=f"remove_{c['id']}"))
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
        
        # We must send a new message for inline keyboards, can't use send_func for all
        await message.answer(text, reply_markup=inline_keyboard, parse_mode="Markdown")

    # If it's the initial command, send a confirmation text.
    if not from_callback:
        kb = get_user_keyboard(message.from_user.id)
        await message.answer("تم عرض القائمة.", reply_markup=kb)


@router.message(Command("select", "x"))
async def cmd_select(message: types.Message):
    global last_gso_contracts
    
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: /x <simple_id>
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("طريقة الاستخدام: /x <ID>\nمثال: /x 5")
            return
        
        input_id = args[1].strip()
        
        # Check if it's a simple ID from the last Gso list
        try:
            simple_id = int(input_id)
            if simple_id not in last_gso_contracts:
                await message.answer("❌ هذا الرقم غير موجود. استخدم أمر `g` أولاً لعرض القائمة.")
                return
            
            contract_data = last_gso_contracts[simple_id]
            contract_id = contract_data['contract_id']
        except ValueError:
            # If not a number, treat as full OCC ID
            contract_id = input_id
        
        # Parse OCC Symbol
        import re
        match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", contract_id)
        if not match:
             await message.answer("❌ صيغة رمز العقد غير صحيحة.")
             return
             
        root, date_str, type_char, strike_str = match.groups()
        
        # Format Expiration: YYMMDD -> YYYY-MM-DD
        expiration = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
        
        # Format Strike: 04500000 -> 4500.0
        strike = float(strike_str) / 1000.0
        
        # Type
        contract_type = "🟢 Call 🟢" if type_char == 'C' else "🔴 Put 🔴"
        
        # Fetch fresh data for Postgres log
        data = await api.get_market_data(root.upper(), type_char.upper(), expiration, str(strike))
        if not data:
             data = {'last_price': 0, 'bid': 0, 'ask': 0}
        
        bid = data.get('bid', 0) or 0
        ask = data.get('ask', 0) or 0
        current_price = (bid + ask) / 2 if (bid and ask) else (data.get('last_price', 0) or 0)
        
        # Log to Postgres with entry market data
        pg_id = await asyncio.to_thread(
            pg_client.add_contract_log, 
            root.upper(), type_char.upper(), float(strike), expiration, current_price,
            None, data  # auction_day=None, market_data=data
        )
        
        # Add to DB
        cmd_id = db.add_command(
            chat_id=message.chat.id, 
            symbol=root, 
            strike=strike, 
            contract_type=type_char, # Store as C/P 
            expiration=expiration,
            contract_id=contract_id,
            postgres_id=pg_id
        )
        
        await message.answer(
            f"✅ تم تفعيل المراقبة للعقد المحدد:\n"
            f"🆔 *{contract_id}*\n"
            f"🔹 السهم: {root}\n"
            f"📅 التاريخ: {expiration}\n"
            f"🎯 السترايك: {strike}\n"
            f"📊 النوع: {contract_type}",
            parse_mode="Markdown"
        )
        
        # Notify the group if Group ID is set
        if Config.TELEGRAM_GROUP_IDS:
            try:
                # Type translation for user friendly message
                type_ar = "🟢 كول 🟢" if type_char == 'C' else "🔴 بوت 🔴"
                
                # Fetch fresh data for image (Already fetched above)
                # data = await api.get_market_data(...) - Removed duplicate
                
                # Calculate mid price (Already calculated)
                # bid = ...
                # current_price = ...

                # Prepare Image Data


                # Prepare Image Data
                img_data = {
                    'symbol': root,
                    'strike': strike,
                    'type': type_char,
                    'last_price': current_price,
                    'entry_price': 0,
                    'expiration': expiration,
                    'volume': data.get('volume', 0),
                    'openInterest': data.get('openInterest', 0),
                    'change_pct': data.get('change_pct', 0),
                    'change_abs': data.get('change_abs', 0),
                    'underlying_price': data.get('underlying_price', 0),
                    'bid': bid,
                    'ask': ask,
                    'impliedVolatility': data.get('impliedVolatility', 0)
                }

                # Generate Image
                image_buf = image_gen.generate_status_image(img_data)
                
                from aiogram.types import BufferedInputFile
                fname = f"{root}_{contract_id}.png"
                photo = BufferedInputFile(image_buf.read(), filename=fname)

                # Prepare Caption using Template
                template_vars = {
                    'symbol': root,
                    'strike': strike,
                    'expiration': expiration,
                    'type_ar': type_ar,
                    'price': f"{current_price:.2f}",
                    'target_price': "0.00",
                    'entry_price': "0.00"
                }

                caption = get_template('select_first').format(**template_vars)
                
                for chat_id in Config.TELEGRAM_GROUP_IDS:
                    try:
                        # Reset buffer position for each send if needed (BufferedInputFile handles read usually, but good practice if reused)
                        # Actually aiogram BufferedInputFile consumes the stream. For multiple sends, we might need multiple instances or byte bytes.
                        # It's safer to use the bytes directly.
                        image_buf.seek(0)
                        photo_reuse = BufferedInputFile(image_buf.read(), filename=fname)
                        
                        await message.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_reuse,
                            caption=caption,
                            parse_mode="Markdown"
                        )
                    except Exception as inner_e:
                        print(f"Failed to send add notification to group {chat_id}: {inner_e}")
            except Exception as e:
                # Log error but don't fail the command
                print(f"Failed to send notification to group: {e}")

    except Exception as e:
        await message.answer(f"حدث خطأ: {e}")

@router.message(Command("remove", "r"))
async def cmd_remove(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    try:
        cmd_id = int(message.text.split()[1])

        # Postgres Logic: Close contract log
        cmd = db.get_command(cmd_id)
        if not cmd:
            await message.answer(f"❌ لا توجد عملية بهذا الرقم: {cmd_id}")
            return
            
        price = 0
        if cmd.get('postgres_id'):
             try:
                 # Use get_batch_option_data like monitor does (more reliable)
                 loop = asyncio.get_running_loop()
                 chain_data = await loop.run_in_executor(None, api.get_batch_option_data, cmd['symbol'], str(cmd['expiration']))
                 
                 # Find our contract in the chain
                 contract_type = 'C' if str(cmd['contract_type']).upper().startswith('C') else 'P'
                 target_strike = float(cmd['strike'])
                 
                 data = chain_data.get((target_strike, contract_type))
                 if not data:
                     # Try fuzzy match
                     for (s, t), d in chain_data.items():
                         if t == contract_type and abs(s - target_strike) < 0.05:
                             data = d
                             break
                 
                 if data:
                     bid = data.get('bid', 0) or 0
                     ask = data.get('ask', 0) or 0
                     mid = (bid + ask) / 2
                     price = mid if mid > 0 else (data.get('last_price', 0) or 0)
                     logger.info(f"Remove CMD: Updating CMD {cmd_id} with exit price {price}")
                 else:
                     logger.warning(f"Remove CMD: No market data found for CMD {cmd_id}")
                     price = 0
                 await asyncio.to_thread(pg_client.update_close_price, cmd['postgres_id'], price, data)
             except Exception as e:
                 print(f"Postgres update error: {e}")

        if db.remove_command(cmd_id):
            await message.answer(f"🗑 تم حذف العملية رقم {cmd_id}.")
            
            # Send exit notification to group
            if Config.TELEGRAM_GROUP_IDS:
                try:
                    type_ar = "🟢 كول 🟢" if str(cmd['contract_type']).upper().startswith('C') else "🔴 بوت 🔴"
                    template_vars = {
                        'symbol': cmd['symbol'],
                        'strike': cmd['strike'],
                        'expiration': cmd['expiration'],
                        'type_ar': type_ar,
                        'price': f"{price:.2f}"
                    }
                    exit_msg = get_template('exit_contract').format(**template_vars)
                    
                    for chat_id in Config.TELEGRAM_GROUP_IDS:
                        try:
                            await message.bot.send_message(
                                chat_id=chat_id,
                                text=exit_msg,
                                parse_mode="Markdown"
                            )
                        except Exception as inner_e:
                            print(f"Failed to send exit notification to group {chat_id}: {inner_e}")
                except Exception as e:
                    print(f"Failed to send exit notification: {e}")
        else:
            await message.answer(f"❌ لا توجد عملية بهذا الرقم: {cmd_id}")
    except (IndexError, ValueError):
        await message.answer("طريقة الاستخدام: /r <الرقم>")

@router.message(Command("stop", "s"))
async def cmd_stop(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    try:
        cmd_id = int(message.text.split()[1])
        if db.update_command_status(cmd_id, 'paused'):
            await message.answer(f"⏸ تم إيقاف العملية رقم {cmd_id} مؤقتاً.")
        else:
            await message.answer(f"❌ لا توجد عملية بهذا الرقم: {cmd_id}")
    except (IndexError, ValueError):
        await message.answer("طريقة الاستخدام: /s <الرقم>")

@router.message(Command("run", "p"))
async def cmd_run(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    try:
        cmd_id = int(message.text.split()[1])
        if db.update_command_status(cmd_id, 'active'):
            await message.answer(f"▶ تم استئناف العملية رقم {cmd_id}.")
        else:
            await message.answer(f"❌ لا توجد عملية بهذا الرقم: {cmd_id}")
    except (IndexError, ValueError):
        await message.answer("طريقة الاستخدام: /p <الرقم>")

@router.message(Command("peaks", "pk"))
async def cmd_peaks(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: /pk SPX 6900 C [2026-01-20]
    try:
        parts = message.text.split()[1:]
        if len(parts) < 3:
            await message.answer("طريقة الاستخدام: /pk SPX 6900 C [2026-01-20]")
            return
        
        symbol = parts[0]
        strike = parts[1]
        c_type = parts[2]
        expiration = parts[3] if len(parts) > 3 else date.today().strftime("%Y-%m-%d")

        # Fetch current price for logging
        current_price_val = 0.0
        try:
             data = await api.get_market_data(symbol.upper(), c_type.upper(), expiration, strike)
             if data:
                 bid = data.get('bid', 0) or 0
                 ask = data.get('ask', 0) or 0
                 current_price_val = (bid + ask) / 2 if (bid and ask) else (data.get('last_price', 0) or 0)
        except Exception as e:
             print(f"Error fetching price for peaks log: {e}")

        # Log to Postgres with entry market data
        pg_id = await asyncio.to_thread(
            pg_client.add_contract_log, 
            symbol.upper(), c_type.upper(), float(strike), expiration, current_price_val,
            None, data if 'data' in dir() else None  # auction_day=None, market_data=data
        )

        cmd_id = db.add_command(
            message.chat.id, symbol.upper(), float(strike), c_type.upper(), expiration, 
            notification_mode='peaks',
            postgres_id=pg_id
        )
        await message.answer(f"📈 بدأت مراقبة القمم لـ {symbol} {strike} {expiration}.\nرقم: {cmd_id}")
    except (IndexError, ValueError):
         await message.answer("طريقة الاستخدام: /pk SPX 6900 C [2026-01-20]")

@router.message(Command("wait", "wt"))
async def cmd_wait(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: /wt SPX 6900 C 5.50 [2026-01-20]
    # Note: re-ordered arguments to allow optional date. Usually user naturally puts date last or before numbers.
    # To support old syntax /wt SYMBOL STRIKE CALL DATE TARGET, we need to be careful.
    # New logic: Scan parts. If part looks like date (YYYY-MM-DD), use it. Leftover is target.
    try:
        parts = message.text.split()[1:]
        if len(parts) < 4:
            await message.answer("طريقة الاستخدام: /wt SPX 6900 C 5.50 [التاريخ]")
            return
        
        symbol = parts[0]
        strike = parts[1]
        c_type = parts[2]
        
        # Check remaining parts for date
        remaining = parts[3:]
        expiration = date.today().strftime("%Y-%m-%d")
        target_str = None

        import re
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')

        for p in remaining:
            if date_pattern.match(p):
                expiration = p
            else:
                target_str = p
        
        if target_str is None:
             await message.answer("يرجى تحديد السعر المستهدف.")
             return

        target_price = float(target_str)
        
        # Determine mode based on current price
        mode = 'wait' # Default: Wait for price to rise >= target
        current_price_val = 0.0
        data_cache = None

        # Fetch current price first
        try:
            data_cache = await api.get_market_data(symbol.upper(), c_type.upper(), expiration, strike)
            if data_cache:
                bid = data_cache.get('bid', 0) or 0
                ask = data_cache.get('ask', 0) or 0
                current_price_val = (bid + ask) / 2 if (bid and ask) else (data_cache.get('last_price', 0) or 0)
                
                # If current price is higher than target, assume we want to catch the drop
                if current_price_val > target_price:
                    mode = 'wait_down'
        except Exception as e:
            print(f"Price fetch in wait error: {e}")

        # Log to Postgres with entry market data
        pg_id = await asyncio.to_thread(
            pg_client.add_contract_log, 
            symbol.upper(), c_type.upper(), float(strike), expiration, current_price_val,
            None, data_cache if 'data_cache' in dir() else None  # auction_day=None, market_data
        )

        cmd_id = db.add_command(
            message.chat.id, symbol.upper(), float(strike), c_type.upper(), expiration, 
            target_price=target_price,
            notification_mode=mode,
            postgres_id=pg_id
        )
        
        trigger_desc = "📉 (هبوط)" if mode == 'wait_down' else "📈 (صعود)"
        await message.answer(f"🎯 انتظار السعر {target_price} {trigger_desc} لـ {symbol} {expiration}.\nرقم: {cmd_id}")

        # Notify Group using template
        if Config.TELEGRAM_GROUP_IDS:
            try:
                # Use cached data
                current_price_str = f"{current_price_val:.2f}" if current_price_val > 0 else "0.00"

                type_ar = "🟢 كول 🟢" if c_type.upper().startswith('C') else "🔴 بوت 🔴"
                template_vars = {
                    'symbol': symbol.upper(),
                    'strike': strike,
                    'expiration': expiration,
                    'type_ar': type_ar,
                    'target_price': target_price,
                    'price': current_price_str,
                    'entry_price': '0.00'
                }
                msg_text = get_template('wait_announce').format(**template_vars)
                
                for chat_id in Config.TELEGRAM_GROUP_IDS:
                    try:
                        await message.bot.send_message(
                            chat_id=chat_id,
                            text=msg_text,
                            parse_mode="Markdown"
                        )
                    except Exception as inner_e:
                        print(f"Failed to send notification to group {chat_id}: {inner_e}")

            except Exception as e:
                print(f"Failed to send notification to group: {e}")

    except (IndexError, ValueError) as e:
         print(f"Wait command error: {e}")
         await message.answer("مراجعة البيانات المدخلة. مثال: /wt SPX 6900 C 5.50")

@router.message(Command("enter", "en"))
async def cmd_enter(message: types.Message):
    # Check Admin
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية لاستخدام هذا الأمر.")
        return

    # Syntax: /en SPX 6900 C 4.20 [2026-01-20]
    # Similar logic to /wt: date is optional
    try:
        parts = message.text.split()[1:]
        if len(parts) < 4:
            await message.answer("طريقة الاستخدام: /en SPX 6900 C 4.20 [التاريخ]")
            return
        
        symbol = parts[0]
        strike = parts[1]
        c_type = parts[2]
        
        # Check remaining parts for date
        remaining = parts[3:]
        expiration = date.today().strftime("%Y-%m-%d")
        entry_str = None

        import re
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')

        for p in remaining:
            if date_pattern.match(p):
                expiration = p
            else:
                entry_str = p
        
        if entry_str is None:
             await message.answer("يرجى تحديد سعر الدخول.")
             return

        entry_price = float(entry_str)

        # Fetch current price for logging
        current_price_val = 0.0
        try:
             data = await api.get_market_data(symbol.upper(), c_type.upper(), expiration, strike)
             if data:
                 bid = data.get('bid', 0) or 0
                 ask = data.get('ask', 0) or 0
                 current_price_val = (bid + ask) / 2 if (bid and ask) else (data.get('last_price', 0) or 0)
        except Exception as e:
             print(f"Error fetching price for enter log: {e}")

        # Log to Postgres with entry market data
        pg_id = await asyncio.to_thread(
            pg_client.add_contract_log, 
            symbol.upper(), c_type.upper(), float(strike), expiration, current_price_val,
            None, data if 'data' in dir() else None  # auction_day=None, market_data=data
        )

        cmd_id = db.add_command(
            message.chat.id, symbol.upper(), float(strike), c_type.upper(), expiration, 
            entry_price=entry_price,
            notification_mode='enter',
            postgres_id=pg_id
        )
        
        type_ar = "🟢 كول 🟢" if c_type.upper().startswith('C') else "🔴 بوت 🔴"
        
        # Send detailed confirmation to Admin (Bot Chat) only
        await message.answer(
            text=(
                f"🚀 *تم تفعيل مراقبة الدخول* (رقم {cmd_id})\n\n"
                f"🔹 *الرمز:* {symbol.upper()}\n"
                f"📅 *التاريخ:* {expiration}\n"
                f"🎯 *السترايك:* {strike}\n"
                f"📊 *النوع:* {type_ar}\n\n"
                f"💰 *سعر الدخول المستهدف:* {entry_price}"
            ),
            parse_mode="Markdown"
        )

    except (IndexError, ValueError) as e:
         print(f"Enter command error: {e}")
         await message.answer("طريقة الاستخدام: /en SPX 6900 C 4.20 [التاريخ]")


# ====== FAVORITES COMMANDS ======

@router.message(Command("fav", "f"))
async def cmd_favorites(message: types.Message):
    """Show favorites list with buttons to select."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    favorites = load_favorites()
    
    if not favorites:
        await message.answer("📋 قائمة المفضلة فارغة.\nاستخدم `/fa SPX` لإضافة رمز.", parse_mode="Markdown")
        return
    
    # Create buttons grid (2 per row)
    buttons = []
    row = []
    for i, item in enumerate(favorites):
        sym = item['symbol']
        display = f"📊 {sym}"
        # No extra days info in button now
        row.append(InlineKeyboardButton(text=display, callback_data=f"fav_{sym}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Show list with numbers for deletion
    list_text = "⭐ *المفضلة:*\n\n"
    for i, item in enumerate(favorites, 1):
        sym = item['symbol']
        extra = ""
        if item.get('type') == 'company':
             extra = " (Company)"
        
        list_text += f"{i}. {sym}{extra}\n"
    list_text += "\n_اضغط على الرمز لعرض العقود_"
    
    await message.answer(list_text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("favadd", "fa"))
async def cmd_fav_add(message: types.Message):
    """Add a symbol to favorites with wizard."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("طريقة الاستخدام: /fa SPX")
            return
        
        symbol = parts[1].upper()
        favorites = load_favorites()
        
        for item in favorites:
            if item['symbol'] == symbol:
                await message.answer(f"⚠️ الرمز {symbol} موجود بالفعل في المفضلة.")
                return
        
        # Ask Type
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🏢 شركة", callback_data=f"favtype_company_{symbol}"),
                InlineKeyboardButton(text="📈 صندوق/مؤشر", callback_data=f"favtype_fund_{symbol}")
            ]
        ])
        
        await message.answer(f"هل الرمز {symbol} شركة أم صندوق؟", reply_markup=keyboard)
        
    except Exception as e:
        await message.answer(f"حدث خطأ: {e}")

@router.callback_query(F.data.startswith("favtype_"))
async def handle_fav_type(callback: types.CallbackQuery):
    """Handle favorite type selection."""
    try:
        _, type_str, symbol = callback.data.split("_")
        
        if type_str == "fund":
            # Save directly
            favorites = load_favorites()
            favorites.append({'symbol': symbol, 'type': 'fund'})
            save_favorites(favorites)
            await callback.message.edit_text(f"✅ تمت إضافة {symbol} إلى المفضلة (صندوق).")
        
        elif type_str == "company":
             # Save directly without asking for days (determined at runtime now)
             favorites = load_favorites()
             favorites.append({'symbol': symbol, 'type': 'company'})
             save_favorites(favorites)
             await callback.message.edit_text(f"✅ تمت إضافة {symbol} إلى المفضلة (شركة).")

    except Exception as e:
        await callback.message.edit_text(f"حدث خطأ: {e}")

# Helper to show expiration selection
async def prompt_fav_expirations(callback_or_message, symbol):
    # Determine if it's a callback or message to decide how to reply
    is_callback = isinstance(callback_or_message, types.CallbackQuery)
    message = callback_or_message.message if is_callback else callback_or_message
    
    if is_callback:
        await callback_or_message.answer("⌛ جلب التواريخ...")
    else:
        await message.answer("⌛ جلب التواريخ...")

    # Fetch expirations
    dates = await api.get_expirations(symbol)
    if not dates:
         if is_callback: await message.answer(f"❌ لا توجد تواريخ لـ {symbol}")
         else: await message.answer(f"❌ لا توجد تواريخ لـ {symbol}")
         return

    # Filter valid
    valid_dates = [d for d in dates if d.get('days') is not None]
    valid_dates.sort(key=lambda x: int(x['days']))
    valid_dates = valid_dates[:15]
    
    buttons = []
    row = []
    
    for d in valid_dates:
        days = d['days']
        date_str = d.get('date', 'Unknown')
        # callback: pch_SYMBOL_DAYS (p for pick chain)
        # Show days + date (e.g. 12D (2026-02-06))
        row.append(InlineKeyboardButton(text=f"{days}D ({date_str})", callback_data=f"pch_{symbol}_{days}"))
        if len(row) == 2:
             buttons.append(row)
             row = []
    if row:
        buttons.append(row)
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    msg_text = f"اختر المدة الزمنية لـ {symbol}:"
    if is_callback:
        # Edit text only if message is editable (it is usually)
        try:
             await message.edit_text(msg_text, reply_markup=kb)
        except:
             await message.answer(msg_text, reply_markup=kb)
    else:
        await message.answer(msg_text, reply_markup=kb)


@router.callback_query(F.data.startswith("pch_"))
async def handle_pick_chain_days(callback: types.CallbackQuery):
    """Handle expiration selection -> Show chain."""
    try:
        _, symbol, days = callback.data.split("_")
        await show_chain_view(callback, symbol, expiry_days=int(days))
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)

async def show_chain_view(callback, symbol, expiry_days=None):
    """Refactored logic to show option chain table."""
    try:
        msg_extra = ""
        if expiry_days:
             msg_extra = f"(مدة {expiry_days} يوم)"

        await callback.answer(f"⌛ جاري جلب بيانات {symbol} {msg_extra}...")
        
        # Create a fake message object to reuse gso logic
        # We'll call the API directly instead
        chain_result = await api.get_option_chain(symbol, expiry_days_target=expiry_days)
        
        if not chain_result:
            await callback.message.answer(f"❌ لم يتم العثور على بيانات لـ {symbol}")
            return
        
        chain_data = chain_result['contracts']
        entry_call = chain_result['entry_call']
        entry_put = chain_result['entry_put']
        
        # Clear previous list and assign new simple IDs
        global last_gso_contracts
        last_gso_contracts = {}
        simple_id = 1
        for c in chain_data:
            c['simple_id'] = simple_id
            last_gso_contracts[simple_id] = c
            simple_id += 1

        # Get all calls and puts first
        all_calls = [c for c in chain_data if c['type'] == 'C']
        all_puts = [c for c in chain_data if c['type'] == 'P']
        
        # Apply filter only if list has more than 10 items
        if len(all_calls) > 10:
            # Filter: Ask between 2 and 10
            filtered_calls = [c for c in all_calls if 2 <= c.get('ask', 0) <= 10]
            # Fallback: if filter returns empty, show all
            calls = filtered_calls if filtered_calls else all_calls
        else:
            calls = all_calls
            
        if len(all_puts) > 10:
            # Filter: Ask between 2 and 10
            filtered_puts = [c for c in all_puts if 2 <= c.get('ask', 0) <= 10]
            # Fallback: if filter returns empty, show all
            puts = filtered_puts if filtered_puts else all_puts
        else:
            puts = all_puts
        
        calls.sort(key=lambda x: x['strike'])
        puts.sort(key=lambda x: x['strike'])
        
        # Limit to 10 rows: first 10 calls, last 10 puts
        calls = calls[:10]
        puts = puts[-10:]
        
        call_table = "عقود الكول:\n"
        call_table += "ID   Strike    Bid    Ask    Last   Vol\n"
        call_table += "────────────────────────────────────\n"
        for c in calls:
             call_table += f"{c['simple_id']:<3}  {c['strike']:<8.0f} {c['bid']:<6.2f} {c['ask']:<6.2f} {c['last']:<6.2f} {c['volume']:,}\n"

        put_table = "عقود البوت:\n"
        put_table += "ID   Strike    Bid    Ask    Last   Vol\n"
        put_table += "────────────────────────────────────\n"
        for c in puts:
             put_table += f"{c['simple_id']:<3}  {c['strike']:<8.0f} {c['bid']:<6.2f} {c['ask']:<6.2f} {c['last']:<6.2f} {c['volume']:,}\n"

        entry_msg = f"🟢 دخول الكول : {entry_call:.2f}\n🔴 دخول البوت : {entry_put:.2f}"
        summary_msg = f"📊 *{symbol}* {msg_extra} - استخدم `/x <ID>` للمراقبة"
        msg_calls = f"```{call_table}```"
        msg_puts = f"```{put_table}```"
        
        # If msg is editable (from expiration selection), we might want to send NEW messages because tables are large
        # But callback usually allows answering.
        # We will answer normally.
        await callback.message.answer(entry_msg, parse_mode="Markdown")
        await callback.message.answer(summary_msg + "\n" + msg_calls + "\n" + msg_puts, parse_mode="Markdown")
        
    except Exception as e:
        await callback.answer(f"حدث خطأ: {e}", show_alert=True)

@router.message(Command("favdel", "fd"))
async def cmd_fav_delete(message: types.Message):
    """Delete a symbol from favorites by number."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("طريقة الاستخدام: /fd 1\n(الرقم من قائمة المفضلة)")
            return
        
        index = int(parts[1]) - 1
        favorites = load_favorites()
        
        if index < 0 or index >= len(favorites):
            await message.answer(f"❌ رقم غير صحيح. القائمة تحتوي على {len(favorites)} عناصر.")
            return
        
        removed = favorites.pop(index)
        save_favorites(favorites)
        
        sym = removed['symbol']
        await message.answer(f"🗑 تم حذف {sym} من المفضلة.")
        
    except ValueError:
        await message.answer("طريقة الاستخدام: /fd 1")
    except Exception as e:
        await message.answer(f"حدث خطأ: {e}")


# ====== TEMPLATE MANAGEMENT COMMANDS ======

@router.message(Command("templates", "template", "tmp"))
async def cmd_templates(message: types.Message):
    """Show all message templates."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    templates = load_templates()
    
    template_names = {
        "select_first": "توصية المراقبة الجديدة",
        "wait_announce": "إعلان الانتظار",
        "wait_first": "الوصول لسعر الانتظار",
        "enter_first": "توصية الدخول",
        "update": "تحديث السعر"
    }
    
    text = "📝 *قوالب الرسائل:*\n\n"
    text += "استخدم `/tset <رقم> <النص>` للتعديل\n\n"
    
    for i, (key, name) in enumerate(template_names.items(), 1):
        current = templates.get(key, "")
        safe_current = current.replace("`", "'")
        preview = safe_current[:50] + "..." if len(safe_current) > 50 else safe_current
        text += f"{i}. *{name}*\n`{key}`\n`{preview}`\n\n"
    
    text += "\n📌 *المتغيرات المتاحة:*\n"
    text += "`{symbol}` - الرمز\n"
    text += "`{strike}` - السترايك\n"
    text += "`{expiration}` - التاريخ\n"
    text += "`{type_ar}` - النوع\n"
    text += "`{price}` - السعر الحالي\n"
    text += "`{target_price}` - سعر الانتظار\n"
    text += "`{entry_price}` - سعر الدخول"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("tset"))
async def cmd_template_set(message: types.Message):
    """Set a message template."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    try:
        # Parse: /tset <key_or_number> <new_text>
        text = message.text
        parts = text.split(maxsplit=2)
        
        if len(parts) < 3:
            await message.answer(
                "طريقة الاستخدام:\n"
                "`/tset <رقم أو اسم> <النص الجديد>`\n\n"
                "مثال:\n"
                "`/tset 1 📢 توصية جديدة...`\n"
                "`/tset update 🔔 تحديث...`",
                parse_mode="Markdown"
            )
            return
        
        key_or_num = parts[1]
        new_text = parts[2]
        
        # Map numbers to keys
        key_map = {
            "1": "select_first",
            "2": "wait_announce",
            "3": "wait_first",
            "4": "enter_first",
            "5": "update"
        }
        
        # Resolve key
        if key_or_num in key_map:
            key = key_map[key_or_num]
        elif key_or_num in DEFAULT_TEMPLATES:
            key = key_or_num
        else:
            await message.answer(f"❌ مفتاح غير معروف: {key_or_num}\nاستخدم `/tmp` لعرض المفاتيح.", parse_mode="Markdown")
            return
        
        templates = load_templates()
        templates[key] = new_text
        save_templates(templates)
        
        await message.answer(
            f"✅ تم تحديث القالب `{key}` بنجاح.\n\n"
            f"📝 *المحتوى الجديد:*\n"
            f"`{new_text}`",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.answer(f"حدث خطأ: {e}")


@router.message(Command("treset"))
async def cmd_template_reset(message: types.Message):
    """Reset templates to defaults."""
    if Config.ADMIN_USER_IDS and str(message.from_user.id) not in Config.ADMIN_USER_IDS:
        await message.reply("⛔ ليس لديك صلاحية.")
        return
    
    try:
        parts = message.text.split()
        
        if len(parts) < 2:
            # Reset all
            save_templates(DEFAULT_TEMPLATES)
            await message.answer("✅ تم إعادة جميع القوالب للإعدادات الافتراضية.")
        else:
            key_or_num = parts[1]
            key_map = {
                "1": "select_first",
                "2": "wait_announce",
                "3": "wait_first",
                "4": "enter_first",
                "5": "update"
            }
            
            if key_or_num in key_map:
                key = key_map[key_or_num]
            elif key_or_num in DEFAULT_TEMPLATES:
                key = key_or_num
            else:
                await message.answer(f"❌ مفتاح غير معروف: {key_or_num}")
                return
            
            templates = load_templates()
            templates[key] = DEFAULT_TEMPLATES[key]
            save_templates(templates)
            await message.answer(f"✅ تم إعادة القالب `{key}` للإعدادات الافتراضية.", parse_mode="Markdown")
            
    except Exception as e:
        await message.answer(f"حدث خطأ: {e}")