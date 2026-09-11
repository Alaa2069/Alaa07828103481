import asyncio
import csv
import html
import io
import logging
import random
import sqlite3
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    FSInputFile,
    BufferedInputFile,
    URLInputFile
)

# ════════════════════ الإعدادات الأساسية ════════════════════
BOT_TOKEN = "8898144793:AAEuRh0nz5Tvp8MSdDD4gGKqPBTKvy-Ge28"
ADMIN_ID = 541029541  # المالك الأساسي للمنظومة

# قائمة مفاتيح الصلاحيات
PERMISSIONS_MAP = {
    "finance": "💳 قبول ورفض الإيداع والسحب",
    "plans": "📊 إدارة باقات الاستثمار",
    "users": "👤 إدارة وتعديل المشتركين",
    "pay_methods": "⚙️ إدارة طرق الدفع",
    "buttons": "🎛 تخصيص أزرار الداشبورد",
    "limits": "💵 تعديل الحدود والأسعار",
    "toggles": "🚦 مفاتيح التشغيل والصيانة",
    "broadcast": "📢 الإذاعة العامة",
    "promo": "🎟 صنع أكواد الهدايا",
    "backup": "📥 النسخ الاحتياطي والبيانات"
}
DEFAULT_ADMIN_PERMISSIONS = ",".join(PERMISSIONS_MAP.keys())

# قاموس أسباب الرفض
REASONS_MAP = {
    "1": "وصل التحويل غير واضح أو غير مطابق",
    "2": "عنوان المحفظة أو الشبكة المختارة غير صحيحة",
    "3": "المبلغ المحول ناقص"
}

# ذاكرة الكاش السريعة
SETTINGS_CACHE = {}
ADMINS_CACHE = {}
SUB_CACHE = {}
user_last_action = {}

# ════════════════════ قاعدة البيانات ════════════════════
def db_conn():
    conn = sqlite3.connect("invest_v13_ultimate.db", timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode = WAL;")
        c.execute("PRAGMA synchronous = NORMAL;")
        c.execute("PRAGMA temp_store = MEMORY;")
        c.execute("PRAGMA cache_size = -64000;")

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                total_invested REAL DEFAULT 0.0,
                active_plan TEXT DEFAULT 'لا يوجد',
                daily_profit REAL DEFAULT 0.0,
                plan_end INTEGER DEFAULT 0,
                last_claim INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                last_bonus INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                saved_wallet TEXT DEFAULT ''
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_code TEXT,
                user_id INTEGER,
                type TEXT,
                method TEXT,
                amount REAL,
                fee REAL DEFAULT 0.0,
                net_amount REAL DEFAULT 0.0,
                details TEXT,
                status TEXT DEFAULT 'pending',
                created_at INTEGER DEFAULT 0,
                expires_at INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                cost REAL,
                daily_profit REAL,
                duration_days INTEGER,
                is_active INTEGER DEFAULT 1
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_id INTEGER,
                plan_name TEXT,
                cost REAL,
                daily_profit REAL,
                start_time INTEGER,
                end_time INTEGER,
                last_claim INTEGER,
                status TEXT DEFAULT 'active'
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_at INTEGER,
                permissions TEXT DEFAULT ''
            )
        ''')
        # جدول قنوات ومجموعات الاشتراك الإجباري المتعددة
        c.execute('''
            CREATE TABLE IF NOT EXISTS force_sub_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE,
                title TEXT,
                invite_link TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                name TEXT,
                details TEXT,
                raw_address TEXT DEFAULT '',
                fee_percent REAL DEFAULT 0.0,
                is_iqd INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward REAL,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS promo_history (
                code TEXT,
                user_id INTEGER,
                used_at INTEGER,
                PRIMARY KEY(code, user_id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                target_type TEXT,
                target_val TEXT,
                row_order INTEGER DEFAULT 1
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        c.execute("CREATE INDEX IF NOT EXISTS idx_ops_uid ON operations(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_usubs_uid_st ON user_subscriptions(user_id, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ops_code ON operations(invoice_code)")

        try:
            c.execute("ALTER TABLE bot_admins ADD COLUMN permissions TEXT DEFAULT ''")
        except Exception:
            pass

        try:
            c.execute("ALTER TABLE plans ADD COLUMN is_active INTEGER DEFAULT 1")
        except Exception:
            pass

        c.execute("SELECT COUNT(*) FROM plans")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO plans (name, cost, daily_profit, duration_days, is_active) VALUES ('الخطة اليومية (24h)', 10.0, 12.0, 1, 1)")
            c.execute("INSERT INTO plans (name, cost, daily_profit, duration_days, is_active) VALUES ('الخطة الأسبوعية (7d)', 50.0, 10.0, 7, 1)")
            c.execute("INSERT INTO plans (name, cost, daily_profit, duration_days, is_active) VALUES ('الخطة الشهرية (30d)', 150.0, 9.0, 30, 1)")

        c.execute("SELECT COUNT(*) FROM payment_methods")
        if c.fetchone()[0] == 0:
            default_methods = [
                ("deposit", "🟢 USDT (شبكة TRC20)", "عنوان TRC20 المعتمد:\n<code>TYDzsYxxxxxxxxxxxxxxxxxxxxxxTRC20</code>", "TYDzsYxxxxxxxxxxxxxxxxxxxxxxTRC20", 0.0, 0, 1),
                ("deposit", "🔵 USDT (شبكة BEP20)", "عنوان BEP20 المعتمد:\n<code>0x71CxxxxxxxxxxxxxxxxxxxxxxxxBEP20</code>", "0x71CxxxxxxxxxxxxxxxxxxxxxxxxBEP20", 0.0, 0, 1),
                ("deposit", "🟡 بايننس (Binance Pay ID)", "معرف Pay ID المعتمد:\n<code>987654321</code>", "987654321", 0.0, 0, 1),
                ("deposit", "📲 زين كاش (Zain Cash - العراق)", "رقم محفظة زين كاش:\n<code>07800000000</code>", "07800000000", 0.0, 1, 1),
                ("deposit", "📲 آسيا سيل (Asiacell - تحويل رصيد)", "رقم التحويل المعتمد:\n<code>07700000000</code>", "07700000000", 0.0, 1, 1),
                ("withdraw", "🟢 USDT (شبكة TRC20)", "أرسل عنوان محفظتك USDT TRC20 للاستلام", "", 1.0, 0, 1),
                ("withdraw", "🔵 USDT (شبكة BEP20)", "أرسل عنوان محفظتك USDT BEP20 للاستلام", "", 0.5, 0, 1),
                ("withdraw", "🟡 بايننس (Binance ID / Pay)", "أرسل معرف بايننس الخاص بك (Pay ID)", "", 0.0, 0, 1),
                ("withdraw", "📲 زين كاش (Zain Cash)", "أرسل رقم محفظة زين كاش للاستلام", "", 0.0, 1, 1),
                ("withdraw", "📲 آسيا سيل (Asiacell)", "أرسل رقم هاتف آسيا سيل لتحويل الرصيد", "", 0.0, 1, 1)
            ]
            for cat, name, details, raw_addr, fee, is_iqd, act in default_methods:
                c.execute(
                    "INSERT INTO payment_methods (category, name, details, raw_address, fee_percent, is_iqd, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cat, name, details, raw_addr, fee, is_iqd, act)
                )

        c.execute("SELECT COUNT(*) FROM dashboard_buttons")
        if c.fetchone()[0] == 0:
            default_btns = [
                ("⚡️ تجميع الأرباح يدوياً", "callback", "claim_profit", 1),
                ("💳 شحن الرصيد (إيداع)", "callback", "open_deposit", 2),
                ("💸 طلب سحب نقدي", "callback", "open_withdraw", 2),
                ("📊 باقات الاستثمار", "callback", "open_plans", 3),
                ("🧮 حاسبة الأرباح الذكية", "callback", "open_calc", 3),
                ("🔍 تتبع وإدارة المعاملات", "callback", "open_track_op", 4),
                ("🔄 تحويل رصيد داخلي", "callback", "open_transfer", 4),
                ("🎟 استخدام كود هدية", "callback", "open_promo", 5),
                ("🎁 الهدية اليومية", "callback", "claim_daily_gift", 5),
                ("👥 رابط الإحالة", "callback", "open_referral", 6),
                ("📜 سجل العمليات", "callback", "open_history", 6),
                ("📈 إحصائيات المنصة", "callback", "open_stats", 7),
                ("📞 الدعم والإثباتات", "callback", "open_support", 7),
                ("🔄 تحديث الشاشة", "callback", "refresh_dash", 8)
            ]
            for title, b_type, b_val, r_order in default_btns:
                c.execute("INSERT INTO dashboard_buttons (title, target_type, target_val, row_order) VALUES (?, ?, ?, ?)", (title, b_type, b_val, r_order))

        defaults = {
            "min_withdraw": "5.0",
            "max_daily_withdraw": "500.0",
            "usd_to_iqd_rate": "1530",
            "ref_percent": "10",
            "daily_bonus": "0.10",
            "transfer_fee_percent": "2",
            "maintenance": "0",
            "withdraw_active": "1",
            "deposit_active": "1",
            "transfer_active": "1",
            "force_sub_active": "0",
            "support_user": "@YourSupport",
            "proof_channel": "",
            "welcome_text": "مرحباً بك في المنصة الاستثمارية الذكية. استثمر، ضاعف أرباحك، واسحب أموالك فوراً بكل أمان."
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()

        c.execute("SELECT key, value FROM settings")
        for row in c.fetchall():
            SETTINGS_CACHE[row["key"]] = row["value"]

        c.execute("SELECT user_id, permissions FROM bot_admins")
        for row in c.fetchall():
            p_set = set(row["permissions"].split(",") if row["permissions"] else [])
            ADMINS_CACHE[row["user_id"]] = p_set

init_db()

# ════════════════════ دوال الكاش السريعة ════════════════════
def get_setting(key: str, default: str = "") -> str:
    return SETTINGS_CACHE.get(key, default)

def set_setting(key: str, value: str):
    SETTINGS_CACHE[key] = value
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

def is_admin(user_id: int) -> bool:
    return (user_id == ADMIN_ID) or (user_id in ADMINS_CACHE)

def has_permission(user_id: int, perm: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    perms = ADMINS_CACHE.get(user_id, set())
    return perm in perms or "all" in perms

def get_admins_with_perm(perm: str) -> list:
    admins = {ADMIN_ID}
    for uid, perms in ADMINS_CACHE.items():
        if perm in perms or "all" in perms:
            admins.add(uid)
    return list(admins)

def get_user(user_id: int, username: str = "", referrer_id: int = 0):
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        if not user:
            valid_ref = referrer_id if (referrer_id != user_id and referrer_id != 0) else 0
            c.execute(
                "INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)",
                (user_id, username, valid_ref)
            )
            if valid_ref != 0:
                c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (valid_ref,))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
        return user

def update_user(user_id: int, **kwargs):
    with db_conn() as conn:
        c = conn.cursor()
        fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        c.execute(f"UPDATE users SET {fields} WHERE user_id = ?", list(kwargs.values()) + [user_id])
        conn.commit()

# ════════════════════ آلات الحالة (FSM) ════════════════════
class Form(StatesGroup):
    dep_custom_amount = State()
    dep_proof = State()
    wth_custom_amount = State()
    wth_target_address = State()
    calc_custom_input = State()
    broadcast_msg = State()
    admin_change_setting = State()
    admin_inspect_user = State()
    admin_adjust_bal = State()
    transfer_target = State()
    transfer_amount = State()
    claim_promo = State()
    admin_add_promo_code = State()
    admin_add_promo_reward = State()
    admin_add_promo_uses = State()
    admin_btn_title = State()
    admin_btn_type = State()
    admin_btn_val = State()
    admin_add_method_cat = State()
    admin_add_method_name = State()
    admin_add_method_details = State()
    admin_add_method_addr = State()
    admin_add_method_fee = State()
    admin_add_method_iqd = State()
    admin_edit_method_details = State()
    track_code = State()
    
    admin_add_plan_name = State()
    admin_add_plan_cost = State()
    admin_add_plan_profit = State()
    admin_add_plan_duration = State()
    admin_edit_plan_val = State()

    admin_add_admin_id = State()
    admin_add_channel_input = State()

def cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء والرجوع للقائمة", callback_data="cancel_action")]
    ])

# ════════════════════ الواجهة الرئيسية ════════════════════
def get_vip_badge(total_invested: float) -> str:
    if total_invested >= 500:
        return "💎 VIP 4 (الماسي)"
    elif total_invested >= 300:
        return "🥇 VIP 3 (الذهبي)"
    elif total_invested >= 150:
        return "🥈 VIP 2 (الفضي)"
    elif total_invested >= 50:
        return "🥉 VIP 1 (البرونزي)"
    return "عضو نشط"

def get_progress_bar(percent: int, length: int = 10) -> str:
    filled = int(length * (percent / 100))
    return "█" * filled + "░" * (length - filled)

def render_dashboard(user_id: int):
    user = get_user(user_id)
    now = int(time.time())
    cooldown = 86400

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM user_subscriptions 
            WHERE user_id = ? AND status = 'active' AND end_time > ?
        """, (user_id, now))
        active_subs = c.fetchall()

    sub_count = len(active_subs)
    total_daily_profit = sum(s["daily_profit"] for s in active_subs)

    if sub_count == 0:
        active_plan_text = "لا يوجد"
        profit_text = "$0.00 / 24h"
        percent = 0
        timer_text = "متوقف (فعّل باقة)"
    else:
        if sub_count == 1:
            active_plan_text = active_subs[0]["plan_name"]
        else:
            active_plan_text = f"{sub_count} باقات نشطة ⚡️"
            
        profit_text = f"${total_daily_profit:.2f} / 24h"

        min_remaining = cooldown
        for s in active_subs:
            elapsed = now - s["last_claim"]
            rem = max(0, cooldown - elapsed)
            if rem < min_remaining:
                min_remaining = rem
        
        elapsed_display = max(0, cooldown - min_remaining)
        percent = min(100, int((elapsed_display / cooldown) * 100))
        h = min_remaining // 3600
        m = (min_remaining % 3600) // 60
        s = min_remaining % 60
        timer_text = f"<code>{h:02d}:{m:02d}:{s:02d}</code>"

    balance = user["balance"]
    ref_count = user["referral_count"]
    vip_badge = get_vip_badge(user["total_invested"])
    safe_username = html.escape(user["username"] or "مشترك")

    text = (
        "╔══════════════════════════╗\n"
        "      💎 <b>لوحة التحكم الاستثمارية</b> 💎\n"
        "╚══════════════════════════╝\n\n"
        f"👤 <b>المشترك:</b> @{safe_username} | <b>{vip_badge}</b>\n"
        f"🆔 <b>المعرف:</b> <code>{user['user_id']}</code>\n"
        "──────────────────────────\n"
        f"💰 <b>رصيد المحفظة:</b> <code>${balance:.2f}</code>\n"
        f"⚡️ <b>الخطط النشطة:</b> <code>{active_plan_text}</code>\n"
        f"📈 <b>إجمالي العائد اليومي:</b> <code>{profit_text}</code>\n"
        f"👥 <b>إجمالي الإحالات:</b> <code>{ref_count} عضو</code>\n"
        "──────────────────────────\n"
        "⏳ <b>دورة الأرباح (أقرب استحقاق):</b>\n"
        f"[{get_progress_bar(percent)}] <code>{percent}%</code>\n"
        f"⏱️ <b>المتبقي للإضافة:</b> {timer_text}\n"
        "──────────────────────────\n"
        "اختر أحد العمليات:"
    )

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM dashboard_buttons ORDER BY row_order ASC, id ASC")
        db_buttons = c.fetchall()

    row_dict = {}
    for b in db_buttons:
        r = b["row_order"]
        if r not in row_dict:
            row_dict[r] = []
        
        if b["target_type"] == "url":
            row_dict[r].append(InlineKeyboardButton(text=b["title"], url=b["target_val"]))
        elif b["target_type"] == "custom_text":
            row_dict[r].append(InlineKeyboardButton(text=b["title"], callback_data=f"cstbtn_{b['id']}"))
        else:
            row_dict[r].append(InlineKeyboardButton(text=b["title"], callback_data=b["target_val"]))

    final_keyboard = []
    for r in sorted(row_dict.keys()):
        final_keyboard.append(row_dict[r])

    if is_admin(user_id):
        final_keyboard.append([InlineKeyboardButton(text="👑 لوحة القيادة العليا (الإدارة)", callback_data="admin_hub")])

    return text, InlineKeyboardMarkup(inline_keyboard=final_keyboard)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# ════════════════════ فحص الاشتراك الإجباري المتعدد فائق السرعة ════════════════════
async def get_unsubscribed_channels(user_id: int) -> list:
    if get_setting("force_sub_active", "0") == "0":
        return []

    now = time.time()
    if user_id in SUB_CACHE and (now - SUB_CACHE[user_id] < 120):
        return []

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM force_sub_channels")
        channels = c.fetchall()

    if not channels:
        return []

    unsubscribed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                unsubscribed.append(ch)
        except Exception:
            # إذا تعذر الفحص يعتبر مشتركاً لتفادي تعطيل البوت
            continue

    if not unsubscribed:
        SUB_CACHE[user_id] = now

    return unsubscribed

@dp.message.outer_middleware()
@dp.callback_query.outer_middleware()
async def security_guard(handler, event, data):
    user_id = event.from_user.id
    now = time.time()

    if now - user_last_action.get(user_id, 0) < 0.12:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    user_last_action[user_id] = now

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row and row["is_banned"] == 1:
            if isinstance(event, Message):
                await event.answer("🚫 حسابك محظور من الاستخدام.")
            else:
                await event.answer("🚫 حسابك محظور!", show_alert=True)
            return

    if get_setting("maintenance", "0") == "1" and not is_admin(user_id):
        msg = "🛠 المنظومة في وضع الصيانة والتحديثات الدورية حالياً."
        if isinstance(event, Message):
            await event.answer(msg)
        else:
            await event.answer("🛠 البوت قيد الصيانة!", show_alert=True)
        return

    # فحص الاشتراك الإجباري المتعدد لجميع القنوات والمجموعات
    if not is_admin(user_id):
        unsub_list = await get_unsubscribed_channels(user_id)
        if unsub_list:
            kb_rows = []
            for ch in unsub_list:
                kb_rows.append([InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch['invite_link'])])
            kb_rows.append([InlineKeyboardButton(text="✅ تحققت من الاشتراك", callback_data="refresh_dash")])
            
            txt = (
                "⚠️ <b>تنبيه هام للاشتراك:</b>\n"
                "──────────────────────────\n"
                "عليك الاشتراك في القنوات والمجموعات الرسمية أدناه لتتمكن من استخدام البوت:\n"
            )
            if isinstance(event, Message):
                await event.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
            else:
                try:
                    await event.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
                except Exception:
                    await event.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
                await event.answer()
            return

    return await handler(event, data)

async def auto_profit_background_worker():
    while True:
        try:
            now = int(time.time())
            cooldown = 86400
            with db_conn() as conn:
                c = conn.cursor()
                c.execute("UPDATE user_subscriptions SET status = 'completed' WHERE status = 'active' AND end_time <= ?", (now,))
                
                c.execute("""
                    SELECT id, user_id, plan_name, daily_profit, last_claim 
                    FROM user_subscriptions 
                    WHERE status = 'active' AND end_time > ?
                """, (now,))
                active_subs = c.fetchall()

                user_profits = {}
                for sub in active_subs:
                    s_id = sub["id"]
                    u_id = sub["user_id"]
                    last_c = sub["last_claim"]
                    profit = sub["daily_profit"]

                    if now - last_c >= cooldown:
                        days = (now - last_c) // cooldown
                        earned = round(days * profit, 2)
                        new_last_c = last_c + (days * cooldown)
                        c.execute("UPDATE user_subscriptions SET last_claim = ? WHERE id = ?", (new_last_c, s_id))
                        user_profits[u_id] = user_profits.get(u_id, 0.0) + earned

                for u_id, total_earned in user_profits.items():
                    total_earned = round(total_earned, 2)
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_earned, u_id))
                    try:
                        await bot.send_message(
                            u_id,
                            f"🎉 <b>إضافة أرباح تلقائية:</b>\n"
                            f"تم إضافة عوائد استثماراتك بقيمة <b>+${total_earned:.2f}</b> لمحفظتك بنجاح!"
                        )
                    except Exception:
                        pass
                conn.commit()
        except Exception as e:
            logging.error(f"Error in profit worker: {e}")
        await asyncio.sleep(60)

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    referrer_id = 0
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            referrer_id = 0

    get_user(message.from_user.id, message.from_user.username or message.from_user.first_name, referrer_id)
    welcome_text = get_setting("welcome_text")
    await message.answer(f"👋 {welcome_text}")
    text, kb = render_dashboard(message.from_user.id)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "cancel_action")
async def cancel_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("تم إلغاء العملية.")
    text, kb = render_dashboard(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "refresh_dash")
async def refresh_handler(call: CallbackQuery):
    if call.from_user.id in SUB_CACHE:
        del SUB_CACHE[call.from_user.id]
    await call.answer("تم التحديث 🔄")
    text, kb = render_dashboard(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data == "claim_profit")
async def claim_handler(call: CallbackQuery):
    user_id = call.from_user.id
    now = int(time.time())
    cooldown = 86400

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE user_subscriptions SET status = 'completed' WHERE status = 'active' AND end_time <= ?", (now,))
        c.execute("SELECT * FROM user_subscriptions WHERE user_id = ? AND status = 'active'", (user_id,))
        subs = c.fetchall()

        if not subs:
            await call.answer("⚠️ ليس لديك أي خطة استثمارية نشطة حالياً!", show_alert=True)
            return

        total_earned = 0.0
        min_remaining = cooldown
        has_ready = False

        for sub in subs:
            s_id = sub["id"]
            last_c = sub["last_claim"]
            profit = sub["daily_profit"]
            elapsed = now - last_c
            if elapsed >= cooldown:
                has_ready = True
                days = elapsed // cooldown
                earned = round(days * profit, 2)
                total_earned += earned
                new_last_c = last_c + (days * cooldown)
                c.execute("UPDATE user_subscriptions SET last_claim = ? WHERE id = ?", (new_last_c, s_id))
            else:
                rem = cooldown - elapsed
                if rem < min_remaining:
                    min_remaining = rem

        if has_ready and total_earned > 0:
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_earned, user_id))
            conn.commit()
            await call.answer(f"🎉 تم استلام أرباح باقاتك بنجاح: +${total_earned:.2f}", show_alert=True)
        else:
            conn.commit()
            h, m = min_remaining // 3600, (min_remaining % 3600) // 60
            await call.answer(f"⏳ دورة الأرباح مستمرة!\nمتبقي لأقرب باقة: {h} ساعة و {m} دقيقة.", show_alert=True)
            return

    text, kb = render_dashboard(user_id)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data == "open_plans")
async def plans_menu(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    now = int(time.time())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_subscriptions WHERE user_id = ? AND status = 'active' AND end_time > ?", (user_id, now))
        my_active_count = c.fetchone()[0]
        c.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY cost ASC")
        plans = c.fetchall()

    text = (
        "📊 <b>باقات الاستثمار الذكية:</b>\n"
        "──────────────────────────\n"
        "💡 <i>يمكنك الاشتراك في أكثر من باقة بنفس الوقت، وستعمل جميعها معاً لمضاعفة أرباحك اليومية.</i>\n\n"
    )
    buttons = []
    
    if my_active_count > 0:
        buttons.append([InlineKeyboardButton(text=f"📦 باقاتي النشطة ({my_active_count})", callback_data="user_my_active_plans")])

    for p in plans:
        total_p = round(p['daily_profit'] * p['duration_days'], 2)
        text += (
            f"🔹 <b>{p['name']}:</b>\n"
            f"• السعر: <b>${p['cost']:.2f}</b> | المدة: <b>{p['duration_days']} يوم</b>\n"
            f"• العائد اليومي: <b>+${p['daily_profit']:.2f}</b> | الإجمالي: <b>${total_p:.2f}</b>\n\n"
        )
        buttons.append([InlineKeyboardButton(text=f"⚡️ تفعيل {p['name']} (${p['cost']:.2f})", callback_data=f"buyplan_{p['id']}")])

    buttons.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "user_my_active_plans")
async def user_view_my_active_plans(call: CallbackQuery):
    user_id = call.from_user.id
    now = int(time.time())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM user_subscriptions 
            WHERE user_id = ? AND status = 'active' AND end_time > ? 
            ORDER BY id DESC
        """, (user_id, now))
        subs = c.fetchall()

    if not subs:
        await call.answer("ليس لديك أي باقة نشطة حالياً!", show_alert=True)
        return

    await call.answer()
    text = "📦 <b>قائمة باقاتك الاستثمارية النشطة حالياً:</b>\n──────────────────────────\n\n"
    total_daily = 0.0

    for idx, s in enumerate(subs, 1):
        rem_sec = max(0, s["end_time"] - now)
        rem_days = rem_sec // 86400
        rem_hours = (rem_sec % 86400) // 3600
        total_daily += s["daily_profit"]

        text += (
            f"<b>{idx}. {s['plan_name']}</b>\n"
            f"• الربح اليومي: <b>+${s['daily_profit']:.2f}</b>\n"
            f"• التكلفة: <code>${s['cost']:.2f}</code>\n"
            f"• المتبقي على الانتهاء: <b>{rem_days} يوم و {rem_hours} ساعة</b>\n\n"
        )

    text += f"──────────────────────────\n📈 <b>إجمالي أرباحك اليومية من كافة الباقات:</b> <b>+${total_daily:.2f}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ تفعيل باقة إضافية", callback_data="open_plans")],
        [InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("buyplan_"))
async def process_buy_plan(call: CallbackQuery):
    plan_id = int(call.data.replace("buyplan_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        p = c.fetchone()

    if not p or p["is_active"] == 0:
        await call.answer("⚠️ هذه الباقة غير متاحة للاشتراك حالياً!", show_alert=True)
        return

    user = get_user(call.from_user.id)
    if user["balance"] < p["cost"]:
        await call.answer(f"❌ رصيدك الحالي (${user['balance']:.2f}) غير كافٍ! اشحن محفظتك أولاً.", show_alert=True)
        return

    now = int(time.time())
    new_invested = user["total_invested"] + p["cost"]
    dur_seconds = p["duration_days"] * 86400

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance - ?, total_invested = ? WHERE user_id = ?", (p["cost"], new_invested, call.from_user.id))
        c.execute("""
            INSERT INTO user_subscriptions (user_id, plan_id, plan_name, cost, daily_profit, start_time, end_time, last_claim, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (call.from_user.id, plan_id, p["name"], p["cost"], p["daily_profit"], now, now + dur_seconds, now))
        conn.commit()

    await call.answer(f"✅ تم تفعيل {p['name']} بنجاح!", show_alert=True)
    text, kb = render_dashboard(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb)

# ════════════════════ نظام الإيداع ════════════════════
@dp.callback_query(F.data == "open_deposit")
async def deposit_select_method(call: CallbackQuery):
    if get_setting("deposit_active", "1") == "0":
        await call.answer("⚠️ الإيداع متوقف مؤقتاً للصيانة.", show_alert=True)
        return

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE category = 'deposit' AND is_active = 1 ORDER BY id ASC")
        methods = c.fetchall()

    if not methods:
        await call.answer("⚠️ لا توجد وسائل إيداع مفعلة حالياً.", show_alert=True)
        return

    await call.answer()
    text = (
        "💳 <b>بوابة الشحن المالي والإيداع الفوري:</b>\n"
        "──────────────────────────\n"
        "اختر وسيلة الدفع المناسبة لإصدار فاتورة شحن فورية:"
    )
    kb_list = []
    for m in methods:
        kb_list.append([InlineKeyboardButton(text=m["name"], callback_data=f"depm_dyn_{m['id']}")])
    kb_list.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("depm_dyn_"))
async def deposit_amount_presets(call: CallbackQuery, state: FSMContext):
    await call.answer()
    m_id = int(call.data.replace("depm_dyn_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE id = ?", (m_id,))
        m = c.fetchone()

    await state.update_data(
        dep_method_id=m_id,
        dep_method_name=m["name"],
        dep_method_details=m["details"],
        dep_raw_addr=m["raw_address"],
        dep_is_iqd=m["is_iqd"]
    )

    iqd_rate = float(get_setting("usd_to_iqd_rate", "1530"))
    iqd_info = f"\n💱 <b>سعر صرف المنصة:</b> 1$ = <code>{iqd_rate:,.0f} د.ع</code>\n" if m["is_iqd"] == 1 else ""

    text = (
        f"🧾 <b>وسيلة الإيداع: {m['name']}</b>\n"
        "──────────────────────────\n"
        f"📌 <b>بيانات التحويل المعتمدة:</b>\n{m['details']}\n"
        f"{iqd_info}"
        "──────────────────────────\n"
        "حدد المبلغ المراد شحنه بالدولار:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="$10", callback_data="depamt_10"),
            InlineKeyboardButton(text="$25", callback_data="depamt_25"),
            InlineKeyboardButton(text="$50", callback_data="depamt_50")
        ],
        [
            InlineKeyboardButton(text="$100", callback_data="depamt_100"),
            InlineKeyboardButton(text="$250", callback_data="depamt_250"),
            InlineKeyboardButton(text="✍️ مبلغ مخصص", callback_data="depamt_custom")
        ],
        [InlineKeyboardButton(text="🔙 رجوع للخلف", callback_data="open_deposit")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "depamt_custom")
async def ask_custom_deposit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.dep_custom_amount)
    await call.message.answer("✏️ أرسل المبلغ المراد شحنه بالدولار (أرقام فقط):", reply_markup=cancel_keyboard())

@dp.message(Form.dep_custom_amount)
async def get_custom_deposit(message: Message, state: FSMContext):
    try:
        amt = round(float(message.text), 2)
        if amt <= 0:
            await message.answer("❌ يجب إدخال مبلغ أكبر من 0.", reply_markup=cancel_keyboard())
            return
        await state.update_data(deposit_amount=amt)
        await generate_and_show_invoice(message, state)
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة فقط.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data.startswith("depamt_"))
async def preset_deposit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    amt = float(call.data.replace("depamt_", ""))
    await state.update_data(deposit_amount=amt)
    await generate_and_show_invoice(call.message, state)

async def generate_and_show_invoice(message: Message, state: FSMContext):
    data = await state.get_data()
    amt = data["deposit_amount"]
    m_name = data["dep_method_name"]
    m_details = data["dep_method_details"]
    raw_addr = data.get("dep_raw_addr", "")
    is_iqd = data.get("dep_is_iqd", 0)

    now = int(time.time())
    inv_code = str(random.randint(10000, 99999))
    await state.update_data(invoice_code=inv_code)

    date_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))

    iqd_section = ""
    if is_iqd == 1:
        rate = float(get_setting("usd_to_iqd_rate", "1530"))
        iqd_val = round(amt * rate)
        iqd_section = f"🇮🇶 <b>المبلغ بالدينار العراقي:</b>\n👉 <code>{iqd_val:,.0f} د.ع</code>\n───────────────────────────\n"

    invoice_text = (
        "╔═══════════════════════════════╗\n"
        f"   🧾 <b>فاتورة شحن رقمية رقم: {inv_code}</b>\n"
        "╚═══════════════════════════════╝\n\n"
        f"🔢 <b>رقم الفاتورة:</b> <code>{inv_code}</code>\n"
        f"📅 <b>تاريخ الإنشاء:</b> <code>{date_str}</code>\n"
        f"💵 <b>المبلغ المطلوب:</b> <code>${amt:.2f}</code>\n"
        f"{iqd_section}"
        f"⚙️ <b>وسيلة التحويل:</b> <b>{m_name}</b>\n\n"
        f"📍 <b>بيانات التحويل المعتمدة:</b>\n{m_details}\n\n"
        "───────────────────────────\n"
        "📸 <b>الخطوة الأخيرة:</b>\n"
        "قم بإتمام الحوالة ثم <b>أرسل لقطة الشاشة أو الوصل</b> هنا لاعتماد الرصيد:"
    )

    await state.set_state(Form.dep_proof)

    if raw_addr and len(raw_addr) > 5:
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={raw_addr}"
        try:
            photo = URLInputFile(qr_url)
            await message.answer_photo(photo=photo, caption=invoice_text, reply_markup=cancel_keyboard())
            return
        except Exception:
            pass

    await message.answer(invoice_text, reply_markup=cancel_keyboard())

@dp.message(Form.dep_proof)
async def process_deposit_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get("deposit_amount", 0.0)
    m_name = data.get("dep_method_name", "عام")
    inv_code = str(data.get("invoice_code", random.randint(10000, 99999)))
    user_id = message.from_user.id
    username = html.escape(message.from_user.username or message.from_user.first_name)
    now = int(time.time())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO operations (invoice_code, user_id, type, method, amount, fee, net_amount, details, created_at, expires_at) VALUES (?, ?, 'deposit', ?, ?, 0.0, ?, ?, ?, 0)",
            (inv_code, user_id, m_name, amt, amt, "إثبات قيد التدقيق", now)
        )
        op_id = c.lastrowid
        conn.commit()

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ قبول وشحن الرصيد", callback_data=f"adm_ok_dep_{op_id}_{user_id}"),
            InlineKeyboardButton(text="❌ رفض الإيداع", callback_data=f"adm_ask_refuse_dep_{op_id}_{user_id}")
        ]
    ])

    admin_caption = (
        f"🔔 <b>فاتورة إيداع رقم {inv_code}:</b>\n"
        f"👤 المستخدم: <code>{user_id}</code> (@{username})\n"
        f"⚙️ الوسيلة: <b>{m_name}</b>\n"
        f"💰 المبلغ: <b>${amt:.2f}</b>"
    )

    for adm in get_admins_with_perm("finance"):
        try:
            if message.photo:
                await bot.send_photo(adm, message.photo[-1].file_id, caption=admin_caption, reply_markup=admin_kb)
            else:
                await bot.send_message(adm, f"{admin_caption}\n📝 الإثبات:\n{html.escape(message.text or 'وصل بدون نص')}", reply_markup=admin_kb)
        except Exception:
            pass

    await state.clear()
    await message.answer(
        f"✅ <b>تم استلام وصل الفاتورة رقم {inv_code} بنجاح!</b>\n"
        "سيقوم المشرف بالتدقيق وشحن حسابك فوراً."
    )

# ════════════════════ نظام السحب المالي ════════════════════
@dp.callback_query(F.data == "open_withdraw")
async def withdraw_select_method(call: CallbackQuery):
    if get_setting("withdraw_active", "1") == "0":
        await call.answer("⚠️ السحب مقفل مؤقتاً للصيانة والتدقيق المالي.", show_alert=True)
        return

    min_w = float(get_setting("min_withdraw", "5.0"))
    max_daily = float(get_setting("max_daily_withdraw", "500.0"))
    user = get_user(call.from_user.id)
    bal = user["balance"]

    if bal < min_w:
        await call.answer(f"⚠️ الحد الأدنى للسحب هو ${min_w:.2f} (رصيدك: ${bal:.2f})", show_alert=True)
        return

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM operations WHERE user_id = ? AND type = 'withdraw' AND status = 'pending'", (call.from_user.id,))
        pending = c.fetchone()[0]

    if pending > 0:
        await call.answer("⚠️ لديك طلب سحب معلق بالفعل! يمكنك إلغاؤه من قسم التتبع إن أردت.", show_alert=True)
        return

    one_day_ago = int(time.time()) - 86400
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT SUM(amount) FROM operations WHERE user_id = ? AND type = 'withdraw' AND status = 'approved' AND created_at > ?", (call.from_user.id, one_day_ago))
        total_withdrawn_today = c.fetchone()[0] or 0.0

    if total_withdrawn_today >= max_daily:
        await call.answer(f"⚠️ تجاوزت سقف السحب اليومي المسموح به (${max_daily:.2f}). حاول غداً.", show_alert=True)
        return

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE category = 'withdraw' AND is_active = 1 ORDER BY id ASC")
        methods = c.fetchall()

    if not methods:
        await call.answer("⚠️ لا توجد وسائل سحب مفعلة حالياً.", show_alert=True)
        return

    await call.answer()
    text = (
        "💸 <b>بوابة السحب المالي المباشر</b>\n"
        "──────────────────────────\n"
        f"💰 رصيدك المتاح: <b>${bal:.2f}</b>\n"
        f"💵 الحد الأدنى: <b>${min_w:.2f}</b> | السقف اليومي: <b>${max_daily:.2f}</b>\n"
        "──────────────────────────\n"
        "اختر وسيلة استلام أموالك:"
    )
    kb_list = []
    for m in methods:
        fee_txt = f" (عمولة {m['fee_percent']}%)" if m["fee_percent"] > 0 else " (مجاناً 0%)"
        kb_list.append([InlineKeyboardButton(text=f"{m['name']}{fee_txt}", callback_data=f"wthm_dyn_{m['id']}")])
    kb_list.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("wthm_dyn_"))
async def withdraw_amount_step(call: CallbackQuery, state: FSMContext):
    await call.answer()
    m_id = int(call.data.replace("wthm_dyn_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE id = ?", (m_id,))
        m = c.fetchone()

    await state.update_data(
        wth_method_id=m_id,
        wth_method_name=m["name"],
        wth_instruction=m["details"],
        wth_fee_percent=m["fee_percent"],
        wth_is_iqd=m["is_iqd"]
    )
    user = get_user(call.from_user.id)
    bal = user["balance"]

    text = (
        f"⚙️ <b>وسيلة السحب:</b> {m['name']}\n"
        f"🏷 <b>عمولة السحب:</b> <code>{m['fee_percent']}%</code>\n"
        f"💰 <b>رصيدك المتاح:</b> <code>${bal:.2f}</code>\n\n"
        "اختر المبلغ المراد سحبه:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="$5", callback_data="wthamt_5"),
            InlineKeyboardButton(text="$10", callback_data="wthamt_10"),
            InlineKeyboardButton(text="$25", callback_data="wthamt_25")
        ],
        [
            InlineKeyboardButton(text="$50", callback_data="wthamt_50"),
            InlineKeyboardButton(text="💰 سحب الكل", callback_data=f"wthamt_{bal}"),
            InlineKeyboardButton(text="✍️ مبلغ مخصص", callback_data="wthamt_custom")
        ],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="open_withdraw")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "wthamt_custom")
async def ask_custom_withdraw(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.wth_custom_amount)
    min_w = float(get_setting("min_withdraw", "5.0"))
    await call.message.answer(f"✏️ أرسل المبلغ المراد سحبه بالدولار (الحد الأدنى ${min_w:.2f}):", reply_markup=cancel_keyboard())

@dp.message(Form.wth_custom_amount)
async def get_custom_withdraw(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    min_w = float(get_setting("min_withdraw", "5.0"))
    try:
        amt = round(float(message.text), 2)
        if amt < min_w or amt > user["balance"]:
            await message.answer(f"❌ مبلغ غير صالح! الحد الأدنى ${min_w:.2f} ورصيدك (${user['balance']:.2f}).", reply_markup=cancel_keyboard())
            return
        await state.update_data(wth_amount=amt)
        await prompt_withdraw_target_choice(message, state)
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام فقط.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data.startswith("wthamt_"))
async def preset_withdraw(call: CallbackQuery, state: FSMContext):
    amt = round(float(call.data.replace("wthamt_", "")), 2)
    user = get_user(call.from_user.id)
    min_w = float(get_setting("min_withdraw", "5.0"))

    if amt < min_w or amt > user["balance"]:
        await call.answer(f"❌ المبلغ غير متوافق مع رصيدك (${user['balance']:.2f})!", show_alert=True)
        return

    await call.answer()
    await state.update_data(wth_amount=amt)
    await prompt_withdraw_target_choice(call.message, state, call.from_user.id)

async def prompt_withdraw_target_choice(message: Message, state: FSMContext, u_id: int = None):
    user_id = u_id or message.chat.id
    user = get_user(user_id)
    saved_w = user["saved_wallet"]
    data = await state.get_data()
    instr = data.get("wth_instruction", "أرسل بيانات الاستلام")

    if saved_w:
        text = (
            "📁 <b>دفتر العناوين المعتمد:</b>\n\n"
            f"لديك حساب استلام محفوظ مسبقاً:\n<code>{saved_w}</code>\n\n"
            "هل ترغب بالسحب إليه فوراً أم إدخال حساب جديد؟"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ السحب للحساب المحفوظ", callback_data="wth_use_saved_wallet")],
            [InlineKeyboardButton(text="✍️ إدخال عنوان / رقم جديد", callback_data="wth_enter_new_wallet")],
            [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action")]
        ])
        await message.answer(text, reply_markup=kb)
    else:
        await state.set_state(Form.wth_target_address)
        await message.answer(f"📝 {instr}:", reply_markup=cancel_keyboard())

@dp.callback_query(F.data == "wth_use_saved_wallet")
async def use_saved_wallet_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user = get_user(call.from_user.id)
    await render_final_withdraw_confirm(call.message, state, user["saved_wallet"])

@dp.callback_query(F.data == "wth_enter_new_wallet")
async def enter_new_wallet_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.wth_target_address)
    data = await state.get_data()
    instr = data.get("wth_instruction", "أرسل بيانات الاستلام")
    await call.message.answer(f"📝 {instr}:", reply_markup=cancel_keyboard())

@dp.message(Form.wth_target_address)
async def get_new_wallet_target(message: Message, state: FSMContext):
    target = html.escape(message.text.strip())
    update_user(message.from_user.id, saved_wallet=target)
    await render_final_withdraw_confirm(message, state, target)

async def render_final_withdraw_confirm(message: Message, state: FSMContext, target: str):
    await state.update_data(wth_target=target)
    data = await state.get_data()

    amt = data["wth_amount"]
    method_name = data["wth_method_name"]
    fee_percent = data.get("wth_fee_percent", 0.0)
    is_iqd = data.get("wth_is_iqd", 0)

    fee_amount = round(amt * (fee_percent / 100), 2)
    net_amt = round(amt - fee_amount, 2)
    await state.update_data(wth_fee=fee_amount, wth_net=net_amt)

    iqd_payout_text = ""
    if is_iqd == 1:
        rate = float(get_setting("usd_to_iqd_rate", "1530"))
        iqd_val = round(net_amt * rate)
        iqd_payout_text = f"🇮🇶 <b>الصافي المحول بالدينار العراقي:</b>\n👉 <code>{iqd_val:,.0f} د.ع</code>\n───────────────────────────\n"

    text = (
        "╔═══════════════════════════════╗\n"
        "   🔍 <b>مراجعة وتأكيد طلب السحب المالي</b>\n"
        "╚═══════════════════════════════╝\n\n"
        f"💵 <b>المبلغ الإجمالي:</b> <code>${amt:.2f}</code>\n"
        f"🏷 <b>عمولة السحب ({fee_percent}%):</b> <code>${fee_amount:.2f}</code>\n"
        f"💰 <b>صافي المبلغ المحول:</b> <b>${net_amt:.2f}</b>\n"
        f"{iqd_payout_text}"
        f"⚙️ <b>وسيلة الاستلام:</b> <b>{method_name}</b>\n"
        f"🎯 <b>عنوان / حساب الاستلام:</b>\n<code>{target}</code>\n"
        "───────────────────────────\n"
        "اضغط تأكيد لإرسال طلب التحويل فوراً:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأكيد وإرسال الطلب فوراً", callback_data="confirm_final_withdraw")],
        [InlineKeyboardButton(text="❌ إلغاء وتعديل", callback_data="cancel_action")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "confirm_final_withdraw")
async def finalize_withdraw_execution(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "wth_amount" not in data:
        await call.answer("انتهت الجلسة، يرجى إعادة المحاولة.", show_alert=True)
        return

    amt = data["wth_amount"]
    fee = data.get("wth_fee", 0.0)
    net_amt = data.get("wth_net", amt)
    method_name = data["wth_method_name"]
    target = data["wth_target"]
    user_id = call.from_user.id
    now = int(time.time())
    wth_code = str(random.randint(10000, 99999))

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        cur_bal = c.fetchone()["balance"]
        if cur_bal < amt:
            await call.answer("❌ رصيدك غير كافٍ!", show_alert=True)
            await state.clear()
            return

        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, user_id))
        c.execute(
            "INSERT INTO operations (invoice_code, user_id, type, method, amount, fee, net_amount, details, created_at) VALUES (?, ?, 'withdraw', ?, ?, ?, ?, ?, ?)",
            (wth_code, user_id, method_name, amt, fee, net_amt, target, now)
        )
        op_id = c.lastrowid
        conn.commit()

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأكيد التحويل وإرسال الوصل", callback_data=f"adm_ok_wth_{op_id}_{user_id}"),
            InlineKeyboardButton(text="❌ رفض السحب", callback_data=f"adm_ask_refuse_wth_{op_id}_{user_id}")
        ]
    ])

    admin_text = (
        f"🚨 <b>طلب سحب رقم {wth_code}:</b>\n"
        f"👤 المستخدم: <code>{user_id}</code> (@{html.escape(call.from_user.username or call.from_user.first_name)})\n"
        f"⚙️ الطريقة: <b>{method_name}</b>\n"
        f"💵 الإجمالي: <code>${amt:.2f}</code> | الصافي المطلوب: <b>${net_amt:.2f}</b>\n"
        f"🎯 الحساب المستلم:\n<code>{target}</code>"
    )

    for adm in get_admins_with_perm("finance"):
        try:
            await bot.send_message(adm, admin_text, reply_markup=admin_kb)
        except Exception:
            pass

    await state.clear()
    await call.message.edit_text(
        f"🎉 <b>تم تسجيل طلب السحب رقم {wth_code} بنجاح!</b>\n\n"
        f"• المبلغ: <b>${amt:.2f}</b>\n"
        f"• الصافي: <b>${net_amt:.2f}</b>\n"
        f"• الوسيلة: <b>{method_name}</b>\n\n"
        "💡 <i>يمكنك تتبع حالة الطلب بالرقم أعلاه من قسم تتبع المعاملات.</i>"
    )

# ════════════════════ مركز تتبع المعاملات ════════════════════
async def show_operation_card(target, op, is_edit: bool = False, viewer_id: int = None):
    st_map = {
        "pending": "⏳ قيد الانتظار والتدقيق",
        "approved": "✅ مكتملة ومؤكدة",
        "rejected": "❌ مرفوضة",
        "cancelled_by_user": "↩️ مستردة إلى المحفظة"
    }
    st_text = st_map.get(op["status"], op["status"])
    d_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(op["created_at"]))

    text = (
        "╔══════════════════════════╗\n"
        f"   🧾 <b>بيانات المعاملة رقم: {op['invoice_code']}</b>\n"
        "╚══════════════════════════╝\n\n"
        f"🔢 <b>رقم المعاملة:</b> <code>{op['invoice_code']}</code>\n"
        f"• النوع: <b>{'شحن رصيد (إيداع)' if op['type'] == 'deposit' else 'سحب نقدي'}</b>\n"
        f"• الوسيلة: <b>{op['method']}</b>\n"
        f"• المبلغ الإجمالي: <b>${op['amount']:.2f}</b>\n"
        f"• الصافي المستلم: <b>${op['net_amount']:.2f}</b>\n"
        f"• الحالة: <b>{st_text}</b>\n"
        f"• التاريخ: <code>{d_str}</code>\n"
        f"• تفاصيل الحساب:\n<code>{op['details']}</code>\n"
        "──────────────────────────"
    )

    kb_list = []
    u_id = viewer_id
    if u_id is None:
        if isinstance(target, CallbackQuery):
            u_id = target.from_user.id
        elif isinstance(target, Message):
            u_id = target.from_user.id

    if op["user_id"] == u_id and op["type"] == "withdraw" and op["status"] == "pending":
        kb_list.append([InlineKeyboardButton(text="↩️ إلغاء السحب واسترداد الرصيد فوراً", callback_data=f"user_cancel_wth_{op['id']}")])

    kb_list.append([InlineKeyboardButton(text="🔙 رجوع لمركز المعاملات", callback_data="open_track_op")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=kb_list)

    if is_edit and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            await target.message.answer(text, reply_markup=reply_markup)
    elif isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup)
    elif isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=reply_markup)

@dp.callback_query(F.data == "open_track_op")
async def open_tracker_menu(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM operations WHERE user_id = ? ORDER BY id DESC LIMIT 6", (user_id,))
        ops = c.fetchall()

    text = (
        "🔍 <b>مركز تتبع وإدارة المعاملات:</b>\n"
        "──────────────────────────\n"
        "اختر معاملتك من القائمة أو ابحث برقم المعاملة مباشرة:"
    )

    kb_list = []
    for op in ops:
        st_icon = "⏳" if op["status"] == "pending" else ("✅" if op["status"] == "approved" else "❌")
        op_type = "إيداع" if op["type"] == "deposit" else "سحب"
        kb_list.append([
            InlineKeyboardButton(
                text=f"{st_icon} #{op['invoice_code']} | {op_type} ${op['amount']:.2f}",
                callback_data=f"view_op_{op['id']}"
            )
        ])

    kb_list.append([InlineKeyboardButton(text="🔎 استعلام برقم المعاملة (أرقام فقط)", callback_data="track_custom_code")])
    kb_list.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("view_op_"))
async def view_operation_detail(call: CallbackQuery):
    await call.answer()
    op_id = int(call.data.replace("view_op_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM operations WHERE id = ?", (op_id,))
        op = c.fetchone()

    if not op:
        await call.answer("المعاملة غير موجودة!", show_alert=True)
        return

    await show_operation_card(call, op, is_edit=True)

@dp.callback_query(F.data.startswith("user_cancel_wth_"))
async def execute_user_withdrawal_cancellation(call: CallbackQuery):
    op_id = int(call.data.replace("user_cancel_wth_", ""))
    user_id = call.from_user.id

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM operations WHERE id = ? AND user_id = ? AND status = 'pending'", (op_id, user_id))
        op = c.fetchone()

        if not op:
            await call.answer("⚠️ لا يمكن إلغاء هذه العملية.", show_alert=True)
            return

        amt = op["amount"]
        c.execute("UPDATE operations SET status = 'cancelled_by_user' WHERE id = ?", (op_id,))
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, user_id))
        conn.commit()

    await call.answer(f"✅ تم إلغاء الطلب واسترداد ${amt:.2f} لمحفظتك فوراً!", show_alert=True)
    await open_tracker_menu(call)

@dp.callback_query(F.data == "track_custom_code")
async def ask_track_code(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.track_code)
    text = (
        "🔍 <b>أرسل رقم المعاملة للبحث عنها:</b>\n"
        "──────────────────────────\n"
        "(أرسل أرقاماً فقط مثال: <code>62554</code>):"
    )
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.track_code)
async def process_track_custom_code(message: Message, state: FSMContext):
    raw = message.text.strip()
    clean_digits = "".join(filter(str.isdigit, raw))

    with db_conn() as conn:
        c = conn.cursor()
        if clean_digits:
            c.execute("""
                SELECT * FROM operations 
                WHERE invoice_code = ? 
                   OR invoice_code = ?
                   OR id = ? 
                   OR invoice_code LIKE ?
                ORDER BY id DESC LIMIT 1
            """, (clean_digits, raw, int(clean_digits), f"%{clean_digits}%"))
        else:
            c.execute("SELECT * FROM operations WHERE invoice_code = ? ORDER BY id DESC LIMIT 1", (raw,))
        op = c.fetchone()

    if not op:
        await message.answer(
            "❌ <b>لم يتم العثور على أي معاملة بهذا الرقم!</b>\n"
            "يرجى التأكد من كتابة الأرقام بشكل صحيح (مثال: <code>62554</code>):",
            reply_markup=cancel_keyboard()
        )
        return

    await state.clear()
    await show_operation_card(message, op, is_edit=False)

# ════════════════════ قرارات المشرف المالي ════════════════════
@dp.callback_query(F.data.startswith("adm_ask_refuse_"))
async def admin_choose_refuse_reason(call: CallbackQuery):
    if not has_permission(call.from_user.id, "finance"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالعمليات المالية!", show_alert=True)
        return
    await call.answer()
    parts = call.data.split("_")
    op_type = parts[3]
    op_id = parts[4]
    u_id = parts[5]

    text = "اختر سبب الرفض ليتم إرساله للمستخدم تلقائياً بالوصل:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ وصل التحويل غير مطابق أو غير واضح", callback_data=f"adm_rej_{op_type}_{op_id}_{u_id}_1")],
        [InlineKeyboardButton(text="❌ عنوان المحفظة أو الشبكة غير صحيحة", callback_data=f"adm_rej_{op_type}_{op_id}_{u_id}_2")],
        [InlineKeyboardButton(text="❌ المبلغ المحول ناقص", callback_data=f"adm_rej_{op_type}_{op_id}_{u_id}_3")],
        [InlineKeyboardButton(text="🔙 تراجع", callback_data="admin_hub")]
    ])

    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=kb)
        else:
            await call.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("adm_rej_"))
async def execute_refusal(call: CallbackQuery):
    if not has_permission(call.from_user.id, "finance"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالعمليات المالية!", show_alert=True)
        return
    parts = call.data.split("_")
    op_type = parts[2]
    op_id = int(parts[3])
    u_id = int(parts[4])
    r_code = parts[5]
    reason = REASONS_MAP.get(r_code, "تم رفض العملية من قبل الإدارة")

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT amount FROM operations WHERE id = ?", (op_id,))
        row_op = c.fetchone()
        amt = row_op["amount"] if row_op else 0.0

        c.execute("UPDATE operations SET status = 'rejected', details = details || ' - سبب الرفض: ' || ? WHERE id = ?", (reason, op_id))
        
        if op_type == "wth":
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, u_id))
            try:
                await bot.send_message(
                    u_id,
                    f"❌ <b>إشعار رفض سحب:</b>\n"
                    f"• السبب: <b>{reason}</b>\n"
                    f"• تمت إعادة المبلغ كاملاً (<b>${amt:.2f}</b>) إلى محفظتك."
                )
            except Exception:
                pass
        else:
            try:
                await bot.send_message(
                    u_id,
                    f"❌ <b>إشعار رفض إيداع:</b>\n"
                    f"• السبب: <b>{reason}</b>\n"
                    "يرجى مراجعة الدعم الفني للاستفسار."
                )
            except Exception:
                pass
        conn.commit()

    status_note = f"\n\n❌ [تم الرفض بالسبب: {reason}]"
    try:
        if call.message.photo:
            cur_caption = call.message.caption or ""
            await call.message.edit_caption(caption=cur_caption + status_note)
        else:
            cur_text = call.message.text or ""
            await call.message.edit_text(text=cur_text + status_note)
    except Exception:
        pass
    await call.answer("تم الرفض وتحديث السجلات.")

@dp.callback_query(F.data.startswith("adm_ok_"))
async def execute_approval(call: CallbackQuery):
    if not has_permission(call.from_user.id, "finance"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالعمليات المالية!", show_alert=True)
        return
    parts = call.data.split("_")
    op_type = parts[2]
    op_id = int(parts[3])
    u_id = int(parts[4])
    date_now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT invoice_code, amount, net_amount, method FROM operations WHERE id = ?", (op_id,))
        row_op = c.fetchone()
        inv_code = row_op["invoice_code"] if row_op else str(op_id)
        amt = row_op["amount"] if row_op else 0.0
        net_amt = row_op["net_amount"] if row_op else amt
        method = row_op["method"] if row_op else "تحويل عام"

        if op_type == "dep":
            user = get_user(u_id)
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, u_id))
            c.execute("UPDATE operations SET status = 'approved' WHERE id = ?", (op_id,))
            
            ref_percent = float(get_setting("ref_percent", "10"))
            ref_id = user["referrer_id"]
            if ref_id and ref_id != 0:
                bonus = round(amt * (ref_percent / 100), 2)
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, ref_id))
                try:
                    await bot.send_message(ref_id, f"🎉 <b>مكافأة إحالة!</b>\nحصلت على عمولة كاش: <b>+${bonus:.2f}</b>.")
                except Exception:
                    pass

            deposit_slip = (
                "╔═══════════════════════════════╗\n"
                "      🧾 <b>وصل إيداع مالي معتمد</b>\n"
                "╚═══════════════════════════════╝\n\n"
                f"🔢 <b>رقم المعاملة:</b> <code>{inv_code}</code>\n"
                f"• المبلغ المودع: <b>+${amt:.2f}</b>\n"
                f"• الحالة: <b>مكتملة ومؤكدة ✅</b>\n"
                f"• التوقيت: <code>{date_now}</code>\n"
                "───────────────────────────\n"
                "تم شحن رصيد محفظتك بنجاح وبإمكانك استثماره الآن."
            )
            try:
                await bot.send_message(u_id, deposit_slip)
            except Exception:
                pass

            try:
                if call.message.photo:
                    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ [تم قبول وشحن الحساب]")
                else:
                    await call.message.edit_text(text=(call.message.text or "") + "\n\n✅ [تم قبول وشحن الحساب]")
            except Exception:
                pass

        elif op_type == "wth":
            c.execute("UPDATE operations SET status = 'approved' WHERE id = ?", (op_id,))
            
            payout_slip = (
                "╔═══════════════════════════════╗\n"
                "      💸 <b>وصل تحويل مالي معتمد</b>\n"
                "╚═══════════════════════════════╝\n\n"
                f"🔢 <b>رقم المعاملة:</b> <code>{inv_code}</code>\n"
                f"• المبلغ المحول: <b>${net_amt:.2f}</b>\n"
                f"• الوسيلة: <b>{method}</b>\n"
                f"• الحالة: <b>تم التحويل بنجاح ✅</b>\n"
                f"• التوقيت: <code>{date_now}</code>\n"
                "───────────────────────────\n"
                "يرجى تفقد حسابك للتأكد من وصول الحوالة."
            )
            try:
                await bot.send_message(u_id, payout_slip)
            except Exception:
                pass

            try:
                if call.message.photo:
                    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ [تم تأكيد التحويل المالي]")
                else:
                    await call.message.edit_text(text=(call.message.text or "") + "\n\n✅ [تم تأكيد التحويل المالي]")
            except Exception:
                pass

            proof_ch = get_setting("proof_channel")
            if proof_ch:
                try:
                    proof_text = (
                        "⚡️ <b>إثبات سحب ناجح جديد!</b> ⚡️\n\n"
                        f"👤 المشترك: <code>{str(u_id)[:3]}***{str(u_id)[-2:]}</code>\n"
                        f"🔢 رقم العملية: <code>{inv_code}</code>\n"
                        f"💰 المبلغ: <b>${net_amt:.2f}</b>\n"
                        f"⚙️ وسيلة الدفع: <b>{method}</b>\n"
                        f"⏱️ التاريخ: <code>{date_now}</code>\n"
                        "──────────────────\n"
                        "استثمر واسحب أرباحك فوراً بكل ثقة!"
                    )
                    await bot.send_message(proof_ch, proof_text)
                except Exception:
                    pass

        conn.commit()
    await call.answer("تمت معالجة الطلب بنجاح.")

# ════════════════════ نظام إدارة الباقات ════════════════════
@dp.callback_query(F.data == "adm_manage_plans")
async def adm_manage_plans_menu(call: CallbackQuery):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans ORDER BY id ASC")
        plans = c.fetchall()

    text = (
        "📊 <b>التحكم الشامل بباقات الاستثمار:</b>\n"
        "──────────────────────────\n"
        "يمكنك إضافة باقة جديدة، أو تعديل شروط وأرباح وحالة أي باقة حالية:"
    )
    buttons = []
    for p in plans:
        status_icon = "🟢" if p["is_active"] == 1 else "🔴 (معطلة)"
        buttons.append([InlineKeyboardButton(text=f"{status_icon} {p['name']} (${p['cost']:.0f})", callback_data=f"admpln_opt_{p['id']}")])

    buttons.append([InlineKeyboardButton(text="➕ إضافة باقة استثمارية جديدة", callback_data="adm_add_plan_start")])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع للوحة الإدارة", callback_data="admin_hub")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "adm_add_plan_start")
async def adm_add_plan_start(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_add_plan_name)
    await call.message.answer("✏️ أرسل اسم الباقة الجديدة (مثال: <code>باقة كبار المستثمرين VIP</code>):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_plan_name)
async def adm_add_plan_name_step(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "plans"):
        return
    await state.update_data(new_p_name=message.text.strip())
    await state.set_state(Form.admin_add_plan_cost)
    await message.answer("💵 أرسل سعر الاشتراك بالدولار (أرقام فقط):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_plan_cost)
async def adm_add_plan_cost_step(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "plans"):
        return
    try:
        cost = round(float(message.text), 2)
        if cost <= 0:
            await message.answer("❌ يجب أن يكون السعر أكبر من 0.")
            return
        await state.update_data(new_p_cost=cost)
        await state.set_state(Form.admin_add_plan_profit)
        await message.answer("📈 أرسل الربح اليومي بالدولار (أرقام فقط):", reply_markup=cancel_keyboard())
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة.")

@dp.message(Form.admin_add_plan_profit)
async def adm_add_plan_profit_step(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "plans"):
        return
    try:
        profit = round(float(message.text), 2)
        if profit <= 0:
            await message.answer("❌ يجب أن يكون الربح أكبر من 0.")
            return
        await state.update_data(new_p_profit=profit)
        await state.set_state(Form.admin_add_plan_duration)
        await message.answer("⏳ أرسل مدة الباقة بالأيام (مثال: <code>30</code>):", reply_markup=cancel_keyboard())
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة.")

@dp.message(Form.admin_add_plan_duration)
async def adm_add_plan_duration_step(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "plans"):
        return
    try:
        duration = int(message.text)
        if duration <= 0:
            await message.answer("❌ يجب أن تكون الأيام 1 على الأقل.")
            return
        data = await state.get_data()
        name = data["new_p_name"]
        cost = data["new_p_cost"]
        profit = data["new_p_profit"]

        with db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO plans (name, cost, daily_profit, duration_days, is_active) VALUES (?, ?, ?, ?, 1)",
                (name, cost, profit, duration)
            )
            conn.commit()

        await state.clear()
        await message.answer(f"✅ <b>تمت إضافة الباقة ({name}) بنجاح!</b>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة لقائمة الباقات", callback_data="adm_manage_plans")]])
        await message.answer("اضغط للمتابعة:", reply_markup=kb)
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح للأيام.")

@dp.callback_query(F.data.startswith("admpln_opt_"))
async def adm_plan_options(call: CallbackQuery):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    await call.answer()
    plan_id = int(call.data.replace("admpln_opt_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        p = c.fetchone()

    if not p:
        await call.answer("الباقة غير موجودة!", show_alert=True)
        return

    st_txt = "🟢 مفعلة وتظهر للمستخدمين" if p["is_active"] == 1 else "🔴 معطلة ومخفية عن الشراء"
    btn_toggle = "🔴 إيقاف مؤقت" if p["is_active"] == 1 else "🟢 إعادة التفعيل"

    text = (
        f"⚙️ <b>إدارة الباقة: {p['name']}</b>\n"
        "──────────────────────────\n"
        f"• الحالة: <b>{st_txt}</b>\n"
        f"• سعر الاشتراك: <b>${p['cost']:.2f}</b>\n"
        f"• الربح اليومي: <b>${p['daily_profit']:.2f}</b>\n"
        f"• المدة بالأيام: <b>{p['duration_days']} يوم</b>\n"
        f"• الإجمالي المحقق: <b>${p['daily_profit'] * p['duration_days']:.2f}</b>\n"
        "──────────────────────────"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_toggle, callback_data=f"admpln_toggle_{plan_id}")],
        [
            InlineKeyboardButton(text="✏️ الاسم", callback_data=f"admpln_edit_{plan_id}_name"),
            InlineKeyboardButton(text="💵 السعر", callback_data=f"admpln_edit_{plan_id}_cost")
        ],
        [
            InlineKeyboardButton(text="📈 الربح اليومي", callback_data=f"admpln_edit_{plan_id}_profit"),
            InlineKeyboardButton(text="⏳ مدة الأيام", callback_data=f"admpln_edit_{plan_id}_duration")
        ],
        [InlineKeyboardButton(text="🗑 حذف الباقة نهائياً", callback_data=f"admpln_delete_{plan_id}")],
        [InlineKeyboardButton(text="🔙 رجوع للباقات", callback_data="adm_manage_plans")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("admpln_toggle_"))
async def adm_plan_toggle(call: CallbackQuery):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    plan_id = int(call.data.replace("admpln_toggle_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT is_active FROM plans WHERE id = ?", (plan_id,))
        cur = c.fetchone()["is_active"]
        new_val = 0 if cur == 1 else 1
        c.execute("UPDATE plans SET is_active = ? WHERE id = ?", (new_val, plan_id))
        conn.commit()

    await call.answer("تم تبديل حالة الباقة بنجاح.")
    call.data = f"admpln_opt_{plan_id}"
    await adm_plan_options(call)

@dp.callback_query(F.data.startswith("admpln_delete_"))
async def adm_plan_delete(call: CallbackQuery):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    plan_id = int(call.data.replace("admpln_delete_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.commit()

    await call.answer("تم حذف الباقة بنجاح.", show_alert=True)
    await adm_manage_plans_menu(call)

@dp.callback_query(F.data.startswith("admpln_edit_"))
async def prompt_edit_plan_val(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "plans"):
        await call.answer("⛔️ ليس لديك صلاحية للتحكم بالباقات!", show_alert=True)
        return
    await call.answer()
    parts = call.data.split("_")
    plan_id = int(parts[2])
    field = parts[3]
    await state.update_data(edit_plan_id=plan_id, edit_plan_field=field)
    await state.set_state(Form.admin_edit_plan_val)
    
    field_names = {"name": "اسم الباقة", "cost": "سعر الاشتراك", "profit": "الربح اليومي", "duration": "مدة الأيام"}
    await call.message.answer(f"✏️ أرسل القيمة الجديدة لـ ({field_names.get(field, field)}):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_edit_plan_val)
async def save_edited_plan_val(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "plans"):
        return
    data = await state.get_data()
    plan_id = data["edit_plan_id"]
    field = data["edit_plan_field"]
    val_raw = message.text.strip()

    with db_conn() as conn:
        c = conn.cursor()
        if field == "name":
            c.execute("UPDATE plans SET name = ? WHERE id = ?", (val_raw, plan_id))
        elif field == "cost":
            c.execute("UPDATE plans SET cost = ? WHERE id = ?", (round(float(val_raw), 2), plan_id))
        elif field == "profit":
            c.execute("UPDATE plans SET daily_profit = ? WHERE id = ?", (round(float(val_raw), 2), plan_id))
        elif field == "duration":
            c.execute("UPDATE plans SET duration_days = ? WHERE id = ?", (int(val_raw), plan_id))
        conn.commit()

    await state.clear()
    await message.answer("✅ تم تحديث بيانات الباقة بنجاح!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للباقات", callback_data="adm_manage_plans")]])
    await message.answer("اضغط للمتابعة:", reply_markup=kb)

# ════════════════════ إدارة باقات المشتركين مباشرة ════════════════════
@dp.callback_query(F.data.startswith("adm_usubs_"))
async def adm_view_user_subscriptions(call: CallbackQuery):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة المستخدمين!", show_alert=True)
        return
    await call.answer()
    uid = int(call.data.replace("adm_usubs_", ""))
    now = int(time.time())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM user_subscriptions WHERE user_id = ? ORDER BY id DESC", (uid,))
        subs = c.fetchall()

    text = f"📦 <b>إدارة باقات المشترك: <code>{uid}</code></b>\n──────────────────────────\n"
    kb_list = []

    if not subs:
        text += "<i>لا توجد باقات سابقة أو حالية لهذا المستخدم.</i>\n\n"
    else:
        for s in subs:
            is_active = (s["status"] == "active" and s["end_time"] > now)
            st_icon = "🟢 نشطة" if is_active else ("🔴 ملغاة" if s["status"] == "cancelled_by_admin" else "⚪️ منتهية")
            rem_d = max(0, (s["end_time"] - now) // 86400) if is_active else 0

            text += (
                f"• <b>{s['plan_name']}</b> (#{s['id']})\n"
                f"  - الحالة: <b>{st_icon}</b> | ربح يومي: <b>${s['daily_profit']:.2f}</b>\n"
                f"  - متبقي: <b>{rem_d} يوم</b>\n"
            )
            if is_active:
                kb_list.append([InlineKeyboardButton(text=f"❌ إلغاء وحذف: {s['plan_name']}", callback_data=f"adm_cancelsub_{s['id']}_{uid}")])

    kb_list.append([InlineKeyboardButton(text="➕ تفعيل باقة مجانية للمشترك مباشرة", callback_data=f"adm_giftsub_{uid}")])
    kb_list.append([InlineKeyboardButton(text="🔙 رجوع لملف المستخدم", callback_data=f"adm_backuser_{uid}")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("adm_cancelsub_"))
async def adm_cancel_user_sub(call: CallbackQuery):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة المستخدمين!", show_alert=True)
        return
    parts = call.data.split("_")
    sub_id, uid = int(parts[2]), int(parts[3])

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT plan_name FROM user_subscriptions WHERE id = ?", (sub_id,))
        row = c.fetchone()
        plan_name = row["plan_name"] if row else "الباقة"
        c.execute("UPDATE user_subscriptions SET status = 'cancelled_by_admin' WHERE id = ?", (sub_id,))
        conn.commit()

    try:
        await bot.send_message(uid, f"⚠️ <b>إشعار إداري:</b> تم إلغاء اشتراكك في <b>{plan_name}</b> من قبل إدارة المنصة.")
    except Exception:
        pass

    await call.answer(f"✅ تم إلغاء الباقة #{sub_id} بنجاح.", show_alert=True)
    call.data = f"adm_usubs_{uid}"
    await adm_view_user_subscriptions(call)

@dp.callback_query(F.data.startswith("adm_giftsub_"))
async def adm_choose_gift_sub(call: CallbackQuery):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة المستخدمين!", show_alert=True)
        return
    await call.answer()
    uid = int(call.data.replace("adm_giftsub_", ""))

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans ORDER BY id ASC")
        plans = c.fetchall()

    text = f"🎁 <b>اختر باقة لمنحها وتفعيلها للمستخدم <code>{uid}</code> مجاناً:</b>"
    kb_list = []
    for p in plans:
        kb_list.append([InlineKeyboardButton(text=f"منح: {p['name']} ({p['duration_days']}d)", callback_data=f"adm_execgift_{p['id']}_{uid}")])
    kb_list.append([InlineKeyboardButton(text="🔙 تراجع", callback_data=f"adm_usubs_{uid}")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("adm_execgift_"))
async def adm_execute_gift_sub(call: CallbackQuery):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة المستخدمين!", show_alert=True)
        return
    parts = call.data.split("_")
    plan_id, uid = int(parts[2]), int(parts[3])

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        p = c.fetchone()

        now = int(time.time())
        dur_seconds = p["duration_days"] * 86400
        c.execute("""
            INSERT INTO user_subscriptions (user_id, plan_id, plan_name, cost, daily_profit, start_time, end_time, last_claim, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (uid, plan_id, p["name"], p["cost"], p["daily_profit"], now, now + dur_seconds, now))
        conn.commit()

    try:
        await bot.send_message(
            uid,
            f"🎉 <b>مكافأة خاصة من الإدارة!</b>\n"
            f"تم منحك وتفعيل <b>{p['name']}</b> في حسابك مجاناً!\n"
            f"• الربح اليومي: <b>+${p['daily_profit']:.2f}</b>\n"
            f"• المدة: <b>{p['duration_days']} يوم</b>"
        )
    except Exception:
        pass

    await call.answer(f"✅ تم تفعيل {p['name']} للمستخدم بنجاح!", show_alert=True)
    call.data = f"adm_usubs_{uid}"
    await adm_view_user_subscriptions(call)

@dp.callback_query(F.data.startswith("adm_backuser_"))
async def adm_back_to_user_profile(call: CallbackQuery, state: FSMContext):
    await call.answer()
    uid = int(call.data.replace("adm_backuser_", ""))
    await show_user_profile_card(call.message, uid, state)

async def show_user_profile_card(message: Message, uid: int, state: FSMContext):
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        u = c.fetchone()
        now = int(time.time())
        c.execute("SELECT COUNT(*) FROM user_subscriptions WHERE user_id = ? AND status = 'active' AND end_time > ?", (uid, now))
        active_subs_count = c.fetchone()[0]

    if not u:
        await message.answer("❌ المستخدم غير مسجل.")
        return

    b_st = "🔴 محظور" if u["is_banned"] == 1 else "🟢 نشط"
    adm_st = "👑 المالك الأساسي" if uid == ADMIN_ID else ("👮‍♂️ مشرف (أدمن)" if is_admin(uid) else "عضو عادي")

    text = (
        f"👤 <b>سجل المستخدم:</b>\n\n"
        f"• المعرف: <code>{u['user_id']}</code>\n"
        f"• الرتبة: <b>{adm_st}</b>\n"
        f"• الرصيد: <b>${u['balance']:.2f}</b>\n"
        f"• إجمالي الاستثمار: <b>${u['total_invested']:.2f}</b>\n"
        f"• الباقات النشطة حالياً: <b>{active_subs_count} باقة</b>\n"
        f"• المحفظة المحفوظة: <code>{u['saved_wallet'] or 'لا توجد'}</code>\n"
        f"• الحالة: <b>{b_st}</b>"
    )
    ban_txt = "🟢 فك الحظر" if u["is_banned"] == 1 else "🚫 حظر الحساب"
    ban_cb = f"usr_unban_{uid}" if u["is_banned"] == 1 else f"usr_ban_{uid}"

    kb_list = [
        [InlineKeyboardButton(text=f"📦 إدارة باقات المشترك ({active_subs_count})", callback_data=f"adm_usubs_{uid}")],
        [InlineKeyboardButton(text="➕ شحن رصيد", callback_data=f"usr_add_{uid}"),
         InlineKeyboardButton(text="➖ خصم رصيد", callback_data=f"usr_sub_{uid}")]
    ]

    if uid != ADMIN_ID and message.chat.id == ADMIN_ID:
        if is_admin(uid):
            kb_list.append([
                InlineKeyboardButton(text="⚙️ تخصيص الصلاحيات", callback_data=f"adm_editperms_{uid}"),
                InlineKeyboardButton(text="🔻 تنزيل من الإشراف", callback_data=f"usr_demote_{uid}")
            ])
        else:
            kb_list.append([InlineKeyboardButton(text="⭐ رفع أدمن", callback_data=f"usr_promote_{uid}")])

    kb_list.append([InlineKeyboardButton(text=ban_txt, callback_data=ban_cb)])
    kb_list.append([InlineKeyboardButton(text="🔙 رجوع للوحة الإدارة", callback_data="admin_hub")])

    await state.clear()
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
    except Exception:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

# ════════════════════ تحكم المالك الحصري بالأدمنية ════════════════════
@dp.callback_query(F.data == "adm_manage_admins")
async def manage_admins_hub(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ هذا القسم خاص بالمالك الأساسي فقط!", show_alert=True)
        return
    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM bot_admins ORDER BY added_at DESC")
        admin_rows = c.fetchall()

    text = (
        "👮‍♂️ <b>غرفة تحكم المالك بطاقم الإشراف (الأدمنية):</b>\n"
        "──────────────────────────\n"
        f"👑 <b>المالك الأساسي:</b> <code>{ADMIN_ID}</code> (صلاحيات غير قابلة للإزالة)\n\n"
        "اضغط على أي أدمن لتخصيص الأزرار والأقسام المسموح أو الممنوع له التحكم بها:"
    )

    kb_list = []
    if not admin_rows:
        text += "\n\n<i>لا يوجد مشرفين مرفوعين حالياً.</i>"
    else:
        for idx, adm in enumerate(admin_rows, 1):
            a_id = adm["user_id"]
            d_str = time.strftime('%Y-%m-%d', time.localtime(adm["added_at"]))
            kb_list.append([InlineKeyboardButton(text=f"⚙️ المشرف #{idx}: {a_id} ({d_str})", callback_data=f"adm_editperms_{a_id}")])

    kb_list.append([InlineKeyboardButton(text="➕ رفع أدمن جديد بالآيدي", callback_data="adm_add_admin_start")])
    kb_list.append([InlineKeyboardButton(text="🔙 رجوع للوحة الإدارة", callback_data="admin_hub")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("adm_editperms_"))
async def edit_admin_permissions_view(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ خاص بالمالك فقط!", show_alert=True)
        return
    await call.answer()
    target_id = int(call.data.replace("adm_editperms_", ""))

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM bot_admins WHERE user_id = ?", (target_id,))
        admin_row = c.fetchone()

    if not admin_row:
        await call.answer("المشرف غير موجود!", show_alert=True)
        await manage_admins_hub(call)
        return

    current_perms = set(admin_row["permissions"].split(",") if admin_row["permissions"] else [])

    text = (
        f"👮‍♂️ <b>لوحة تحكم المالك بخصائص الأدمن: <code>{target_id}</code></b>\n"
        "──────────────────────────\n"
        "اضغط على أي زر لتشغيله أو منعه من التحكم به فوراً:\n"
        "🟢 = مسموح للأدمن التحكم به | 🔴 = ممنوع ومخفي عنه"
    )

    kb_list = []
    for perm_key, perm_title in PERMISSIONS_MAP.items():
        is_enabled = perm_key in current_perms
        status_icon = "🟢 مسموح" if is_enabled else "🔴 ممنوع"
        kb_list.append([
            InlineKeyboardButton(
                text=f"{status_icon} | {perm_title}",
                callback_data=f"adm_toggleperm_{target_id}_{perm_key}"
            )
        ])

    kb_list.append([
        InlineKeyboardButton(text="🟢 السماح بالكل", callback_data=f"adm_allperms_{target_id}_enable"),
        InlineKeyboardButton(text="🔴 منع الكل", callback_data=f"adm_allperms_{target_id}_disable")
    ])
    kb_list.append([InlineKeyboardButton(text="❌ تنزيل من الإشراف نهائياً", callback_data=f"adm_demote_{target_id}")])
    kb_list.append([InlineKeyboardButton(text="🔙 رجوع لقائمة الأدمنية", callback_data="adm_manage_admins")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("adm_toggleperm_"))
async def toggle_specific_permission(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    target_id = int(parts[2])
    perm_key = parts[3]

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT permissions FROM bot_admins WHERE user_id = ?", (target_id,))
        row = c.fetchone()
        if not row:
            await call.answer("المشرف غير موجود.")
            return
        perms = set(row["permissions"].split(",") if row["permissions"] else [])
        if perm_key in perms:
            perms.remove(perm_key)
            action_txt = "تم حظر الصلاحية"
        else:
            perms.add(perm_key)
            action_txt = "تم منح الصلاحية"

        new_perms_str = ",".join(perms)
        c.execute("UPDATE bot_admins SET permissions = ? WHERE user_id = ?", (new_perms_str, target_id))
        conn.commit()

        ADMINS_CACHE[target_id] = perms

    await call.answer(action_txt)
    call.data = f"adm_editperms_{target_id}"
    await edit_admin_permissions_view(call)

@dp.callback_query(F.data.startswith("adm_allperms_"))
async def set_all_permissions(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    target_id = int(parts[2])
    mode = parts[3]

    new_perms_str = DEFAULT_ADMIN_PERMISSIONS if mode == "enable" else ""
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE bot_admins SET permissions = ? WHERE user_id = ?", (new_perms_str, target_id))
        conn.commit()

    ADMINS_CACHE[target_id] = set(new_perms_str.split(",") if new_perms_str else [])

    await call.answer("تم تحديث كافة الصلاحيات بنجاح.")
    call.data = f"adm_editperms_{target_id}"
    await edit_admin_permissions_view(call)

@dp.callback_query(F.data == "adm_add_admin_start")
async def start_add_admin_process(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ خاص بالمالك فقط!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_add_admin_id)
    text = (
        "👮‍♂️ <b>رفع مشرف (أدمن) جديد:</b>\n"
        "──────────────────────────\n"
        "أرسل الآن الآيدي (ID) الرقمي للشخص المراد ترقيته:"
    )
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_admin_id)
async def process_add_admin_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_adm_id = int(message.text.strip())
        if new_adm_id == ADMIN_ID or is_admin(new_adm_id):
            await message.answer("⚠️ هذا الحساب أدمن بالفعل في البوت!", reply_markup=cancel_keyboard())
            return

        now = int(time.time())
        with db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO bot_admins (user_id, added_at, permissions) VALUES (?, ?, ?)",
                (new_adm_id, now, DEFAULT_ADMIN_PERMISSIONS)
            )
            conn.commit()

        ADMINS_CACHE[new_adm_id] = set(DEFAULT_ADMIN_PERMISSIONS.split(","))

        try:
            await bot.send_message(
                new_adm_id,
                "🎉 <b>تهانينا!</b>\n"
                "تمت ترقيتك إلى <b>مشرف (أدمن)</b> في المنظومة من قبل المالك الأساسي."
            )
        except Exception:
            pass

        await state.clear()
        await message.answer(f"✅ <b>تم رفع المشرف <code>{new_adm_id}</code> بنجاح!</b>\nيمكنك الآن التحكم بصلاحياته من القائمة.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ تخصيص صلاحيات هذا الأدمن الآن", callback_data=f"adm_editperms_{new_adm_id}")]])
        await message.answer("اضغط للمتابعة:", reply_markup=kb)
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة فقط (User ID).", reply_markup=cancel_keyboard())

@dp.callback_query(F.data.startswith("adm_demote_"))
async def demote_admin_callback(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ تنزيل الأدمن محصور بالمالك فقط!", show_alert=True)
        return
    target_id = int(call.data.replace("adm_demote_", ""))
    if target_id == ADMIN_ID:
        await call.answer("❌ لا يمكن تنزيل المالك الأساسي!", show_alert=True)
        return

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bot_admins WHERE user_id = ?", (target_id,))
        conn.commit()

    if target_id in ADMINS_CACHE:
        del ADMINS_CACHE[target_id]

    try:
        await bot.send_message(target_id, "⚠️ <b>إشعار إداري:</b> تم تنزيلك من رتبة مشرف (أدمن).")
    except Exception:
        pass

    await call.answer(f"✅ تم تنزيل الأدمن {target_id} بنجاح.", show_alert=True)
    await manage_admins_hub(call)

@dp.callback_query(F.data.startswith("usr_promote_"))
async def usr_promote_shortcut(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ رفع الأدمن خاص بالمالك فقط!", show_alert=True)
        return
    target_id = int(call.data.replace("usr_promote_", ""))
    now = int(time.time())
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO bot_admins (user_id, added_at, permissions) VALUES (?, ?, ?)", (target_id, now, DEFAULT_ADMIN_PERMISSIONS))
        conn.commit()

    ADMINS_CACHE[target_id] = set(DEFAULT_ADMIN_PERMISSIONS.split(","))

    try:
        await bot.send_message(
            target_id,
            "🎉 <b>تهانينا!</b>\nتمت ترقيتك إلى <b>مشرف (أدمن)</b> في المنظومة."
        )
    except Exception:
        pass

    await call.answer("✅ تم رفع المستخدم كأدمن بنجاح!", show_alert=True)
    await show_user_profile_card(call.message, target_id, state)

@dp.callback_query(F.data.startswith("usr_demote_"))
async def usr_demote_shortcut(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ خاص بالمالك فقط!", show_alert=True)
        return
    target_id = int(call.data.replace("usr_demote_", ""))
    if target_id == ADMIN_ID:
        await call.answer("❌ لا يمكن تنزيل المالك الأساسي!", show_alert=True)
        return

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bot_admins WHERE user_id = ?", (target_id,))
        conn.commit()

    if target_id in ADMINS_CACHE:
        del ADMINS_CACHE[target_id]

    try:
        await bot.send_message(target_id, "⚠️ <b>إشعار إداري:</b> تم تنزيلك من رتبة مشرف.")
    except Exception:
        pass

    await call.answer("✅ تم تنزيل المستخدم من الإشراف بنجاح!", show_alert=True)
    await show_user_profile_card(call.message, target_id, state)

# ════════════════════ إدارة وسائل الدفع ════════════════════
@dp.callback_query(F.data == "adm_pay_methods_hub")
async def pay_methods_hub(call: CallbackQuery):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    await call.answer()
    text = (
        "⚙️ <b>غرفة التحكم بوسائل الشحن والسحب:</b>\n"
        "──────────────────────────\n"
        "يمكنك تعديل أي وسيلة، إيقافها، حذفها، أو إضافة وسيلة جديدة:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 إدارة وسائل الإيداع (شحن)", callback_data="adm_view_methods_deposit")],
        [InlineKeyboardButton(text="📤 إدارة وسائل السحب (كاش)", callback_data="adm_view_methods_withdraw")],
        [InlineKeyboardButton(text="➕ إضافة وسيلة جديدة", callback_data="adm_add_method_start")],
        [InlineKeyboardButton(text="🔙 رجوع للوحة الإدارة", callback_data="admin_hub")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("adm_view_methods_"))
async def view_methods_by_category(call: CallbackQuery):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    await call.answer()
    cat = call.data.replace("adm_view_methods_", "")
    cat_title = "الإيداع" if cat == "deposit" else "السحب"

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE category = ? ORDER BY id ASC", (cat,))
        methods = c.fetchall()

    text = f"⚙️ <b>وسائل {cat_title}:</b>\nاضغط على أي وسيلة للتحكم بها:\n"
    kb_list = []
    for m in methods:
        st = "🟢" if m["is_active"] == 1 else "🔴"
        kb_list.append([InlineKeyboardButton(text=f"{st} {m['name']}", callback_data=f"adm_meth_opt_{m['id']}")])

    kb_list.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="adm_pay_methods_hub")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("adm_meth_opt_"))
async def method_options(call: CallbackQuery):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    await call.answer()
    m_id = int(call.data.replace("adm_meth_opt_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM payment_methods WHERE id = ?", (m_id,))
        m = c.fetchone()

    st_text = "🟢 مفعلة وتظهر للجميع" if m["is_active"] == 1 else "🔴 معطلة ومخفية"
    btn_toggle = "🔴 إيقاف مؤقت" if m["is_active"] == 1 else "🟢 إعادة التفعيل"

    text = (
        f"⚙️ <b>التحكم بالوسيلة: {m['name']}</b>\n"
        "──────────────────────────\n"
        f"• القسم: <b>{'إيداع' if m['category'] == 'deposit' else 'سحب'}</b>\n"
        f"• الحالة: <b>{st_text}</b>\n"
        f"• العمولة: <b>{m['fee_percent']}%</b>\n"
        f"• محول الدينار: <b>{'نعم 🇮🇶' if m['is_iqd'] == 1 else 'لا'}</b>\n"
        f"• التعليمات:\n{m['details']}\n"
        "──────────────────────────"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_toggle, callback_data=f"adm_meth_toggle_{m['id']}")],
        [InlineKeyboardButton(text="✏️ تعديل النص والبيانات", callback_data=f"adm_meth_editdetails_{m['id']}")],
        [InlineKeyboardButton(text="🗑 حذف الوسيلة نهائياً", callback_data=f"adm_meth_delete_{m['id']}")],
        [InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data=f"adm_view_methods_{m['category']}")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("adm_meth_toggle_"))
async def toggle_method_status(call: CallbackQuery):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    m_id = int(call.data.replace("adm_meth_toggle_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT is_active FROM payment_methods WHERE id = ?", (m_id,))
        cur = c.fetchone()["is_active"]
        new_val = 0 if cur == 1 else 1
        c.execute("UPDATE payment_methods SET is_active = ? WHERE id = ?", (new_val, m_id))
        conn.commit()

    await call.answer("تم تغيير حالة الوسيلة.")
    await method_options(call)

@dp.callback_query(F.data.startswith("adm_meth_delete_"))
async def delete_method_permanently(call: CallbackQuery):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    m_id = int(call.data.replace("adm_meth_delete_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT category FROM payment_methods WHERE id = ?", (m_id,))
        cat = c.fetchone()["category"]
        c.execute("DELETE FROM payment_methods WHERE id = ?", (m_id,))
        conn.commit()

    await call.answer("تم حذف الوسيلة نهائياً.", show_alert=True)
    call.data = f"adm_view_methods_{cat}"
    await view_methods_by_category(call)

@dp.callback_query(F.data.startswith("adm_meth_editdetails_"))
async def prompt_edit_method_details(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    await call.answer()
    m_id = int(call.data.replace("adm_meth_editdetails_", ""))
    await state.update_data(target_method_id=m_id)
    await state.set_state(Form.admin_edit_method_details)
    await call.message.answer("✏️ أرسل البيانات والتعليمات الجديدة للوسيلة:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_edit_method_details)
async def save_edited_method_details(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "pay_methods"):
        return
    data = await state.get_data()
    m_id = data["target_method_id"]
    new_text = message.text.strip()

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE payment_methods SET details = ? WHERE id = ?", (new_text, m_id))
        conn.commit()

    await state.clear()
    await message.answer("✅ تم تحديث بيانات الوسيلة بنجاح!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة لقسم الطرق", callback_data="adm_pay_methods_hub")]])
    await message.answer("اضغط للمتابعة:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_method_start")
async def start_add_method(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "pay_methods"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة وسائل الدفع!", show_alert=True)
        return
    await call.answer()
    text = "اختر تصنيف الوسيلة الجديدة:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 إضافة وسيلة شحن (إيداع)", callback_data="addmethcat_deposit")],
        [InlineKeyboardButton(text="📤 إضافة وسيلة سحب (كاش)", callback_data="addmethcat_withdraw")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("addmethcat_"))
async def get_add_method_cat(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "pay_methods"):
        return
    await call.answer()
    cat = call.data.replace("addmethcat_", "")
    await state.update_data(new_m_cat=cat)
    await state.set_state(Form.admin_add_method_name)
    await call.message.answer("✏️ أرسل اسم الوسيلة (مثال: <code>🪙 TON Wallet</code>):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_method_name)
async def get_add_method_name(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "pay_methods"):
        return
    await state.update_data(new_m_name=message.text.strip())
    await state.set_state(Form.admin_add_method_fee)
    await message.answer("🏷 أرسل نسبة العمولة % (مثال: <code>0</code> أو <code>1.5</code>):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_method_fee)
async def get_add_method_fee(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "pay_methods"):
        return
    try:
        fee = float(message.text)
        await state.update_data(new_m_fee=fee)
        await state.set_state(Form.admin_add_method_iqd)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇮🇶 نعم، تحويل دينار عراقي", callback_data="muniqd_1")],
            [InlineKeyboardButton(text="🌐 لا، بالدولار فقط", callback_data="muniqd_0")]
        ])
        await message.answer("هل هذه الوسيلة تعتمد الدينار العراقي لعرض الصرف التلقائي؟", reply_markup=kb)
    except ValueError:
        await message.answer("❌ يرجى كتابة أرقام فقط.")

@dp.callback_query(F.data.startswith("muniqd_"))
async def get_add_method_iqd(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "pay_methods"):
        return
    await call.answer()
    iqd_flag = int(call.data.replace("muniqd_", ""))
    await state.update_data(new_m_iqd=iqd_flag)
    await state.set_state(Form.admin_add_method_addr)
    await call.message.answer("📍 أرسل العنوان أو الرقم الخام (للباركود) أو أرسل 0 للتخطي:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_method_addr)
async def get_add_method_addr(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "pay_methods"):
        return
    raw_addr = "" if message.text.strip() == "0" else message.text.strip()
    await state.update_data(new_m_addr=raw_addr)
    await state.set_state(Form.admin_add_method_details)
    await message.answer("📝 أرسل التعليمات المطبوعة للمستخدم عند اختيار هذه الوسيلة:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_method_details)
async def finalize_add_method(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "pay_methods"):
        return
    data = await state.get_data()
    cat = data["new_m_cat"]
    name = data["new_m_name"]
    fee = data["new_m_fee"]
    is_iqd = data["new_m_iqd"]
    raw_addr = data["new_m_addr"]
    details = message.text.strip()

    with db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO payment_methods (category, name, details, raw_address, fee_percent, is_iqd, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (cat, name, details, raw_addr, fee, is_iqd)
        )
        conn.commit()

    await state.clear()
    await message.answer(f"✅ <b>تمت إضافة وسيلة {('الإيداع' if cat == 'deposit' else 'السحب')} بنجاح!</b>\nالاسم: <b>{name}</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة لغرفة التحكم", callback_data="adm_pay_methods_hub")]])
    await message.answer("اضغط للرجوع:", reply_markup=kb)

# ════════════════════ الخدمات الأخرى ════════════════════
@dp.callback_query(F.data == "claim_daily_gift")
async def daily_gift_handler(call: CallbackQuery):
    bonus_val = float(get_setting("daily_bonus", "0.10"))
    user = get_user(call.from_user.id)
    now = int(time.time())
    cooldown = 86400

    if now - user["last_bonus"] < cooldown:
        rem = cooldown - (now - user["last_bonus"])
        h, m = rem // 3600, (rem % 3600) // 60
        await call.answer(f"⏳ حصلت على هديتك مسبقاً!\nعد بعد: {h} ساعة و {m} دقيقة.", show_alert=True)
        return

    new_balance = user["balance"] + bonus_val
    update_user(call.from_user.id, balance=round(new_balance, 2), last_bonus=now)
    await call.answer(f"🎁 استلمت هديتك اليومية: +${bonus_val:.2f}", show_alert=True)
    text, kb = render_dashboard(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "open_calc")
async def calculator_home(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY id ASC")
        plans = c.fetchall()

    text = "🧮 <b>حاسبة الأرباح الذكية:</b>\nاختر باقة استثمارية لعرض مضاعفاتها أو احسب بمبلغ مخصص:"
    buttons = []
    for p in plans:
        buttons.append([InlineKeyboardButton(text=f"📊 حساب: {p['name']} (${p['cost']:.0f})", callback_data=f"calc_plan_{p['id']}_1")])
    buttons.append([InlineKeyboardButton(text="✍️ حساب بمبلغ مخصص (مقارنة شاملة)", callback_data="calc_custom_btn")])
    buttons.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("calc_plan_"))
async def calculate_plan_details(call: CallbackQuery):
    await call.answer()
    parts = call.data.split("_")
    plan_id, multiplier = int(parts[2]), int(parts[3])

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        p = c.fetchone()

    cost = p["cost"] * multiplier
    daily = p["daily_profit"] * multiplier
    duration = p["duration_days"]
    total_rev = round(daily * duration, 2)
    net_profit = round(total_rev - cost, 2)
    roi = round((net_profit / cost) * 100, 1)

    text = (
        f"🧮 <b>تحليل العوائد الاستثمارية ({p['name']}):</b>\n"
        f"🔢 المضاعف: <code>{multiplier}x</code> | رأس المال: <code>${cost:.2f}</code>\n"
        f"📈 العائد اليومي: <code>+${daily:.2f}</code>\n"
        f"💰 الإجمالي النهائي: <code>${total_rev:.2f}</code>\n"
        f"🎯 صافي الأرباح: <b>+${net_profit:.2f}</b> (ROI: <b>+{roi}%</b>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1x" + (" ✅" if multiplier == 1 else ""), callback_data=f"calc_plan_{plan_id}_1"),
            InlineKeyboardButton(text="2x" + (" ✅" if multiplier == 2 else ""), callback_data=f"calc_plan_{plan_id}_2"),
            InlineKeyboardButton(text="5x" + (" ✅" if multiplier == 5 else ""), callback_data=f"calc_plan_{plan_id}_5"),
            InlineKeyboardButton(text="10x" + (" ✅" if multiplier == 10 else ""), callback_data=f"calc_plan_{plan_id}_10")
        ],
        [InlineKeyboardButton(text=f"🚀 تفعيل {p['name']} الآن", callback_data=f"buyplan_{plan_id}")],
        [InlineKeyboardButton(text="🔙 رجوع للحاسبة", callback_data="open_calc")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "calc_custom_btn")
async def ask_custom_calc_amount(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.calc_custom_input)
    text = "✍️ أرسل المبلغ بالدولار لحساب عوائده في كل الخطط:"
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.calc_custom_input)
async def process_custom_calc_amount(message: Message, state: FSMContext):
    try:
        amount = round(float(message.text), 2)
        if amount <= 0:
            await message.answer("❌ أدخل رقماً أكبر من 0.", reply_markup=cancel_keyboard())
            return
        with db_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY id ASC")
            plans = c.fetchall()

        text = f"📊 <b>تقرير المقارنة لمبلغ (${amount:.2f}):</b>\n──────────────────────────\n"
        for p in plans:
            daily_ratio = p["daily_profit"] / p["cost"]
            calc_daily = round(amount * daily_ratio, 2)
            calc_total = round(calc_daily * p["duration_days"], 2)
            calc_net = round(calc_total - amount, 2)
            calc_roi = round((calc_net / amount) * 100, 1)
            text += f"🔹 <b>{p['name']} ({p['duration_days']} يوم):</b>\n• يومياً: <code>+${calc_daily:.2f}</code> | الإجمالي: <code>${calc_total:.2f}</code> | الصافي: <b>+${calc_net:.2f}</b> (ROI: <b>+{calc_roi}%</b>)\n\n"

        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]])
        await message.answer(text, reply_markup=kb)
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام فقط.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data == "open_transfer")
async def open_transfer_menu(call: CallbackQuery, state: FSMContext):
    if get_setting("transfer_active", "1") == "0":
        await call.answer("⚠️ خاصية تحويل الرصيد معطلة حالياً.", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.transfer_target)
    fee = get_setting("transfer_fee_percent", "2")
    text = f"🔄 <b>تحويل الرصيد الفوري:</b>\n• عمولة التحويل: <b>{fee}%</b>\nأرسل الآيدي (ID) الرقمي للمستلم:"
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.transfer_target)
async def get_transfer_target(message: Message, state: FSMContext):
    try:
        target_id = int(message.text)
        if target_id == message.from_user.id:
            await message.answer("❌ لا يمكنك التحويل لنفسك!", reply_markup=cancel_keyboard())
            return
        target_user = get_user(target_id)
        if not target_user:
            await message.answer("❌ المستخدم غير موجود بالمنظومة.", reply_markup=cancel_keyboard())
            return
        await state.update_data(transfer_target_id=target_id)
        await state.set_state(Form.transfer_amount)
        await message.answer(f"👤 المستلم: <code>{target_id}</code>\nأرسل المبلغ بالدولار:", reply_markup=cancel_keyboard())
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام فقط.", reply_markup=cancel_keyboard())

@dp.message(Form.transfer_amount)
async def process_transfer_amount(message: Message, state: FSMContext):
    sender = get_user(message.from_user.id)
    try:
        amount = round(float(message.text), 2)
        if amount <= 0 or amount > sender["balance"]:
            await message.answer(f"❌ مبلغ غير صالح! رصيدك (${sender['balance']:.2f}).", reply_markup=cancel_keyboard())
            return

        data = await state.get_data()
        target_id = data["transfer_target_id"]
        fee_percent = float(get_setting("transfer_fee_percent", "2"))
        fee = round(amount * (fee_percent / 100), 2)
        received_amt = round(amount - fee, 2)

        with db_conn() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, message.from_user.id))
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (received_amt, target_id))
            conn.commit()

        await state.clear()
        await message.answer(f"✅ تم التحويل بنجاح! الصافي: ${received_amt:.2f}")
        try:
            await bot.send_message(target_id, f"💳 وصلتك حوالة بقيمة <b>+${received_amt:.2f}</b> من المشترك <code>{message.from_user.id}</code>.")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data == "open_promo")
async def open_promo_input(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.claim_promo)
    text = "🎟 أرسل كود الهدية لإضافة الرصيد لمحفظتك فوراً:"
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.claim_promo)
async def process_promo_claim(message: Message, state: FSMContext):
    code_text = message.text.strip().upper()
    user_id = message.from_user.id
    now = int(time.time())

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM promocodes WHERE code = ?", (code_text,))
        promo = c.fetchone()
        if not promo or promo["used_count"] >= promo["max_uses"]:
            await message.answer("❌ كود غير صالح أو منتهي.", reply_markup=cancel_keyboard())
            return
        c.execute("SELECT * FROM promo_history WHERE code = ? AND user_id = ?", (code_text, user_id))
        if c.fetchone():
            await message.answer("⚠️ لقد استخدمت هذا الكود مسبقاً!", reply_markup=cancel_keyboard())
            return

        reward = promo["reward"]
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
        c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code_text,))
        c.execute("INSERT INTO promo_history VALUES (?, ?, ?)", (code_text, user_id, now))
        conn.commit()

    await state.clear()
    await message.answer(f"🎉 تم شحن محفظتك بمبلغ <b>+${reward:.2f}</b> بنجاح!")

@dp.callback_query(F.data == "open_referral")
async def referral_handler(call: CallbackQuery):
    await call.answer()
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{call.from_user.id}"
    user = get_user(call.from_user.id)
    ref_percent = get_setting("ref_percent", "10")
    text = f"👥 <b>برنامج الشركاء والإحالة:</b>\nاربح <b>{ref_percent}%</b> كاش فوري عن كل شحن لصديقك!\n\n🔗 رابطك المباشر:\n<code>{ref_link}</code>\n\n📊 إجمالي الإحالات: <code>{user['referral_count']} عضو</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "open_history")
async def history_handler(call: CallbackQuery):
    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT invoice_code, type, amount, status FROM operations WHERE user_id = ? ORDER BY id DESC LIMIT 5", (call.from_user.id,))
        rows = c.fetchall()

    history_text = ""
    if not rows:
        history_text = "لا توجد أي معاملات مسجلة حتى الآن."
    else:
        for r in rows:
            op_type = "إيداع 💳" if r["type"] == "deposit" else "سحب 💸"
            st_map = {
                "pending": "⏳ قيد المعالجة",
                "approved": "✅ ناجحة",
                "rejected": "❌ مرفوضة",
                "cancelled_by_user": "↩️ مستردة"
            }
            status = st_map.get(r["status"], r["status"])
            history_text += f"• <b>{op_type}</b> (#{r['invoice_code']}) بمبلغ <b>${r['amount']:.2f}</b> | {status}\n"

    text = f"📜 <b>آخر 5 عمليات في حسابك:</b>\n\n{history_text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "open_stats")
async def open_platform_stats(call: CallbackQuery):
    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        members = c.fetchone()[0]
        c.execute("SELECT SUM(amount) FROM operations WHERE type='deposit' AND status='approved'")
        deposits = c.fetchone()[0] or 0.0
        c.execute("SELECT SUM(amount) FROM operations WHERE type='withdraw' AND status='approved'")
        payouts = c.fetchone()[0] or 0.0

    text = f"📈 <b>إحصائيات المنصة:</b>\n• المشتركين: <b>{members}</b>\n• الإيداعات المعتمدة: <b>${deposits:.2f}</b>\n• السحوبات المكتملة: <b>${payouts:.2f}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "open_support")
async def support_handler(call: CallbackQuery):
    await call.answer()
    sup_user = get_setting("support_user", "@YourSupport")
    proof_ch = get_setting("proof_channel", "")
    kb_list = [[InlineKeyboardButton(text="💬 التحدث مع الدعم الفني", url=f"https://t.me/{sup_user.replace('@', '')}")]]
    if proof_ch:
        kb_list.append([InlineKeyboardButton(text="📢 قناة الإثباتات", url=proof_ch if proof_ch.startswith("http") else f"https://t.me/{proof_ch.replace('@', '')}")])
    kb_list.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])
    await call.message.edit_text("📞 فريق العمل متواجد لخدمتكم.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

# ════════════════════ لوحة تحكم الإدارة ════════════════════
@dp.callback_query(F.data == "admin_hub")
async def admin_hub_handler(call: CallbackQuery):
    u_id = call.from_user.id
    if not is_admin(u_id):
        return

    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(amount) FROM operations WHERE type='deposit' AND status='approved'")
        total_dep = c.fetchone()[0] or 0.0
        c.execute("SELECT SUM(amount) FROM operations WHERE type='withdraw' AND status='approved'")
        total_wth = c.fetchone()[0] or 0.0

    text = f"👑 <b>لوحة تحكم الإدارة:</b>\n👥 الأعضاء: <b>{total_users}</b> | 💰 الإيداعات: <b>${total_dep:.2f}</b> | 💸 السحوبات: <b>${total_wth:.2f}</b>"

    kb_list = []
    if u_id == ADMIN_ID:
        kb_list.append([InlineKeyboardButton(text="👮‍♂️ إدارة ورفع الأدمنية وتخصيص صلاحياتهم", callback_data="adm_manage_admins")])

    row = []
    if has_permission(u_id, "plans"):
        row.append(InlineKeyboardButton(text="📊 باقات الاستثمار", callback_data="adm_manage_plans"))
    if has_permission(u_id, "pay_methods"):
        row.append(InlineKeyboardButton(text="💳 وسائل الشحن والسحب", callback_data="adm_pay_methods_hub"))
    if row:
        kb_list.append(row)

    row = []
    if has_permission(u_id, "buttons"):
        row.append(InlineKeyboardButton(text="🎛 أزرار الداشبورد", callback_data="adm_custom_buttons_hub"))
    if has_permission(u_id, "limits"):
        row.append(InlineKeyboardButton(text="⚙️ الحدود وأسعار الصرف", callback_data="adm_edit_limits"))
    if row:
        kb_list.append(row)

    row = []
    if has_permission(u_id, "limits"):
        row.append(InlineKeyboardButton(text="📢 الاشتراك الإجباري", callback_data="adm_forcesub_menu"))
    if has_permission(u_id, "promo"):
        row.append(InlineKeyboardButton(text="🎟 إنشاء كود هدية", callback_data="adm_create_promo"))
    if row:
        kb_list.append(row)

    row = []
    if has_permission(u_id, "backup"):
        row.append(InlineKeyboardButton(text="📊 تصدير البيانات (CSV)", callback_data="adm_export_csv"))
    if has_permission(u_id, "toggles"):
        row.append(InlineKeyboardButton(text="🚦 مفاتيح التشغيل", callback_data="adm_toggles"))
    if row:
        kb_list.append(row)

    row = []
    if has_permission(u_id, "users"):
        row.append(InlineKeyboardButton(text="🔍 فحص وإدارة مستخدم", callback_data="adm_user_inspect"))
    if has_permission(u_id, "backup"):
        row.append(InlineKeyboardButton(text="📥 نسخة احتياطية (DB)", callback_data="adm_backup_db"))
    if row:
        kb_list.append(row)

    row = []
    if has_permission(u_id, "limits"):
        row.append(InlineKeyboardButton(text="✍️ كليشة الترحيب", callback_data="chset_welcome_text"))
    if has_permission(u_id, "broadcast"):
        row.append(InlineKeyboardButton(text="📢 إذاعة عامة", callback_data="admin_broadcast"))
    if row:
        kb_list.append(row)

    kb_list.append([InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data == "adm_custom_buttons_hub")
async def custom_buttons_hub(call: CallbackQuery):
    if not has_permission(call.from_user.id, "buttons"):
        await call.answer("⛔️ ليس لديك صلاحية لتعديل الأزرار!", show_alert=True)
        return
    await call.answer()
    text = "🎛 <b>إدارة وتخصيص أزرار الداشبورد:</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة زر جديد", callback_data="adm_add_button_start")],
        [InlineKeyboardButton(text="🗑 حذف زر من الواجهة", callback_data="adm_delete_button_menu")],
        [InlineKeyboardButton(text="🔄 استعادة الأزرار الافتراضية", callback_data="adm_reset_default_buttons")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_hub")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "adm_add_button_start")
async def start_add_button(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "buttons"):
        await call.answer("⛔️ ليس لديك صلاحية لتعديل الأزرار!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_btn_title)
    await call.message.answer("✏️ أرسل اسم الزر:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_btn_title)
async def get_btn_title(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "buttons"):
        return
    await state.update_data(b_title=message.text.strip())
    await state.set_state(Form.admin_btn_type)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 رابط خارجي (URL)", callback_data="btype_url")],
        [InlineKeyboardButton(text="📝 صفحة نصية", callback_data="btype_custom_text")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action")]
    ])
    await message.answer("اختر نوع الزر:", reply_markup=kb)

@dp.callback_query(F.data.startswith("btype_"))
async def get_btn_type(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "buttons"):
        return
    await call.answer()
    b_type = call.data.replace("btype_", "")
    await state.update_data(b_type=b_type)
    await state.set_state(Form.admin_btn_val)
    prompt = "🔗 أرسل الرابط الكامل:" if b_type == "url" else "📝 أرسل النص المعروض:"
    await call.message.answer(prompt, reply_markup=cancel_keyboard())

@dp.message(Form.admin_btn_val)
async def save_new_button(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "buttons"):
        return
    data = await state.get_data()
    title, b_type, val = data["b_title"], data["b_type"], message.text.strip()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(row_order) FROM dashboard_buttons")
        new_row = (c.fetchone()[0] or 1) + 1
        c.execute("INSERT INTO dashboard_buttons (title, target_type, target_val, row_order) VALUES (?, ?, ?, ?)", (title, b_type, val, new_row))
        conn.commit()
    await state.clear()
    await message.answer("✅ تمت إضافة الزر بنجاح للواجهة!")

@dp.callback_query(F.data == "adm_delete_button_menu")
async def delete_button_menu(call: CallbackQuery):
    if not has_permission(call.from_user.id, "buttons"):
        return
    await call.answer()
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM dashboard_buttons ORDER BY id ASC")
        buttons = c.fetchall()
    kb_list = [[InlineKeyboardButton(text=f"❌ حذف: {b['title']}", callback_data=f"delbtn_{b['id']}")] for b in buttons]
    kb_list.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="adm_custom_buttons_hub")])
    await call.message.edit_text("🗑 اضغط على أي زر لحذفه فوراً:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("delbtn_"))
async def execute_delete_button(call: CallbackQuery):
    if not has_permission(call.from_user.id, "buttons"):
        return
    btn_id = int(call.data.replace("delbtn_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM dashboard_buttons WHERE id = ?", (btn_id,))
        conn.commit()
    await call.answer("✅ تم حذف الزر.")
    await delete_button_menu(call)

@dp.callback_query(F.data == "adm_reset_default_buttons")
async def reset_default_buttons_exec(call: CallbackQuery):
    if not has_permission(call.from_user.id, "buttons"):
        return
    default_btns = [
        ("⚡️ تجميع الأرباح يدوياً", "callback", "claim_profit", 1),
        ("💳 شحن الرصيد (إيداع)", "callback", "open_deposit", 2),
        ("💸 طلب سحب نقدي", "callback", "open_withdraw", 2),
        ("📊 باقات الاستثمار", "callback", "open_plans", 3),
        ("🧮 حاسبة الأرباح الذكية", "callback", "open_calc", 3),
        ("🔍 تتبع وإدارة المعاملات", "callback", "open_track_op", 4),
        ("🔄 تحويل رصيد داخلي", "callback", "open_transfer", 4),
        ("🎟 استخدام كود هدية", "callback", "open_promo", 5),
        ("🎁 الهدية اليومية", "callback", "claim_daily_gift", 5),
        ("👥 رابط الإحالة", "callback", "open_referral", 6),
        ("📜 سجل العمليات", "callback", "open_history", 6),
        ("📈 إحصائيات المنصة", "callback", "open_stats", 7),
        ("📞 الدعم والإثباتات", "callback", "open_support", 7),
        ("🔄 تحديث الشاشة", "callback", "refresh_dash", 8)
    ]
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM dashboard_buttons")
        for title, b_type, b_val, r_order in default_btns:
            c.execute("INSERT INTO dashboard_buttons (title, target_type, target_val, row_order) VALUES (?, ?, ?, ?)", (title, b_type, b_val, r_order))
        conn.commit()
    await call.answer("تمت استعادة الأزرار الافتراضية بنجاح!", show_alert=True)
    await custom_buttons_hub(call)

@dp.callback_query(F.data.startswith("cstbtn_"))
async def custom_button_click(call: CallbackQuery):
    await call.answer()
    btn_id = int(call.data.replace("cstbtn_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT title, target_val FROM dashboard_buttons WHERE id = ?", (btn_id,))
        b = c.fetchone()
    if b:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة للرئيسية", callback_data="refresh_dash")]])
        await call.message.edit_text(f"📌 <b>{b['title']}</b>\n──────────────────────────\n\n{b['target_val']}", reply_markup=kb)
    else:
        await call.answer("الزر غير متوفر.", show_alert=True)

@dp.callback_query(F.data == "adm_export_csv")
async def export_transactions_csv(call: CallbackQuery):
    if not has_permission(call.from_user.id, "backup"):
        await call.answer("⛔️ ليس لديك صلاحية لتصدير البيانات!", show_alert=True)
        return
    await call.answer("جاري تصدير التقرير...")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Invoice", "User ID", "Type", "Method", "Amount", "Fee", "Net", "Status", "Date"])
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, invoice_code, user_id, type, method, amount, fee, net_amount, status, created_at FROM operations ORDER BY id DESC")
        for row in c.fetchall():
            d_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row["created_at"]))
            writer.writerow([row["id"], row["invoice_code"], row["user_id"], row["type"], row["method"], row["amount"], row["fee"], row["net_amount"], row["status"], d_str])
    doc = BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename=f"report_{int(time.time())}.csv")
    await bot.send_document(call.from_user.id, doc, caption="📊 تقرير المعاملات بصيغة CSV.")

@dp.callback_query(F.data == "adm_create_promo")
async def start_create_promo(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "promo"):
        await call.answer("⛔️ ليس لديك صلاحية لإنشاء أكواد الهدايا!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_add_promo_code)
    await call.message.answer("✏️ أرسل كود الهدية (مثال: <code>CASH50</code>):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_promo_code)
async def get_promo_code(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "promo"):
        return
    await state.update_data(p_code=message.text.strip().upper())
    await state.set_state(Form.admin_add_promo_reward)
    await message.answer("💰 أرسل قيمة المكافأة بالدولار:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_promo_reward)
async def get_promo_reward(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "promo"):
        return
    try:
        r = float(message.text)
        await state.update_data(p_reward=r)
        await state.set_state(Form.admin_add_promo_uses)
        await message.answer("🔢 أرسل أقصى عدد مرات للاستخدام:", reply_markup=cancel_keyboard())
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة.")

@dp.message(Form.admin_add_promo_uses)
async def get_promo_uses(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "promo"):
        return
    try:
        uses = int(message.text)
        data = await state.get_data()
        with db_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO promocodes VALUES (?, ?, ?, 0)", (data["p_code"], data["p_reward"], uses))
            conn.commit()
        await state.clear()
        await message.answer(f"✅ تم إنشاء كود الهدية <code>{data['p_code']}</code> بنجاح!")
    except ValueError:
        await message.answer("❌ أدخل رقماً صحيحاً.")

# ════════════════════ نظام الاشتراك الإجباري المتعدد المطور ════════════════════
@dp.callback_query(F.data == "adm_forcesub_menu")
async def force_sub_settings(call: CallbackQuery):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية لتعديل الاشتراك الإجباري!", show_alert=True)
        return
    await call.answer()
    st = "🟢 مفعل" if get_setting("force_sub_active", "0") == "1" else "🔴 معطل"

    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM force_sub_channels ORDER BY id ASC")
        channels = c.fetchall()

    text = (
        "📢 <b>غرفة إدارة قنوات ومجموعات الاشتراك الإجباري:</b>\n"
        "──────────────────────────\n"
        f"• الحالة العامة: <b>{st}</b>\n"
        f"• عدد القنوات/المجموعات المضافة: <b>{len(channels)}</b>\n\n"
    )

    kb_list = [
        [InlineKeyboardButton(text=f"تبديل الحالة العامة ({st})", callback_data="toggle_force_sub_active")],
        [InlineKeyboardButton(text="➕ إضافة قناة أو مجموعة جديدة", callback_data="adm_add_fsub_channel")]
    ]

    if channels:
        text += "📋 <b>القنوات والمجموعات المفروضة حالياً:</b>\n"
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. <b>{ch['title']}</b> (<code>{ch['chat_id']}</code>)\n"
            kb_list.append([InlineKeyboardButton(text=f"🗑 حذف: {ch['title']}", callback_data=f"adm_del_fsub_{ch['id']}")])
        text += "\n"
    else:
        text += "<i>لا توجد أي قنوات مضافة حالياً.</i>\n\n"

    kb_list.append([InlineKeyboardButton(text="🔙 رجوع للوحة الإدارة", callback_data="admin_hub")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data == "toggle_force_sub_active")
async def toggle_force_sub_active_handler(call: CallbackQuery):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية!", show_alert=True)
        return
    cur = get_setting("force_sub_active", "0")
    set_setting("force_sub_active", "0" if cur == "1" else "1")
    SUB_CACHE.clear()
    await call.answer("تم تبديل حالة الاشتراك الإجباري.")
    await force_sub_settings(call)

@dp.callback_query(F.data == "adm_add_fsub_channel")
async def ask_add_channel_fsub(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_add_channel_input)
    text = (
        "📢 <b>إضافة قناة أو مجموعة للاشتراك الإجباري:</b>\n"
        "──────────────────────────\n"
        "⚠️ <b>ملاحظة هامة:</b> تأكد من رفع البوت كمشرف (Admin) داخل القناة أو المجموعة أولاً.\n\n"
        "أرسل الآن معرف القناة (مثال: <code>@MyChannel</code>) أو الآيدي الرقمي (مثال: <code>-1001234567890</code>):"
    )
    await call.message.edit_text(text, reply_markup=cancel_keyboard())

@dp.message(Form.admin_add_channel_input)
async def process_add_channel_fsub(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "limits"):
        return

    chat_input = message.text.strip()
    try:
        chat = await bot.get_chat(chat_input)
        chat_id = str(chat.id)
        title = chat.title or chat_input

        # توليد أو استخراج رابط الدعوة
        invite_link = chat.invite_link
        if not invite_link:
            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
            else:
                try:
                    invite_link = await bot.export_chat_invite_link(chat_id)
                except Exception:
                    invite_link = f"https://t.me/{chat_input.replace('@', '')}"

        with db_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO force_sub_channels (chat_id, title, invite_link) VALUES (?, ?, ?)", (chat_id, title, invite_link))
            conn.commit()

        SUB_CACHE.clear()
        await state.clear()
        await message.answer(f"✅ <b>تمت إضافة {title} للاشتراك الإجباري بنجاح!</b>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 العودة لقسم الاشتراك الإجباري", callback_data="adm_forcesub_menu")]])
        await message.answer("اضغط للمتابعة:", reply_markup=kb)
    except Exception as e:
        await message.answer(
            f"❌ <b>تعذر جلب بيانات القناة/المجموعة!</b>\n\n"
            f"• تأكد أن المعرف أو الآيدي صحيح.\n"
            f"• تأكد من رفع البوت مشرفاً داخلها.\n"
            f"الخطأ: <code>{html.escape(str(e))}</code>",
            reply_markup=cancel_keyboard()
        )

@dp.callback_query(F.data.startswith("adm_del_fsub_"))
async def delete_fsub_channel(call: CallbackQuery):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية!", show_alert=True)
        return
    ch_id = int(call.data.replace("adm_del_fsub_", ""))
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM force_sub_channels WHERE id = ?", (ch_id,))
        conn.commit()

    SUB_CACHE.clear()
    await call.answer("✅ تم حذف القناة من الاشتراك الإجباري.")
    await force_sub_settings(call)

@dp.callback_query(F.data == "adm_backup_db")
async def download_backup_database(call: CallbackQuery):
    if not has_permission(call.from_user.id, "backup"):
        await call.answer("⛔️ ليس لديك صلاحية لتحميل نسخة احتياطية!", show_alert=True)
        return
    await call.answer("جاري استخراج النسخة...")
    try:
        doc = FSInputFile("invest_v13_ultimate.db", filename=f"backup_invest_{int(time.time())}.db")
        await bot.send_document(call.from_user.id, doc, caption="📦 نسخة احتياطية من قاعدة بيانات المنظومة الكاملة.")
    except Exception as e:
        await call.message.answer(f"❌ خطأ في الإرسال: {e}")

@dp.callback_query(F.data == "adm_edit_limits")
async def edit_limits_menu(call: CallbackQuery):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية لتعديل الحدود والأسعار!", show_alert=True)
        return
    await call.answer()
    text = (
        "⚙️ <b>الحدود والنسب وأسعار الصرف المالية:</b>\n──────────────────────────\n"
        f"• الحد الأدنى للسحب: <b>${get_setting('min_withdraw', '5.0')}</b>\n"
        f"• السقف اليومي للسحب: <b>${get_setting('max_daily_withdraw', '500.0')}</b>\n"
        f"• سعر صرف الدولار بالدينار: <b>{get_setting('usd_to_iqd_rate', '1530')} د.ع</b>\n"
        f"• نسبة الإحالة: <b>{get_setting('ref_percent', '10')}%</b>\n"
        f"• عمولة التحويل الداخلي: <b>{get_setting('transfer_fee_percent', '2')}%</b>\n"
        f"• الهدية اليومية: <b>${get_setting('daily_bonus', '0.10')}</b>\n"
        f"• معرف الدعم: <b>{get_setting('support_user')}</b>\n"
        f"• قناة الإثباتات: <b>{get_setting('proof_channel') or 'غير محددة'}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 أدنى حد للسحب", callback_data="chset_min_withdraw"),
         InlineKeyboardButton(text="🛑 السقف اليومي للسحب", callback_data="chset_max_daily_withdraw")],
        [InlineKeyboardButton(text="💱 سعر صرف IQD", callback_data="chset_usd_to_iqd_rate"),
         InlineKeyboardButton(text="👥 عمولة الإحالة", callback_data="chset_ref_percent")],
        [InlineKeyboardButton(text="🔄 عمولة التحويل", callback_data="chset_transfer_fee_percent"),
         InlineKeyboardButton(text="🎁 الهدية اليومية", callback_data="chset_daily_bonus")],
        [InlineKeyboardButton(text="📞 معرف الدعم", callback_data="chset_support_user"),
         InlineKeyboardButton(text="📢 قناة الإثباتات", callback_data="chset_proof_channel")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_hub")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("chset_"))
async def prompt_change_setting(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "limits"):
        await call.answer("⛔️ ليس لديك صلاحية!", show_alert=True)
        return
    await call.answer()
    key = call.data.replace("chset_", "")
    await state.update_data(target_key=key)
    await state.set_state(Form.admin_change_setting)
    await call.message.answer(f"✏️ أرسل القيمة الجديدة لـ (<code>{key}</code>):", reply_markup=cancel_keyboard())

@dp.message(Form.admin_change_setting)
async def save_new_setting(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "limits"):
        return
    data = await state.get_data()
    set_setting(data["target_key"], message.text.strip())
    await state.clear()
    await message.answer("✅ تم حفظ وتحديث الإعداد المالي بنجاح!")

@dp.callback_query(F.data == "adm_toggles")
async def toggles_menu(call: CallbackQuery):
    if not has_permission(call.from_user.id, "toggles"):
        await call.answer("⛔️ ليس لديك صلاحية لمفاتيح التشغيل والصيانة!", show_alert=True)
        return
    await call.answer()
    maint = "🔴 مفعل" if get_setting("maintenance") == "1" else "🟢 معطل"
    wth = "🟢 مفعل" if get_setting("withdraw_active") == "1" else "🔴 مقفل"
    dep = "🟢 مفعل" if get_setting("deposit_active") == "1" else "🔴 مقفل"
    trans = "🟢 مفعل" if get_setting("transfer_active") == "1" else "🔴 مقفل"

    text = "🚦 مفاتيح التحكم السريع:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"تبديل الصيانة ({maint})", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(text=f"تبديل السحب ({wth})", callback_data="toggle_withdraw_active")],
        [InlineKeyboardButton(text=f"تبديل الإيداع ({dep})", callback_data="toggle_deposit_active")],
        [InlineKeyboardButton(text=f"تبديل تحويل الرصيد ({trans})", callback_data="toggle_transfer_active")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_hub")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("toggle_"))
async def handle_toggle(call: CallbackQuery):
    if not has_permission(call.from_user.id, "toggles"):
        await call.answer("⛔️ ليس لديك صلاحية!", show_alert=True)
        return
    key = call.data.replace("toggle_", "")
    cur = get_setting(key, "0")
    set_setting(key, "0" if cur == "1" else "1")
    await call.answer("تم تبديل الحالة.")
    await toggles_menu(call)

@dp.callback_query(F.data == "adm_user_inspect")
async def ask_user_inspect(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لإدارة المشتركين!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.admin_inspect_user)
    await call.message.answer("🔍 أرسل آيدي (ID) المستخدم للتحقق منه وإدارة باقاته:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_inspect_user)
async def process_user_inspect(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "users"):
        return
    try:
        uid = int(message.text)
        await show_user_profile_card(message, uid, state)
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام فقط.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data.startswith("usr_"))
async def user_actions_callback(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "users"):
        await call.answer("⛔️ ليس لديك صلاحية لتعديل حسابات المستخدمين!", show_alert=True)
        return
    parts = call.data.split("_")
    action, uid = parts[1], int(parts[2])

    if action in ["ban", "unban"]:
        update_user(uid, is_banned=(1 if action == "ban" else 0))
        await call.answer("تم تحديث حالة الحساب.")
        await show_user_profile_card(call.message, uid, state)
    elif action in ["add", "sub"]:
        await call.answer()
        await state.update_data(target_uid=uid, mode=action)
        await state.set_state(Form.admin_adjust_bal)
        await call.message.answer("✏️ أرسل المبلغ بالدولار:", reply_markup=cancel_keyboard())

@dp.message(Form.admin_adjust_bal)
async def process_adjust_bal(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "users"):
        return
    try:
        val = round(float(message.text), 2)
        data = await state.get_data()
        uid, mode = data["target_uid"], data["mode"]
        u = get_user(uid)
        new_bal = u["balance"] + val if mode == "add" else max(0.0, u["balance"] - val)
        update_user(uid, balance=round(new_bal, 2))
        await state.clear()
        await message.answer(f"✅ تم تعديل الرصيد بنجاح إلى: <b>${new_bal:.2f}</b>")
    except ValueError:
        await message.answer("❌ يرجى إدخال أرقام صحيحة.", reply_markup=cancel_keyboard())

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    if not has_permission(call.from_user.id, "broadcast"):
        await call.answer("⛔️ ليس لديك صلاحية للإذاعة العامة!", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.broadcast_msg)
    await call.message.answer("✏️ أرسل نص الرسالة لبثها لكافة المشتركين:", reply_markup=cancel_keyboard())

@dp.message(Form.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "broadcast"):
        return
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()

    s, f = 0, 0
    m = await message.answer("⏳ جاري بث الرسالة...")
    for row in users:
        try:
            await bot.send_message(row["user_id"], message.text)
            s += 1
            await asyncio.sleep(0.04)
        except Exception:
            f += 1
    await state.clear()
    await m.edit_text(f"✅ اكتملت الإذاعة: نجح {s} | تعذر {f}")

# ════════════════════ تشغيل المنظومة ════════════════════
async def main():
    print("🚀 المنظومة تعمل الآن بنظام الاشتراك الإجباري المتعدد فائق السرعة...")
    asyncio.create_task(auto_profit_background_worker())
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
