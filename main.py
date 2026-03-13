# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import logging
import platform
import os
from pyrogram import Client, idle
from pyrogram.errors import AuthKeyUnregistered, FloodWait, BadMsgNotification
from config import API_ID, API_HASH, BOT_TOKEN

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pyrogram ichki ulanish/uzilish loglarini sokinlashtirish
# (har upload uchun uclient connect/disconnect bo'ladi — bu normal, INFO shovqin qiladi)
logging.getLogger("pyrogram.session.session").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection.connection").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session.auth").setLevel(logging.WARNING)

# Setup uvloop for improved performance if not on Windows
def setup_event_loop():
    if platform.system() != "Windows":
        try:
            import uvloop
            uvloop.install()
            logger.info("uvloop installed successfully in main.py")
        except ImportError:
            logger.warning("uvloop not available in main.py, using default event loop")
    else:
        # Use new event loop policy for Windows to avoid issues
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy') and asyncio.get_event_loop_policy().__class__.__name__ != 'WindowsSelectorEventLoopPolicy':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("Using WindowsSelectorEventLoopPolicy in main.py")

# Maximum retries for connection issues
MAX_RETRIES = 3
RETRY_DELAY = 5

class ConnectionError(Exception):
    """Custom exception for network connection errors"""
    pass

class Bot(Client):
    def __init__(self):
        # Initialize uvloop before creating the client
        setup_event_loop()
        
        # Create sessions directory if it doesn't exist
        os.makedirs("sessions", exist_ok=True)
        
        super().__init__(
            "sessions/techvj_login",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="TechVJ"),
            workers=50,
            sleep_threshold=10
        )
        # Additional connection state variables
        self._connection_retries = 0
        self._is_connected = False
        self._last_ping_time = 0
        self._connection_errors = []

    async def start(self):
        """Start the bot with improved error handling"""
        for attempt in range(MAX_RETRIES):
            try:
                await super().start()
                self._is_connected = True
                logger.info('✅ Bot Started Modified By 𝐖𝐎𝐎𝐃𝐜𝐫𝐚𝐟𝐭')
                print('✔️ Bot Started Modified By 𝐖𝐎𝐎𝐃𝐜𝐫𝐚𝐟𝐭')
                
                # Log event loop implementation
                loop = asyncio.get_event_loop()
                loop_class = loop.__class__.__name__
                logger.info(f"Bot running with event loop: {loop_class}")
                
                # Start the connection monitor
                asyncio.create_task(self._connection_monitor())
                return
            except (AuthKeyUnregistered, BadMsgNotification) as e:
                # These errors indicate a serious authentication issue, we won't retry
                logger.error(f"Critical authentication error: {e}")
                raise
            except FloodWait as e:
                # For these errors, we'll retry with backoff
                wait_time = getattr(e, 'x', RETRY_DELAY * (attempt + 1))
                logger.warning(f"Connection error: {e}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            except OSError as e:
                # Handle network-related OS errors
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Network error: {e}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                # For other errors, retry with exponential backoff
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.error(f"Failed to start bot: {e}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {wait_time} seconds... (Attempt {attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to start after {MAX_RETRIES} attempts")
                    raise

    def run(self):
        """Run the bot with the event loop"""
        loop = asyncio.get_event_loop()
        
        # Log event loop implementation
        loop_class = loop.__class__.__name__
        logger.info(f"Bot run() with event loop: {loop_class}")
        
        try:
            loop.run_until_complete(self.start())
            loop.run_until_complete(idle())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot stopped due to error: {e}")
        finally:
            loop.run_until_complete(self.stop())
            
    async def stop(self, *args):
        """Stop the bot with improved error handling"""
        try:
            self._is_connected = False
            await super().stop()
            logger.info('Bot Stopped Successfully')
            print('Bot Stopped Bye')
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Force clean stop
            print('Bot Stopped with errors')

    async def restart(self):
        """Restart the bot by stopping and starting again"""
        try:
            await self.stop()
            await asyncio.sleep(1)
            await self.start()
            logger.info("Bot successfully restarted")
            return True
        except Exception as e:
            logger.error(f"Error during restart: {e}")
            return False

    async def is_connected(self):
        """Check if the bot is still connected to Telegram"""
        return self._is_connected
        
    async def _connection_monitor(self):
        """Monitor the connection status and attempt to fix issues"""
        while self._is_connected:
            try:
                # Perform a simple API call to check connection
                await self.get_me()
                # If successful, clear any stored connection errors
                self._connection_errors.clear()
            except Exception as e:
                # Track the error
                logger.warning(f"Connection check failed: {e}")
                self._connection_errors.append(str(e))
                
                # If we've accumulated too many errors, try to reconnect
                if len(self._connection_errors) >= 3:
                    logger.warning("Multiple connection failures detected, attempting to reconnect...")
                    try:
                        await super().disconnect()
                        await asyncio.sleep(1)
                        await super().connect()
                        logger.info("Reconnection successful")
                        self._connection_errors.clear()
                    except Exception as reconnect_error:
                        logger.error(f"Reconnection failed: {reconnect_error}")
                        self._is_connected = False
                        break
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute

# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01
