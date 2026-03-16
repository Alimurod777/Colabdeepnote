# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

"""
Quick start guide for flood wait protection.
"""

import asyncio
from TechVJ.flood_control import flood_controller
from TechVJ.upload_queue import queue_upload, process_upload_queue


# Example 1: Check before uploading
async def example_check_flood():
    user_id = 123456789
    await flood_controller.wait_if_needed(user_id)
    print("Safe to upload!")


# Example 2: Handle flood wait
async def example_handle_flood():
    user_id = 123456789
    wait_seconds = 45
    await flood_controller.handle_flood_wait(user_id, wait_seconds)
    print(f"User {user_id} is rate limited for {wait_seconds}s")


# Example 3: Process upload queue
async def example_queue_processing():
    """Start this as a background task when bot starts."""
    await process_upload_queue(max_retries=3)


# Integration checklist:
# 1. ✅ Import flood_controller in your upload handler
# 2. ✅ Call wait_if_needed() before sending files
# 3. ✅ Call handle_flood_wait() in FloodWait exception handler
# 4. ✅ Add 1-2 second delays between multiple uploads
# 5. ✅ Test with /api/upload endpoint for rate limiting

__all__ = ['flood_controller', 'queue_upload', 'process_upload_queue']
