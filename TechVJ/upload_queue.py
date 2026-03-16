# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import io
from typing import Optional, Callable
from pyrogram.errors import FloodWait

# Upload queue
upload_queue = asyncio.Queue()


async def queue_upload(
    upload_func: Callable,
    user_id: int,
    *args,
    **kwargs
) -> bool:
    """
    Queue an upload operation with flood wait protection.
    
    Args:
        upload_func: The async upload function to call
        user_id: User ID for rate limiting
        *args, **kwargs: Arguments to pass to upload_func
    
    Returns:
        True if successful, False otherwise
    """
    await upload_queue.put({
        'func': upload_func,
        'user_id': user_id,
        'args': args,
        'kwargs': kwargs
    })
    return True


async def process_upload_queue(max_retries: int = 3) -> None:
    """
    Process upload queue with flood wait handling.
    Run this in background as a task.
    """
    while True:
        try:
            item = await upload_queue.get()
            
            upload_func = item['func']
            user_id = item['user_id']
            args = item['args']
            kwargs = item['kwargs']
            
            # Retry with exponential backoff
            for attempt in range(max_retries):
                try:
                    await upload_func(*args, **kwargs)
                    break
                except FloodWait as e:
                    wait_time = e.value
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise
            
            upload_queue.task_done()
        except Exception as e:
            print(f"[UPLOAD QUEUE] Error: {e}")
            await asyncio.sleep(1)
