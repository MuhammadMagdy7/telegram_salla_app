"""
PostgreSQL-based Database module for Webull Bot.
Replaces the original SQLite implementation.
Uses psycopg2 for synchronous operations (compatible with existing codebase).
"""
import psycopg2
import psycopg2.extras
import logging
from .config import Config

logger = logging.getLogger(__name__)


class Database:
    """
    PostgreSQL Database handler for monitoring commands.
    Uses the `monitoring_commands` table in the shared PostgreSQL database.
    """
    
    def __init__(self):
        self.conn_params = {
            "dbname": Config.POSTGRES_DB,
            "user": Config.POSTGRES_USER,
            "password": Config.POSTGRES_PASSWORD,
            "host": Config.POSTGRES_HOST,
            "port": Config.POSTGRES_PORT,
        }
        self._init_db()

    def _get_conn(self):
        """Get a new database connection."""
        try:
            return psycopg2.connect(**self.conn_params)
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def _init_db(self):
        """Initialize database - verify connection and table exists."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                # Create monitoring_commands table if not exists
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS monitoring_commands (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        strike DECIMAL NOT NULL,
                        contract_type VARCHAR(1) NOT NULL,
                        expiration DATE NOT NULL,
                        target_price DECIMAL,
                        entry_price DECIMAL,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        contract_id TEXT,
                        notification_mode VARCHAR(20) DEFAULT 'always',
                        postgres_id INTEGER,
                        last_notified_price DECIMAL DEFAULT 0,
                        peak_price DECIMAL DEFAULT 0
                    )
                ''')
                # Add columns if they don't exist (for existing databases)
                cur.execute("ALTER TABLE monitoring_commands ADD COLUMN IF NOT EXISTS last_notified_price DECIMAL DEFAULT 0")
                cur.execute("ALTER TABLE monitoring_commands ADD COLUMN IF NOT EXISTS peak_price DECIMAL DEFAULT 0")
                conn.commit()
            conn.close()
            logger.info("PostgreSQL Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")

    def add_command(self, chat_id, symbol, strike, contract_type, expiration, 
                    target_price=None, entry_price=None, contract_id=None, 
                    notification_mode='always', postgres_id=None):
        """Add a new monitoring command."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO monitoring_commands 
                    (chat_id, symbol, strike, contract_type, expiration, 
                     target_price, entry_price, contract_id, notification_mode, postgres_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (chat_id, symbol, strike, contract_type, expiration, 
                      target_price, entry_price, contract_id, notification_mode, postgres_id))
                cmd_id = cur.fetchone()[0]
                conn.commit()
            conn.close()
            return cmd_id
        except Exception as e:
            logger.error(f"Error adding command: {e}")
            return None

    def get_active_commands(self):
        """Get all active monitoring commands."""
        try:
            conn = self._get_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM monitoring_commands WHERE status = 'active'")
                rows = cur.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting active commands: {e}")
            return []

    def get_chat_commands(self, chat_id):
        """Get all commands for a specific chat."""
        try:
            conn = self._get_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM monitoring_commands WHERE chat_id = %s", (chat_id,))
                rows = cur.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting chat commands: {e}")
            return []

    def get_command(self, cmd_id):
        """Get a specific command by ID."""
        try:
            conn = self._get_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM monitoring_commands WHERE id = %s", (cmd_id,))
                row = cur.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting command {cmd_id}: {e}")
            return None

    def update_command_status(self, cmd_id, status):
        """Update the status of a command."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE monitoring_commands SET status = %s WHERE id = %s", 
                    (status, cmd_id)
                )
                rows = cur.rowcount
                conn.commit()
            conn.close()
            return rows > 0
        except Exception as e:
            logger.error(f"Error updating command status: {e}")
            return False

    def remove_command(self, cmd_id):
        """Remove a command by ID."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM monitoring_commands WHERE id = %s", (cmd_id,))
                rows = cur.rowcount
                conn.commit()
            conn.close()
            return rows > 0
        except Exception as e:
            logger.error(f"Error removing command {cmd_id}: {e}")
            return False

    def update_price_tracking(self, cmd_id, last_notified_price, peak_price):
        """Update the last notified price and peak price for a command."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE monitoring_commands SET last_notified_price = %s, peak_price = %s WHERE id = %s",
                    (last_notified_price, peak_price, cmd_id)
                )
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating price tracking for cmd {cmd_id}: {e}")
