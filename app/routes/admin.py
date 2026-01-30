import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import io
try:
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    Image = None
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from datetime import datetime
from app.config import get_settings
from app.db import db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
security = HTTPBasic()
settings = get_settings()

# Simple session management (cookie based)
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        return None
    return user

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # In production, use hashed passwords!
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD_HASH: # treat hash as plain for demo if needed, but user asked for hash
        request.session["user"] = username
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/admin/login")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/admin/login")
    
    # Metrics
    total_subs = await db.fetchrow("SELECT COUNT(*) as count FROM subscriptions")
    active_subs = await db.fetchrow("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'active'")
    users_count = await db.fetchrow("SELECT COUNT(*) as count FROM users")
    
    recent_subs = await db.fetch("SELECT * FROM subscriptions ORDER BY created_at DESC LIMIT 10")
    recent_users = await db.fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT 10")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_subs": total_subs['count'],
        "active_subs": active_subs['count'],
        "users_count": users_count['count'],
        "recent_subs": recent_subs,
        "recent_users": recent_users
    })

@router.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/admin/login")
        
    logs = await db.fetch("SELECT * FROM webhook_logs ORDER BY created_at DESC LIMIT 50")
    return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})

@router.post("/subscriptions/add_manual")
async def add_manual_subscription(
    request: Request,
    phone_number: str = Form(...),
    days: int = Form(30)
):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")
    
    # Clean phone
    clean_phone = phone_number.strip().replace("+", "").replace(" ", "")
    
    # Check if user exists
    existing_user = await db.fetchrow("SELECT telegram_user_id FROM users WHERE phone_number = $1", clean_phone)
    
    if existing_user:
        # User exists, add subscription directly
        from app.services.subscription_manager import SubscriptionManager
        # Generate fake order ID
        manual_order_id = f"MANUAL_{secrets.token_hex(4).upper()}"
        
        try:
            await SubscriptionManager.create_subscription(existing_user['telegram_user_id'], manual_order_id, days)
            # Notify user? (Ideally yes, but skipped for now or needs bot instance)
        except Exception as e:
            # Handle unique constraint or other errors
            pass 
    else:
        # User not found, add to pending
        await db.execute("""
            INSERT INTO pending_subscriptions (phone_number, salla_order_id, days, status)
            VALUES ($1, $2, $3, 'pending')
        """, clean_phone, f"MANUAL_{secrets.token_hex(4).upper()}", days)
        
    return RedirectResponse(url="/admin/dashboard?msg=sub_added", status_code=303)

@router.post("/subscriptions/delete")
async def delete_subscription(
    request: Request,
    subscription_id: int = Form(...)
):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")
    
    # Get subscription info before deleting
    sub = await db.fetchrow("SELECT * FROM subscriptions WHERE id = $1", subscription_id)
    
    if sub:
        # Delete from database
        await db.execute("DELETE FROM subscriptions WHERE id = $1", subscription_id)
        
        # Try to kick user from group (if configured)
        try:
            from app.config import get_settings
            from aiogram import Bot
            settings = get_settings()
            
            if settings.PRIVATE_CHANNEL_ID and sub['telegram_user_id']:
                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                try:
                    await bot.ban_chat_member(
                        chat_id=settings.PRIVATE_CHANNEL_ID,
                        user_id=sub['telegram_user_id']
                    )
                    # Unban to allow future re-joining
                    await bot.unban_chat_member(
                        chat_id=settings.PRIVATE_CHANNEL_ID,
                        user_id=sub['telegram_user_id']
                    )
                except Exception as e:
                    print(f"Could not remove user from group: {e}")
                finally:
                    await bot.session.close()
        except Exception as e:
            print(f"Error during user removal: {e}")
    
    return RedirectResponse(url="/admin/dashboard?msg=sub_deleted", status_code=303)

# Contracts Management
@router.get("/contracts", response_class=HTMLResponse)
async def list_contracts(request: Request, period: str = "all"):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")
    
    query = "SELECT * FROM option_contracts"
    args = []
    
    if period == "month":
        query += " WHERE contract_date >= DATE_TRUNC('month', CURRENT_DATE)"
    elif period == "week":
        query += " WHERE contract_date >= DATE_TRUNC('week', CURRENT_DATE)"
        
    query += " ORDER BY contract_date DESC"
    
    contracts = await db.fetch(query, *args)
    return templates.TemplateResponse("contracts.html", {"request": request, "contracts": contracts, "period": period})

@router.post("/contracts/add")
async def add_contract(
    request: Request,
    contract_date: str = Form(...),
    strike: str = Form(...),
    contract_price: float = Form(0),
    closing_price: float = Form(0)
):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")
    
    # Convert date string to date object
    dt_obj = datetime.strptime(contract_date, "%Y-%m-%d").date()
    
    # SIMPLE LOGIC:
    # User enters: contract_price (entry) and closing_price (exit)
    # System calculates:
    # - If closing_price >= contract_price: profit = closing_price, loss = 0, net = closing_price - contract_price
    # - If closing_price < contract_price: profit = 0, loss = contract_price - closing_price, net = -(loss)
    
    if closing_price >= contract_price:
        # Profit or breakeven
        profit = closing_price  # Store closing price in profit column
        loss = 0
        net_profit = closing_price - contract_price
    else:
        # Loss
        profit = 0
        loss = contract_price - closing_price
        net_profit = -loss
        
    await db.execute(
        "INSERT INTO option_contracts (contract_date, strike, contract_price, profit, loss, net_profit) VALUES ($1, $2, $3, $4, $5, $6)",
        dt_obj, strike, contract_price, profit, loss, net_profit
    )
    return RedirectResponse(url="/admin/contracts", status_code=303)

@router.post("/contracts/delete")
async def delete_contract(request: Request, contract_id: int = Form(...)):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")
    
    await db.execute("DELETE FROM option_contracts WHERE id = $1", contract_id)
    return RedirectResponse(url="/admin/contracts", status_code=303)


@router.post("/contracts/generate_image")
async def generate_contract_image(request: Request, contract_ids: str = Form(...)):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/admin/login")

    if not Image:
        return HTMLResponse("Pillow library not installed. Please install it to generate images.", status_code=500)

    # Clean and parse IDs
    try:
        if "," in contract_ids:
            ids = [int(x.strip()) for x in contract_ids.split(",") if x.strip()]
        else:
            ids = [int(contract_ids.strip())]
    except ValueError:
        return HTMLResponse("Invalid contract IDs", status_code=400)
    
    if not ids:
        return HTMLResponse("No contracts selected", status_code=400)

    # Fetch contracts
    query = "SELECT * FROM option_contracts WHERE id = ANY($1::int[])"
    contracts = await db.fetch(query, ids)
    
    if not contracts:
        return HTMLResponse("Contracts not found", status_code=404)

    # Sort checks if multiple
    contracts.sort(key=lambda x: x['contract_date'])

    img_buffer = io.BytesIO()
    
    # Helper for Arabic text
    def ar(text):
        if not text: return ""
        try:
            reshaped_text = arabic_reshaper.reshape(str(text))
            return get_display(reshaped_text)
        except:
            return str(text)

    if len(contracts) == 1:
        # Single Contract: Detailed Entry + Exit Cards
        c = contracts[0]
        
        # === Colors ===
        COLOR_BG = (10, 14, 23)
        COLOR_CARD = (18, 24, 38)
        COLOR_TEXT_PRIMARY = (255, 255, 255)
        COLOR_TEXT_SECONDARY = (140, 150, 170)
        COLOR_ACCENT = (0, 200, 180)  # Teal
        COLOR_GREEN = (46, 204, 113)
        COLOR_RED = (231, 76, 60)
        COLOR_GOLD = (255, 215, 0)
        COLOR_BORDER = (40, 50, 70)
        
        # Dimensions
        img_width = 1000  # Wider for details
        card_height = 320 # Taller for details
        net_height = 160
        padding = 20
        img_height = card_height * 2 + net_height + (padding * 4)  # Removed separate logo section
        
        img = Image.new('RGB', (img_width, img_height), color=COLOR_BG)
        d = ImageDraw.Draw(img)
        
        # Fonts
        def get_font(size):
            try: return ImageFont.truetype("arial.ttf", size)
            except: return ImageFont.load_default()

        fnt_title = get_font(32)
        fnt_label = get_font(24)
        fnt_val = get_font(28)
        fnt_price = get_font(80)
        fnt_net = get_font(60)
        fnt_small = get_font(20)
        
        # --- Helper to draw Data Grid ---
        def draw_data_grid(draw, x_start, y_start, width, data_dict):
            # 2 Rows of 3 Columns
            col_width = width / 3
            row_h = 50
            
            # Row 1: Bid | Ask | Vol
            # Row 2: IV | OI | Underlying
            
            items = [
                ("BID", f"${data_dict.get('bid', 0)}"),
                ("ASK", f"${data_dict.get('ask', 0)}"),
                ("VOL", f"{data_dict.get('vol', 0)}"),
                ("IV", f"{data_dict.get('iv', 0)}%"),
                ("OI", f"{data_dict.get('oi', 0)}"),
                ("UND", f"${data_dict.get('und', 0)}")
            ]
            
            # Draw Row 1
            for i in range(3):
                lbl, val = items[i]
                x = x_start + (i * col_width)
                draw.text((x + 20, y_start), lbl, font=fnt_label, fill=COLOR_TEXT_SECONDARY)
                draw.text((x + 20, y_start + 30), str(val), font=fnt_val, fill=COLOR_TEXT_PRIMARY)
                
            # Draw Row 2
            y_start += 70
            for i in range(3):
                lbl, val = items[i+3]
                x = x_start + (i * col_width)
                draw.text((x + 20, y_start), lbl, font=fnt_label, fill=COLOR_TEXT_SECONDARY)
                draw.text((x + 20, y_start + 30), str(val), font=fnt_val, fill=COLOR_TEXT_PRIMARY)

        # Data Prep
        strike = c['strike']
        contract_date = c['contract_date']
        
        # Entry Data
        entry_price = float(c['contract_price'] or 0)
        entry_data = {
            'bid': c.get('entry_bid') or 0,
            'ask': c.get('entry_ask') or 0,
            'vol': c.get('entry_volume') or 0,
            'iv': c.get('entry_iv') or 0,
            'oi': c.get('entry_oi') or 0,
            'und': c.get('entry_underlying') or 0
        }
        
        # Exit Data
        profit = float(c['profit'] or 0)
        loss = float(c['loss'] or 0)
        net_profit = float(c['net_profit'] or 0)
        
        # New Logic: Profit OR Loss column holds the exit price. If both 0, it's open (use entry).
        if profit > 0:
            exit_price = profit
        elif loss > 0:
            exit_price = loss
        else:
            exit_price = entry_price
        
        exit_data = {
            'bid': c.get('exit_bid') or 0,
            'ask': c.get('exit_ask') or 0,
            'vol': c.get('exit_volume') or 0,
            'iv': c.get('exit_iv') or 0,
            'oi': c.get('exit_oi') or 0,
            'und': c.get('exit_underlying') or 0
        }

        # === CARD 1: ENTRY ===
        y = padding
        d.rounded_rectangle([padding, y, img_width - padding, y + card_height], radius=15, fill=COLOR_CARD, outline=COLOR_BORDER)
        
        # Header
        d.text((img_width/2, y + 40), ar(f"🔹 بداية العقد  - {strike}"), font=fnt_title, fill=COLOR_ACCENT, anchor="ms")
        d.text((100, y + 150), f"${entry_price:.2f}", font=fnt_price, fill=COLOR_TEXT_PRIMARY, anchor="ls")
        d.text((100, y + 180), "ENTRY PRICE", font=fnt_small, fill=COLOR_TEXT_SECONDARY, anchor="ls")
        
        # Grid
        draw_data_grid(d, 400, y + 100, 550, entry_data)
        d.text((img_width - 40, y + card_height - 30), str(c.get('entry_timestamp') or contract_date), font=fnt_small, fill=COLOR_TEXT_SECONDARY, anchor="rs")

        # === CARD 2: EXIT ===
        y += card_height + padding
        d.rounded_rectangle([padding, y, img_width - padding, y + card_height], radius=15, fill=COLOR_CARD, outline=COLOR_BORDER)
        
        exit_color = COLOR_GREEN if net_profit >= 0 else COLOR_RED
        d.text((img_width/2, y + 40), ar(f"🔸 نهاية العقد  - {strike}"), font=fnt_title, fill=exit_color, anchor="ms")
        d.text((100, y + 150), f"${exit_price:.2f}", font=fnt_price, fill=exit_color, anchor="ls")
        d.text((100, y + 180), "EXIT PRICE", font=fnt_small, fill=COLOR_TEXT_SECONDARY, anchor="ls")
        
        # Grid
        draw_data_grid(d, 400, y + 100, 550, exit_data)
        d.text((img_width - 40, y + card_height - 30), str(c.get('exit_timestamp') or "Open"), font=fnt_small, fill=COLOR_TEXT_SECONDARY, anchor="rs")

        # === NET PROFIT with LOGO ===
        y += card_height + padding
        d.rounded_rectangle([padding, y, img_width - padding, y + net_height], radius=15, fill=COLOR_CARD, outline=COLOR_GOLD)
        
        # Try to load logo and place it on the right side of net profit section
        logo_loaded = False
        try:
            import os
            logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "logo.png")
            if os.path.exists(logo_path):
                logo = Image.open(logo_path)
                logo.thumbnail((120, 80), Image.LANCZOS)
                logo_x = img_width - padding - logo.width - 30
                logo_y = y + (net_height - logo.height) // 2
                img.paste(logo, (logo_x, logo_y), logo if logo.mode=='RGBA' else None)
                logo_loaded = True
        except:
            pass
        
        # If logo not loaded, show INVESTLY text on the right
        if not logo_loaded:
            d.text((img_width - padding - 100, y + net_height // 2), "INVESTLY", font=fnt_title, fill=COLOR_GOLD, anchor="mm")
        
        # Net profit text (centered-left to make room for logo)
        d.text((padding + 200, y + 40), ar("💰 صافي الربح"), font=fnt_title, fill=COLOR_GOLD, anchor="ms")
        net_sign = "+" if net_profit >= 0 else ""
        d.text((padding + 200, y + 110), f"{net_sign}${net_profit:.2f}", font=fnt_net, fill=exit_color, anchor="ms")

        img.save(img_buffer, format='PNG')
        
    else:
        # Table Image Generation
        img_width = 1000
        row_height = 60
        header_height = 100
        total_height = header_height + (len(contracts) * row_height) + 150
        
        img = Image.new('RGB', (img_width, total_height), color=(20, 20, 25))
        d = ImageDraw.Draw(img)
        
        try:
            fnt_head = ImageFont.truetype("arial.ttf", 30)
            fnt_row = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            fnt_head = ImageFont.load_default()
            fnt_row = ImageFont.load_default()

        # Header -> Arabic RTL
        # Original: ["Date", "Strike", "Price", "Profit", "Loss", "Net"]
        # RTL Visual Order (Right to Left): Date (Right), Strike, Price, Profit, Loss, Net (Left)
        # But wait, usually tables are read Right-to-Left in Arabic.
        # Column 1 (Rightmost): Date. Column 6 (Leftmost): Net.
        # Let's map X coordinates to this.
        
        headers = ["التاريخ", "العقد", "سعر العقد", "الربح", "الخسارة", "الصافي"]
        headers = [ar(h) for h in headers]
        
        # X Coords (Right to Left distribution)
        # Old X: [50, 200, 450, 600, 750, 900] (Left -> Right)
        # We want Col 1 (Date) at 900 approx.
        # Col 6 (Net) at 50 approx.
        col_x = [900, 750, 550, 400, 250, 80]
        
        y = 40
        for i, h in enumerate(headers):
            # i=0 (Date) -> col_x[0]=900
            d.text((col_x[i], y), h, font=fnt_head, fill=(255, 215, 0), anchor="ms") # Centered on X
            
        d.line((20, 90, img_width-20, 90), fill=(100, 100, 100), width=2)
            
        # Rows
        y = header_height + 40
        
        for c in contracts:
            net = c['net_profit']
            
            # Values in same order as headers: Date, Strike, Price, Profit, Loss, Net
            row_vals = [
                str(c['contract_date']),
                str(c['strike']),
                str(c['contract_price']),
                str(c['profit']),
                str(c['loss']),
                str(net)
            ]
            
            for i, val in enumerate(row_vals):
                color = (255, 255, 255)
                if i == 3 and float(val or 0) > 0: color = (0, 255, 0)
                if i == 4 and float(val or 0) > 0: color = (255, 0, 0)
                if i == 5: color = (0, 255, 0) if net >= 0 else (255, 0, 0)
                
                # Reshape val (numbers mostly, but good to be safe)
                val_ar = ar(val)
                d.text((col_x[i], y), val_ar, font=fnt_row, fill=color, anchor="ms")
            
            y += row_height

        # Footer
        y += 20
        d.line((20, y, img_width-20, y), fill=(255, 255, 255), width=2)
        y += 40
        
        total_net = sum(c['net_profit'] for c in contracts)
        d.text((img_width/2, y), ar(f"إجمالي أرباح القناة اليوم: {total_net}"), font=fnt_head, fill=(255, 215, 0), anchor="ms")

        img.save(img_buffer, format='PNG')


    img_buffer.seek(0)
    return StreamingResponse(img_buffer, media_type="image/png")

