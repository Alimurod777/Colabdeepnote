
"""
progress_store.py — Disk-free progress tracking with speed & ETA.
Disk .txt fayllar o'rniga RAM dict ishlatiladi.
"""
from __future__ import annotations
import time

# key: f"{msg_id}_down" | f"{msg_id}_up"
# value: {"current": int, "total": int, "start_time": float, "last_time": float, "last_bytes": int}
_store: dict[str, dict] = {}


def write_progress(key: str, current: int, total: int) -> None:
    """Progress ma'lumotini RAMga yozadi."""
    if total <= 0:
        return
    now = time.time()
    if key not in _store:
        _store[key] = {
            "current": current,
            "total": total,
            "start_time": now,
            "last_time": now,
            "last_bytes": 0,
        }
    else:
        _store[key]["current"] = current
        _store[key]["total"] = total
        _store[key]["last_time"] = now


def read_progress(key: str) -> str:
    """Hozirgi progress — fomat: '45.2% • 12.3 MB/s • ETA: 1m 23s'"""
    data = _store.get(key)
    if not data:
        return "0.0%"

    current = data["current"]
    total = data["total"]
    start_time = data["start_time"]
    now = time.time()

    percent = current * 100 / total
    elapsed = now - start_time

    # Tezlik: o'rtacha (barqaror ko'rsatgich)
    speed = current / elapsed if elapsed > 0.5 else 0  # bytes/sec

    # ETA
    remaining = total - current
    if speed > 0:
        eta_sec = int(remaining / speed)
        if eta_sec >= 3600:
            eta_str = f"{eta_sec // 3600}h {(eta_sec % 3600) // 60}m"
        elif eta_sec >= 60:
            eta_str = f"{eta_sec // 60}m {eta_sec % 60}s"
        else:
            eta_str = f"{eta_sec}s"
    else:
        eta_str = "—"

    # Bayt → odam o'qiydigan format
    def fmt_bytes(b: int) -> str:
        if b >= 1_073_741_824:
            return f"{b / 1_073_741_824:.2f} GB"
        elif b >= 1_048_576:
            return f"{b / 1_048_576:.1f} MB"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    speed_str = f"{fmt_bytes(int(speed))}/s" if speed > 0 else "—"
    done_str = fmt_bytes(current)
    total_str = fmt_bytes(total)

    return f"{percent:.1f}% • {done_str}/{total_str} • {speed_str} • ETA: {eta_str}"


def clear_progress(key: str) -> None:
    """Key ni o'chiradi (download/upload tugagandan keyin)."""
    _store.pop(key, None)
