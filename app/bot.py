import logging
import asyncio
import io
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from app.config import get_settings
from app.db import db
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ReportLab & Arabic Support
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import arabic_reshaper
from bidi.algorithm import get_display

# Register Font logic (Try standard paths)
try:
    pdfmetrics.registerFont(TTFont('Arial', 'C:\\Windows\\Fonts\\arial.ttf'))
    FONT_NAME = 'Arial'
except:
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf')) # Setup for relative path
        FONT_NAME = 'Arial'
    except:
        FONT_NAME = 'Helvetica' # Fallback (No Arabic)

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Bot and Dispatcher
bot = Bot(token=settings.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Keyboards
contact_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📱 مشاركة رقم الهاتف", request_contact=True)]
], resize_keyboard=True, one_time_keyboard=True)

# Empty keyboard to remove reply keyboard after contact
remove_kb = types.ReplyKeyboardRemove()

def get_main_menu():
    """Generate main menu inline keyboard."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 تقارير الصفقات 📊", callback_data="menu_reports")],
        [
            InlineKeyboardButton(text="🟢 اشتراك جديد", callback_data="menu_new_sub"),
            InlineKeyboardButton(text="🔄 تجديد اشتراك", callback_data="menu_renew_sub")
        ],
        [InlineKeyboardButton(text="🟢 حالة الاشتراك", callback_data="menu_status")],
        [InlineKeyboardButton(text="🎁 تجربة مجانية 3 أيام", callback_data="menu_free_trial")]
    ])

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Check if user exists
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_user_id = $1", user_id)
    
    if not user:
        logger.info(f"New user detected: {user_id} ({username}). Saving to DB...")
        # Initial insert without phone
        await db.execute(
            "INSERT INTO users (telegram_user_id, telegram_username, telegram_full_name) VALUES ($1, $2, $3) ON CONFLICT (telegram_user_id) DO NOTHING",
            user_id, username, full_name
        )
        logger.info(f"User {user_id} saved successfully.")
        await message.answer(
            "حياك الله! قبل عرض القائمة، الرجاء إرسال رقمك:",
            reply_markup=contact_kb
        )
    elif not user['phone_number']:
        logger.info(f"User {user_id} exists but has no phone.")
        await message.answer(
            "حياك الله! قبل عرض القائمة، الرجاء إرسال رقمك:",
            reply_markup=contact_kb
        )
    else:
        logger.info(f"User {user_id} fully registered.")
        await message.answer(
            "اختر من القائمة:",
            reply_markup=get_main_menu()
        )

# https://salla.sa/investly11/ZqXYQvB
@dp.message(F.contact)
async def handle_contact(message: types.Message):
    contact = message.contact
    user_id = message.from_user.id
    
    if contact.user_id != user_id:
        await message.answer("يرجى مشاركة رقم هاتفك الخاص.")
        return

    phone = contact.phone_number
    # Basic E.164 normalization (remove +, spaces)
    if phone.startswith('+'):
        phone = phone[1:]
    
    # Store phone
    await db.execute(
        "UPDATE users SET phone_number = $1, updated_at = NOW() WHERE telegram_user_id = $2",
        phone, user_id
    )
    
    # First response: confirm phone saved (remove keyboard)
    await message.answer("✅ تم حفظ رقم جوالك", reply_markup=remove_kb)
    
    # Check for pending subscriptions
    pending = await db.fetch("SELECT * FROM pending_subscriptions WHERE phone_number = $1 AND status = 'pending'", phone)
    
    if pending:
        from app.services.subscription_manager import SubscriptionManager
        count = 0
        for p in pending:
            # Create subscription
            # Use Pending ID or Salla ID if available
            order_id = p['salla_order_id'] or f"MANUAL_{p['id']}"
            days = p['days'] or 30
            
            try:
                await SubscriptionManager.create_subscription(user_id, order_id, days)
                
                # Mark as claimed
                await db.execute("UPDATE pending_subscriptions SET status = 'claimed' WHERE id = $1", p['id'])
                count += 1
            except Exception as e:
                logger.error(f"Error activating pending sub {p['id']}: {e}")
        
        if count > 0:
            await message.answer(
                f"🎉 تم العثور على {count} اشتراك(ات) معلق(ة) وتفعيلها!"
            )

    # Show main menu
    await message.answer(
        "اختر من القائمة:",
        reply_markup=get_main_menu()
    )

def reshape_text(text):
    if FONT_NAME == 'Helvetica': return text # No Arabic support
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

async def generate_pdf_report(month_name: str, contracts: list) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Calculate Totals
    total_profit = sum([(c['profit'] or 0) for c in contracts])
    total_loss = sum([(c['loss'] or 0) for c in contracts])
    total_net = sum([(c['net_profit'] or 0) for c in contracts])

    # --- Summary Table ---
    # Top position for table
    table_y_top = height - 50
    table_width = 500
    table_x = (width - table_width) / 2
    row_height = 25
    
    # Row 1: Main Title (Gray)
    c.setFillColor(colors.Color(0.8, 0.8, 0.8)) # Light Grey
    c.rect(table_x, table_y_top - row_height, table_width, row_height, fill=1, stroke=1)
    
    c.setFillColor(colors.black)
    c.setFont(FONT_NAME, 14)
    # Title Text
    title_text = reshape_text(f"إجمالي أرباح شهر {month_name}")
    c.drawCentredString(width / 2, table_y_top - row_height + 8, title_text)
    
    # Row 2: Headers (Green/Red/Yellow)
    headers_y = table_y_top - (row_height * 2)
    col_width = table_width / 3
    
    # Col 1 (Right) - Gross Profit - Green
    c.setFillColor(colors.Color(0.6, 1, 0.6)) 
    c.rect(table_x + 2*col_width, headers_y, col_width, row_height, fill=1, stroke=1)
    
    # Col 2 (Middle) - Loss - Red
    c.setFillColor(colors.Color(1, 0.6, 0.6)) 
    c.rect(table_x + col_width, headers_y, col_width, row_height, fill=1, stroke=1)
    
    # Col 3 (Left) - Net - Yellow
    c.setFillColor(colors.Color(1, 1, 0.6)) 
    c.rect(table_x, headers_y, col_width, row_height, fill=1, stroke=1)
    
    # Header Texts
    c.setFillColor(colors.black)
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(table_x + 2.5*col_width, headers_y + 8, reshape_text("إجمالي الربح بالعقد"))
    c.drawCentredString(table_x + 1.5*col_width, headers_y + 8, reshape_text("إجمالي الخسارة"))
    c.drawCentredString(table_x + 0.5*col_width, headers_y + 8, reshape_text("صافي الربح"))

    # Row 3: Values (White)
    values_y = headers_y - row_height
    c.setFillColor(colors.white)
    
    c.rect(table_x + 2*col_width, values_y, col_width, row_height, fill=1, stroke=1)
    c.rect(table_x + col_width, values_y, col_width, row_height, fill=1, stroke=1)
    c.rect(table_x, values_y, col_width, row_height, fill=1, stroke=1)
    
    # Values Text
    c.setFillColor(colors.black)
    c.setFont(FONT_NAME, 12)
    c.drawCentredString(table_x + 2.5*col_width, values_y + 8, str(total_profit))
    c.drawCentredString(table_x + 1.5*col_width, values_y + 8, str(total_loss))
    c.drawCentredString(table_x + 0.5*col_width, values_y + 8, str(total_net))
    
    # --- End Summary Table ---
    
    # Start of detailed list
    y = values_y - 40 
    
    # List Headers
    headers = ["التاريخ", "سترايك", "سعر العقد", "الربح", "الخسارة", "صافي العقد"]
    # Adjust X positions to match A4/Used width layout (Right aligned)
    # Total width ~600. Margins ~50.
    x_positions = [550, 450, 350, 270, 190, 100]
    
    c.setFont(FONT_NAME, 12)
    for i, h in enumerate(headers):
        text = reshape_text(h)
        c.drawRightString(x_positions[i], y, text)
        
    y -= 10
    c.line(50, y, 560, y)
    y -= 25
    
    # Data Info
    c.setFont(FONT_NAME, 10)
    for contract in contracts:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont(FONT_NAME, 10)
            
        contract_date = contract['contract_date'].strftime('%Y-%m-%d')
        strike = str(contract['strike'])
        price = str(contract['contract_price'])
        profit = contract['profit'] or 0
        loss = contract['loss'] or 0
        net = contract['net_profit'] or 0
        
        c.setFillColor(colors.black)
        c.drawRightString(x_positions[0], y, contract_date)
        c.drawRightString(x_positions[1], y, strike)
        c.drawRightString(x_positions[2], y, price)
        
        # Profit (Green if > 0)
        col = colors.green if profit > 0 else colors.black
        c.setFillColor(col)
        c.drawRightString(x_positions[3], y, str(profit))
        
        # Loss (Red if > 0)
        col = colors.red if loss > 0 else colors.black
        c.setFillColor(col)
        c.drawRightString(x_positions[4], y, str(loss))
            
        # Net
        c.setFillColor(colors.green if net >= 0 else colors.red)
        c.drawRightString(x_positions[5], y, str(net))
        
        c.setFillColor(colors.black)
        c.line(50, y-5, 560, y-5)
        y -= 20
        
    c.save()
    buffer.seek(0)
    return buffer.read()

# === CALLBACK HANDLERS FOR INLINE MENU ===

@dp.callback_query(F.data == "menu_reports")
async def cb_reports(callback: types.CallbackQuery):
    """Handle reports button callback."""
    await callback.answer()
    
    # Fetch contracts last 3 months
    contracts = await db.fetch("""
        SELECT * FROM option_contracts 
        WHERE contract_date >= NOW() - INTERVAL '3 months' 
        ORDER BY contract_date DESC
    """)
    
    if not contracts:
        await callback.message.answer("❌ لا توجد صفقات مسجلة في الأشهر الثلاثة الماضية.")
        return
        
    # Group by Month
    grouped = {}
    for c in contracts:
        month_key = c['contract_date'].strftime('%Y-%m')
        if month_key not in grouped:
            grouped[month_key] = []
        grouped[month_key].append(c)
        
    await callback.message.answer("جاري إنشاء التقارير... ⏳")
    
    for month, data in grouped.items():
        pdf_bytes = await generate_pdf_report(month, data)
        file = BufferedInputFile(pdf_bytes, filename=f"report_{month}.pdf")
        await callback.message.answer_document(file, caption=f"تقرير شهر {month}")
    
    # Show menu again
    await callback.message.answer("هل تحتاج شيء آخر؟", reply_markup=get_main_menu())

@dp.callback_query(F.data == "menu_new_sub")
async def cb_new_subscription(callback: types.CallbackQuery):
    """Handle new subscription button callback."""
    await callback.answer()
    await callback.message.answer(
        "للاشتراك في خدماتنا، يرجى زيارة متجرنا:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛒 زيارة المتجر", url="https://salla.sa/investly11")],
            [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
        ])
    )

@dp.callback_query(F.data == "menu_renew_sub")
async def cb_renew_subscription(callback: types.CallbackQuery):
    """Handle renew subscription button callback."""
    await callback.answer()
    await callback.message.answer(
        "لتجديد اشتراكك، يمكنك زيارة المتجر:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 تجديد الاشتراك", url="https://salla.sa/investly11")],
            [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
        ])
    )

@dp.callback_query(F.data == "menu_status")
async def cb_subscription_status(callback: types.CallbackQuery):
    """Handle subscription status button callback."""
    await callback.answer()
    user_id = callback.from_user.id
    
    query = "SELECT * FROM subscriptions WHERE telegram_user_id = $1 AND status = 'active' AND end_date > NOW() ORDER BY end_date DESC LIMIT 1"
    sub = await db.fetchrow(query, user_id)
    
    if sub:
        end_date = sub['end_date']
        now = datetime.now(end_date.tzinfo)
        remaining = (end_date - now).days
        
        msg = f"✅ لديك اشتراك فعال.\n"
        msg += f"📅 ينتهي في: {end_date.strftime('%Y-%m-%d')}\n"
        msg += f"⏳ الأيام المتبقية: {max(0, remaining)} يوم"
    else:
        msg = "❌ لا توجد اشتراكات نشطة حالياً."
        
    await callback.message.answer(
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="� رجوع", callback_data="menu_back")]
        ])
    )

@dp.callback_query(F.data == "menu_renew_link")
async def cb_renew_invite_link(callback: types.CallbackQuery):
    """Handle renew invite link button callback."""
    await callback.answer()
    user_id = callback.from_user.id
    
    # Check subscription first
    query = "SELECT * FROM subscriptions WHERE telegram_user_id = $1 AND status = 'active' AND end_date > NOW() LIMIT 1"
    sub = await db.fetchrow(query, user_id)
    
    if not sub:
        await callback.message.answer(
            "⚠️ لا يوجد اشتراك نشط لتجديد الرابط.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )
        return
    
    # Check if user is already in the channel
    try:
        member = await bot.get_chat_member(settings.CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            await callback.message.answer(
                "✅ أنت بالفعل عضو في القناة!",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
                ])
            )
            return
    except Exception as e:
        # User not in channel or error - continue to give link
        pass
    
    # Check if user already has an unused invite link stored
    if sub.get('invite_link'):
        await callback.message.answer(
            f"🔗 رابط الدخول الخاص بك:\n{sub['invite_link']}\n\n⚠️ هذا الرابط صالح لمرة واحدة فقط.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )
        return
    
    # Create new single-use invite link
    try:
        chat_invite: types.ChatInviteLink = await bot.create_chat_invite_link(
             chat_id=settings.CHANNEL_ID, 
             member_limit=1,
             name=f"Sub_{sub['id']}_{user_id}"
        )
        
        # Store the link in the subscription
        await db.execute(
            "UPDATE subscriptions SET invite_link = $1 WHERE id = $2",
            chat_invite.invite_link, sub['id']
        )
        
        await callback.message.answer(
            f"🔗 إليك رابط الدخول الخاص بك:\n{chat_invite.invite_link}\n\n⚠️ هذا الرابط صالح لمرة واحدة فقط.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to generate link: {e}")
        await callback.message.answer(
            "⚠️ حدث خطأ أثناء إنشاء الرابط.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )

@dp.callback_query(F.data == "menu_free_trial")
async def cb_free_trial(callback: types.CallbackQuery):
    """Handle free trial button callback."""
    await callback.answer()
    user_id = callback.from_user.id
    
    # Check if user already had a trial
    existing_trial = await db.fetchrow(
        "SELECT * FROM subscriptions WHERE telegram_user_id = $1 AND salla_order_id LIKE 'TRIAL_%'",
        user_id
    )
    
    if existing_trial:
        await callback.message.answer(
            "⚠️ لقد استخدمت التجربة المجانية من قبل.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🟢 اشتراك جديد", callback_data="menu_new_sub")],
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )
        return
    
    # Create 3-day trial subscription
    try:
        from app.services.subscription_manager import SubscriptionManager
        import secrets
        trial_order_id = f"TRIAL_{secrets.token_hex(4).upper()}"
        await SubscriptionManager.create_subscription(user_id, trial_order_id, 3)
        
        await callback.message.answer(
            "🎉 تم تفعيل تجربتك المجانية لمدة 3 أيام!\n\nاستمتع بجميع المميزات.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔗 الحصول على رابط الدخول", callback_data="menu_renew_link")],
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to create trial: {e}")
        await callback.message.answer(
            "⚠️ حدث خطأ أثناء تفعيل التجربة المجانية.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_back")]
            ])
        )

@dp.callback_query(F.data == "menu_back")
async def cb_back_to_menu(callback: types.CallbackQuery):
    """Handle back button - return to main menu."""
    await callback.answer()
    await callback.message.answer("اختر من القائمة:", reply_markup=get_main_menu())

@dp.chat_join_request()
async def handle_join_request(update: types.ChatJoinRequest):
    """
    Accept join requests automatically if user has active subscription.
    Channel must be set to 'Approve Join Requests'.
    """
    user_id = update.from_user.id
    chat_id = update.chat.id
    
    # Check if this is our target channel (optional, strictly speaking)
    # if str(chat_id) != settings.CHANNEL_ID: return
    
    query = "SELECT * FROM subscriptions WHERE telegram_user_id = $1 AND status = 'active' AND end_date > NOW()"
    sub = await db.fetchrow(query, user_id)
    
    if sub:
        await update.approve()
        try:
            await bot.send_message(user_id, "تم قبول طلب انضمامك للقناة تلقائياً ✅\nنتمنى لك تجربة موفقة.")
        except:
            pass
    # Else: Ignore request, or maybe send message saying "Subscription needed"

async def send_notification(user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.error(f"Failed to send message to {user_id}: {e}")

async def start_bot():
    # Set menu button
    await bot.set_my_commands([
        types.BotCommand(command="start", description="القائمة الرئيسية")
    ])
    logger.info("Starting bot polling...")
    await dp.start_polling(bot, handle_signals=False)
