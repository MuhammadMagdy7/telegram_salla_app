import psycopg2
import logging
from datetime import datetime, date
from .config import Config

logger = logging.getLogger(__name__)

class PostgresClient:
    def __init__(self):
        self.conn_params = {
            "dbname": Config.POSTGRES_DB,
            "user": Config.POSTGRES_USER,
            "password": Config.POSTGRES_PASSWORD,
            "host": Config.POSTGRES_HOST,
            "port": Config.POSTGRES_PORT,
        }
        # Verify connection on init
        try:
             conn = self._get_conn()
             conn.close()
        except Exception as e:
             logger.error(f"Failed to connect to PostgreSQL: {e}")

    def _get_conn(self):
        try:
            return psycopg2.connect(**self.conn_params)
        except Exception as e:
            logger.error(f"FATAL: Could not connect to Postgres DB: {e}")
            print(f"FATAL: Could not connect to Postgres DB: {e}")
            raise e

    def get_or_create_stock(self, symbol, company_name=None):
        """
        Ensures the stock exists in the `stocks` table.
        Returns the stock ID.
        """
        symbol = symbol.upper()
        
        try:
            conn = self._get_conn()
        except:
            return None

        try:
            with conn.cursor() as cur:
                # Check if exists
                cur.execute("SELECT id FROM stocks WHERE symbol = %s", (symbol,))
                res = cur.fetchone()
                if res:
                    return res[0]
                
                # Create if not exists
                # Determine market (assume US for now)
                market = "US" 
                name = company_name if company_name else symbol
                
                print(f"DEBUG: Inserting new stock {symbol}")
                cur.execute(
                    "INSERT INTO stocks (symbol, company_name, market) VALUES (%s, %s, %s) RETURNING id",
                    (symbol, name, market)
                )
                new_id = cur.fetchone()[0]
                conn.commit()
                print(f"DEBUG: Created stock {symbol} with ID {new_id}")
                return new_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in get_or_create_stock: {e}")
            print(f"Error in get_or_create_stock: {e}")
            return None
        finally:
            conn.close()

    def add_contract_log(self, symbol, contract_type, strike, expiration, start_price, auction_day=None, market_data=None):
        """
        Logs a new monitoring/auction entry into `option_contracts`.
        Adapted to new schema with entry market data.
        """
        print(f"DEBUG: Attempting to log contract: {symbol} {contract_type} {strike} {expiration}")
        
        # Round values to 2 decimal places
        try:
            strike_val = round(float(strike), 2)
            start_price = round(float(start_price), 2)
        except Exception as e:
            print(f"Warning: Could not round values: {e}")
            strike_val = strike
        
        # Type character (C for Call, P for Put)
        type_str = str(contract_type).upper()
        type_char = 'C' if 'C' in type_str else 'P'

        if 'PUT' in type_str and 'C' in type_str: 
             type_char = 'P' 
             
        if type_str.startswith('C'): type_char = 'C'
        if type_str.startswith('P'): type_char = 'P'

        # Construct new strike string
        # e.g. CRWD 477.5 P
        formatted_strike_str = f"{symbol} {strike_val} {type_char}"

        # Extract entry market data if provided
        entry_bid = None
        entry_ask = None
        entry_underlying = None
        entry_volume = None
        entry_oi = None
        entry_iv = None
        
        if market_data:
            entry_bid = market_data.get('bid')
            entry_ask = market_data.get('ask')
            entry_underlying = market_data.get('underlying_price')
            entry_volume = market_data.get('volume')
            entry_oi = market_data.get('openInterest')
            entry_iv = market_data.get('impliedVolatility')

        try:
            conn = self._get_conn()
        except:
            return None

        try:
            with conn.cursor() as cur:
                print(f"DEBUG: Inserting contract with formatted strike: {formatted_strike_str}")
                # Initial insert: All start at 0 for Profit/Loss/Net
                cur.execute("""
                    INSERT INTO option_contracts 
                    (contract_date, strike, contract_price, profit, loss, net_profit, 
                     entry_bid, entry_ask, entry_underlying, entry_volume, entry_oi, entry_iv, entry_timestamp,
                     created_at)
                    VALUES (%s, %s, %s, 0, 0, 0, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                """, (expiration, formatted_strike_str, start_price, 
                      entry_bid, entry_ask, entry_underlying, entry_volume, entry_oi, entry_iv))
                
                new_id = cur.fetchone()[0]
                conn.commit()
                print(f"DEBUG: Successfully logged contract. Postgres ID: {new_id}")
                return new_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error logging contract to Postgres: {e}")
            print(f"Error logging contract to Postgres: {e}")
            return None
        finally:
            conn.close()

    def update_close_price(self, pg_id, close_price, market_data=None):
        """
        Updates the profit/loss for a contract log with exit market data.
        """
        try:
            close_price = round(float(close_price), 2)
        except Exception as e:
            print(f"Warning: Could not round close_price: {e}")
            return

        # Skip update if close_price is 0 (no data from API) - keep initial values
        if close_price == 0 or close_price is None:
            print(f"DEBUG: Skipping update for PG_ID={pg_id} - close_price is 0 or None")
            return

        # Extract exit market data if provided
        exit_bid = None
        exit_ask = None
        exit_underlying = None
        exit_volume = None
        exit_oi = None
        exit_iv = None
        
        if market_data:
            exit_bid = market_data.get('bid')
            exit_ask = market_data.get('ask')
            exit_underlying = market_data.get('underlying_price')
            exit_volume = market_data.get('volume')
            exit_oi = market_data.get('openInterest')
            exit_iv = market_data.get('impliedVolatility')

        print(f"DEBUG: Updating result for PG_ID={pg_id} ClosePrice={close_price}")
        try:
            conn = self._get_conn()
        except:
            return

        try:
            with conn.cursor() as cur:
                # CORRECT LOGIC PER USER REQUEST:
                # If close >= contract (profit): profit = close_price, loss = 0.
                # If close < contract (loss): profit = 0, loss = close_price.
                # Net Profit = (Close - Contract) ALWAYS.
                cur.execute("""
                    UPDATE option_contracts
                    SET 
                        profit = CASE 
                            WHEN %s >= contract_price THEN %s 
                            ELSE 0 
                        END,
                        loss = CASE 
                            WHEN %s < contract_price THEN %s
                            ELSE 0 
                        END,
                        net_profit = ROUND((%s - contract_price)::numeric, 2),
                        exit_bid = %s,
                        exit_ask = %s,
                        exit_underlying = %s,
                        exit_volume = %s,
                        exit_oi = %s,
                        exit_iv = %s,
                        exit_timestamp = NOW()
                    WHERE id = %s
                """, (close_price, close_price, close_price, close_price, close_price,
                      exit_bid, exit_ask, exit_underlying, exit_volume, exit_oi, exit_iv, pg_id))
                conn.commit()
                print("DEBUG: Profit/Loss/Net and exit data updated.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating result in Postgres: {e}")
            print(f"Error updating result in Postgres: {e}")
        finally:
            conn.close()
