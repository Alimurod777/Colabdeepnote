# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import signal
import time
import logging
import sys
import platform
# Import Bot class directly from main.py to avoid circular import
from main import Bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Global unhandled exception handler ──
def global_exception_handler(loop, context):
    """asyncio event loop uchun global exception handler.
    Hech qanday unhandled exception bot'ni to'xtatmasin."""
    exception = context.get("exception")
    message = context.get("message", "No message")

    if exception:
        # Bu xatolarni jimgina o'tkazib yuboramiz (normal)
        if isinstance(exception, (ConnectionResetError, OSError, TimeoutError)):
            logger.warning(f"Network exception (handled): {type(exception).__name__}: {exception}")
            return
        # RuntimeError: transport closed — bu ham normal
        if isinstance(exception, RuntimeError) and "closed" in str(exception).lower():
            logger.warning(f"Transport closed exception (handled): {exception}")
            return
        logger.error(f"Unhandled async exception: {type(exception).__name__}: {exception}\nContext: {message}")
    else:
        logger.error(f"Unhandled async error: {message}")


def setup_global_handlers():
    """Barcha turdagi exception handler'larni o'rnatadi."""
    # 1) asyncio loop uchun
    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(global_exception_handler)
    except RuntimeError:
        pass  # No loop yet

    # 2) threading uchun (pyrogram ichki threadlari)
    import threading
    _original_excepthook = threading.excepthook
    def thread_exception_handler(args):
        logger.error(
            f"Unhandled thread exception in {args.thread}: "
            f"{args.exc_type.__name__}: {args.exc_value}"
        )
        # Tizim kritik xatolarni o'tkazamiz
        if args.exc_type in (SystemExit, KeyboardInterrupt):
            if _original_excepthook:
                _original_excepthook(args)
    threading.excepthook = thread_exception_handler

    # 3) sys.excepthook — hech bo'lmaganda log qilamiz
    _original_sys_excepthook = sys.excepthook
    def sys_exception_handler(exc_type, exc_value, exc_tb):
        if exc_type in (SystemExit, KeyboardInterrupt):
            _original_sys_excepthook(exc_type, exc_value, exc_tb)
            return
        logger.error(f"Unhandled sys exception: {exc_type.__name__}: {exc_value}", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = sys_exception_handler

# Connection parameters
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 60

# Setup uvloop for improved performance if not on Windows
def setup_event_loop():
    if platform.system() != "Windows":
        try:
            import uvloop
            uvloop.install()
            logger.info("uvloop installed successfully")
        except ImportError:
            logger.warning("uvloop not available, using default event loop")
    else:
        # Use new event loop policy for Windows to avoid issues
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy') and asyncio.get_event_loop_policy().__class__.__name__ != 'WindowsSelectorEventLoopPolicy':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("Using WindowsSelectorEventLoopPolicy")

class BotRunner:
    def __init__(self):
        self.bot = None
        self.running = True
        self.retry_count = 0
        self.last_restart_time = 0
        self.restart_cooldown = 60  # Cooldown period between restarts in seconds

    async def start_bot(self):
        """Start the bot with retry mechanism"""
        while self.running:
            try:
                # Check if we need to apply cooldown
                time_since_restart = time.time() - self.last_restart_time
                if time_since_restart < self.restart_cooldown and self.retry_count > 0:
                    wait_time = self.restart_cooldown - time_since_restart
                    logger.info(f"Cooling down for {wait_time:.1f} seconds before restart...")
                    await asyncio.sleep(wait_time)

                # Create and start bot
                self.bot = Bot()
                await self.bot.start()
                logger.info("Bot successfully started")
                self.retry_count = 0  # Reset retry counter on successful start

                # Keep the bot running until stopped
                await self._monitor_bot()

            except Exception as e:
                if not self.running:
                    break
                
                # Calculate delay with exponential backoff
                delay = min(INITIAL_RETRY_DELAY * (2 ** self.retry_count), MAX_RETRY_DELAY)
                self.retry_count += 1
                self.last_restart_time = time.time()
                
                logger.error(f"Bot crashed: {str(e)}")
                logger.info(f"Restarting in {delay} seconds... (Attempt {self.retry_count}/{MAX_RETRIES})")
                
                # Stop the bot if it's still running
                await self._safe_stop_bot()
                
                # Stop after maximum retries
                if self.retry_count >= MAX_RETRIES:
                    logger.error(f"Maximum retries ({MAX_RETRIES}) reached. Stopping.")
                    self.running = False
                    break
                    
                await asyncio.sleep(delay)

    async def _monitor_bot(self):
        """Monitor the bot and detect connection issues"""
        try:
            # Use a simple event to keep the bot running
            stop_event = asyncio.Event()
            while self.running and self.bot:
                try:
                    # Check connection every 30 seconds
                    await asyncio.wait_for(stop_event.wait(), timeout=30)
                except asyncio.TimeoutError:
                    # Check if the bot is still connected
                    if hasattr(self.bot, "is_connected") and callable(self.bot.is_connected):
                        is_connected = False
                        try:
                            is_connected = await self.bot.is_connected()
                        except Exception as e:
                            logger.error(f"Connection check failed: {e}")
                            
                        if not is_connected:
                            logger.warning("Bot disconnected. Restarting...")
                            break
        except asyncio.CancelledError:
            logger.info("Bot monitor task cancelled")
        except Exception as e:
            logger.error(f"Error in bot monitor: {e}")

    async def _safe_stop_bot(self):
        """Safely stop the bot if it's running"""
        if self.bot:
            try:
                await self.bot.stop()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")
            self.bot = None

    async def stop(self):
        """Stop the bot runner"""
        self.running = False
        await self._safe_stop_bot()
        logger.info("Bot runner stopped")

def shutdown_handler(sig, frame):
    """Handle shutdown signals"""
    print(f"Received exit signal {sig}")
    # We can't call async functions directly from a signal handler
    # Just exit and let the atexit handlers clean up
    raise KeyboardInterrupt

async def main():
    """Main entry point"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Set up global exception handlers
    setup_global_handlers()
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(global_exception_handler)

    runner = BotRunner()
    try:
        await runner.start_bot()
    finally:
        await runner.stop()
        print("Bot has been shut down")

if __name__ == "__main__":
    try:
        # Setup the appropriate event loop based on platform
        setup_event_loop()
        
        # Always use a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(global_exception_handler)
        setup_global_handlers()
        
        # Log event loop implementation
        loop_class = loop.__class__.__name__
        logger.info(f"Using event loop: {loop_class}")
        
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        try:
            # Clean up pending tasks
            pending = asyncio.all_tasks(loop)
            if pending:
                print(f"Cleaning up {len(pending)} pending tasks...")
                for task in pending:
                    task.cancel()
                
                # Give tasks a chance to properly cancel
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        # Close the event loop properly
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            loop.close()
        
        print("Bot shut down")

# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01
