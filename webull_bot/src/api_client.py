import aiohttp
import logging
import asyncio
import requests
import urllib3
import os
import shutil
import tempfile
import certifi
from .config import Config
from webull import webull # Import webull
import certifi
import os

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# --- FIX FOR ARABIC PATHS ("مستقل") CAUSING SSL ERRORS ---
try:
    # 1. Create a safe temp directory (ASCII path)
    safe_temp_dir = tempfile.gettempdir()
    safe_cert_path = os.path.join(safe_temp_dir, "cacert.pem")
    
    # 2. Copy the certificate file from the problematic path to the safe path
    current_cert_path = certifi.where()
    shutil.copy2(current_cert_path, safe_cert_path)
    
    # 3. Force requests/curl/openssl to use the safe path
    os.environ['REQUESTS_CA_BUNDLE'] = safe_cert_path
    os.environ['CURL_CA_BUNDLE'] = safe_cert_path
    os.environ['SSL_CERT_FILE'] = safe_cert_path
    
except Exception as e:
    logging.warning(f"Failed to apply SSL fix: {e}")

# # Disable SSL Warnings as a backup
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# # Monkeypatch requests to disable SSL verification globally (Double safety)
# original_session_request = requests.Session.request

# def patched_request(self, method, url, *args, **kwargs):
#     kwargs['verify'] = False 
#     return original_session_request(self, method, url, *args, **kwargs)

# requests.Session.request = patched_request
# # ---------------------------------------------------------

logger = logging.getLogger(__name__)

class MassiveAPIClient:
    def __init__(self):
        # Initialize Webull client
        self.wb = webull()
        self.wb._access_token = Config.WEBULL_ACCESS_TOKEN
        self.wb.logged_in = True
        
        # Cache for ticker IDs to reduce API calls
        self.ticker_cache = {}

    def _get_occ_symbol(self, symbol, expiration, contract_type, strike, use_original_symbol=False):
        """Format parameters into OCC Option Symbol."""
        if use_original_symbol:
             search_symbol = symbol.upper()
        else:
            # Adjust symbol for Indices (OCC symbols use SPX not SPXW usually)
            search_symbol = symbol.upper()
            if search_symbol in ['SPXW', 'SPXP']:
                search_symbol = 'SPX'
            elif search_symbol in ['NDXW', 'NDXP']:
                search_symbol = 'NDX'

        # Root symbol: 6 characters, padded with spaces
        root = f"{search_symbol:<6}"
        
        # Expiration: YYMMDD
        # Input expiration is YYYY-MM-DD
        year = expiration[2:4]
        month = expiration[5:7]
        day = expiration[8:10]
        exp_str = f"{year}{month}{day}"

        # Type: C or P
        type_str = 'C' if contract_type.upper().startswith('C') else 'P'

        # Strike: 8 digits (multiplied by 1000)
        # 150 -> 00150000
        strike_val = int(float(strike) * 1000)
        strike_str = f"{strike_val:08d}"

        return f"{root}{exp_str}{type_str}{strike_str}"

    def _get_webull_data(self, symbol, contract_type, expiration, strike):
        """Fetch real-time data using Webull options chain."""
        try:
            # Normalize inputs
            target_strike = float(strike)
            is_call = contract_type.upper().startswith('C')
            
            # Map symbol (SPXW -> SPX)
            search_symbol = symbol.upper()
            if search_symbol in ['SPXW', 'SPXP']:
                search_symbol = 'SPX'
            elif search_symbol in ['NDXW', 'NDXP']:
                 search_symbol = 'NDX'

            # Use get_options to find the chain and specific contract
            # This seems more reliable than guessing OCC symbols
            try:
                # wb.get_options handles 'tickerId' lookup internally if we pass symbol string
                chain = self.wb.get_options(stock=search_symbol, expireDate=expiration)
                
                if chain and isinstance(chain, list):
                    # Find closest strike
                    target_row = None
                    for row in chain:
                        row_strike = float(row.get('strikePrice', 0))
                        if abs(row_strike - target_strike) < 0.01:
                            target_row = row
                            break
                    
                    if target_row:
                        type_key = 'call' if is_call else 'put'
                        if type_key in target_row:
                            data = target_row[type_key]
                            
                            # Extract Data
                            last = float(data.get('close') or data.get('price') or 0)
                            
                            # Bid/Ask are often in lists
                            bid = 0.0
                            if 'bidList' in data and data['bidList']:
                                bid = float(data['bidList'][0].get('price', 0))
                            
                            ask = 0.0
                            if 'askList' in data and data['askList']:
                                ask = float(data['askList'][0].get('price', 0))
                                
                            volume = int(data.get('volume') or 0)
                            oi = int(data.get('openInterest') or 0)
                            
                            # Construct OCC symbol if possible or use what we have
                            # SPXW260121C06805000 is inside 'symbol' key usually
                            contract_symbol = data.get('symbol')

                            return {
                                'last_price': last,
                                'bid': bid,
                                'ask': ask,
                                'volume': volume,
                                'openInterest': oi,
                                'impliedVolatility': float(data.get('impVol') or 0),
                                'change_abs': float(data.get('change') or 0),
                                'change_pct': float(data.get('changeRatio') or 0),
                                'underlying_price': 0, # Webull options response might not have underlying real-time
                                'contractSymbol': contract_symbol
                            }

            except Exception as e:
                logger.warning(f"Failed to fetch option chain via Webull: {e}")

            logger.warning(f"No data found in Webull chain for {symbol} {expiration} {strike}")
            return None

        except Exception as e:
            logger.error(f"Webull Fetch Error for {symbol}: {e}")
            return None

        except Exception as e:
            logger.error(f"Webull Fetch Error for {symbol}: {e}")
            return None

    def get_batch_option_data(self, symbol, expiration):
        """Fetch entire option chain for a symbol and expiration to support batch lookups."""
        try:
            # Map symbol (SPXW -> SPX)
            search_symbol = symbol.upper()
            if search_symbol in ['SPXW', 'SPXP']:
                search_symbol = 'SPX'
            elif search_symbol in ['NDXW', 'NDXP']:
                 search_symbol = 'NDX'

            # Fetch Chain
            chain = self.wb.get_options(stock=search_symbol, expireDate=expiration)
            
            # Dictionary for looking up contracts: Key is (strike, type_char)
            # type_char: 'C' or 'P'
            lookup = {}

            if chain and isinstance(chain, list):
                for row in chain:
                    row_strike = float(row.get('strikePrice', 0))
                    
                    # Parse Call
                    if 'call' in row:
                        data = row['call']
                        processed = self._parse_webull_option_data(data)
                        lookup[(row_strike, 'C')] = processed
                    
                    # Parse Put
                    if 'put' in row:
                        data = row['put']
                        processed = self._parse_webull_option_data(data)
                        lookup[(row_strike, 'P')] = processed
            
            return lookup
            
        except Exception as e:
            logger.error(f"Batch fetch error for {symbol} {expiration}: {e}")
            return {}

    def _parse_webull_option_data(self, data):
        """Helper to parse a single option data dict from Webull chain."""
        last = float(data.get('close') or data.get('price') or 0)
        
        bid = 0.0
        if 'bidList' in data and data['bidList']:
            bid = float(data['bidList'][0].get('price', 0))
        
        ask = 0.0
        if 'askList' in data and data['askList']:
            ask = float(data['askList'][0].get('price', 0))
            
        volume = int(data.get('volume') or 0)
        oi = int(data.get('openInterest') or 0)
        
        return {
            'last_price': last,
            'bid': bid,
            'ask': ask,
            'volume': volume,
            'openInterest': oi,
            'impliedVolatility': float(data.get('impVol') or 0),
            'change_abs': float(data.get('change') or 0),
            'change_pct': float(data.get('changeRatio') or 0),
            'underlying_price': 0,
            'contractSymbol': data.get('symbol')
        }

    async def get_market_data(self, symbol, contract_type, expiration, strike):
        """Fetch real-time data for a specific option contract using Webull."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_webull_data, symbol, contract_type, expiration, strike)

    async def get_current_price(self, symbol):
        """Fetch current price for the underlying asset using Webull."""
        try:
            loop = asyncio.get_running_loop()
            
            def fetch():
                # Get ticker ID
                try:
                    # Search for ticker
                    # Note: get_ticker(symbol) returns info
                    ticker_info = self.wb.get_ticker(symbol)
                    
                    if not ticker_info or 'tickerId' not in ticker_info:
                        logger.warning(f"Webull ticker not found for {symbol}")
                        return None
                        
                    ticker_id = ticker_info['tickerId']
                    
                    # Get Quote
                    # Note: get_quote requires tId parameter if we pass an ID string/int
                    quote = self.wb.get_quote(tId=str(ticker_id))
                    # price is usually in 'close', 'price', 'pPrice'
                    # quote usually contains: 'close', 'open', 'high', 'low', 'price', 'bid', 'ask' etc.
                    current_price = float(quote.get('close') or quote.get('price') or quote.get('pPrice') or 0)
                    return current_price
                except Exception as e:
                    logger.error(f"Webull get_current_price error: {e}")
                    return None
            
            price = await loop.run_in_executor(None, fetch)
            return price
        except Exception as e:
            logger.error(f"Error fetching price from Webull for {symbol}: {e}")
            return None

    async def get_expirations(self, symbol):
        """Fetch available expirations for a symbol."""
        try:
            loop = asyncio.get_running_loop()
            def fetch():
                search_symbol = symbol.upper()
                if search_symbol in ['SPXW', 'SPXP']: search_symbol = 'SPX'
                elif search_symbol in ['NDXW', 'NDXP']: search_symbol = 'NDX'
                
                return self.wb.get_options_expiration_dates(search_symbol)
            
            return await loop.run_in_executor(None, fetch)
        except Exception as e:
            logger.error(f"Error fetching expirations: {e}")
            return []

    async def get_option_chain(self, symbol, expiry_days_target=None):
        """Fetch option chain for a symbol using Webull."""
        try:
            loop = asyncio.get_running_loop()
            
            def fetch_webull_chain():
                # Map symbol (SPXW -> SPX)
                search_symbol = symbol.upper()
                if search_symbol in ['SPXW', 'SPXP']:
                    search_symbol = 'SPX'
                elif search_symbol in ['NDXW', 'NDXP']:
                    search_symbol = 'NDX'
                
                # Get Ticker ID first
                try:
                    # get_ticker returns an int (tickerId)
                    ticker_info = self.wb.get_ticker(search_symbol)
                    
                    if not ticker_info:
                        return None, 0
                    
                    # Ensure it's an int (tickerId)
                    if isinstance(ticker_info, dict):
                         spx_id = int(ticker_info.get('tickerId'))
                    else:
                         spx_id = int(ticker_info)
                    
                    # Get Current Price
                    try:
                        quote = self.wb.get_quote(tId=str(spx_id))
                        current_price = float(quote.get('close') or quote.get('price') or 0)
                    except:
                        current_price = 0

                    # Get Expirations
                    # We utilize the library method to get available dates
                    # NOTE: get_options_expiration_dates expects a SYMBOL string, not an ID.
                    dates_data = self.wb.get_options_expiration_dates(search_symbol)
                    
                    if not dates_data:
                         return None, current_price
                    
                    # dates_data is usually a list of dicts: [{'date': '...', 'days': ...}, ...]
                    target_date = None
                    
                    if expiry_days_target is not None:
                        # Sort by distance to target
                        # Filter out invalid items if any
                        valid_dates = [d for d in dates_data if d.get('days') is not None]
                        if valid_dates:
                            valid_dates.sort(key=lambda x: abs(int(x['days']) - int(expiry_days_target)))
                            target_date = valid_dates[0]['date']
                        elif dates_data:
                             # Fallback if days missing
                             target_date = dates_data[0]['date']
                    else:
                        # We pick the nearest valid expiration
                        for d in dates_data:
                             # Ensure we pick a date (maybe skip today if market closed? No, keep simple)
                             target_date = d['date']
                             break
                    
                    if not target_date:
                         return None, current_price

                    # Get Chain for this expiration (Explicitly)
                    chain = self.wb.get_options(stock=search_symbol, expireDate=target_date)
                    
                    return chain, current_price
                except Exception as e:
                    logger.error(f"Webull chain fetch error: {e}")
                    return None, 0

            chain, current_price = await loop.run_in_executor(None, fetch_webull_chain)
            
            if chain is None:
                 return None

            result = []
            entry_call = 0
            entry_put = 0
            
            # Chain is list of dicts: {'strikePrice': ..., 'call': {...}, 'put': {...}}
            
            # Helper to check proximity
            def is_atm(strike):
                return abs(float(strike) - current_price)

            # --- Process Chain ---
            # Sort by strike distance to current price for ATM filter
            if current_price > 0:
                chain.sort(key=lambda x: abs(float(x.get('strikePrice', 0)) - current_price))
                # Take 14 closest
                chain = chain[:14]
                # Sort back by strike
                chain.sort(key=lambda x: float(x.get('strikePrice', 0)))
            else:
                 chain = chain[:14]

            # Find ATM strikes for Entry calculation
            if current_price > 0 and len(chain) > 0:
                 # Closest is roughly the middle of our filtered list
                 # Just iterate to find best approximation
                 best_atm_row = min(chain, key=lambda x: abs(float(x.get('strikePrice', 0)) - current_price))
                 atm_strike = float(best_atm_row.get('strikePrice'))
                 
                 # Calculate entries
                 if 'call' in best_atm_row:
                     c_bid = 0
                     c_ask = 0
                     if 'bidList' in best_atm_row['call']: c_bid = float(best_atm_row['call']['bidList'][0]['price'])
                     if 'askList' in best_atm_row['call']: c_ask = float(best_atm_row['call']['askList'][0]['price'])
                     mid = (c_bid + c_ask) / 2
                     entry_call = atm_strike + mid
                
                 if 'put' in best_atm_row:
                     p_bid = 0
                     p_ask = 0
                     if 'bidList' in best_atm_row['put']: p_bid = float(best_atm_row['put']['bidList'][0]['price'])
                     if 'askList' in best_atm_row['put']: p_ask = float(best_atm_row['put']['askList'][0]['price'])
                     mid = (p_bid + p_ask) / 2
                     entry_put = atm_strike - mid

            for row in chain:
                strike = float(row.get('strikePrice'))
                
                # Call
                if 'call' in row:
                    c_data = row['call']
                    c_bid = 0
                    c_ask = 0
                    if 'bidList' in c_data: c_bid = float(c_data['bidList'][0]['price'])
                    if 'askList' in c_data: c_ask = float(c_data['askList'][0]['price'])
                    
                    result.append({
                        "contract_id": c_data.get('symbol'),
                        "strike": strike,
                        "type": 'C',
                        "bid": c_bid,
                        "ask": c_ask,
                        "last": float(c_data.get('close') or c_data.get('price') or 0),
                        "volume": int(c_data.get('volume') or 0)
                    })
                
                # Put
                if 'put' in row:
                    p_data = row['put']
                    p_bid = 0
                    p_ask = 0
                    if 'bidList' in p_data: p_bid = float(p_data['bidList'][0]['price'])
                    if 'askList' in p_data: p_ask = float(p_data['askList'][0]['price'])
                    
                    result.append({
                        "contract_id": p_data.get('symbol'),
                        "strike": strike,
                        "type": 'P',
                        "bid": p_bid,
                        "ask": p_ask,
                        "last": float(p_data.get('close') or p_data.get('price') or 0),
                        "volume": int(p_data.get('volume') or 0)
                    })
            
            return {
                'contracts': result,
                'entry_call': entry_call,
                'entry_put': entry_put
            }

        except Exception as e:
            logger.error(f"Error fetching data from Webull: {e}")
            return None
