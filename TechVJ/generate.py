# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import traceback
import asyncio
import os
import io
import glob
import logging
import qrcode
from pyrogram.types import Message
from pyrogram import Client, filters
from asyncio.exceptions import TimeoutError
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid
)
from TechVJ.strings import strings
from config import API_ID, API_HASH
from database.db import database

logger = logging.getLogger(__name__)

SESSION_STRING_SIZE = 351

def get(obj, key, default=None):
    try:
        return obj[key]
    except:
        return default

@Client.on_message(filters.private & ~filters.forwarded & filters.command(["logout"]))
async def logout(_, msg):
    user_data = database.find_one({"chat_id": msg.chat.id})
    if user_data is None or not user_data.get('session'):
        return 
    data = {
        'session': None,
        'logged_in': False,
        'is_premium': False,
    }
    database.update_one({'_id': user_data['_id']}, {'$set': data})
    await msg.reply("**Logout Successfully** ♦")

@Client.on_message(filters.private & ~filters.forwarded & filters.command(["login"]))
async def main(bot: Client, message: Message):
    database.insert_one({"chat_id": message.from_user.id})
    user_data = database.find_one({"chat_id": message.from_user.id})
    if get(user_data, 'logged_in', False):
        await message.reply(strings['already_logged_in'])
        return 
    user_id = int(message.from_user.id)
    try:
        phone_number_msg = await bot.ask(
            chat_id=user_id,
            text="<b>Please send your phone number which includes country code</b>\n<b>Example:</b> <code>+13124562345, +9171828181889</code>",
            filters=filters.text,
            timeout=300,
        )
    except TimeoutError:
        logger.warning(f"User {user_id}: phone number input timeout")
        await bot.send_message(user_id, "⏰ **Vaqt tugadi.** Telefon raqam kiritilmadi.\nQayta boshlash uchun /login yuboring.")
        return
    except Exception as e:
        logger.error(f"User {user_id}: phone ask error: {e}")
        await bot.send_message(user_id, f"**Xatolik yuz berdi:** `{e}`\nQayta urinib ko'ring: /login")
        return

    if phone_number_msg.text == '/cancel':
        return await phone_number_msg.reply('<b>process cancelled !</b>')
    phone_number = phone_number_msg.text

    # Create sessions directory if it doesn't exist
    os.makedirs("sessions", exist_ok=True)
    session_path = f"sessions/temp_user_{user_id}"

    client = Client(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        await phone_number_msg.reply("Sending OTP...")
        try:
            code = await client.send_code(phone_number)
        except PhoneNumberInvalid:
            await phone_number_msg.reply('`PHONE_NUMBER` **is invalid.**')
            return

        try:
            phone_code_msg = await bot.ask(
                user_id,
                "Please check for an OTP in official telegram account. If you got it, send OTP here after reading the below format. \n\nIf OTP is `12345`, **please send it as** `1 2 3 4 5`.\n\n**Enter /cancel to cancel The Procces**",
                filters=filters.text,
                timeout=600,
            )
        except TimeoutError:
            logger.warning(f"User {user_id}: OTP input timeout (600s)")
            await bot.send_message(user_id, "⏰ **OTP kiritish vaqti tugadi (10 daqiqa).**\nQayta boshlash uchun /login yuboring.")
            return
        except Exception as e:
            logger.error(f"User {user_id}: OTP ask error: {e}")
            await bot.send_message(user_id, f"**Xatolik yuz berdi:** `{e}`\nQayta urinib ko'ring: /login")
            return

        if phone_code_msg.text == '/cancel':
            return await phone_code_msg.reply('<b>process cancelled !</b>')
        try:
            phone_code = phone_code_msg.text.replace(" ", "")
            await client.sign_in(phone_number, code.phone_code_hash, phone_code)
        except PhoneCodeInvalid:
            await phone_code_msg.reply('**OTP is invalid.**')
            return
        except PhoneCodeExpired:
            await phone_code_msg.reply('**OTP is expired.**')
            return
        except SessionPasswordNeeded:
            try:
                two_step_msg = await bot.ask(
                    user_id,
                    '**Your account has enabled two-step verification. Please provide the password.\n\nEnter /cancel to cancel The Procces**',
                    filters=filters.text,
                    timeout=300,
                )
            except TimeoutError:
                logger.warning(f"User {user_id}: 2FA password input timeout")
                await bot.send_message(user_id, "⏰ **2FA parol kiritish vaqti tugadi.**\nQayta boshlash uchun /login yuboring.")
                return
            except Exception as e:
                logger.error(f"User {user_id}: 2FA ask error: {e}")
                await bot.send_message(user_id, f"**Xatolik yuz berdi:** `{e}`\nQayta urinib ko'ring: /login")
                return

            if two_step_msg.text == '/cancel':
                return await two_step_msg.reply('<b>process cancelled !</b>')
            try:
                password = two_step_msg.text
                await client.check_password(password=password)
            except PasswordHashInvalid:
                await two_step_msg.reply('**Invalid Password Provided**')
                return
        string_session = await client.export_session_string()
        # is_premium ni disconnect dan OLDIN aniqlash
        try:
            me = await client.get_me()
            is_premium = getattr(me, 'is_premium', False) or False
        except Exception:
            is_premium = False
        await client.disconnect()
        if len(string_session) < SESSION_STRING_SIZE:
            return await message.reply('<b>invalid session sring</b>')
        try:
            user_data = database.find_one({"chat_id": message.from_user.id})
            if user_data is not None:
                data = {
                    'session': string_session,
                    'logged_in': True,
                    'is_premium': is_premium,
                }

                database.update_one({'_id': user_data['_id']}, {'$set': data})
        except Exception as e:
            return await message.reply_text(f"<b>ERROR IN LOGIN:</b> `{e}`")
        await bot.send_message(message.from_user.id, "<b>Account Login Successfully.\n\nIf You Get Any Error Related To AUTH KEY Then /logout and /login again</b>")
    finally:
        # Ensure client is disconnected
        try:
            await client.disconnect()
        except:
            pass
        
        # Clean up temporary session file
        try:
            if os.path.exists(f"{session_path}.session"):
                os.remove(f"{session_path}.session")
        except:
            pass


@Client.on_message(filters.private & ~filters.forwarded & filters.command(["qrlogin"]))
async def qr_login(bot: Client, message: Message):
    user_id = message.from_user.id

    database.insert_one({"chat_id": user_id})
    user_data = database.find_one({"chat_id": user_id})

    if user_data and user_data.get("logged_in"):
        await message.reply("**Siz allaqachon login qilgansiz.**\nQayta login uchun avval /logout qiling.")
        return

    status_msg = await message.reply("**QR kod tayyorlanmoqda...**")

    session_path = f"sessions/temp_qr_{user_id}"
    os.makedirs("sessions", exist_ok=True)
    client = Client(session_path, API_ID, API_HASH)
    qr_msg = None

    try:
        await client.connect()

        qr_login_obj = await client.qr_login()

        qr_img = qrcode.make(qr_login_obj.url)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)

        await status_msg.delete()
        qr_msg = await bot.send_photo(
            chat_id=user_id,
            photo=buf,
            caption=(
                "**QR kod orqali login:**\n\n"
                "1. Telegramni oching (boshqa qurilmada)\n"
                "2. Settings → Devices → Scan QR Code\n"
                "3. Ushbu QR kodni skanlang\n\n"
                "_QR kod 30 soniyada yangilanadi_"
            )
        )

        try:
            await asyncio.wait_for(qr_login_obj.wait(), timeout=30)
        except asyncio.TimeoutError:
            await qr_login_obj.recreate()
            qr_img2 = qrcode.make(qr_login_obj.url)
            buf2 = io.BytesIO()
            qr_img2.save(buf2, format="PNG")
            buf2.seek(0)
            await qr_msg.delete()
            qr_msg = await bot.send_photo(
                chat_id=user_id,
                photo=buf2,
                caption="**Yangilangan QR kod** (30 soniya):\n\nTelegramda Scan QR Code bosing."
            )
            await asyncio.wait_for(qr_login_obj.wait(), timeout=30)

        # Export session BEFORE disconnect (inside try block)
        string_session = await client.export_session_string()

        if len(string_session) < 351:
            await bot.send_message(user_id, "**Noto'g'ri session string. Qayta urinib ko'ring.**")
            return

        try:
            me = await client.get_me()
            is_premium = getattr(me, 'is_premium', False) or False
        except Exception:
            is_premium = False

        data = {"session": string_session, "logged_in": True, "is_premium": is_premium}
        database.update_one({"chat_id": user_id}, {"$set": data})
        await bot.send_message(user_id, "**QR orqali login muvaffaqiyatli!**\n\nAgar xato chiqsa /logout va /qrlogin ni qayta ishlating.")

    except SessionPasswordNeeded:
        try:
            try:
                pwd_msg = await bot.ask(
                    user_id,
                    "**2FA parol kerak. Iltimos parolni kiriting:**\n\n/cancel — bekor qilish",
                    filters=filters.text,
                    timeout=300
                )
            except TimeoutError:
                logger.warning(f"User {user_id}: QR 2FA password input timeout")
                await bot.send_message(user_id, "⏰ **2FA parol kiritish vaqti tugadi.**\nQayta boshlash uchun /qrlogin yuboring.")
                return
            except Exception as e:
                logger.error(f"User {user_id}: QR 2FA ask error: {e}")
                await bot.send_message(user_id, f"**Xatolik yuz berdi:** `{e}`")
                return

            if pwd_msg.text == "/cancel":
                await pwd_msg.reply("**Bekor qilindi.**")
                return
            await client.check_password(pwd_msg.text)
            # After 2FA, export session
            string_session = await client.export_session_string()
            if len(string_session) < 351:
                await bot.send_message(user_id, "**Noto'g'ri session string.**")
                return
            try:
                me = await client.get_me()
                is_premium = getattr(me, 'is_premium', False) or False
            except Exception:
                is_premium = False
            data = {"session": string_session, "logged_in": True, "is_premium": is_premium}
            database.update_one({"chat_id": user_id}, {"$set": data})
            await bot.send_message(user_id, "**QR orqali login muvaffaqiyatli!**\n\nAgar xato chiqsa /logout va /qrlogin ni qayta ishlating.")
        except PasswordHashInvalid:
            await bot.send_message(user_id, "**Noto'g'ri parol.**")
        except Exception:
            await bot.send_message(user_id, "**2FA jarayonida xato yuz berdi.**")
    except asyncio.TimeoutError:
        await bot.send_message(user_id, "**QR kod muddati tugadi. /qrlogin ni qayta yuboring.**")
    except Exception as e:
        await bot.send_message(user_id, f"**Xato:** `{e}`")
    finally:
        if qr_msg:
            try:
                await qr_msg.delete()
            except Exception:
                pass
        try:
            await client.disconnect()
        except Exception:
            pass
        try:
            for f in glob.glob(f"{session_path}*"):
                os.remove(f)
        except Exception:
            pass


# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01
