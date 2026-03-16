# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import time
import logging
from typing import Dict
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)


class FloodWaitController:
    """
    Minimal flood wait protection system.
    Manages per-user upload queue with exponential backoff.
    """
    
    def __init__(self):
        self.user_locks: Dict[int, asyncio.Lock] = {}
        self.user_wait_until: Dict[int, float] = {}
        self.user_retry_delay: Dict[int, float] = {}
        
    async def wait_if_needed(self, user_id: int) -> None:
        """Wait if user hit flood limit"""
        now = time.time()
        wait_until = self.user_wait_until.get(user_id, 0)
        
        if now < wait_until:
            sleep_time = wait_until - now
            logger.warning(f"User {user_id}: FloodWait {sleep_time:.1f}s")
            await asyncio.sleep(sleep_time)
    
    async def handle_flood_wait(self, user_id: int, flood_wait_seconds: int) -> None:
        """Handle FloodWait error"""
        self.user_wait_until[user_id] = time.time() + flood_wait_seconds
        logger.warning(f"User {user_id}: FloodWait set to {flood_wait_seconds}s")
    
    def get_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create lock for user"""
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]
    
    async def acquire(self, user_id: int) -> None:
        """Acquire lock and check flood wait"""
        lock = self.get_lock(user_id)
        await lock.acquire()
        await self.wait_if_needed(user_id)
    
    def release(self, user_id: int) -> None:
        """Release lock"""
        lock = self.get_lock(user_id)
        if lock.locked():
            lock.release()


# Global instance
flood_controller = FloodWaitController()
