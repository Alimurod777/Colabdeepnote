import asyncio
import traceback
import platform
from flask import Flask, jsonify, request
import threading
from main import Bot
import json
from TechVJ.flood_control import flood_controller
import io
import os
import time as time_module

# Setup uvloop for improved performance if not on Windows
def setup_event_loop():
    if platform.system() != "Windows":
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            print("uvloop installed successfully")
        except ImportError:
            print("uvloop not available, using default event loop")
    else:
        # Use new event loop policy for Windows to avoid issues
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy') and asyncio.get_event_loop_policy().__class__.__name__ != 'WindowsSelectorEventLoopPolicy':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            print("Using WindowsSelectorEventLoopPolicy")

# Initialize uvloop
setup_event_loop()

app = Flask(__name__)
bot = None
bot_thread = None
bot_event_loop = None

@app.route('/')
def hello_world():
    global bot, bot_thread
    bot_status = "Running" if bot_thread and bot_thread.is_alive() else "Not running"
    return jsonify({
        "status": "active",
        "message": "Telegram Save Restricted Content Bot",
        "bot_status": bot_status
    })

@app.route('/status')
def status():
    global bot, bot_thread
    bot_status = "Running" if bot_thread and bot_thread.is_alive() else "Not running"
    return jsonify({
        "status": "active",
        "bot_status": bot_status
    })

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """
    Minimal flood wait protected upload endpoint.
    POST /api/upload with JSON body containing upload parameters.
    """
    global bot, bot_event_loop
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"status": "error", "message": "user_id required"}), 400
        
        # Check flood wait
        flood_wait = flood_controller.user_wait_until.get(user_id, 0)
        import time
        now = time.time()
        if now < flood_wait:
            wait_time = int(flood_wait - now)
            return jsonify({
                "status": "flood_wait",
                "wait_seconds": wait_time,
                "message": f"Please wait {wait_time} seconds"
            }), 429
        
        # Queue upload to bot event loop
        if bot and bot_event_loop:
            # Create a coroutine to run in bot's event loop
            async def process_upload():
                try:
                    # Your upload processing logic here
                    # For now, just acknowledge
                    return True
                except Exception as e:
                    print(f"Upload error: {e}")
                    return False
            
            # Schedule the coroutine
            future = asyncio.run_coroutine_threadsafe(process_upload(), bot_event_loop)
            result = future.result(timeout=30)
            
            return jsonify({
                "status": "success",
                "message": "Upload queued"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Bot not running"
            }), 503
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def run_bot():
    global bot, bot_event_loop
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot_event_loop = loop
        
        # Log event loop implementation
        loop_class = loop.__class__.__name__
        print(f"Bot running with event loop: {loop_class}")
        
        bot = Bot()
        bot.run()
    except Exception as e:
        print(f"Bot crashed with error: {e}")
        print(traceback.format_exc())
        # Try to restart the bot after a delay
        asyncio.sleep(5)
        run_bot()  # Attempt to restart

def start_bot_thread():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        return True
    return False

@app.route('/restart')
def restart_bot():
    global bot, bot_thread
    if bot_thread and bot_thread.is_alive():
        # We can't directly stop the thread, but we can create a new one
        bot_thread = None
    
    success = start_bot_thread()
    return jsonify({
        "status": "success" if success else "already_running",
        "message": "Bot restart initiated" if success else "Bot is already running"
    })

if __name__ == "__main__":
    # Start the bot in a separate thread
    start_bot_thread()
    # Run Flask app
    app.run(host='0.0.0.0', port=8080)

