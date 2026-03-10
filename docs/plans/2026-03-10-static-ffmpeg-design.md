# Static FFmpeg Auto-Install Design

**Date:** 2026-03-10

## Maqsad

Tizimda ffmpeg o'rnatilmagan bo'lsa, `pip install -r requirements.txt` bilan avtomatik static ffmpeg binary yuklanishi va ishlatilishi.

## O'zgarishlar

### 1. `requirements.txt`
`static-ffmpeg>=2.5` qatori qo'shiladi.

### 2. `TechVJ/save.py` — `get_ffmpeg()` yangilash

Priority tartibi:
1. System ffmpeg (`shutil.which("ffmpeg")`)
2. `static-ffmpeg` paketi (`static_ffmpeg.add_paths()` → PATH ga qo'shiladi)
3. `staticfiles/ffmpeg` manual binary (zaxira)
4. `None` — ffmpeg mavjud emas

```python
def get_ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        if shutil.which("ffmpeg"):
            return "ffmpeg"
    except ImportError:
        pass
    if os.path.exists(STATIC_FFMPEG_PATH) and os.access(STATIC_FFMPEG_PATH, os.X_OK):
        return STATIC_FFMPEG_PATH
    return None
```
