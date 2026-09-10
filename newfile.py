import os
import zipfile
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

API_TOKEN = "8981641534:AAGdt2NCwbd5AFiPhTHOWxMDtIm8ij2_MK4"  # ضع توكن البوت هنا

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# حالات المحادثة
class BotStates(StatesGroup):
    waiting_for_zip = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    welcome_text = (
        "مرحباً! 👋\n\n"
        "أرسل ملف ZIP يحتوي على جلسات .session\n"
        "وسأعرض لك الأرقام واحدًا تلو الآخر مع إمكانية جلب الكود.\n\n"
        "⏳ ملفاتك تُحذف تلقائيًا بعد المعالجة."
    )
    await message.answer(welcome_text)
    await state.set_state(BotStates.waiting_for_zip)

@dp.message(BotStates.waiting_for_zip, F.document)
async def handle_zip(message: types.Message, state: FSMContext):
    document = message.document
    if not document.file_name.endswith('.zip'):
        await message.answer("⚠️ يرجى إرسال ملف بصيغة ZIP فقط.")
        return

    waiting_msg = await message.answer("⏳ جاري استخراج الجلسات...")
    
    file_info = await bot.get_file(document.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    
    extract_dir = f"sessions_{message.from_user.id}"
    os.makedirs(extract_dir, exist_ok=True)
    
    zip_path = os.path.join(extract_dir, "sessions.zip")
    with open(zip_path, "wb") as f:
        f.write(downloaded_file.read())
        
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
        
    # البحث عن ملفات الجلسة
    session_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.session'):
                session_files.append(os.path.join(root, file))
                
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=waiting_msg.message_id,
        text=f"✅ تم العثور على {len(session_files)} جلسة."
    )
    
    if not session_files:
        await message.answer("⚠️ لم يتم العثور على أي ملفات .session داخل ملف الـ ZIP.")
        return

    # معالجة الجلسات
    for idx, sess_path in enumerate(session_files, 1):
        sess_name = os.path.basename(sess_path)
        # ملاحظة: API_ID و API_HASH افتراضية أو عامة لتطبيق Telegram (يمكنك استبدالها)
        API_ID = 611335
        API_HASH = 'd524b414d21f4d37f08684c1df41ac9d'
        
        client = TelegramClient(sess_path.replace('.session', ''), API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                phone = f"+{me.phone}" if me.phone else "غير متوفر"
                
                # جلب آخر رسالة من Telegram (خدمة المصادقة 777000 أو رسمية) لجلب الكود
                code = "لا يوجد كود حديث"
                async for dialog in client.iter_dialogs(limit=5):
                    if dialog.id == 777000:
                        async for msg in client.iter_messages(dialog, limit=1):
                            code = msg.text
                        break
                
                builder = InlineKeyboardBuilder()
                builder.button(text="🔄 إعادة جلب الكود", callback_data=f"refresh_{idx}")
                builder.button(text="🚪 تسجيل خروج من الرقم", callback_data=f"logout_{idx}")
                builder.adjust(1)
                
                response_text = (
                    f"📞 {phone}\n"
                    f"✉️ الكود: {code}"
                )
                await message.answer(response_text, reply_markup=builder.as_markup())
            else:
                await message.answer(f"⚠️ الجلسة {sess_name} غير مسجل دخولها أو منتهية الصلاحية.")
        except Exception as e:
            await message.answer(f"❌ حدث خطأ في قراءة الجلسة {sess_name}: {str(e)}")
        finally:
            await client.disconnect()
            
    await message.answer("✅ تم الانتهاء من جميع الأرقام.")
    
    # تنظيف الملفات
    for f in os.listdir(extract_dir):
        try:
            os.remove(os.path.join(extract_dir, f))
        except:
            pass
    try:
        os.rmdir(extract_dir)
    except:
        pass

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())