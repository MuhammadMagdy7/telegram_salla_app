from PIL import Image, ImageDraw, ImageFont
import io
import datetime

class ImageGenerator:
    def generate_status_image(self, data):
        """
        Generate a clean, modern trading-style status image.
        """
        # === Colors (Modern Dark Theme) ===
        COLOR_BG = (10, 14, 23)           # Near-black background
        COLOR_CARD = (18, 24, 38)         # Slightly lighter card bg
        COLOR_TEXT_PRIMARY = (255, 255, 255)  # White
        COLOR_TEXT_SECONDARY = (140, 150, 170)  # Muted grey-blue
        COLOR_ACCENT = (0, 200, 180)      # Teal/Turquoise for main price
        COLOR_GREEN = (46, 204, 113)      # Positive change
        COLOR_RED = (231, 76, 60)         # Negative change
        COLOR_WARNING = (241, 196, 15)    # Yellow warning
        COLOR_BORDER = (40, 50, 70)       # Subtle border
        
        width, height = 1200, 420
        image = Image.new('RGB', (width, height), color=COLOR_BG)
        draw = ImageDraw.Draw(image)

        # === Font Loader ===
        def get_font(size):
            # List of potential font paths (Windows, Linux, misc)
            # Re-ordered to prioritize Arial-like metrics (LiberationSans) over DejaVu
            font_candidates = [
                "arial.ttf",      # Windows/Generic
                "Arial.ttf",      # Linux Case-sensitive
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", # Generic Arial alternative
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf", # Ubuntu mscorefonts
                "/usr/share/fonts/TTF/Arial.ttf",        # Arch Linux
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", # Fallback 1 (Regular)
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Fallback 2 (Bold)
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                "C:\\Windows\\Fonts\\arial.ttf"
            ]
            
            for path in font_candidates:
                try:
                    return ImageFont.truetype(path, size)
                except IOError:
                    continue
            
            # Fallback if no TTF found (Will result in small default font)
            print("WARNING: No TrueType font found. Using default bitmap font.")
            return ImageFont.load_default()

        # Fonts - UPSCALED sizes (~1.5x)
        font_symbol = get_font(54)
        font_sub = get_font(32)
        font_price_big = get_font(120)
        font_price_label = get_font(27)
        font_change = get_font(42)
        font_detail_label = get_font(27)
        font_detail_value = get_font(36)
        font_footer = get_font(24)

        # === Data Extraction ===
        bid = data.get('bid', 0) or 0
        ask = data.get('ask', 0) or 0
        last = data.get('last_price', 0) or 0
        mid = (bid + ask) / 2 if (bid and ask) else last
        
        change_abs = data.get('change_abs', 0) or 0
        change_pct = data.get('change_pct', 0) or 0
        underlying = data.get('underlying_price', 0) or 0
        volume = data.get('volume', 0) or 0
        open_interest = data.get('openInterest', 0) or 0
        
        spread = ask - bid if (bid and ask) else 0
        
        is_positive = change_abs >= 0
        change_color = COLOR_GREEN if is_positive else COLOR_RED
        sign = "+" if is_positive else ""
        arrow = "^" if is_positive else "v"

        # === Draw Card Background ===
        card_margin = 15
        draw.rounded_rectangle(
            [card_margin, card_margin, width - card_margin, height - card_margin],
            radius=18,
            fill=COLOR_CARD,
            outline=COLOR_BORDER
        )

        # === HEADER SECTION ===
        header_y = 33
        
        # Header: Symbol + Strike
        symbol = data.get('symbol', 'N/A')
        strike = data.get('strike', 0)
        header_text = f"{symbol} ${strike}"
        draw.text((38, header_y), header_text, font=font_symbol, fill=COLOR_TEXT_PRIMARY)
        
        # Sub-header: Date + Type (Gray)
        try:
            exp_obj = datetime.datetime.strptime(data.get('expiration', ''), "%Y-%m-%d")
            date_str = exp_obj.strftime("%d %b %y")
        except:
            date_str = data.get('expiration', '')
        
        contract_type = "CALL" if data.get('type', 'C').upper().startswith('C') else "PUT"
        info_text = f"{date_str} {contract_type}"
        draw.text((38, header_y + 63), info_text, font=font_sub, fill=COLOR_TEXT_SECONDARY)
        
        # Underlying price & IV (top right)
        iv = data.get('impliedVolatility', 0) or 0
        iv_text = f"IV: {iv:.1%}"
        iv_bbox = draw.textbbox((0, 0), iv_text, font=font_sub)
        iv_w = iv_bbox[2] - iv_bbox[0]
        draw.text((width - iv_w - 38, header_y + 68), iv_text, font=font_sub, fill=COLOR_TEXT_SECONDARY)

        ul_text = f"${underlying:,.2f}"
        ul_bbox = draw.textbbox((0, 0), ul_text, font=font_sub)
        ul_w = ul_bbox[2] - ul_bbox[0]
        draw.text((width - ul_w - 38, header_y + 8), ul_text, font=font_sub, fill=COLOR_TEXT_SECONDARY)

        # === MAIN PRICE (Center-Left) ===
        price_y = 142
        
        # Big Mid Price
        mid_text = f"${mid:.2f}"
        draw.text((38, price_y), mid_text, font=font_price_big, fill=COLOR_ACCENT)
        
        # Change below price
        # change_y = price_y + 128
        # change_text = f"{arrow} {sign}{change_abs:.2f} ({sign}{change_pct:.1f}%)"
        # draw.text((38, change_y), change_text, font=font_change, fill=COLOR_GREEN)

        # === RIGHT PANEL ===
        panel_x = 630
        row_y = 142
        row_gap = 75
        col_gap = 150
        
        # Bid / Ask
        draw.text((panel_x, row_y), "BID", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        draw.text((panel_x + col_gap, row_y), "ASK", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        draw.text((panel_x, row_y + 33), f"${bid:.2f}", font=font_detail_value, fill=COLOR_TEXT_PRIMARY)
        draw.text((panel_x + col_gap, row_y + 33), f"${ask:.2f}", font=font_detail_value, fill=COLOR_TEXT_PRIMARY)
        
        # Volume / OI
        row2_y = row_y + row_gap + 22
        draw.text((panel_x, row2_y), "VOL", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        draw.text((panel_x + col_gap, row2_y), "OI", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        
        vol_color = COLOR_TEXT_PRIMARY
        oi_color = COLOR_WARNING if open_interest == 0 else COLOR_TEXT_PRIMARY
        
        draw.text((panel_x, row2_y + 33), f"{volume:,}", font=font_detail_value, fill=vol_color)
        draw.text((panel_x + col_gap, row2_y + 33), f"{open_interest:,}", font=font_detail_value, fill=oi_color)
        
        # Last price (smaller, far right)
        last_x = 930
        draw.text((last_x, row_y), "LAST", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        draw.text((last_x, row_y + 33), f"${last:.2f}", font=font_detail_value, fill=COLOR_TEXT_SECONDARY)
        
        # Spread
        draw.text((last_x, row2_y), "SPREAD", font=font_detail_label, fill=COLOR_TEXT_SECONDARY)
        spread_color = COLOR_WARNING if spread > mid * 0.1 else COLOR_TEXT_SECONDARY
        draw.text((last_x, row2_y + 33), f"${spread:.2f}", font=font_detail_value, fill=spread_color)

        # === FOOTER ===
        footer_y = height - 48
        timestamp = datetime.datetime.now().strftime("%H:%M %d/%m")
        footer_text = f"{timestamp} ET"
        
        bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
        text_w = bbox[2] - bbox[0]
        draw.text((width - text_w - 38, footer_y), footer_text, font=font_footer, fill=COLOR_TEXT_SECONDARY)

        # === Save ===
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return buf

