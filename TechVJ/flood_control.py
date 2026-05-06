# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)


UPLOAD_CONCURRENCY_LIMIT = 2


class FloodWaitController:
    """
    Minimal flood wait protection system.
    Manages per-user upload queue with exponential backoff.
    """
    
    def __init__(self):
        self.user_locks: Dict[int, asyncio.Lock] = {}
        self.user_wait_until: Dict[int, float] = {}
        self.user_retry_delay: Dict[int, float] = {}
        self.user_upload_semaphores: Dict[int, asyncio.Semaphore] = {}
        self.user_last_flood_wait: Dict[int, float] = {}
        self.user_last_flood_time: Dict[int, float] = {}
        
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
        self.user_last_flood_wait[user_id] = float(flood_wait_seconds)
        self.user_last_flood_time[user_id] = time.time()
        logger.warning(f"User {user_id}: FloodWait set to {flood_wait_seconds}s")

    def get_recent_flood_wait(self, user_id: int, window_seconds: int = 300) -> float:
        """Return recent FloodWait value if it happened within the given window."""
        last_time = self.user_last_flood_time.get(user_id)
        if not last_time:
            return 0.0
        if time.time() - last_time > window_seconds:
            return 0.0
        return float(self.user_last_flood_wait.get(user_id, 0.0))

    def get_upload_delay(self, user_id: int, base_delay: float, max_delay: float) -> float:
        """Compute adaptive delay based on recent FloodWait feedback."""
        flood_wait = self.get_recent_flood_wait(user_id)
        if flood_wait <= 0:
            return base_delay
        return min(max_delay, max(base_delay, flood_wait / 2))
    
    def get_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create lock for user"""
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]

    def get_upload_semaphore(self, user_id: int) -> asyncio.Semaphore:
        """Get or create upload semaphore for user"""
        if user_id not in self.user_upload_semaphores:
            self.user_upload_semaphores[user_id] = asyncio.Semaphore(UPLOAD_CONCURRENCY_LIMIT)
        return self.user_upload_semaphores[user_id]

    @asynccontextmanager
    async def upload_slot(self, user_id: int):
        """Acquire and release an upload slot for a user."""
        semaphore = self.get_upload_semaphore(user_id)
        await semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()
    
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
