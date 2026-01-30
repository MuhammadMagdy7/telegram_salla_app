"""
Contract Card Image Generator for Webull Bot.
Creates trading-style contract cards matching the reference design.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import datetime

# Get the project root directory (telegram_salla_app)
# This file is at: webull_bot/src/contract_card_gen.py
# So we need to go up 2 levels to webull_bot, then up one more to telegram_salla_app
WEBULL_BOT_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(WEBULL_BOT_DIR)
LOGO_PATH = os.path.join(PROJECT_ROOT, "static", "logo.png")


class ContractCardGenerator:
    """
    Generates professional trading card images for option contracts.
    Design inspired by the reference image with dark theme and logo.
    """
    
    # === Color Palette ===
    COLOR_BG_DARK = (15, 15, 20)           # Near black
    COLOR_BG_GRADIENT_TOP = (25, 30, 45)   # Dark blue-grey
    COLOR_BG_GRADIENT_BOTTOM = (10, 12, 18) # Darker
    COLOR_CARD_BG = (20, 25, 35)           # Card background
    COLOR_GOLD = (218, 165, 32)            # Gold accent
    COLOR_YELLOW = (255, 215, 0)           # Bright yellow
    COLOR_TEXT_WHITE = (255, 255, 255)
    COLOR_TEXT_GREY = (150, 155, 165)
    COLOR_GREEN = (0, 200, 100)            # Profit green
    COLOR_RED = (255, 70, 70)              # Loss red
    COLOR_TEAL = (0, 200, 180)             # Accent color
    
    def __init__(self):
        self.logo = None
        self._load_logo()
    
    def _load_logo(self):
        """Load the logo image."""
        try:
            if os.path.exists(LOGO_PATH):
                self.logo = Image.open(LOGO_PATH).convert("RGBA")
            else:
                print(f"Warning: Logo not found at {LOGO_PATH}")
        except Exception as e:
            print(f"Error loading logo: {e}")
    
    def _get_font(self, size, bold=False):
        """Get a TrueType font with fallbacks."""
        font_candidates = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "arial.ttf",
        ]
        
        for path in font_candidates:
            try:
                return ImageFont.truetype(path, size)
            except IOError:
                continue
        
        return ImageFont.load_default()
    
    def _create_gradient_background(self, width, height):
        """Create a gradient background."""
        image = Image.new('RGB', (width, height), self.COLOR_BG_DARK)
        draw = ImageDraw.Draw(image)
        
        # Simple vertical gradient
        for y in range(height):
            ratio = y / height
            r = int(self.COLOR_BG_GRADIENT_TOP[0] * (1 - ratio) + self.COLOR_BG_GRADIENT_BOTTOM[0] * ratio)
            g = int(self.COLOR_BG_GRADIENT_TOP[1] * (1 - ratio) + self.COLOR_BG_GRADIENT_BOTTOM[1] * ratio)
            b = int(self.COLOR_BG_GRADIENT_TOP[2] * (1 - ratio) + self.COLOR_BG_GRADIENT_BOTTOM[2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        return image
    
    def generate_contract_card(self, data):
        """
        Generate a contract card image.
        
        Args:
            data: dict with keys:
                - symbol: str (e.g., "SPXW", "SPX")
                - strike: float
                - type: str ("C" or "P")
                - expiration: str (YYYY-MM-DD)
                - price: float (current mid price)
                - change_pct: float (percentage change)
                - change_abs: float (absolute change)
                - volume: int
                - open_price: float
                - high: float
                - low: float
                - underlying_price: float
        
        Returns:
            BytesIO buffer containing PNG image
        """
        width, height = 800, 450
        
        # Create base image with gradient
        image = self._create_gradient_background(width, height)
        draw = ImageDraw.Draw(image)
        
        # === Fonts ===
        font_header = self._get_font(22)
        font_price_big = self._get_font(90, bold=True)
        font_change = self._get_font(28)
        font_label = self._get_font(16)
        font_value = self._get_font(24)
        font_symbol_badge = self._get_font(36, bold=True)
        
        # === Extract Data ===
        symbol = data.get('symbol', 'N/A')
        strike = data.get('strike', 0)
        contract_type = data.get('type', 'C')
        expiration = data.get('expiration', '')
        price = data.get('price', 0) or data.get('last_price', 0) or 0
        change_pct = data.get('change_pct', 0) or 0
        change_abs = data.get('change_abs', 0) or 0
        volume = data.get('volume', 0) or 0
        open_price = data.get('open_price', 0) or 0
        high = data.get('high', 0) or 0
        low = data.get('low', 0) or 0
        underlying = data.get('underlying_price', 0) or 0
        
        # Type display
        type_display = "(W)Call" if contract_type.upper().startswith('C') else "(W)Put"
        is_positive = change_pct >= 0
        change_color = self.COLOR_GREEN if is_positive else self.COLOR_RED
        sign = "+" if is_positive else ""
        
        # === Draw Card Border ===
        card_margin = 20
        draw.rounded_rectangle(
            [card_margin, card_margin, width - card_margin, height - card_margin],
            radius=15,
            fill=self.COLOR_CARD_BG,
            outline=self.COLOR_GOLD,
            width=2
        )
        
        # === Header: Contract Info ===
        header_y = 35
        try:
            exp_date = datetime.datetime.strptime(expiration, "%Y-%m-%d")
            exp_str = exp_date.strftime("%d %b %y")
        except:
            exp_str = expiration
        
        header_text = f"{symbol} ${underlying:,.0f} {exp_str} {type_display} {int(strike)}"
        draw.text((40, header_y), header_text, font=font_header, fill=self.COLOR_TEXT_GREY)
        
        # === Main Price (Large) ===
        price_y = 80
        price_text = f"{price:.2f}"
        draw.text((40, price_y), price_text, font=font_price_big, fill=self.COLOR_TEAL)
        
        # === Change Percentage ===
        change_y = price_y + 15
        change_text = f"{sign}{change_abs:.2f}"
        pct_text = f"{sign}{change_pct:.0f}%"
        
        # Position change text to the right of price
        price_bbox = draw.textbbox((40, price_y), price_text, font=font_price_big)
        change_x = price_bbox[2] + 15
        
        draw.text((change_x, change_y), change_text, font=font_change, fill=change_color)
        draw.text((change_x, change_y + 35), pct_text, font=font_change, fill=change_color)
        
        # === Logo (Right Side) ===
        if self.logo:
            logo_size = 150
            logo_resized = self.logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            logo_x = width - logo_size - 50
            logo_y = 80
            
            # Paste logo with alpha
            image.paste(logo_resized, (logo_x, logo_y), logo_resized)
        
        # === Symbol Badge (Below Logo) ===
        badge_x = width - 180
        badge_y = 250
        
        # Draw badge background circle
        badge_radius = 40
        draw.ellipse(
            [badge_x - badge_radius, badge_y - badge_radius, 
             badge_x + badge_radius, badge_y + badge_radius],
            fill=self.COLOR_GOLD
        )
        
        # Draw symbol text centered in badge
        symbol_short = symbol[:3]  # First 3 chars
        sym_bbox = draw.textbbox((0, 0), symbol_short, font=font_symbol_badge)
        sym_w = sym_bbox[2] - sym_bbox[0]
        sym_h = sym_bbox[3] - sym_bbox[1]
        draw.text(
            (badge_x - sym_w // 2, badge_y - sym_h // 2 - 5), 
            symbol_short, 
            font=font_symbol_badge, 
            fill=self.COLOR_BG_DARK
        )
        
        # === Metrics Grid (Bottom Left) ===
        grid_y = 280
        col_width = 120
        
        metrics = [
            ("Open", f"{open_price:.2f}" if open_price else "—"),
            ("High", f"{high:.2f}" if high else "—"),
            ("Low", f"{low:.2f}" if low else "—"),
            ("Volume", f"{volume:,}" if volume else "—"),
        ]
        
        for i, (label, value) in enumerate(metrics):
            x = 40 + (i * col_width)
            draw.text((x, grid_y), label, font=font_label, fill=self.COLOR_TEXT_GREY)
            draw.text((x, grid_y + 25), value, font=font_value, fill=self.COLOR_TEXT_WHITE)
        
        # === Footer: Timestamp ===
        footer_y = height - 50
        timestamp = datetime.datetime.now().strftime("%H:%M %d/%m/%Y")
        draw.text((40, footer_y), f"⏱ {timestamp}", font=font_label, fill=self.COLOR_TEXT_GREY)
        
        # === Save to buffer ===
        buf = io.BytesIO()
        image.save(buf, format='PNG', quality=95)
        buf.seek(0)
        return buf
    
    def generate_from_db_record(self, record, market_data=None):
        """
        Generate card from a database record.
        
        Args:
            record: dict from option_contracts table
            market_data: optional dict with live market data
        """
        # Parse strike field (format: "SYMBOL STRIKE TYPE" e.g., "SPXW 6960.0 P")
        strike_str = record.get('strike', '')
        parts = str(strike_str).split()
        
        if len(parts) >= 3:
            symbol = parts[0]
            strike = float(parts[1])
            contract_type = parts[2]
        else:
            symbol = record.get('symbol', 'N/A')
            strike = float(strike_str) if strike_str else 0
            contract_type = record.get('contract_type', 'C')
        
        data = {
            'symbol': symbol,
            'strike': strike,
            'type': contract_type,
            'expiration': str(record.get('contract_date', '')),
            'price': float(record.get('contract_price', 0) or 0),
            'change_pct': 0,
            'change_abs': float(record.get('net_profit', 0) or 0),
            'volume': 0,
            'open_price': 0,
            'high': 0,
            'low': 0,
            'underlying_price': 0,
        }
        
        # Override with live market data if available
        if market_data:
            data.update({
                'price': market_data.get('price', data['price']),
                'change_pct': market_data.get('change_pct', 0),
                'change_abs': market_data.get('change_abs', 0),
                'volume': market_data.get('volume', 0),
                'underlying_price': market_data.get('underlying_price', 0),
            })
        
        return self.generate_contract_card(data)


# Singleton instance
contract_card_gen = ContractCardGenerator()
