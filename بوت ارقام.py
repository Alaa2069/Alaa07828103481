import asyncio
import json
import os
import random
import re
import time

from telethon import Button, TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    MessageIdInvalidError,
    MessageNotModifiedError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    UserNotParticipantError,
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.messages import GetFullChatRequest

# ==================== البيانات الأساسية ====================
API_ID = 36456714
API_HASH = "c13dbc44c88677140a15dc96341b8dbe"
BOT_TOKEN = "8920829669:AAHCT16ySVuaDlfIDzIpsG16yQvsZXVjHQg"

ACC_FILE = "registered_accounts.json"
NUM_FILE = "numbers_for_sale.json"
USER_FILE = "user_data.json"
CONF_FILE = "bot_settings.json"
CARDS_FILE = "gift_cards.json"

client = TelegramClient("BotSessionV3", API_ID, API_HASH)

# ==================== الذاكرة المؤقتة ====================
u_clients = {}
code_reqs = {}
u_sessions = {}
avail_nums = {}
syyad_users = {}
gift_cards = {}
user_verifications = {}
admin_states = {}
pending_logins = {}

syyad_conf = {
    "admin_ids": ["541029541"],
    "dailyGiftPoints": 0.1,
    "referralPoints": 5,
    "force_channels": [], 
    "support_user": "@Telegram",
    "verification_enabled": True,
    "owner_id": "541029541",
    "binance_id": "123456789", 
    "superpay_name": "Alaa Ahmed Ali",
    "superpay_number": "7847602237",
}


# ==================== وظائف حفظ وتنسيق البيانات ====================
def load(fpath, d_val):
    if not os.path.exists(fpath):
        save(fpath, d_val)
        return d_val
    with open(fpath, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except Exception:
            return d_val


def save(fpath, data):
    with open(fpath, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def load_all():
    global u_sessions, avail_nums, syyad_users, syyad_conf, gift_cards
    u_sessions = load(ACC_FILE, {})
    avail_nums = load(NUM_FILE, {})
    syyad_users = load(USER_FILE, {})
    gift_cards = load(CARDS_FILE, {})
    loaded_settings = load(CONF_FILE, {})
    syyad_conf.update(loaded_settings)


def save_all():
    save(ACC_FILE, u_sessions)
    save(NUM_FILE, avail_nums)
    save(CONF_FILE, syyad_conf)
    save(USER_FILE, syyad_users)
    save(CARDS_FILE, gift_cards)


def get_user_data(uid, name=None, username=None):
    uid_str = str(uid)
    if uid_str not in syyad_users:
        syyad_users[uid_str] = {
            "points": 0,
            "stars": 0,
            "last_daily_gift": 0,
            "referred_by": None,
            "referral_count": 0,
            "verified": False,
            "name": name or "مستخدم",
            "username": username or "لا يوجد",
        }
        save(USER_FILE, syyad_users)
    else:
        if name:
            syyad_users[uid_str]["name"] = name
        if username:
            syyad_users[uid_str]["username"] = username
    return syyad_users[uid_str]


def is_adm(uid):
    return str(uid) in syyad_conf["admin_ids"] or str(uid) == str(
        syyad_conf.get("owner_id")
    )


def is_owner(uid):
    return str(uid) == str(syyad_conf.get("owner_id"))


# ==================== نظام الاشتراك الإجباري المتقدم ====================
async def check_sub(uid):
    channels = syyad_conf.get("force_channels", [])
    if not channels:
        return True, []

    unsubbed = []
    for ch in channels:
        ch_clean = ch.strip()
        if not ch_clean:
            continue
        
        target = ch_clean
        if "t.me/" in target:
            target = target.split("t.me/")[-1].replace("+", "").strip()
            if not target.startswith("@") and not target.startswith("-100"):
                target = f"@{target}"

        try:
            res = await client(GetParticipantRequest(channel=target, participant=uid))
            if not (res and res.participant):
                unsubbed.append(ch_clean)
        except UserNotParticipantError:
            unsubbed.append(ch_clean)
        except Exception:
            try:
                chat_info = await client(GetFullChatRequest(chat_id=int(target) if target.replace('-', '').isdigit() else target))
                participants = [p.user_id for p in chat_info.full_chat.participants.participants]
                if uid not in participants:
                    unsubbed.append(ch_clean)
            except Exception:
                unsubbed.append(ch_clean)

    return len(unsubbed) == 0, unsubbed


# ==================== إدارة حسابات التليجرام ====================
async def init_acc(phone, api_id, api_hash, sess_str):
    if phone in u_clients and u_clients[phone].is_connected():
        return True

    try:
        u_client = TelegramClient(StringSession(sess_str), api_id, api_hash)

        @u_client.on(events.NewMessage(incoming=True, chats=777000))
        async def proc_code_msg(event):
            code_match = re.search(r"\b(\d{5,6})\b", event.message.text)
            if code_match:
                code = code_match.group(1)
                buyer_id = code_reqs.get(phone)
                if buyer_id:
                    two_fa = u_sessions.get(phone, {}).get(
                        "two_factor_password", "لا يوجد"
                    )
                    msg = (
                        f"⚡️ **وصل كود التحقق بنجاح!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📞 **الرقم:** `{phone}`\n"
                        f"🔑 **الكود:** `{code}`\n"
                        f"🔐 **التحقق بخطوتين:** `{two_fa}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                    await client.send_message(
                        int(buyer_id),
                        msg,
                        buttons=[
                            [
                                Button.inline(
                                    "🚪 تسجيل الخروج وحذف الجلسة",
                                    data=f"delnum_{phone}",
                                )
                            ]
                        ],
                        parse_mode="markdown",
                    )

        await u_client.connect()
        if await u_client.is_user_authorized():
            u_clients[phone] = u_client
            return True
        else:
            return False
    except Exception as e:
        print(f"⚠️ فشل الاتصال بالحساب {phone}: {e}")
        return False


async def run_all_accs():
    tasks = []
    for phone, details in u_sessions.items():
        if details.get("session_str"):
            tasks.append(
                init_acc(
                    phone,
                    details.get("api_id", API_ID),
                    details.get("api_hash", API_HASH),
                    details["session_str"],
                )
            )
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ==================== الأوامر والقوائم ====================
@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    uid = event.sender_id
    uid_str = str(uid)
    
    sender = await event.get_sender()
    name = getattr(sender, "first_name", "مستخدم") if sender else "مستخدم"
    username = f"@{sender.username}" if sender and sender.username else "لا يوجد"

    u_data = get_user_data(uid, name=name, username=username)

    is_subbed, unsubbed_list = await check_sub(uid)
    if not is_subbed:
        buttons = []
        for idx, ch in enumerate(unsubbed_list, 1):
            clean_link = ch.replace("@", "").replace("https://t.me/", "").replace("http://t.me/", "")
            link_url = ch if ch.startswith("http") else f"https://t.me/{clean_link}"
            buttons.append([Button.url(f"📢 القناة/المجموعة ({idx})", link_url)])
        
        buttons.append([Button.inline("🔄 تحقق من الاشتراك الان", data="check_sub")])
        
        msg_text = (
            "⚠️ **عذراً عزيزي، يجب عليك الاشتراك في القنوات/المجموعات التالية لاستخدام البوت:**\n\n"
            "اشترك في جميع القنوات أعلاه ثم اضغط على زر **(تحقق من الاشتراك الان)** بالأسفل."
        )
        await event.respond(msg_text, buttons=buttons, parse_mode="markdown")
        return

    args = event.text.split()
    if len(args) > 1 and args[1].isdigit() and args[1] != uid_str:
        ref_id = args[1]
        if not u_data.get("referred_by"):
            u_data["referred_by"] = ref_id
            ref_data = get_user_data(ref_id)
            ref_data["points"] = round(ref_data["points"] + syyad_conf.get("referralPoints", 5), 2)
            ref_data["referral_count"] += 1
            save_all()
            try:
                await client.send_message(
                    int(ref_id),
                    f"🎉 **انضم مستخدم جديد عبر رابطك!**\nحصلت على `+{syyad_conf.get('referralPoints', 5)}` $.",
                )
            except Exception:
                pass

    if syyad_conf.get("verification_enabled") and not u_data.get("verified"):
        a, b = random.randint(1, 15), random.randint(1, 15)
        user_verifications[uid_str] = str(a + b)
        await event.respond(
            f"🤖 **اختبار أمان سريع:**\nكم حاصل جمع: `{a} + {b}` ؟\nأرسل الناتج برقم فقط.",
            parse_mode="markdown",
        )
        return

    await show_main_menu(event, is_callback=False)


async def show_main_menu(event, is_callback=False):
    uid = event.sender_id
    u_data = get_user_data(uid)

    msg = (
        f"👑 **أهلاً بك في بوت شراء الأرقام**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **بيانات حسابك:**\n"
        f"• 🆔 **الآيدي:** `{uid}`\n"
        f"• 💰 **الرصيد:** `{round(u_data['points'], 2)}` $\n"
        f"• 👥 **الإحالات:** `{u_data.get('referral_count', 0)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 **اختر الخدمات من القائمة أدناه:**"
    )

    support_url = syyad_conf.get("support_user", "@Telegram").replace("@", "https://t.me/")

    buttons = [
        [
            Button.inline("📱 شراء أرقام", data="buy_numbers"),
            Button.inline("💳 شحن الرصيد", data="recharge_menu"),
        ],
        [
            Button.inline("🎁 الهدية اليومية", data="daily_gift"),
            Button.inline("🎟 شحن كارت", data="use_card"),
        ],
        [
            Button.inline("🔗 رابط الإحالة", data="referral_link"),
            Button.inline("📜 سجل أرقامي", data="my_numbers_log"),
        ],
        [
            Button.inline("👤 حسابي", data="my_account"),
            Button.url("🛠 الدعم الفني", support_url),
        ],
    ]

    if is_owner(uid):
        buttons.append(
            [Button.inline("👑 لوحة تحكم المالك الكاملة", data="owner_main")]
        )
    elif is_adm(uid):
        buttons.append(
            [Button.inline("⚙️ لوحة الأدمن الاحترافية", data="admin_main")]
        )

    if is_callback:
        try:
            await event.edit(msg, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        except MessageIdInvalidError:
            await client.send_message(
                uid, msg, buttons=buttons, parse_mode="markdown"
            )
    else:
        await event.respond(msg, buttons=buttons, parse_mode="markdown")


# ==================== معالجة النصوص والإدخالات والوسائط ====================
@client.on(events.NewMessage)
async def message_handler(event):
    uid = event.sender_id
    uid_str = str(uid)
    text = event.text.strip() if event.text else ""

    if text.startswith("/"):
        return

    sender = await event.get_sender()
    name = getattr(sender, "first_name", "مستخدم") if sender else "مستخدم"
    username = f"@{sender.username}" if sender and sender.username else "لا يوجد"
    get_user_data(uid, name=name, username=username)

    if uid_str in user_verifications:
        if text == user_verifications[uid_str]:
            del user_verifications[uid_str]
            get_user_data(uid)["verified"] = True
            save_all()
            await event.respond("✅ **تم التأكد بنجاح!**")
            await show_main_menu(event, is_callback=False)
        else:
            await event.respond("❌ **إجابة خاطئة! حاول مرة أخرى.**")
        return

    if uid_str not in admin_states:
        return

    state = admin_states[uid_str].get("step")

    if state == "WAIT_SUPERPAY_PROOF":
        del admin_states[uid_str]
        sp_name = syyad_conf.get("superpay_name", "غير محدد")
        sp_num = syyad_conf.get("superpay_number", "غير محدد")
        
        msg_to_adm = (
            f"🔴 **طلب شحن جديد عبر تطبيق سوبركي (SuperPay)!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 👤 **المستخدم:** `{uid}`\n"
            f"• 📄 **التفاصيل/الملاحظة:** `{text if text else 'مرفق صورة/ملف إثبات'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"الحساب المستهدف:\n"
            f"• الاسم: `{sp_name}`\n"
            f"• الرقم: `{sp_num}`"
        )
        btns = [
            [
                Button.inline("✅ قبول وتحويل $", data=f"approve_sp_{uid}"),
                Button.inline("❌ رفض الطلب", data=f"reject_sp_{uid}"),
            ]
        ]
        
        for adm in syyad_conf["admin_ids"]:
            try:
                if event.media:
                    await client.send_file(int(adm), event.media, caption=msg_to_adm, buttons=btns, parse_mode="markdown")
                else:
                    await client.send_message(int(adm), msg_to_adm, buttons=btns, parse_mode="markdown")
            except Exception:
                pass

        await event.respond(
            "⏳ **تم إرسال إثبات الدفع (سوبركي) إلى الأدمن بنجاح!**\nسيتم مراجعة الطلب وإضافة الرصيد إلى حسابك فور التأكيد.",
            buttons=[[Button.inline("⬅️ القائمة الرئيسية", data="main_menu")]],
            parse_mode="markdown"
        )
        return

    if state == "WAIT_SUPERPAY_AMOUNT" and is_adm(uid):
        target_uid = admin_states[uid_str].get("target_user")
        del admin_states[uid_str]
        try:
            amount = float(text)
            if amount > 0:
                t_data = get_user_data(target_uid)
                t_data["points"] = round(t_data["points"] + amount, 2)
                save_all()
                try:
                    await client.send_message(
                        int(target_uid),
                        f"🎉 **تم قبول طلب الشحن الخاص بك عبر SuperPay!**\nتم إضافة `{amount}` $ إلى حسابك.",
                        parse_mode="markdown"
                    )
                except Exception:
                    pass
                await event.respond(
                    f"✅ **تم شحن `{amount}` $ بنجاح للمستخدم `{target_uid}`.**",
                    buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
                    parse_mode="markdown"
                )
            else:
                await event.respond("❌ **يرجى إدخال مبلغ أكبر من 0!**")
        except ValueError:
            await event.respond("❌ **يرجى إدخال رقم صحيح!**")
        return

    if is_adm(uid) and state == "WAIT_SET_SUPERPAY_NAME":
        del admin_states[uid_str]
        syyad_conf["superpay_name"] = text
        save_all()
        await event.respond(
            f"✅ **تم تحديث اسم حساب سوبركي بنجاح إلى:** `{text}`",
            buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
            parse_mode="markdown"
        )
        return

    if is_adm(uid) and state == "WAIT_SET_SUPERPAY_NUM":
        del admin_states[uid_str]
        syyad_conf["superpay_number"] = text
        save_all()
        await event.respond(
            f"✅ **تم تحديث رقم حساب سوبركي بنجاح إلى:** `{text}`",
            buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
            parse_mode="markdown"
        )
        return

    if state == "WAIT_BINANCE_PROOF":
        del admin_states[uid_str]
        binance_id = syyad_conf.get("binance_id", "غير محدد")
        msg_to_adm = (
            f"🟡 **طلب شحن جديد عبر باينانس Binance Pay!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 👤 **المستخدم:** `{uid}`\n"
            f"• 📄 **معرف/تفاصيل العملية:**\n`{text if text else 'مرفق صورة إثبات'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ملاحظة: تأكد من تحويل المبلغ إلى Binance ID: `{binance_id}`"
        )
        btns = [
            [
                Button.inline("✅ قبول وتحويل $", data=f"approve_bin_{uid}"),
                Button.inline("❌ رفض الطلب", data=f"reject_bin_{uid}"),
            ]
        ]
        for adm in syyad_conf["admin_ids"]:
            try:
                if event.media:
                    await client.send_file(int(adm), event.media, caption=msg_to_adm, buttons=btns, parse_mode="markdown")
                else:
                    await client.send_message(int(adm), msg_to_adm, buttons=btns, parse_mode="markdown")
            except Exception:
                pass
        await event.respond(
            "⏳ **تم إرسال إثبات الدفع إلى الأدمن بنجاح!**\nسيتم مراجعة الطلب وإضافة الرصيد إلى حسابك فور التأكيد.",
            buttons=[[Button.inline("⬅️ القائمة الرئيسية", data="main_menu")]],
            parse_mode="markdown"
        )
        return

    if state == "WAIT_BINANCE_AMOUNT" and is_adm(uid):
        target_uid = admin_states[uid_str].get("target_user")
        del admin_states[uid_str]
        try:
            amount = float(text)
            if amount > 0:
                t_data = get_user_data(target_uid)
                t_data["points"] = round(t_data["points"] + amount, 2)
                save_all()
                try:
                    await client.send_message(
                        int(target_uid),
                        f"🎉 **تم قبول طلب الشحن الخاص بك عبر Binance!**\nتم إضافة `{amount}` $ إلى حسابك.",
                        parse_mode="markdown"
                    )
                except Exception:
                    pass
                await event.respond(
                    f"✅ **تم شحن `{amount}` $ بنجاح للمستخدم `{target_uid}`.**",
                    buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
                    parse_mode="markdown"
                )
            else:
                await event.respond("❌ **يرجى إدخال مبلغ أكبر من 0!**")
        except ValueError:
            await event.respond("❌ **يرجى إدخال رقم صحيح!**")
        return

    if is_adm(uid) and state == "WAIT_SET_BINANCE_ID":
        del admin_states[uid_str]
        syyad_conf["binance_id"] = text
        save_all()
        await event.respond(
            f"✅ **تم تحديث Binance ID بنجاح إلى:** `{text}`",
            buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
            parse_mode="markdown"
        )
        return

    if state == "WAIT_CARD":
        del admin_states[uid_str]
        card_code = text
        if card_code in gift_cards and not gift_cards[card_code]["used"]:
            pts = gift_cards[card_code]["points"]
            gift_cards[card_code]["used"] = True
            gift_cards[card_code]["used_by"] = uid_str
            u_data = get_user_data(uid)
            u_data["points"] = round(u_data["points"] + pts, 2)
            save_all()
            await event.respond(
                f"🎉 **تم شحن الكارت بنجاح!**\nحصلت على `+{pts}` $.",
                buttons=[
                    [Button.inline("⬅️ القائمة الرئيسية", data="main_menu")]
                ],
                parse_mode="markdown",
            )
        else:
            await event.respond(
                "❌ **الكارت غير صحيح أو تم استخدامه من قبل!**",
                buttons=[
                    [Button.inline("⬅️ القائمة الرئيسية", data="main_menu")]
                ],
            )
        return

    if is_owner(uid) and state == "WAIT_GIVE_POINTS":
        del admin_states[uid_str]
        parts = text.split()
        if len(parts) == 2 and parts[0].isdigit():
            try:
                target_id = parts[0]
                amount = float(parts[1])
                target_data = get_user_data(target_id)
                target_data["points"] = round(target_data["points"] + amount, 2)
                save_all()
                await event.respond(
                    f"✅ **تم تعديل $ المستخدم `{target_id}` بنجاح!**\nالرصيد الجديد: `{target_data['points']}` $.",
                    buttons=[[Button.inline("⬅️ رجوع لوحة المالك", data="owner_main")]],
                    parse_mode="markdown"
                )
            except ValueError:
                await event.respond("❌ **يرجى إدخال رقم صحيح!**")
        else:
            await event.respond("❌ **صيغة غير صحيحة! أرسل الآيدي ثم المبلغ (مثال: `541029541 100` أو `541029541 0.5`).**")
        return

    if is_adm(uid):
        if state == "WAIT_SET_DAILY":
            del admin_states[uid_str]
            try:
                val = float(text)
                syyad_conf["dailyGiftPoints"] = val
                save_all()
                await event.respond(
                    f"✅ **تم تحديث $ الهدية اليومية إلى:** `{val}` $",
                    buttons=[
                        [Button.inline("⬅️ رجوع للوحة", data="admin_main")]
                    ],
                    parse_mode="markdown",
                )
            except ValueError:
                await event.respond("❌ **يرجى إدخال رقم صحيح (مثال: 0.1 أو 1)!**")
            return

        if state == "WAIT_SET_REF":
            del admin_states[uid_str]
            try:
                val = float(text)
                syyad_conf["referralPoints"] = val
                save_all()
                await event.respond(
                    f"✅ **تم تحديث $ الإحالة إلى:** `{val}` $",
                    buttons=[
                        [Button.inline("⬅️ رجوع للوحة", data="admin_main")]
                    ],
                    parse_mode="markdown",
                )
            except ValueError:
                await event.respond("❌ **يرجى إدخال رقم صحيح (مثال: 0.5 أو 5)!**")
            return

        if state == "WAIT_ADD_ADMIN":
            del admin_states[uid_str]
            if text.isdigit():
                if text not in syyad_conf["admin_ids"]:
                    syyad_conf["admin_ids"].append(text)
                    save_all()
                    await event.respond(
                        f"✅ **تم رفع المستخدم `{text}` كـ أدمن بنجاح!**",
                        buttons=[
                            [
                                Button.inline(
                                    "⬅️ رجوع للوحة", data="admin_main"
                                )
                            ]
                        ],
                        parse_mode="markdown",
                    )
                else:
                    await event.respond(
                        "⚠️ **هذا المستخدم أدمن بالفعل!**",
                        buttons=[
                            [
                                Button.inline(
                                    "⬅️ رجوع للوحة", data="admin_main"
                                )
                            ]
                        ],
                    )
            else:
                await event.respond("❌ **يرجى إدخال آيدي صحيح (أرقام فقط)!**")
            return

        if state == "WAIT_ADD_CHAN":
            del admin_states[uid_str]
            raw_list = re.split(r'[\s,\n]+', text)
            clean_list = [item.strip() for item in raw_list if item.strip()]
            
            current_chans = syyad_conf.get("force_channels", [])
            for ch in clean_list:
                if ch not in current_chans:
                    current_chans.append(ch)
            
            syyad_conf["force_channels"] = current_chans
            save_all()
            
            ch_text = "\n".join([f"• `{c}`" for c in current_chans])
            await event.respond(
                f"✅ **تم إضافة القنوات إلى قائمة الاشتراك الإجباري بنجاح:**\n\n{ch_text}",
                buttons=[[Button.inline("⬅️ رجوع لإعدادات الاشتراك", data="adm_set_chan")]],
                parse_mode="markdown",
            )
            return

        if state == "WAIT_SET_SUPPORT":
            del admin_states[uid_str]
            syyad_conf["support_user"] = text
            save_all()
            await event.respond(
                f"✅ **تم ضبط معرف الدعم الفني إلى:** `{text}`",
                buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
                parse_mode="markdown",
            )
            return

        if state == "WAIT_MAKE_CARD":
            del admin_states[uid_str]
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                try:
                    pts = float(parts[0])
                    count = int(parts[1])
                    created = []
                    for _ in range(count):
                        code = f"CARD-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))}"
                        gift_cards[code] = {
                            "points": pts,
                            "used": False,
                            "used_by": None,
                        }
                        created.append(code)
                    save_all()
                    msg = f"✅ **تم إنشاء {count} كروت شحن بنجاح:**\n\n"
                    for c in created:
                        msg += f"🎟 `{c}` ($: {pts})\n"
                    await event.respond(
                        msg,
                        buttons=[
                            [
                                Button.inline(
                                    "⬅️ رجوع للوحة", data="admin_main"
                                )
                            ]
                        ],
                        parse_mode="markdown",
                    )
                except ValueError:
                    await event.respond("❌ **صيغة غير صحيحة! أرسل (الرصيد $ العدد).**")
            else:
                await event.respond(
                    "❌ **صيغة غير صحيحة! أرسل (الرصيد $ العدد).**"
                )
            return

        if state == "WAIT_ADD_NUM_PHONE":
            phone = text
            admin_states[uid_str] = {"step": "WAIT_ADD_NUM_COUNTRY", "temp_phone": phone}
            await event.respond(
                f"🌍 **أدخل الدولة الخاصة بالرقم `{phone}`:**\n(مثال: امريكا، مصر، العراق...)",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
            return

        if state == "WAIT_ADD_NUM_COUNTRY":
            country = text
            phone = admin_states[uid_str].get("temp_phone")
            admin_states[uid_str] = {"step": "WAIT_ADD_NUM_PRICE", "temp_phone": phone, "temp_country": country}
            await event.respond(
                f"💰 **أدخل سعر الرقم (بالدولار $):**\n(مثال: `0.2` أو `1`)",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
            return

        if state == "WAIT_ADD_NUM_PRICE":
            try:
                price = float(text)
            except ValueError:
                await event.respond("❌ **السعر يجب أن يكون رقماً (مثال: 1 أو 0.2)! أعد إدخال السعر:**")
                return

            phone = admin_states[uid_str].get("temp_phone")
            country = admin_states[uid_str].get("temp_country")
            admin_states[uid_str] = {"step": "WAIT_ADD_NUM_2FA", "temp_phone": phone, "temp_country": country, "temp_price": price}
            await event.respond(
                f"🔐 **أدخل كلمة سر التحقق بخطوتين (2FA):**\n(إذا لم توجد أرسل: `لا يوجد`)",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
            return

        if state == "WAIT_ADD_NUM_2FA":
            two_fa = text if text else "لا يوجد"
            phone = admin_states[uid_str].get("temp_phone")
            country = admin_states[uid_str].get("temp_country")
            price = admin_states[uid_str].get("temp_price")

            temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
            await temp_client.connect()

            try:
                sent_code = await temp_client.send_code_request(phone)
                pending_logins[uid_str] = {
                    "phone": phone,
                    "price": price,
                    "country": country,
                    "two_fa": two_fa,
                    "phone_code_hash": sent_code.phone_code_hash,
                    "client": temp_client
                }
                admin_states[uid_str] = {"step": "WAIT_OTP_CODE"}
                await event.respond(
                    f"📩 **تم إرسال كود التحقق إلى التليجرام الخاص بالرقم `{phone}`.**\n\n"
                    f"الرجاء إرسال الكود الآن برقم فقط (مثال: `12345`):",
                    buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                    parse_mode="markdown"
                )
            except Exception as e:
                await temp_client.disconnect()
                del admin_states[uid_str]
                await event.respond(
                    f"❌ **فشل طلب الكود للرقم:**\n`{e}`",
                    buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]]
                )
            return

        if state == "WAIT_OTP_CODE":
            login_info = pending_logins.get(uid_str)
            if not login_info:
                del admin_states[uid_str]
                await event.respond("❌ انتهت الجلسة، حاول إضافة الرقم من جديد.")
                return

            otp = text.replace(" ", "")
            temp_client = login_info["client"]
            phone = login_info["phone"]

            try:
                await temp_client.sign_in(phone, otp, phone_code_hash=login_info["phone_code_hash"])
            except SessionPasswordNeededError:
                if login_info["two_fa"] != "لا يوجد":
                    try:
                        await temp_client.sign_in(password=login_info["two_fa"])
                    except Exception as e:
                        await event.respond(f"❌ **كلمة سر 2FA غير صحيحة:** {e}")
                        return
                else:
                    await event.respond("❌ **الحساب يتطلب كلمة سر 2FA، يرجى إرسالها.**")
                    return
            except PhoneCodeInvalidError:
                await event.respond("❌ **كود التحقق غير صحيح، أرسل الكود الصحيح مرة أخرى:**")
                return
            except Exception as e:
                await temp_client.disconnect()
                del pending_logins[uid_str]
                del admin_states[uid_str]
                await event.respond(f"❌ **فشل تسجيل الدخول:** {e}")
                return

            sess_str = temp_client.session.save()

            avail_nums[phone] = {
                "price_points": login_info["price"],
                "country": login_info["country"],
                "status": "available",
                "buyer_id": None,
            }
            u_sessions[phone] = {
                "session_str": sess_str,
                "api_id": API_ID,
                "api_hash": API_HASH,
                "two_factor_password": login_info["two_fa"],
            }
            code_reqs[phone] = uid_str
            save_all()

            await init_acc(phone, API_ID, API_HASH, sess_str)

            del pending_logins[uid_str]
            del admin_states[uid_str]

            await event.respond(
                f"✅ **تم ربط الحساب وإضافة الرقم `{phone}` بنجاح!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **السعر:** `{login_info['price']}` $\n"
                f"🌍 **الدولة:** `{login_info['country']}`\n"
                f"🔐 **2FA:** `{login_info['two_fa']}`",
                buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
                parse_mode="markdown"
            )
            return


# ==================== معالجة الضغط على الأزرار (Callbacks) ====================
@client.on(events.CallbackQuery)
async def callback_handler(event):
    uid = event.sender_id
    uid_str = str(uid)
    data = event.data.decode("utf-8")
    
    sender = await event.get_sender()
    name = getattr(sender, "first_name", "مستخدم") if sender else "مستخدم"
    username = f"@{sender.username}" if sender and sender.username else "لا يوجد"
    u_data = get_user_data(uid, name=name, username=username)

    if data == "check_sub":
        is_subbed, _ = await check_sub(uid)
        if is_subbed:
            await event.answer("✅ تم التأكد من اشتراكك بنجاح!", alert=True)
            await show_main_menu(event, is_callback=True)
        else:
            await event.answer(
                "❌ لم تشترك بعد في جميع القنوات/المجموعات المطلوبة!",
                alert=True,
            )
        return

    if data == "main_menu":
        if uid_str in pending_logins:
            try:
                await pending_logins[uid_str]["client"].disconnect()
            except Exception:
                pass
            del pending_logins[uid_str]
        if uid_str in admin_states:
            del admin_states[uid_str]
        await show_main_menu(event, is_callback=True)
        return

    if data == "recharge_menu":
        text = (
            f"💳 **قسم شحن الرصيد الاحترافي**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **رصيدك الحالي:** `{round(u_data['points'], 2)}` $\n\n"
            f"👇 **اختر طريقة الشحن المناسبة:**"
        )
        buttons = [
            [Button.inline("🔴 الشحن عبر تطبيق سوبركي (SuperPay)", data="recharge_superpay")],
            [Button.inline("🟡 الشحن عبر باينانس (Binance Pay)", data="recharge_binance")],
            [Button.inline("🎟 شحن عبر كارت هدية", data="use_card")],
            [Button.inline("⬅️ القائمة الرئيسية", data="main_menu")],
        ]
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "recharge_superpay":
        sp_name = syyad_conf.get("superpay_name", "Alaa Ahmed Ali")
        sp_num = syyad_conf.get("superpay_number", "7847602237")
        admin_states[uid_str] = {"step": "WAIT_SUPERPAY_PROOF"}
        
        text = (
            f"🔴 **الشحن بواسطة تطبيق سوبركي (SuperPay)**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **اسم الحساب:** `{sp_name}`\n"
            f"💳 **رقم الحساب/البطاقة:** `{sp_num}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 **جدول أسعار الشحن (كم تحوّل ⬅️ كم تحصل):**\n"
            f"• **1,500 د.ع** ⬅️ تحصل على **1.00 $**\n"
            f"• **3,000 د.ع** ⬅️ تحصل على **2.00 $**\n"
            f"• **7,500 د.ع** ⬅️ تحصل على **5.00 $**\n"
            f"• **15,000 د.ع** ⬅️ تحصل على **10.00 $**\n"
            f"*(أو يمكنك تحويل أي مبلغ وسيتم احتسابه بنفس النسبة)*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 **الخطوات:**\n"
            f"1. قم بتحويل المبلغ المطلوب عبر تطبيق سوبركي إلى البيانات أعلاه.\n"
            f"2. قم بإرسال **صورة إثبات التحويل (Screenshot)** أو **تفاصيل العملية** هنا فوراً.\n\n"
            f"👇 **أرسل صورة الإثبات أو النص الآن:**"
        )
        try:
            await event.edit(text, buttons=[[Button.inline("❌ إلغاء", data="recharge_menu")]], parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("approve_sp_") and is_adm(uid):
        target_uid = data.replace("approve_sp_", "")
        admin_states[uid_str] = {"step": "WAIT_SUPERPAY_AMOUNT", "target_user": target_uid}
        try:
            await event.edit(
                f"✅ **أدخل المبلغ ($) المراد إضافته لحساب المستخدم `{target_uid}`:**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("reject_sp_") and is_adm(uid):
        target_uid = data.replace("reject_sp_", "")
        try:
            await client.send_message(
                int(target_uid),
                "❌ **عذراً، تم رفض طلب الشحن عبر تطبيق سوبركي الخاص بك.**\nتأكد من صحة التحويل وتواصل مع الدعم.",
                parse_mode="markdown"
            )
        except Exception:
            pass
        await event.answer("❌ تم رفض طلب الشحن.", alert=True)
        try:
            await event.edit(f"❌ **تم رفض طلب الشحن للمستخدم `{target_uid}`.**", parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_sp_name" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_SUPERPAY_NAME"}
        try:
            await event.edit(
                f"🔴 **أرسل اسم حساب سوبركي الجديد (الاسم الحالي: `{syyad_conf.get('superpay_name')}`):**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_sp_num" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_SUPERPAY_NUM"}
        try:
            await event.edit(
                f"🔴 **أرسل رقم حساب/بطاقة سوبركي الجديد (الرقم الحالي: `{syyad_conf.get('superpay_number')}`):**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "recharge_binance":
        binance_id = syyad_conf.get("binance_id", "غير محدد")
        admin_states[uid_str] = {"step": "WAIT_BINANCE_PROOF"}
        text = (
            f"🟡 **الشحن بواسطة Binance Pay**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **Binance ID الخاص بالبوت:**\n`{binance_id}`\n\n"
            f"📝 **الخطوات:**\n"
            f"1. قم بتحويل المبلغ المراد شحنه إلى Binance ID أعلاه.\n"
            f"2. قم بإرسال **معرف المعاملة (TxID / Order ID)** أو **رقم حسابك في باينانس** هنا فوراً.\n\n"
            f"👇 **أرسل الإثبات الآن بالتكست أو صورة:**"
        )
        try:
            await event.edit(text, buttons=[[Button.inline("❌ إلغاء", data="recharge_menu")]], parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("approve_bin_") and is_adm(uid):
        target_uid = data.replace("approve_bin_", "")
        admin_states[uid_str] = {"step": "WAIT_BINANCE_AMOUNT", "target_user": target_uid}
        try:
            await event.edit(
                f"✅ **أدخل المبلغ ($) المراد إضافته لحساب المستخدم `{target_uid}`:**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("reject_bin_") and is_adm(uid):
        target_uid = data.replace("reject_bin_", "")
        try:
            await client.send_message(
                int(target_uid),
                "❌ **عذراً، تم رفض طلب الشحن عبر باينانس الخاصة بك.**\nتأكد من صحة التحويل وتواصل مع الدعم.",
                parse_mode="markdown"
            )
        except Exception:
            pass
        await event.answer("❌ تم رفض طلب الشحن.", alert=True)
        try:
            await event.edit(f"❌ **تم رفض طلب الشحن للمستخدم `{target_uid}`.**", parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_binance" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_BINANCE_ID"}
        try:
            await event.edit(
                f"🟡 **أرسل Binance Pay ID الجديد (الخيارات الحالية: `{syyad_conf.get('binance_id')}`):**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "daily_gift":
        now = time.time()
        last_claim = u_data.get("last_daily_gift", 0)
        if now - last_claim >= 86400:
            pts = syyad_conf.get("dailyGiftPoints", 0.1)
            u_data["points"] = round(u_data["points"] + pts, 2)
            u_data["last_daily_gift"] = now
            save_all()
            await event.answer(
                f"🎉 مبروك! حصلت على +{pts} $ كهدية يومية.", alert=True
            )
            await show_main_menu(event, is_callback=True)
        else:
            hours_left = int((86400 - (now - last_claim)) // 3600)
            await event.answer(
                f"⏳ أخذت الهدية اليوم! عد بعد {hours_left} ساعة.", alert=True
            )
        return

    if data == "my_account":
        user_nums_count = sum(
            1 for p, d in avail_nums.items() if str(d.get("buyer_id")) == uid_str
        )
        text = (
            f"👤 **بيانات حسابك التفصيلية:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• **الآيدي:** `{uid}`\n"
            f"• **رصيد $:** `{round(u_data['points'], 2)}` $\n"
            f"• **إجمالي الدعوات:** `{u_data.get('referral_count', 0)}` مستخدم\n"
            f"• **عدد الأرقام المشتراة:** `{user_nums_count}` رقم\n"
            f"• **حالة الحساب:** مؤكد ✅"
        )
        buttons = [
            [Button.inline("📜 سجل أرقامي المشتراة", data="my_numbers_log")],
            [Button.inline("⬅️ رجوع", data="main_menu")],
        ]
        try:
            await event.edit(
                text,
                buttons=buttons,
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "my_numbers_log":
        my_bought_nums = [
            p for p, d in avail_nums.items() if str(d.get("buyer_id")) == uid_str
        ]

        if not my_bought_nums:
            try:
                await event.edit(
                    "📜 **سجل أرقامك المشتراة:**\n━━━━━━━━━━━━━━━━━━━━\n❌ لم تقم بشراء أي أرقام بعد!",
                    buttons=[[Button.inline("⬅️ رجوع", data="main_menu")]],
                )
            except MessageNotModifiedError:
                pass
            return

        text = "📜 **سجل الأرقام التي قمت بشراؤها:**\n━━━━━━━━━━━━━━━━━━━━\n"
        buttons = []
        for p in my_bought_nums:
            two_fa = u_sessions.get(p, {}).get("two_factor_password", "لا يوجد")
            country = avail_nums[p].get("country", "عام")
            text += f"📞 `{p}` | 🌍 {country}\n🔐 **2FA:** `{two_fa}`\n━━━━━━━━━━━━━━━━━━━━\n"
            buttons.append([Button.inline(f"📥 جلب كود الرقم {p}", data=f"getcode_{p}")])

        buttons.append([Button.inline("⬅️ رجوع", data="main_menu")])
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "referral_link":
        me = await client.get_me()
        link = f"https://t.me/{me.username}?start={uid}"
        text = (
            f"🔗 **رابط الدعوة الخاص بك:**\n`{link}`\n\n"
            f"📢 شارك هذا الرابط مع أصدقائك.\n"
            f"🎁 **لكل دخول:** ستحصل على `+{syyad_conf.get('referralPoints', 5)}` $ فورية!"
        )
        try:
            await event.edit(
                text,
                buttons=[[Button.inline("⬅️ رجوع", data="main_menu")]],
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "buy_numbers":
        countries_data = {}
        for p, d in avail_nums.items():
            if d.get("status") == "available":
                c = d.get("country", "عام")
                if c not in countries_data:
                    countries_data[c] = {"count": 0, "price": d.get("price_points", 0)}
                countries_data[c]["count"] += 1

        if not countries_data:
            try:
                await event.edit(
                    "❌ **عذراً، لا توجد أرقام متوفرة الآن.**\nسيتم إضافة أرقام جديدة قريباً!",
                    buttons=[[Button.inline("⬅️ رجوع", data="main_menu")]],
                )
            except MessageNotModifiedError:
                pass
            return

        country_flags = {
            "امريكا": "🇺🇸", "أمريكا": "🇺🇸", "بريطانيا": "🇬🇧", "الهند": "🇮🇳",
            "سبام": "🚫", "مصر": "🇪🇬", "السعودية": "🇸🇦", "العراق": "🇮🇶", "عام": "🌍"
        }

        country_btn_list = []
        for c_name, c_info in countries_data.items():
            flag = country_flags.get(c_name, "🌍")
            btn_text = f"{flag} {c_name} | {c_info['price']}$ | {c_info['count']}"
            country_btn_list.append(Button.inline(btn_text, data=f"show_c_{c_name}"))

        buttons = []
        for i in range(0, len(country_btn_list), 2):
            buttons.append(country_btn_list[i:i+2])

        buttons.append([Button.inline("🔍 بحث", data="search_country")])
        buttons.append([Button.inline("رجوع", data="main_menu")])

        text = "🌍 **قائمة الدول المتاحة:**\n\nاختر الدولة التي تريد شراء حساب منها:"
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("show_c_"):
        c_name = data.replace("show_c_", "")
        avail_in_c = [
            (p, d) for p, d in avail_nums.items() 
            if d.get("status") == "available" and d.get("country", "عام") == c_name
        ]
        if not avail_in_c:
            await event.answer("❌ لا توجد أرقام متاحة لهذه الدولة حالياً!", alert=True)
            return

        text = f"📱 **الأرقام المتوفرة - {c_name}:**\n━━━━━━━━━━━━━━━━━━━━\n"
        buttons = []
        for p, d in avail_in_c[:10]:
            masked_p = p[:-6] + "******" if len(p) > 6 else p
            text += f"📞 `{masked_p}` | 💰 `{d.get('price_points')}` $\n"
            buttons.append([Button.inline(f"شراء الرقم {masked_p}", data=f"buy_{p}")])

        buttons.append([Button.inline("⬅️ رجوع لقائمة الدول", data="buy_numbers")])
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "search_country":
        await event.answer("🔍 أرسل اسم الدولة للبحث عن الأرقام المتوفرة.", alert=True)
        return

    if data.startswith("buy_"):
        phone = data.replace("buy_", "")
        if phone in avail_nums and avail_nums[phone]["status"] == "available":
            price = avail_nums[phone]["price_points"]
            if u_data["points"] >= price:
                u_data["points"] = round(u_data["points"] - price, 2)
                avail_nums[phone]["status"] = "sold"
                avail_nums[phone]["buyer_id"] = uid_str
                code_reqs[phone] = uid_str
                save_all()

                try:
                    buyer_entity = await client.get_entity(int(uid))
                    buyer_name = buyer_entity.first_name or "بدون اسم"
                    buyer_username = f"@{buyer_entity.username}" if buyer_entity.username else "لا يوجد"
                except Exception:
                    buyer_name = "غير معروف"
                    buyer_username = "لا يوجد"

                for adm in syyad_conf["admin_ids"]:
                    try:
                        await client.send_message(
                            int(adm),
                            f"🛒 **عملية شراء جديدة!**\n"
                            f"• 👤 **المستخدم:** `{uid}`\n"
                            f"• 🏷 **الاسم:** {buyer_name}\n"
                            f"• 🌐 **اليوزر:** {buyer_username}\n"
                            f"• 📞 **الرقم:** `{phone}`",
                            parse_mode="markdown"
                        )
                    except Exception:
                        pass

                try:
                    await event.edit(
                        f"✅ **تم شراء الرقم بنجاح!**\n━━━━━━━━━━━━━━━━━━━━\n"
                        f"📞 **الرقم:** `{phone}`\n"
                        f"⏱ أدخل الرقم في تليجرام الآن واطلب الكود، وسيصلك الكود هنا فوراً...",
                        buttons=[
                            [
                                Button.inline(
                                    "📥 طلب/جلب الكود مباشرة",
                                    data=f"getcode_{phone}",
                                )
                            ],
                            [
                                Button.inline(
                                    "🚪 تسجيل الخروج وحذف الجلسة",
                                    data=f"delnum_{phone}",
                                )
                            ],
                            [
                                Button.inline(
                                    "⬅️ القائمة الرئيسية", data="main_menu"
                                )
                            ],
                        ],
                        parse_mode="markdown",
                    )
                except MessageNotModifiedError:
                    pass
            else:
                await event.answer(
                    "❌ لا تملك $ كافي لشراء هذا الرقم!", alert=True
                )
        return

    if data.startswith("getcode_"):
        phone = data.replace("getcode_", "")
        if phone in u_clients:
            try:
                code_found = None
                async for m in u_clients[phone].iter_messages(777000, limit=5):
                    if m.text:
                        cm = re.search(r"\b(\d{5,6})\b", m.text)
                        if cm:
                            code_found = cm.group(1)
                            break
                if code_found:
                    two_fa = u_sessions.get(phone, {}).get(
                        "two_factor_password", "لا يوجد"
                    )
                    await event.answer(
                        f"🔑 الكود: {code_found}\n🔐 2FA: {two_fa}",
                        alert=True,
                    )
                else:
                    await event.answer(
                        "⏳ لم يصل الكود بعد! اطلب الكود في تليجرام وحاول مجدداً.",
                        alert=True,
                    )
            except Exception as e:
                await event.answer(
                    f"⚠️ تعذر جلب الكود: {e}", alert=True
                )
        else:
            await event.answer(
                "❌ الجلسة غير متصلة حالياً!", alert=True
            )
        return

    if data.startswith("delnum_"):
        phone = data.replace("delnum_", "")
        if phone in u_clients:
            try:
                await u_clients[phone].log_out()
            except Exception:
                try:
                    await u_clients[phone].disconnect()
                except Exception:
                    pass
            del u_clients[phone]

        if phone in u_sessions:
            del u_sessions[phone]

        if phone in code_reqs:
            del code_reqs[phone]

        save_all()

        await event.answer("✅ تم تسجيل الخروج وحذف الجلسة بنجاح!", alert=True)
        try:
            await event.edit(
                f"✅ **تم تسجيل الخروج وحذف جلسة الرقم `{phone}` بنجاح.**",
                buttons=[
                    [Button.inline("⬅️ القائمة الرئيسية", data="main_menu")]
                ],
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "use_card":
        admin_states[uid_str] = {"step": "WAIT_CARD"}
        try:
            await event.edit(
                "🎟 **أدخل رمز كارت الشحن الآن:**",
                buttons=[[Button.inline("❌ إلغاء", data="main_menu")]],
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "owner_main" and is_owner(uid):
        ver_status = "مفعل 🟢" if syyad_conf.get("verification_enabled", True) else "معطل 🔴"
        text = (
            f"👑 **لوحة التحكم الكاملة الخاصة بالمالك**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 🆔 **آيدي المالك:** `{syyad_conf.get('owner_id')}`\n"
            f"• 🟡 **Binance ID:** `{syyad_conf.get('binance_id', 'غير محدد')}`\n"
            f"• 🔴 **اسم سوبركي:** `{syyad_conf.get('superpay_name', 'غير محدد')}`\n"
            f"• 💳 **رقم سوبركي:** `{syyad_conf.get('superpay_number', 'غير محدد')}`\n"
            f"• 🛡 **نظام التحقق الآلي:** {ver_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"تحكم كامل بكافة صلاحيات وسيرفر البوت:"
        )
        buttons = [
            [
                Button.inline("⚙️ لوحة الأدمن العامة", data="admin_main"),
                Button.inline("➕/➖ إضافة أو خصم $ لمستخدم", data="owner_give_points"),
            ],
            [
                Button.inline("✏️ تعديل اسم سوبركي", data="adm_set_sp_name"),
                Button.inline("✏️ تعديل رقم سوبركي", data="adm_set_sp_num"),
            ],
            [
                Button.inline(f"🔄 تغيير حالة اختبار الأمان ({ver_status})", data="owner_toggle_ver"),
            ],
            [
                Button.inline("👑 رفع أدمن جديد", data="adm_add_admin"),
                Button.inline("❌ تنزيل أدمن", data="adm_remove_admin"),
            ],
            [
                Button.inline("📋 عرض قائمة الأدمنية", data="owner_list_admins"),
            ],
            [Button.inline("⬅️ القائمة الرئيسية", data="main_menu")],
        ]
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "owner_toggle_ver" and is_owner(uid):
        syyad_conf["verification_enabled"] = not syyad_conf.get("verification_enabled", True)
        save_all()
        await event.answer("✅ تم تغيير حالة اختبار الأمان بنجاح!", alert=True)
        await callback_handler(event)
        return

    if data == "owner_give_points" and is_owner(uid):
        admin_states[uid_str] = {"step": "WAIT_GIVE_POINTS"}
        try:
            await event.edit(
                "💰 **أرسل الآيدي والمبلغ المراد إضافته (أو خصمه بسالب):**\n\n`الآيدي المبلغ`\nمثال لإضافة 0.5 $: `541029541 0.5`\nمثال لخصم 0.1 $: `541029541 -0.1`",
                buttons=[[Button.inline("❌ إلغاء", data="owner_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "owner_list_admins" and is_owner(uid):
        admins = syyad_conf.get("admin_ids", [])
        text = "📋 **قائمة الأدمنية المرفوعين:**\n━━━━━━━━━━━━━━━━━━━━\n"
        for idx, a_id in enumerate(admins, 1):
            text += f"{idx}. 🆔 `{a_id}`\n"
        try:
            await event.edit(
                text,
                buttons=[[Button.inline("⬅️ رجوع لوحة المالك", data="owner_main")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "admin_main" and is_adm(uid):
        text = "⚙️ **لوحة تحكم الأدمن الشاملة**"
        buttons = [
            [
                Button.inline("➕ إضافة رقم جديد", data="adm_add_num"),
                Button.inline("🎟 صنع كارت شحن", data="adm_make_card"),
            ],
            [
                Button.inline("🔴 ضبط اسم سوبركي", data="adm_set_sp_name"),
                Button.inline("🔴 ضبط رقم سوبركي", data="adm_set_sp_num"),
            ],
            [
                Button.inline("🟡 ضبط Binance ID", data="adm_set_binance"),
                Button.inline("📢 إعدادات الاشتراك الإجباري", data="adm_set_chan"),
            ],
            [
                Button.inline("🎁 تعديل الـ $ والهدية", data="adm_set_points"),
                Button.inline("🛠 تعديل الدعم الفني", data="adm_set_support"),
            ],
            [
                Button.inline("📊 إحصائيات البوت", data="adm_stats"),
                Button.inline("👥 سجل المستخدمين", data="adm_users_log_p1"),
            ],
            [
                Button.inline("👑 إضافة أدمن", data="adm_add_admin"),
                Button.inline("❌ تنزيل أدمن", data="adm_remove_admin"),
            ],
        ]

        if is_owner(uid):
            buttons.append([Button.inline("👑 لوحة المالك", data="owner_main")])

        buttons.append([Button.inline("⬅️ القائمة الرئيسية", data="main_menu")])

        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_support" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_SUPPORT"}
        try:
            await event.edit(
                "🛠 **أرسل معرف الدعم الفني الجديد (مثال: @Username):**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
            )
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("adm_users_log_") and is_adm(uid):
        page = int(data.replace("adm_users_log_p", "")) if "p" in data else 1
        all_users = list(syyad_users.items())
        total_users = len(all_users)
        
        per_page = 5
        total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        current_batch = all_users[start_idx:end_idx]

        text = (
            f"👥 **سجل المستخدمين المفصل (صفحة {page}/{total_pages}):**\n"
            f"📊 **إجمالي المستخدمين:** `{total_users}` مستخدم\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )

        for idx, (u_id, u_info) in enumerate(current_batch, start=start_idx + 1):
            pts = u_info.get("points", 0)
            refs = u_info.get("referral_count", 0)
            u_name = u_info.get("name", "مستخدم")
            u_username = u_info.get("username", "لا يوجد")
            verified = "مؤكد ✅" if u_info.get("verified") else "غير مؤكد ❌"
            bought_nums = sum(1 for p, d in avail_nums.items() if str(d.get("buyer_id")) == str(u_id))
            
            text += (
                f"{idx}️⃣ 👤 الاسم: `{u_name}`\n"
                f"   • 🔗 اليوزر: {u_username}\n"
                f"   • 🆔 الآيدي: `{u_id}`\n"
                f"   • 💰 الرصيد: `{round(pts, 2)}` $\n"
                f"   • 👥 الإحالات: `{refs}` | 📱 أرقام: `{bought_nums}`\n"
                f"   • 🛡 الحالة: {verified}\n"
                f"------------------------------------\n"
            )

        nav_buttons = []
        if page > 1:
            nav_buttons.append(Button.inline("⬅️ السابق", data=f"adm_users_log_p{page - 1}"))
        if page < total_pages:
            nav_buttons.append(Button.inline("التالي ➡️", data=f"adm_users_log_p{page + 1}"))

        buttons = []
        if nav_buttons:
            buttons.append(nav_buttons)
        buttons.append([Button.inline("⬅️ رجوع لوحة الأدمن", data="admin_main")])

        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_stats" and is_adm(uid):
        total_users = len(syyad_users)
        total_nums = len(avail_nums)
        avail_count = sum(
            1 for d in avail_nums.values() if d.get("status") == "available"
        )
        sold_count = sum(
            1 for d in avail_nums.values() if d.get("status") == "sold"
        )
        cards_count = len(gift_cards)

        text = (
            f"📊 **إحصائيات البوت الشاملة:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 👥 **عدد المستخدمين:** `{total_users}`\n"
            f"• 📱 **إجمالي الأرقام:** `{total_nums}`\n"
            f"• 🟢 **الأرقام المتاحة:** `{avail_count}`\n"
            f"• 🔴 **الأرقام المباعة:** `{sold_count}`\n"
            f"• 🎟 **كروت الشحن:** `{cards_count}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await event.edit(
                text,
                buttons=[[Button.inline("⬅️ رجوع للوحة", data="admin_main")]],
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_add_num" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_ADD_NUM_PHONE"}
        try:
            await event.edit(
                "📱 **أدخل رقم الهاتف المراد إضافته:**\n(مع رمز الدولة، مثال: `+12723175425`)",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_make_card" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_MAKE_CARD"}
        try:
            await event.edit(
                "🎟 **أدخل تفاصيل الكارت بالشكل:**\n`الـ $ العدد`\nمثال: `0.5 5` (لإنشاء 5 كروت بقيمة 0.5 $ لكل كارت)",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
                parse_mode="markdown",
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_chan" and is_adm(uid):
        curr_chans = syyad_conf.get("force_channels", [])
        ch_text = "\n".join([f"{idx}. `{c}`" for idx, c in enumerate(curr_chans, 1)]) if curr_chans else "❌ لا توجد قنوات أو مجموعات مضافة حالياً."
        
        text = (
            f"📢 **قائمة الاشتراك الإجباري الحالية:**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{ch_text}\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 اختر إجراء مما يلي:"
        )
        buttons = [
            [Button.inline("➕ إضافة قنوات/مجموعات", data="adm_add_chan_input")],
            [Button.inline("🗑 مسح قنوات محددة", data="adm_del_chan_select")],
            [Button.inline("⚠️ تفريغ كافة القنوات", data="adm_clear_chans")],
            [Button.inline("⬅️ رجوع للوحة", data="admin_main")],
        ]
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_add_chan_input" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_ADD_CHAN"}
        try:
            await event.edit(
                "➕ **أرسل معرّفات أو روابط القنوات والمجموعات المراد إضافتها:**\n\n"
                "يمكنك إرسال أكثر من قناة/مجموعة يفصل بينها مسافة أو سطر جديد.\n"
                "**مثال:**\n`@channel1 @group2 https://t.me/channel3`",
                buttons=[[Button.inline("❌ إلغاء", data="adm_set_chan")]],
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_del_chan_select" and is_adm(uid):
        curr_chans = syyad_conf.get("force_channels", [])
        if not curr_chans:
            await event.answer("❌ لا توجد قنوات مسجلة لحذفها!", alert=True)
            return

        buttons = []
        for idx, ch in enumerate(curr_chans):
            buttons.append([Button.inline(f"🗑 حذف: {ch}", data=f"delchan_{idx}")])
        buttons.append([Button.inline("⬅️ رجوع", data="adm_set_chan")])

        try:
            await event.edit(
                "🗑 **اختر القناة أو المجموعة المراد إزالتها:**",
                buttons=buttons,
                parse_mode="markdown"
            )
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("delchan_") and is_adm(uid):
        idx = int(data.replace("delchan_", ""))
        curr_chans = syyad_conf.get("force_channels", [])
        if 0 <= idx < len(curr_chans):
            removed = curr_chans.pop(idx)
            syyad_conf["force_channels"] = curr_chans
            save_all()
            await event.answer(f"✅ تم حذف {removed} بنجاح!", alert=True)
            await callback_handler(event)
        return

    if data == "adm_clear_chans" and is_adm(uid):
        syyad_conf["force_channels"] = []
        save_all()
        await event.answer("✅ تم تفريغ كافة قنوات الاشتراك الإجباري!", alert=True)
        await callback_handler(event)
        return

    if data == "adm_set_points" and is_adm(uid):
        daily_pts = syyad_conf.get("dailyGiftPoints", 0.1)
        ref_pts = syyad_conf.get("referralPoints", 5)
        text = (
            f"⚙️ **إعدادات الـ $ الحالية:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 🎁 **$ الهدية اليومية:** `{daily_pts}` $\n"
            f"• 👥 **$ الإحالة:** `{ref_pts}` $\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 اختر ما تريد تعديله:"
        )
        buttons = [
            [
                Button.inline("🎁 تعديل الهدية اليومية", data="adm_set_daily"),
                Button.inline("👥 تعديل $ الإحالة", data="adm_set_ref"),
            ],
            [Button.inline("⬅️ رجوع", data="admin_main")],
        ]
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_daily" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_DAILY"}
        try:
            await event.edit(
                "🎁 **أدخل القيمة الجديدة لـ $ الهدية اليومية (مثال: 0.1):**",
                buttons=[[Button.inline("❌ إلغاء", data="adm_set_points")]],
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_set_ref" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_SET_REF"}
        try:
            await event.edit(
                "👥 **أدخل القيمة الجديدة لـ $ لكل إحالة (مثال: 0.5):**",
                buttons=[[Button.inline("❌ إلغاء", data="adm_set_points")]],
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_add_admin" and is_adm(uid):
        admin_states[uid_str] = {"step": "WAIT_ADD_ADMIN"}
        try:
            await event.edit(
                "👑 **أرسل آيدي (ID) المستخدم المراد رفعه كـ أدمن:**",
                buttons=[[Button.inline("❌ إلغاء", data="admin_main")]],
            )
        except MessageNotModifiedError:
            pass
        return

    if data == "adm_remove_admin" and is_adm(uid):
        admins = syyad_conf.get("admin_ids", [])
        if not admins:
            try:
                await event.edit(
                    "❌ **لا يوجد أدمنية حالياً في النظام!**",
                    buttons=[[Button.inline("⬅️ رجوع", data="admin_main")]],
                )
            except MessageNotModifiedError:
                pass
            return

        text = "❌ **اختر الأدمن المراد تنزيله:**\n"
        buttons = []
        for adm in admins:
            buttons.append(
                [Button.inline(f"👤 تنزيل: {adm}", data=f"deladm_{adm}")]
            )
        buttons.append([Button.inline("⬅️ رجوع", data="admin_main")])
        try:
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except MessageNotModifiedError:
            pass
        return

    if data.startswith("deladm_") and is_adm(uid):
        target_adm = data.replace("deladm_", "")
        if target_adm in syyad_conf.get("admin_ids", []):
            syyad_conf["admin_ids"].remove(target_adm)
            save_all()
            await event.answer(f"✅ تم تنزيل الأدمن {target_adm} بنجاح!", alert=True)
            await show_main_menu(event, is_callback=True)
        return


# ==================== التشغيل الرئيسي ====================
async def main():
    load_all()
    await client.start(bot_token=BOT_TOKEN)
    print("🤖 البوت يعمل بنجاح الآن...")
    await run_all_accs()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
