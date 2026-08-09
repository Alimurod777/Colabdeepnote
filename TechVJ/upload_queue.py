# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio
import io
import time
import logging
from typing import Optional, Callable
from pyrogram.errors import FloodWait
from TechVJ.flood_control import flood_controller

logger = logging.getLogger(__name__)

UPLOAD_WORKER_COUNT = 8
DEFAULT_UPLOAD_DELAY = 0.4
MIN_UPLOAD_DELAY = 0.2
MAX_UPLOAD_DELAY = 6.0

# Upload queue
upload_queue = asyncio.Queue()
_user_last_upload: dict[int, float] = {}
_workers_started = False


async def queue_upload(
    upload_func: Callable,
    user_id: int,
    *args,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
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
        'kwargs': kwargs,
        'on_complete': on_complete,
        'on_error': on_error,
    })
    return True


def start_upload_workers(worker_count: int = UPLOAD_WORKER_COUNT, max_retries: int = 3) -> None:
    """Start background upload workers once."""
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    for idx in range(worker_count):
        asyncio.create_task(_upload_worker(idx, max_retries=max_retries))


def _get_target_delay(user_id: int) -> float:
    base_delay = DEFAULT_UPLOAD_DELAY
    adaptive_delay = flood_controller.get_upload_delay(user_id, base_delay, MAX_UPLOAD_DELAY)
    return max(MIN_UPLOAD_DELAY, adaptive_delay)


async def _apply_smart_delay(user_id: int) -> None:
    last_time = _user_last_upload.get(user_id)
    if last_time is None:
        return
    target_delay = _get_target_delay(user_id)
    elapsed = time.time() - last_time
    if elapsed < target_delay:
        await asyncio.sleep(target_delay - elapsed)


def _record_upload_time(user_id: int) -> None:
    _user_last_upload[user_id] = time.time()


async def _run_callback(cb: Optional[Callable], **kwargs) -> None:
    if not cb:
        return
    try:
        result = cb(**kwargs)
        if asyncio.iscoroutine(result):
            await result
    except Exception as cb_err:
        logger.warning(f"[UPLOAD QUEUE] Callback error: {cb_err}")


async def _upload_worker(worker_id: int, max_retries: int = 3) -> None:
    while True:
        item = await upload_queue.get()
        try:
            upload_func = item['func']
            user_id = item['user_id']
            args = item['args']
            kwargs = item['kwargs']
            on_complete = item.get('on_complete')
            on_error = item.get('on_error')

            await _apply_smart_delay(user_id)

            success = False
            last_error = None

            for attempt in range(max_retries):
                try:
                    result = await upload_func(*args, user_id=user_id, **kwargs)
                    success = result is None or bool(result)
                    last_error = None
                    break
                except FloodWait as e:
                    wait_time = getattr(e, 'value', getattr(e, 'x', 0))
                    await flood_controller.handle_flood_wait(user_id, int(wait_time))
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    raise
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise

            _record_upload_time(user_id)

            if success:
                await _run_callback(on_complete, success=True, error=None)
            else:
                await _run_callback(on_error, success=False, error=last_error)
        except Exception as e:
            logger.warning(f"[UPLOAD QUEUE] Worker {worker_id} error: {e}")
            await _run_callback(item.get('on_error'), success=False, error=e)
        finally:
            upload_queue.task_done()


async def process_upload_queue(max_retries: int = 3) -> None:
    """
    Process upload queue with flood wait handling.
    Run this in background as a task.
    """
    await _upload_worker(0, max_retries=max_retries)
