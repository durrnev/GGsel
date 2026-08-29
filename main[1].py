# -*- coding: utf-8 -*-
"""
Funpay Market — гарант-бот для безопасных сделок.
aiogram 3.x, JSON-хранилище, RU/EN локализация, админ-панель.
"""
import asyncio
import json
import os
import random
import re
import string
import sys
import threading
from html import escape as h

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    WebAppInfo,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage, SendPhoto

# ─────────────────────────────── Конфиг ───────────────────────────────
with open("config.json", "r", encoding="utf-8") as _f:
    CFG = json.load(_f)

BOT_TOKEN = CFG.get("BOT_TOKEN", "")
OWNER_IDS = set(CFG.get("OWNER_IDS", []))
BOT_USERNAME = CFG.get("BOT_USERNAME", "FunPaySaveBot")
MANAGER_USERNAME = CFG.get("MANAGER_USERNAME", "PIayerokNFT")
SUPPORT_USERNAME = CFG.get("SUPPORT_USERNAME", "FunpaySafetys")
MINIAPP_URL = CFG.get("MINIAPP_URL", "").strip()
COMMISSION_PERCENT = float(CFG.get("COMMISSION_PERCENT", 1.0))
MIN_DEALS_WITHDRAW = int(CFG.get("MIN_DEALS_WITHDRAW", 2))
RATES = {str(k).upper(): float(v) for k, v in CFG.get("RATES", {}).items()}
RATES.setdefault("USD", 1.0)

# Валюты сделки (код -> отображаемое имя)
CURRENCIES = ["RUB", "KZT", "UAH", "BYN", "GRAM", "STARS"]
CURRENCY_NAME = {"GRAM": "GRAM(TON)"}
CURRENCY_SYM = {"USD": "$", "RUB": "₽", "KZT": "₸", "UAH": "₴", "BYN": "Br", "GRAM": "TON", "STARS": "⭐"}

# ── Premium-эмодзи (document_id) из пакета TranslucentPack ──
# Для HTML: <tg-emoji emoji-id='…'>символ</tg-emoji> и для кнопок icon_custom_emoji_id
E = {
    "💼": "5276037216244624892",
    "🤝": "5298668674532538341",
    "⚡️": "5276111746812112286",
    "🛡": "5276262671962892944",
    "🪙": "5276037216244624892",
    "📦": "5278540791336165644",
    "💡": "5278753302023004775",
    "⬇️": "5206510891247371052",
    "🏖": "5278413853577734640",
    "🧑‍🎓": "5276381204470329471",
    "💪": "5276314275994954605",
    "😎": "5276127848644503161",
    "😘": "5278611606756942667",
    "🫥": "5275979556308674886",
    "😇": "5276111746812112286",
    "📌": "5278227821364275264",
    "💎": "5276111746812112286",
    "💳": "5276037216244624892",
    "⭐️": "5276111746812112286",
    "🚽": "5278647306525108244",
    "📞": "5278589204207528856",
    "💭": "5278589204207528856",
    "👑": "5276229330131772747",
    "🛒": "5278613311858959074",
    "❗️": "5276240711795107620",
    "🏦": "5276037216244624892",
    "💸": "5276037216244624892",
    "💳_CUR": "5276037216244624892",
    "🫰": "5298668674532538341",
    "💵": "5276037216244624892",
    "💰": "5276037216244624892",
    "✍️": "5278589204207528856",
    "✅": "5278411813468269386",
    "🔗": "5278305362703835500",
    "🧩": "5276442772826515132",
    "💔": "5278611606756942667",
    "📈": "5278778882848220741",
    "👥": "5298668674532538341",
    "🚫": "5278578973595427038",
    "💱": "5276037216244624892",
    "👛": "5276398496008663230",
    "🇷🇺": "5206202791768393003",
    "1⃣": "5244961448525848230",
}

# Не-премиум эмодзи -> премиум аналог (для авто-конвертации в текстах и кнопках)
E2P = {
    "❌": "🚫",
    "⭐": "⭐️",
    "🛟": "📞",
    "📂": "📈",
    "📜": "📦",
    "📊": "📈",
    "🌐": "🏦",
    "🙈": "🫥",
    "👤": "👥",
    "🌍": "🧩",
    "🤖": "⚡️",
    "🎉": "😎",
    "❔": "💭",
    "🇬🇧": "🧩",
    "🚀": "⚡️",
    "📨": "✍️",
    "🏠": "🏦",
    "🎁": "📦",
    "📢": "👥",
    "🏷": "🏦",
    "🤵": "👑",
    "🔢": "1⃣",
    "➕": "👥",
    "🗑": "🚫",
    "⚙️": "🛡",
    "ℹ️": "💡",
}

_PREF = sorted(set(E) | set(E2P), key=len, reverse=True)

_TAG = re.compile(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>")


def _plain(s):
    return _TAG.sub(r"\1", s)


def _leading_icon(raw):
    for k in _PREF:
        if raw.startswith(k):
            return E2P.get(k, k), raw[len(k):].strip()
    return None, raw


def premium(s):
    """Заменяет эмодзи на премиум <tg-emoji> теги, не трогая существующие теги."""
    if not s:
        return s
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s.startswith("<tg-emoji", i):
            end = s.find("</tg-emoji>", i)
            if end != -1:
                out.append(s[i:end + len("</tg-emoji>")])
                i = end + len("</tg-emoji>")
                continue
        matched = False
        for k in _PREF:
            if s.startswith(k, i):
                out.append(pe(E2P.get(k, k)))
                i += len(k)
                matched = True
                break
        if not matched:
            out.append(s[i])
            i += 1
    return "".join(out)

ICON = dict(E)
ICON["🪙_USDT"] = E["🪙"]
ICON["🪙_BTC"] = E["🪙"]
ICON["💸_RUB"] = E["💸"]
ICON["💳_UAH"] = E["💳_CUR"]
ICON["🫰_KZT"] = E["🫰"]
ICON["💵_BYN"] = E["💵"]
ICON["🪙_GRAM"] = E["🪙"]


def pe(symbol):
    eid = E.get(symbol)
    if eid:
        return "<tg-emoji emoji-id='{0}'>{1}</tg-emoji>".format(eid, h(symbol))
    return h(symbol)


DATA_FILE = "data.json"
DEALS_FILE = "deals.json"
ADMINS_FILE = "admins.json"

_lock = threading.Lock()


def load_json(path, default):
    with _lock:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default


def save_json(path, data):
    with _lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


USERS = load_json(DATA_FILE, {})
DEALS = load_json(DEALS_FILE, {})
PANEL_ADMINS = set(load_json(ADMINS_FILE, []))


def save_users():
    save_json(DATA_FILE, USERS)


def save_deals():
    save_json(DEALS_FILE, DEALS)


def save_admins():
    save_json(ADMINS_FILE, list(PANEL_ADMINS))


def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(CFG, f, ensure_ascii=False, indent=2)


def is_banned(uid):
    return bool(USERS.get(str(uid), {}).get("banned"))


def is_restricted(uid):
    return bool(USERS.get(str(uid), {}).get("restricted"))


# ─────────────────────────────── Утилиты ───────────────────────────────
def get_user(uid):
    uid = str(uid)
    if uid not in USERS:
        USERS[uid] = {
            "balance": 0.0,
            "deals": 0,
            "verified": False,
            "currency": "USD",
            "hide_balance": False,
            "req": {},
            "refs": 0,
            "lang": "ru",
        }
        save_users()
    return USERS[uid]


def username(user):
    if user and user.username:
        return "@" + user.username
    if user and user.first_name:
        return h(user.first_name)
    return "Пользователь"


def fmt(n):
    if n is None:
        return "0"
    n = float(n)
    if n == int(n):
        return str(int(n))
    return str(round(n, 2))


def rate_for(cur):
    return float(RATES.get(cur.upper(), 1.0))


def usd_to(cur, usd):
    return usd * rate_for(cur)


def cur_to_usd(cur, amount):
    r = rate_for(cur)
    return amount / r if r else 0.0


def new_deal_code():
    alphabet = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(alphabet, k=10))
        if code not in DEALS:
            return code


def cur_name(cur):
    return CURRENCY_NAME.get(cur, cur)


def cur_sym(cur):
    return CURRENCY_SYM.get(cur.upper(), "")


# ─────────────────────────────── Локализация ───────────────────────────────
T = {
    "ru": {
        "menu_title": "🛒 Funpay Market 🛒\n\n<blockquote>⭐Наши преимущества:\n\n• 🛡 Защита от мошенников\n• 📦 Автоматическое удержание средств\n• 📈 Прозрачная статистика\n• 📞 Поддержка 24/7\n• ✅ История сделок</blockquote>",
        "blurb": "Покупатель / Продавец",
        "btn_create": "💰 Создать сделку",
        "btn_profile": "👤 Профиль",
        "btn_verify": "💎 Верификация",
        "btn_req": "💳 Реквизиты",
        "btn_lang": "🌍 Язык",
        "btn_ref": "🔗 Рефералы",
        "btn_more": "ℹ️ Подробнее",
        "btn_miniapp": "Мини-ап",
        "btn_support": "🛟 Поддержка",
        "back": "Вернуться",
        "menu": "Меню",
        "cancel": "Отменить",

        "profile": "ℹ️ Профиль:\n\nИмя: {name}\nБаланс: {balance}\nУспешных сделок: {deals}\nВерифицирован: {ver}\n\n⭐Выберите нужный раздел ниже",
        "btn_rates": "💱 Курс валют",
        "btn_topup": "💰 Пополнить",
        "btn_withdraw": "💸 Баланс вывести",
        "btn_settings": "⚙️ Настройки",
        "ver_yes": "✅",
        "ver_no": "❌",
        "balance_hidden": "****",
        "currency_selected": "Баланс отображается в {cur}",
        "balance_hidden_on": "Баланс скрыт",
        "balance_hidden_off": "Баланс виден",

        "rates": "💱 Курс валют к доллару\n\n" + "\n".join("💵 {c} >> {r}".format(c=cur_name(c), r=fmt(RATES.get(c, 0))) for c in ["RUB", "KZT", "UAH", "BYN", "GRAM", "STARS"]),

        "topup": "💰 Пополнение\n\n⭐Выберите способ пополнения\n\n✅После оплаты баланс обновится автоматически",
        "btn_cryptobot": "🤖 CryptoBot",
        "topup_method": "💳 Пополнение через {m}\n\nПополните через поддержку: @{support}\n\nПосле пополнения баланс обновится автоматически.",
        "topup_notice": "Пополнение через {m} временно недоступно. Скоро заработает!",

        "withdraw": "💸 Вывод\n\nВывод от {min}x сделок\n\nУ вас успешных сделок: {deals}\n\n⭐После выполнения условий, средства можно вывести через менеджера @{manager}",
        "withdraw_need": "Вывод доступен от {min}x сделок. У вас пока {deals}.",
        "withdraw_ok": "Вывод от {min}x сделок ✅\n\nЗаявка на вывод отправлена менеджеру @{manager}",

        "settings": "💡 Настройки:",
        "btn_disp_cur": "💱 Валюта отображения",
        "btn_hide_bal": "🙈 Скрыть баланс",
        "choose_currency": "💱 Выберите, в какой валюте отображать баланс",
        "set_currency_done": "Готово! Баланс отображается в {cur}",
        "hide_cur": "🙈 Валюта отображения",
        "hide_bal_status": "Сейчас баланс: {status}",

        "req": "💳 Реквизиты\n\n" + "\n".join("• {c}: {v}".format(c=cur_name(c), v="Не указано") for c in CURRENCIES) + "\n\n⭐Выберите нужный раздел ниже",
        "btn_edit_req": "✏️ Изменить реквизиты",
        "req_choose": "💳 Выберите валюту для изменения реквизитов",
        "req_input": "💳 Введите ваш номер телефона или карту для {c}\n\n⭐Пример:\n+7 123 456 78 90\n2020 2020 2020 2020",
        "req_input_ton": "💳 Введите ваш TON-кошелёк для GRAM(TON)\n\n⭐Пример:\nUQAmzx-...",
        "req_input_stars": "💳 Введите ваш username для STARS\n\n⭐Пример:\n@username",
        "req_saved": "✅ Реквизиты для {c} сохранены: {v}",
        "req_value": "Не указано",
        "req_title": "💳 Реквизиты",
        "req_line": "• {c}: {v}",
        "req_footer": "⭐Выберите нужный раздел ниже",

        "ref": "🔗 Ваша реферальная ссылка:\n{link}\n\nПриглашайте друзей и получайте бонусы за их сделки!\n\nВаше количество рефералов: {refs}",
        "ref_new": "🎉 По вашей ссылке пришёл новый реферал!",
        "ref_link": "https://t.me/{bot}?start=ref_{id}",

        "more": "ℹ️ Подробнее:\n\n✅Мы – гарант сервис, наша задача помочь вам провести безопасные сделки, и оформить быстрый вывод!\n\n❔Ответы на частые вопросы:\n\n• Как долго происходит вывод? Обычно не более 2-х минут, в редких случаях до 2-х суток.\n\n• Почему нужно передавать подарок менеджеру, но не покупателю? Причина проста: покупатель может наврать что ему не пришёл подарок, что затягивает ситуацию, но наш менеджер автоматически проверяет наличие NFT подарка и уже обмануть не получится.\n\n• Как быстро происходит пополнение? Пополнение также занимает не более 2-х минут.\n\n• Я увидел похожего бота, стоит ли мне доверять? Если вы увидели другого бота кроме @{bot}, ни в коем случае не проводите с ним сделки!",

        "lang_title": "⭐ Выберите язык:",
        "btn_ru": "🇷🇺 Русский",
        "btn_en": "🇬🇧 English",
        "lang_done": "Язык: {lang}",

        "verify": "💎 Премиум-статус Funpay Market\n\n⭐Что дает премиум-статус:\n• Верификация продавца - знак доверия\n• Гарант сделок - защита от мошенников\n• Приоритетная поддержка - быстрые ответы\n• Сниженная комиссия - 1% >> 0.5%\n• Быстрые выплаты - в течение 1 часа\n\n✅ Безопасность:\n•  Страхование сделок\n•  Юридическая защита\n•  Поддержка 24/7\n\n🚀 Преимущества:\n•  Повышенное доверие покупателей\n•  Больше успешных сделок\n•  Персональный менеджер\n•  Эксклюзивные предложения\n\n📌Как получить Премиум-статус:\n•  Вам должно быть 18+\n•  У вас должно быть 50+ сделок\n•  На вашем балансе должно быть более 100$",
        "btn_apply": "📨 Подать заявку",
        "apply_soon": "⏳ Заявки временно недоступны. Скоро заработают!",

        "support_text": "🛟 Поддержка 24/7\n\nСвяжитесь с нами: @{support}",

        "nd_role": "💰 Новая сделка\n\n⭐Кем вы выступаете в этой сделке?\n\n💼 Продавец — вы продаёте товар/услугу и получаете оплату.\n🛒 Покупатель — вы платите и получаете товар/услугу.",
        "btn_seller": "💼 Продавец",
        "btn_buyer": "🛒 Покупатель",
        "nd_currency": "💰 Способ получения оплаты:\n\n⭐Куда вы хотите получить оплату?",
        "nd_amount": "💰 Введите сумму в {c}:",
        "nd_desc": "ℹ️ Опишите предмет сделки:\n\nНапример: https://t.me/nft/PlushPepe-111\nили просто текстовое описание товара",
        "nd_bad_amount": "❌ Введите корректное число больше 0.",
        "nd_cancelled": "❌ Создание сделки отменено.",

        "deal_waiting": "💰 Сделка #{code}\n\n📌Статус: ожидает второго участника\n✅Вы: {role}\n\n🛒Покупатель: {buyer}\n💼Продавец: {seller}\n\n💱Валюта: {currency}\n💰Сумма: {amount}\nℹ️Описание: {desc}\n\n💳Покупатель не оплатил сделку ❌\n\n🔗Ссылка для второго участника:\n{link}",
        "deal_waiting_join": "💰 Сделка #{code}\n\n📌Статус: ожидает второго участника\n✅Вы: {role}\n\n🛒Покупатель: {buyer}\n💼Продавец: {seller}\n\n💱Валюта: {currency}\n💰Сумма: {amount}\nℹ️Описание: {desc}\n\n💳Покупатель не оплатил сделку ❌\n\n🔗Ссылка для второго участника:\n{link}",
        "deal_gathered": "💰 Сделка #{code}\n\n📌Статус: участники собраны\n✅Вы: {role}\n\n🛒Покупатель: {buyer}\n💼Продавец: {seller}\n\n💱Валюта: {currency}\n💰Сумма: {amount}\nℹ️Описание: {desc}\n\n💳Покупатель не оплатил сделку ❌\n\n🔗Ссылка для второго участника:\n{link}\n\n\n💳Покупатель присоединится к сделке — ожидайте оплату",
        "deal_gathered_buyer": "💰 Сделка #{code}\n\n📌Статус: участники собраны\n✅Вы: {role}\n\n🛒Покупатель: {buyer}\n💼Продавец: {seller}\n\n💱Валюта: {currency}\n💰Сумма: {amount}\nℹ️Описание: {desc}\n\n💳Покупатель не оплатил сделку ❌",
        "deal_paid_buyer": "✅ Оплата подтверждена! Продавец уведомлен о вашем платеже.\n\n💸 Ожидайте подтверждения передачи NFT от менеджера...\n\n📂 Ваша статистика будет обновлена после подтверждения менеджером.\n\nОжидайте получения товара через менеджера.",
        "deal_paid_seller": "ПЛАТЁЖ ПОДТВЕРЖДЁН!\n\n✅ Покупатель {buyer} подтвердил оплату\n📜 Сделка: #{code}\n💼 Товар: {desc}\n💸 Сумма: {amount} {currency}\n\n📂 Финансовые условия:\n• Комиссия системы: {cc}% ({ccv} {currency})\n• К зачислению на баланс: {cred} {currency}\n\nТРЕБУЕТСЯ ВАШЕ ДЕЙСТВИЕ:\n1. Передайте товар менеджеру https://t.me/{manager}\n2. После передачи нажмите кнопку ниже\n3. Менеджер подтвердит получение товара\n4. Сумма {cred} {currency} будет зачислена на ваш баланс\n\n❌ Не передавайте товар покупателю напрямую!",
        "btn_join_deal": "🤝 Присоединиться к сделке",
        "btn_pay": "💳 Оплатить",
        "btn_submit": "📦 Подать заявку на передачу товара",
        "btn_confirm_receipt": "✅ Подтвердить получение",
        "btn_cancel_deal": "❌ Отменить сделку",
        "btn_menu": "🏠 Вернуться в меню",
        "deal_join_alert": "✅ Вы присоединились к сделке #{code}!",
        "deal_joined_notify": "✅ Вы подключились к сделке #{code} как {role}.\n\n🛡 Вся оплата и передача товара проходит ТОЛЬКО через менеджера @{manager}.\n🔜 После подтверждения оплаты покупателем — передайте товар менеджеру.",
        "deal_full": "❌ Сделка #{code} уже собрана.",
        "deal_not_found": "❌ Сделка не найдена.",
        "deal_pay_ok": "✅ Оплата прошла! Продавец уведомлён.",
        "deal_no_money": "❌ Недостаточно средств на балансе.",
        "deal_confirm_ok": "✅ Спасибо! Получение подтверждено, средства зачислены продавцу.",
        "deal_submitted": "✅ Заявка на передачу отправлена!\n\n📂 Сделка: #{code}\n💼 Товар: {desc}\n💸 К зачислению: {cred} {currency}\n\nОжидайте подтверждения получения от покупателя.",
        "deal_submitted_buyer": "📦 Продавец передал товар по сделке #{code}.\n\n✅ Проверьте товар и подтвердите получение, чтобы деньги поступили продавцу.",
        "deal_submitted_buyer_notify": "📦 Продавец передал товар по сделке #{code}.\n\n✅ Проверьте товар и нажмите «Подтвердить получение», чтобы деньги поступили продавцу.",
        "deal_submitted_seller_last": "✅ Заявка на передачу товара отправлена!\n\n📂 Сделка: #{code}\n⏳ Ожидайте подтверждения получения от покупателя.",
        "deal_done_seller": "✅ Сделка завершена!\n\n💸 На ваш баланс зачислено: {cred} {currency}\n📜 Сделка: #{code}\n\nСпасибо за работу!",
        "deal_done_buyer": "✅ Сделка завершена!\n\n🎁 Товар отправлен вам.\n📜 Сделка: #{code}\n\nСпасибо за покупку!",
        "deal_done_seller_last": "✅ Сделка завершена!\n\n✅ Получение подтверждено покупателем.\n💸 На ваш баланс зачислено: {cred} {currency}\n📜 Сделка: #{code}\n\nСпасибо за работу!",
        "deal_done_buyer_last": "✅ Сделка завершена!\n\n✅ Получение подтверждено, средства зачислены продавцу.\n📜 Сделка: #{code}\n\nСпасибо за покупку!",
        "deal_cancelled": "❌ Сделка #{code} отменена.",
        "deal_cancelled_buyer_refund": "❌ Сделка #{code} отменена. Средства возвращены на баланс.",

        "role_buyer": "Покупатель",
        "role_seller": "Продавец",
        "no_one": "Нет",
        "btn_back_menu": "❌ Вернуться",
        "btn_back_profile": "❌ Вернуться",
        "btn_back_settings": "❌ Вернуться",
        "btn_back_req": "❌ Вернуться",
        "btn_back_topup": "❌ Вернуться",

        "admin_no": "❌ У вас нет доступа к панели.",
        "admin_title": "⚙️ Админ-панель Funpay Market",
        "admin_stats": "📊 Статистика",
        "admin_settings": "⚙️ Настройки",
        "admin_admins": "👥 Админы",
        "admin_deals": "📦 Сделки",
        "admin_broadcast": "📢 Рассылка",
        "admin_close": "❌ Закрыть",
        "admin_stats_text": "📊 Статистика:\n\n👥 Пользователей: {users}\n💰 Общий баланс: {balance}$\n📦 Всего сделок: {deals}\n⏳ Ожидают участника: {waiting}\n🤝 В процессе: {active}\n✅ Завершено: {done}",
        "admin_panel_text": "👑 Админ-панель\n\nВыберите действие:",
        "admin_settings_text": "⚙️ Настройки:\n\n🤖 Бот: @{bot}\n🏷 Сервис: {name}\n🤵 Менеджер: @{manager}\n📊 Комиссия: {cc}%\n🔢 Мин. сделок для вывода: {min}\n🛟 Поддержка: @{support}\n🧩 Мини-ап: {mini}",
        "btn_edit_name": "✏️ Название сервиса",
        "btn_edit_bot": "✏️ Username бота",
        "btn_edit_manager": "✏️ Менеджер",
        "btn_edit_commission": "✏️ Комиссия (%)",
        "btn_edit_min": "✏️ Мин. сделок",
        "btn_edit_support": "✏️ Поддержка",
        "btn_edit_miniapp": "✏️ Мини-ап",
        "admin_edit_prompt": "Введите новое значение для: {what}",
        "admin_edit_done": "✅ Сохранено",
        "admin_admins_text": "👥 Панельные админы:\n\n{list}\n\nВладельцы: {owners}",
        "btn_admin_add": "➕ Добавить админа",
        "admin_add_prompt": "Отправьте ID или @username нового админа:",
        "admin_add_done": "✅ {name} ({uid}) добавлен в панель.",
        "admin_add_fail": "❌ Пользователь не найден.",
        "btn_admin_rm": "🗑",
        "admin_rm_done": "✅ Админ {uid} удалён.",
        "admin_deals_text": "📦 Сделки ({n}):\n\n{list}",
        "admin_deal_confirm": "✅ Подтвердить передачу",
        "admin_deal_cancel": "❌ Отменить",
        "admin_broadcast_prompt": "Отправьте текст рассылки (HTML):",
        "admin_broadcast_ok": "✅ Рассылка отправлена {n} пользователям.",
        "admin_confirm_done": "✅ Передача подтверждена. Сделка #{code} завершена.",
        "btn_admin_give": "💰 Выдать баланс",
        "btn_admin_take": "💸 Забрать баланс",
        "btn_admin_ban": "🚫 Выдать бан",
        "btn_admin_unban": "✅ Разбанить",
        "btn_admin_restrict": "🚫 Ограничить оплату",
        "btn_admin_unrestrict": "✅ Снять ограничение",
        "btn_admin_manager": "👑 Сменить менеджера",
        "btn_admin_workers": "👥 Список воркеров",
        "btn_admin_log": "📦 Лог сделок",
        "admin_action_prompt_give": "Формат: <code>ID ВАЛЮТА СУММА</code>\nПример: <code>123456 RUB 5000</code>",
        "admin_action_prompt_take": "Формат: <code>ID ВАЛЮТА СУММА</code>\nПример: <code>123456 RUB 5000</code>",
        "admin_action_prompt_ban": "Введите ID пользователя для бана:",
        "admin_action_prompt_unban": "Введите ID пользователя для разбана:",
        "admin_action_prompt_restrict": "Введите ID пользователя для ограничения оплаты:",
        "admin_action_prompt_unrestrict": "Введите ID пользователя для снятия ограничения оплаты:",
        "admin_action_prompt_manager": "Текущий менеджер: {mgr}\n\nВведите новый @username:",
        "admin_workers_empty": "Воркеров пока нет",
        "admin_workers_title": "Список воркеров ({n}):",
        "admin_give_ok": "{amount} {cur} выдано пользователю {uid}.",
        "admin_take_ok": "{amount} {cur} забрано у пользователя {uid}.",
        "admin_ban_ok": "Пользователь {user_id} забанен.",
        "admin_unban_ok": "Пользователь {user_id} разбанен.",
        "admin_restrict_ok": "Оплата ограничена для {user_id}.",
        "admin_unrestrict_ok": "Ограничение снято для {user_id}.",
        "admin_manager_ok": "Менеджер изменён: {mgr}",
        "admin_bad_input": "Неверный формат ввода.",
        "banned": "Вы забанены в этом боте.",
        "pay_blocked": "Оплата недоступна. Обратитесь в поддержку @{support}",

        "unknown": "Используйте /start",
        "started": "Добро пожаловать в Funpay Market!",

        "goy_title": "💼 Пополнение баланса",
        "goy_choose": "Выберите валюту:",
        "goy_enter": "Валюта: {cur}\n\nВведите сумму:",
        "goy_bad": "❌ Введите корректное положительное число.",
        "goy_cancelled": "❌ Отменено.",
        "goy_done": "✅ Баланс пополнен!\n\n+{amount} {cur}\nБаланс: {bal} {cur}",
        "goy_no_access": "❌ У вас нет доступа.",
        "goy_granted": "✅ Лее, брат, ты теперь воркер!\n\n💡 Чтобы оплатить — достаточно нажать на кнопку «Оплатить»\n\n<code>/set_my_deals число</code> — установить кол-во сделок\n<code>/goy</code> — пополнить свой баланс",
        "set_deals_usage": "❌ Использование: <code>/set_my_deals число</code>",
        "set_deals_done": "✅ Количество сделок установлено: <code>{n}</code>",
    },
    "en": {
        "menu_title": "🛒 Funpay Market 🛒\n\n<blockquote>⭐Our advantages:\n\n• 🛡 Scam protection\n• 📦 Automatic funds hold\n• 📈 Transparent statistics\n• 📞 24/7 support\n• ✅ Deal history</blockquote>",
        "blurb": "Buyer / Seller",
        "btn_create": "💰 Create deal",
        "btn_profile": "👤 Profile",
        "btn_verify": "💎 Verification",
        "btn_req": "💳 Requisites",
        "btn_lang": "🌍 Language",
        "btn_ref": "🔗 Referrals",
        "btn_more": "ℹ️ More",
        "btn_miniapp": "Mini app",
        "btn_support": "🛟 Support",
        "back": "Back",
        "menu": "Menu",
        "cancel": "Cancel",

        "profile": "ℹ️ Profile:\n\nName: {name}\nBalance: {balance}\nSuccessful deals: {deals}\nVerified: {ver}\n\n⭐Select the section below",
        "btn_rates": "💱 Exchange rates",
        "btn_topup": "💰 Top up",
        "btn_withdraw": "💸 Withdraw",
        "btn_settings": "⚙️ Settings",
        "ver_yes": "✅",
        "ver_no": "❌",
        "balance_hidden": "****",
        "currency_selected": "Balance is shown in {cur}",
        "balance_hidden_on": "Balance hidden",
        "balance_hidden_off": "Balance visible",

        "rates": "💱 Exchange rates to USD\n\n" + "\n".join("💵 {c} >> {r}".format(c=cur_name(c), r=fmt(RATES.get(c, 0))) for c in ["RUB", "KZT", "UAH", "BYN", "GRAM", "STARS"]),

        "topup": "💰 Top up\n\n⭐Choose payment method\n\n✅After payment the balance updates automatically",
        "btn_cryptobot": "🤖 CryptoBot",
        "topup_method": "💳 Top up via {m}\n\nPlease top up via support: @{support}\n\nAfter payment the balance updates automatically.",
        "topup_notice": "Top up via {m} is temporarily unavailable. Coming soon!",

        "withdraw": "💸 Withdrawal\n\nWithdrawal from {min} deals\n\nYour successful deals: {deals}\n\n⭐After the conditions are met, funds can be withdrawn via manager @{manager}",
        "withdraw_need": "Withdrawal available from {min} deals. You have {deals}.",
        "withdraw_ok": "Withdrawal from {min} deals ✅\n\nWithdrawal request sent to manager @{manager}",

        "settings": "💡 Settings:",
        "btn_disp_cur": "💱 Display currency",
        "btn_hide_bal": "🙈 Hide balance",
        "choose_currency": "💱 Choose the currency to display balance",
        "set_currency_done": "Done! Balance is shown in {cur}",
        "hide_cur": "🙈 Display currency",
        "hide_bal_status": "Balance is currently: {status}",

        "req": "💳 Requisites\n\n" + "\n".join("• {c}: {v}".format(c=cur_name(c), v="Not set") for c in CURRENCIES) + "\n\n⭐Select the section below",
        "btn_edit_req": "✏️ Edit requisites",
        "req_choose": "💳 Choose currency to edit requisites",
        "req_input": "💳 Enter your phone number or card for {c}\n\n⭐Example:\n+7 123 456 78 90\n2020 2020 2020 2020",
        "req_input_ton": "💳 Enter your TON wallet for GRAM(TON)\n\n⭐Example:\nUQAmzx-...",
        "req_input_stars": "💳 Enter your username for STARS\n\n⭐Example:\n@username",
        "req_saved": "✅ Requisites for {c} saved: {v}",
        "req_value": "Not set",
        "req_title": "💳 Requisites",
        "req_line": "• {c}: {v}",
        "req_footer": "⭐Select the section below",

        "ref": "🔗 Your referral link:\n{link}\n\nInvite friends and get bonuses for their deals!\n\nYour referrals: {refs}",
        "ref_new": "🎉 A new user came through your link!",
        "ref_link": "https://t.me/{bot}?start=ref_{id}",

        "more": "ℹ️ More:\n\n✅We are an escrow service, our goal is to help you make safe deals and get fast withdrawal!\n\n❔FAQ:\n\n• How long does withdrawal take? Usually no more than 2 minutes, rarely up to 2 days.\n\n• Why transfer the gift to the manager and not the buyer? Simple: the buyer may lie that the gift did not arrive, which delays the situation, but our manager automatically checks the NFT gift and deception is impossible.\n\n• How fast is top up? Top up also takes no more than 2 minutes.\n\n• I saw a similar bot, should I trust it? If you see a bot other than @{bot}, never deal with it!",

        "lang_title": "⭐ Choose language:",
        "btn_ru": "🇷🇺 Русский",
        "btn_en": "🇬🇧 English",
        "lang_done": "Language: {lang}",

        "verify": "💎 Funpay Market premium status\n\n⭐What premium gives:\n• Seller verification - trust badge\n• Deal escrow - scam protection\n• Priority support - fast answers\n• Reduced commission - 1% >> 0.5%\n• Fast payouts - within 1 hour\n\n✅ Security:\n•  Deal insurance\n•  Legal protection\n•  24/7 support\n\n🚀 Benefits:\n•  Higher buyer trust\n•  More successful deals\n•  Personal manager\n•  Exclusive offers\n\n📌How to get Premium:\n•  You must be 18+\n•  You must have 50+ deals\n•  Your balance must be above 100$",
        "btn_apply": "📨 Apply",
        "apply_soon": "⏳ Applications are temporarily unavailable. Coming soon!",

        "support_text": "🛟 24/7 Support\n\nContact us: @{support}",

        "nd_role": "💰 New deal\n\n⭐What is your role in this deal?\n\n💼 Seller — you sell an item/service and receive payment.\n🛒 Buyer — you pay and receive an item/service.",
        "btn_seller": "💼 Seller",
        "btn_buyer": "🛒 Buyer",
        "nd_currency": "💰 Payment method:\n\n⭐Where do you want to receive payment?",
        "nd_amount": "💰 Enter the amount in {c}:",
        "nd_desc": "ℹ️ Describe the deal item:\n\nExample: https://t.me/nft/PlushPepe-111\nor just a text description",
        "nd_bad_amount": "❌ Enter a valid number greater than 0.",
        "nd_cancelled": "❌ Deal creation cancelled.",

        "deal_waiting": "💰 Deal #{code}\n\n📌Status: waiting for second participant\n✅You: {role}\n\n🛒Buyer: {buyer}\n💼Seller: {seller}\n\n💱Currency: {currency}\n💰Amount: {amount}\nℹ️Description: {desc}\n\n💳Buyer has not paid the deal ❌\n\n🔗Link for the second participant:\n{link}",
        "deal_waiting_join": "💰 Deal #{code}\n\n📌Status: waiting for second participant\n✅You: {role}\n\n🛒Buyer: {buyer}\n💼Seller: {seller}\n\n💱Currency: {currency}\n💰Amount: {amount}\nℹ️Description: {desc}\n\n💳Buyer has not paid the deal ❌\n\n🔗Link for the second participant:\n{link}",
        "deal_gathered": "💰 Deal #{code}\n\n📌Status: participants gathered\n✅You: {role}\n\n🛒Buyer: {buyer}\n💼Seller: {seller}\n\n💱Currency: {currency}\n💰Amount: {amount}\nℹ️Description: {desc}\n\n💳Buyer has not paid the deal ❌\n\n🔗Link for the second participant:\n{link}\n\n\n💳Buyer will join the deal — waiting for payment",
        "deal_gathered_buyer": "💰 Deal #{code}\n\n📌Status: participants gathered\n✅You: {role}\n\n🛒Buyer: {buyer}\n💼Seller: {seller}\n\n💱Currency: {currency}\n💰Amount: {amount}\nℹ️Description: {desc}\n\n💳Buyer has not paid the deal ❌",
        "deal_paid_buyer": "✅ Payment confirmed! The seller has been notified.\n\n💸 Waiting for NFT transfer confirmation from the manager...\n\n📂 Your statistics will be updated after manager confirmation.\n\nExpect to receive the item via the manager.",
        "deal_paid_seller": "PAYMENT CONFIRMED!\n\n✅ Buyer {buyer} confirmed the payment\n📜 Deal: #{code}\n💼 Item: {desc}\n💸 Amount: {amount} {currency}\n\n📂 Financial terms:\n• System commission: {cc}% ({ccv} {currency})\n• To be credited: {cred} {currency}\n\nYOUR ACTION REQUIRED:\n1. Transfer the item to the manager https://t.me/{manager}\n2. After transfer press the button below\n3. The manager confirms receiving the item\n4. {cred} {currency} will be credited to your balance\n\n❌ Do NOT transfer the item directly to the buyer!",
        "btn_join_deal": "🤝 Join the deal",
        "btn_pay": "💳 Pay",
        "btn_submit": "📦 Submit item transfer request",
        "btn_confirm_receipt": "✅ Confirm receipt",
        "btn_cancel_deal": "❌ Cancel deal",
        "btn_menu": "🏠 Back to menu",
        "deal_join_alert": "✅ You joined the deal #{code}!",
        "deal_joined_notify": "✅ You joined the deal #{code} as {role}.\n\n🛡 All payments and item transfer go ONLY through the manager @{manager}.\n🔜 After the buyer confirms the payment — hand the item to the manager.",
        "deal_full": "❌ Deal #{code} is already full.",
        "deal_not_found": "❌ Deal not found.",
        "deal_pay_ok": "✅ Payment successful! The seller has been notified.",
        "deal_no_money": "❌ Not enough funds on balance.",
        "deal_confirm_ok": "✅ Thank you! Receipt confirmed, funds credited to the seller.",
        "deal_submitted": "✅ Transfer request sent!\n\n📂 Deal: #{code}\n💼 Item: {desc}\n💸 To be credited: {cred} {currency}\n\nWaiting for the buyer to confirm receipt.",
        "deal_submitted_buyer": "📦 The seller transferred the item for deal #{code}.\n\n✅ Check the item and confirm receipt so the seller gets paid.",
        "deal_submitted_buyer_notify": "📦 The seller transferred the item for deal #{code}.\n\n✅ Check the item and press \"Confirm receipt\" so the seller gets paid.",
        "deal_submitted_seller_last": "✅ Item transfer request sent!\n\n📂 Deal: #{code}\n⏳ Waiting for the buyer to confirm receipt.",
        "deal_done_seller": "✅ Deal completed!\n\n💸 Credited to your balance: {cred} {currency}\n📜 Deal: #{code}\n\nThanks for the work!",
        "deal_done_buyer": "✅ Deal completed!\n\n🎁 Item sent to you.\n📜 Deal: #{code}\n\nThanks for the purchase!",
        "deal_done_seller_last": "✅ Deal completed!\n\n✅ Receipt confirmed by the buyer.\n💸 Credited to your balance: {cred} {currency}\n📜 Deal: #{code}\n\nThanks for the work!",
        "deal_done_buyer_last": "✅ Deal completed!\n\n✅ Receipt confirmed, funds credited to the seller.\n📜 Deal: #{code}\n\nThanks for the purchase!",
        "deal_cancelled": "❌ Deal #{code} cancelled.",
        "deal_cancelled_buyer_refund": "❌ Deal #{code} cancelled. Funds returned to balance.",

        "role_buyer": "Buyer",
        "role_seller": "Seller",
        "no_one": "None",
        "btn_back_menu": "❌ Back",
        "btn_back_profile": "❌ Back",
        "btn_back_settings": "❌ Back",
        "btn_back_req": "❌ Back",
        "btn_back_topup": "❌ Back",

        "admin_no": "❌ You have no access to the panel.",
        "admin_title": "⚙️ Funpay Market Admin Panel",
        "admin_stats": "📊 Statistics",
        "admin_settings": "⚙️ Settings",
        "admin_admins": "👥 Admins",
        "admin_deals": "📦 Deals",
        "admin_broadcast": "📢 Broadcast",
        "admin_close": "❌ Close",
        "admin_stats_text": "📊 Statistics:\n\n👥 Users: {users}\n💰 Total balance: {balance}$\n📦 Total deals: {deals}\n⏳ Waiting for participant: {waiting}\n🤝 In progress: {active}\n✅ Completed: {done}",
        "admin_panel_text": "👑 Admin panel\n\nChoose an action:",
        "admin_settings_text": "⚙️ Settings:\n\n🤖 Bot: @{bot}\n🏷 Service: {name}\n🤵 Manager: @{manager}\n📊 Commission: {cc}%\n🔢 Min deals to withdraw: {min}\n🛟 Support: @{support}\n🧩 Mini app: {mini}",
        "btn_edit_name": "✏️ Service name",
        "btn_edit_bot": "✏️ Bot username",
        "btn_edit_manager": "✏️ Manager",
        "btn_edit_commission": "✏️ Commission (%)",
        "btn_edit_min": "✏️ Min deals",
        "btn_edit_support": "✏️ Support",
        "btn_edit_miniapp": "✏️ Mini app",
        "admin_edit_prompt": "Enter a new value for: {what}",
        "admin_edit_done": "✅ Saved",
        "admin_admins_text": "👥 Panel admins:\n\n{list}\n\nOwners: {owners}",
        "btn_admin_add": "➕ Add admin",
        "admin_add_prompt": "Send the ID or @username of the new admin:",
        "admin_add_done": "✅ {name} ({uid}) added to the panel.",
        "admin_add_fail": "❌ User not found.",
        "btn_admin_rm": "🗑",
        "admin_rm_done": "✅ Admin {uid} removed.",
        "admin_deals_text": "📦 Deals ({n}):\n\n{list}",
        "admin_deal_confirm": "✅ Confirm transfer",
        "admin_deal_cancel": "❌ Cancel",
        "admin_broadcast_prompt": "Send the broadcast text (HTML):",
        "admin_broadcast_ok": "✅ Broadcast sent to {n} users.",
        "admin_confirm_done": "✅ Transfer confirmed. Deal #{code} completed.",
        "btn_admin_give": "💰 Give balance",
        "btn_admin_take": "💸 Take balance",
        "btn_admin_ban": "🚫 Ban",
        "btn_admin_unban": "✅ Unban",
        "btn_admin_restrict": "🚫 Restrict payment",
        "btn_admin_unrestrict": "✅ Remove restriction",
        "btn_admin_manager": "👑 Set manager",
        "btn_admin_workers": "👥 Workers list",
        "btn_admin_log": "📦 Deals log",
        "admin_action_prompt_give": "Format: <code>ID CURRENCY AMOUNT</code>\nExample: <code>123456 RUB 5000</code>",
        "admin_action_prompt_take": "Format: <code>ID CURRENCY AMOUNT</code>\nExample: <code>123456 RUB 5000</code>",
        "admin_action_prompt_ban": "Enter the user ID to ban:",
        "admin_action_prompt_unban": "Enter the user ID to unban:",
        "admin_action_prompt_restrict": "Enter the user ID to restrict payment:",
        "admin_action_prompt_unrestrict": "Enter the user ID to remove payment restriction:",
        "admin_action_prompt_manager": "Current manager: {mgr}\n\nEnter a new @username:",
        "admin_workers_empty": "No workers yet",
        "admin_workers_title": "Workers list ({n}):",
        "admin_give_ok": "{amount} {cur} given to user {uid}.",
        "admin_take_ok": "{amount} {cur} taken from user {uid}.",
        "admin_ban_ok": "User {user_id} banned.",
        "admin_unban_ok": "User {user_id} unbanned.",
        "admin_restrict_ok": "Payment restricted for {user_id}.",
        "admin_unrestrict_ok": "Restriction removed for {user_id}.",
        "admin_manager_ok": "Manager changed: {mgr}",
        "admin_bad_input": "Invalid input format.",
        "banned": "You are banned in this bot.",
        "pay_blocked": "Payment unavailable. Contact support @{support}",

        "unknown": "Use /start",
        "started": "Welcome to Funpay Market!",

        "goy_title": "💰 Balance top-up",
        "goy_choose": "Choose currency:",
        "goy_enter": "Currency: {cur}\n\nEnter the amount:",
        "goy_bad": "❌ Enter a valid positive number.",
        "goy_cancelled": "❌ Cancelled.",
        "goy_done": "✅ Balance topped up!\n\n+{amount} {cur}\nBalance: {bal} {cur}",
        "goy_no_access": "❌ You have no access.",
        "goy_granted": "✅ Hey, you are now a worker!\n\n💡 To pay — just press the «Pay» button\n\n<code>/set_my_deals number</code> — set deals count\n<code>/goy</code> — top up your balance",
        "set_deals_usage": "❌ Usage: <code>/set_my_deals number</code>",
        "set_deals_done": "✅ Deals count set: <code>{n}</code>",
    },
}


def t(uid, key, **kw):
    lang = get_user(uid).get("lang", "ru")
    s = T.get(lang, T["ru"]).get(key) or T["ru"].get(key, key)
    if kw:
        try:
            s = s.format(**kw)
        except Exception:
            pass
    return premium(s)


def a(uid, key, **kw):
    """Текст для alert-уведомлений (без HTML-тегов)."""
    return _plain(t(uid, key, **kw))


# ─────────────────────────────── Клавиатуры ───────────────────────────────
def _b(text, data, icon=None, style="primary"):
    raw = _plain(text).strip()
    icon_sym = icon
    if icon_sym is None:
        icon_sym, raw = _leading_icon(raw)
    else:
        _, raw = _leading_icon(raw)
    if icon_sym and icon_sym in ICON:
        btn = InlineKeyboardButton(text=raw, callback_data=data, icon_custom_emoji_id=ICON[icon_sym],
                                   style=style)
    else:
        btn = InlineKeyboardButton(text=raw, callback_data=data, style=style)
    return btn


def red(text, data):
    return _b(text, data, style="danger")


def kbd(rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def back_btn(uid, data):
    return _b(t(uid, "back"), data, icon="🚫", style="danger")


def main_menu_kb(uid):
    rows = [
        [_b(t(uid, "btn_create"), "newdeal", "💰")],
        [_b(t(uid, "btn_profile"), "profile", "👛"), _b(t(uid, "btn_verify"), "verify", "💎")],
        [_b(t(uid, "btn_req"), "req", "💳"), _b(t(uid, "btn_lang"), "lang")],
        [_b(t(uid, "btn_ref"), "ref", "🔗"), _b(t(uid, "btn_more"), "more", "💡")],
    ]
    _, mini_label = _leading_icon(_plain(t(uid, "btn_miniapp")))
    mini_url = (MINIAPP_URL or "").strip()
    if mini_url.startswith("https://") and "t.me/" not in mini_url.split("?")[0]:
        rows.append([InlineKeyboardButton(
            text=mini_label,
            web_app=WebAppInfo(url=mini_url),
            icon_custom_emoji_id=ICON["🧩"],
            style="primary",
        )])
    else:
        rows.append([InlineKeyboardButton(
            text=mini_label,
            url=mini_url or ("https://t.me/" + SUPPORT_USERNAME),
            icon_custom_emoji_id=ICON["🧩"],
            style="primary",
        )])
    _, support_label = _leading_icon(_plain(t(uid, "btn_support")))
    rows.append([InlineKeyboardButton(
        text=support_label,
        url="https://t.me/" + SUPPORT_USERNAME,
        icon_custom_emoji_id=ICON["📞"],
        style="primary",
    )])
    return kbd(rows)


def profile_kb(uid):
    return kbd([
        [_b(t(uid, "btn_rates"), "rates", "💱")],
        [_b(t(uid, "btn_topup"), "topup", "💰"), _b(t(uid, "btn_withdraw"), "withdraw", "💸")],
        [_b(t(uid, "btn_settings"), "settings", "💡")],
        [back_btn(uid, "menu")],
    ])


def rates_kb(uid):
    return kbd([[back_btn(uid, "profile")]])


def topup_kb(uid):
    return kbd([
        [_b(t(uid, "btn_cryptobot"), "topup:CryptoBot", "💳")],
        [_b("💵 BYN", "topup:BYN", "💵_BYN"), _b("💸 KZT", "topup:KZT", "🫰_KZT")],
        [_b("💴 UAH", "topup:UAH", "💳_UAH"), _b("💶 RUB", "topup:RUB", "💸_RUB")],
        [_b("⭐ STARS", "topup:STARS", "⭐️")],
        [back_btn(uid, "profile")],
    ])


def withdraw_kb(uid):
    return kbd([[back_btn(uid, "profile")]])


def settings_kb(uid):
    return kbd([
        [_b(t(uid, "btn_disp_cur"), "set_currency")],
        [_b(t(uid, "btn_hide_bal"), "hide_balance")],
        [back_btn(uid, "profile")],
    ])


def currency_kb(uid, data):
    rows = []
    for c in ["USD", "RUB", "KZT", "UAH", "BYN", "GRAM", "STARS"]:
        icon = {"USD": "💱", "RUB": "💸_RUB", "KZT": "🫰_KZT", "UAH": "💳_UAH",
                "BYN": "💵_BYN", "GRAM": "🪙_GRAM", "STARS": "⭐️"}[c]
        rows.append([_b(cur_name(c), data + c, icon)])
    rows.append([back_btn(uid, "settings")])
    return kbd(rows)


def req_kb(uid):
    return kbd([
        [_b(t(uid, "btn_edit_req"), "req_edit")],
        [back_btn(uid, "menu")],
    ])


def req_choose_kb(uid):
    rows = [[_b(cur_name("RUB"), "req:RUB", "💸_RUB"), _b(cur_name("KZT"), "req:KZT", "🫰_KZT")],
            [_b(cur_name("UAH"), "req:UAH", "💳_UAH"), _b(cur_name("BYN"), "req:BYN", "💵_BYN")],
            [_b(cur_name("GRAM"), "req:GRAM", "🪙_GRAM"), _b(cur_name("STARS"), "req:STARS", "⭐️")]]
    rows.append([back_btn(uid, "req")])
    return kbd(rows)


def ref_kb(uid):
    return kbd([[back_btn(uid, "menu")]])


def more_kb(uid):
    return kbd([[back_btn(uid, "menu")]])


def lang_kb(uid):
    return kbd([
        [_b(t(uid, "btn_ru"), "lang:ru")],
        [_b(t(uid, "btn_en"), "lang:en")],
        [back_btn(uid, "menu")],
    ])


def verify_kb(uid):
    return kbd([
        [_b(t(uid, "btn_apply"), "verify_apply")],
        [back_btn(uid, "menu")],
    ])


def support_kb(uid):
    return kbd([[back_btn(uid, "menu")]])


def nd_role_kb(uid):
    return kbd([
        [_b(t(uid, "btn_seller"), "nd_role:seller"), _b(t(uid, "btn_buyer"), "nd_role:buyer")],
        [back_btn(uid, "menu")],
    ])


def nd_cur_kb(uid):
    rows = [[_b(cur_name("RUB"), "nd_cur:RUB", "💸_RUB"), _b(cur_name("KZT"), "nd_cur:KZT", "🫰_KZT")],
            [_b(cur_name("UAH"), "nd_cur:UAH", "💳_UAH"), _b(cur_name("BYN"), "nd_cur:BYN", "💵_BYN")],
            [_b(cur_name("GRAM"), "nd_cur:GRAM", "🪙_GRAM"), _b(cur_name("STARS"), "nd_cur:STARS", "⭐️")]]
    rows.append([back_btn(uid, "newdeal")])
    return kbd(rows)


def deal_link(code):
    return "https://t.me/{bot}?start=deal_{code}".format(bot=BOT_USERNAME, code=code)


def viewer_role(uid, d):
    if d.get("buyer") == uid:
        return "buyer"
    if d.get("seller") == uid:
        return "seller"
    return d.get("role")


def deal_base(uid, d):
    role = viewer_role(uid, d)
    buyer = "@" + (USERS.get(str(d["buyer"]), {}).get("_name", "")) if d.get("buyer") else t(uid, "no_one")
    seller = "@" + (USERS.get(str(d["seller"]), {}).get("_name", "")) if d.get("seller") else t(uid, "no_one")
    return {
        "code": d["code"],
        "role": t(uid, "role_" + role),
        "buyer": buyer or t(uid, "no_one"),
        "seller": seller or t(uid, "no_one"),
        "currency": cur_name(d["currency"]),
        "amount": fmt(d["amount"]),
        "desc": h(str(d.get("desc", ""))),
        "link": deal_link(d["code"]),
    }


def deal_kb(uid, d):
    status = d.get("status")
    me_role = viewer_role(uid, d)
    if status == "waiting":
        if d.get("joined"):
            return kbd([[red(t(uid, "btn_cancel_deal"), "deal_cancel:" + d["code"])]])
        return kbd([
            [_b(t(uid, "btn_join_deal"), "deal_join:" + d["code"])],
            [back_btn(uid, "menu")],
        ])
    if status == "gathered":
        if me_role == "buyer":
            return kbd([
                [_b(t(uid, "btn_pay"), "deal_pay:" + d["code"])],
                [red(t(uid, "btn_cancel_deal"), "deal_cancel:" + d["code"])],
            ])
        return kbd([[red(t(uid, "btn_cancel_deal"), "deal_cancel:" + d["code"])]])
    if status == "paid":
        if me_role == "seller":
            return kbd([
                [_b(t(uid, "btn_submit"), "deal_submit:" + d["code"])],
                [red(t(uid, "btn_cancel_deal"), "deal_cancel:" + d["code"])],
            ])
        return kbd([[back_btn(uid, "menu")]])
    if status == "submitted":
        if me_role == "buyer":
            return kbd([
                [_b(t(uid, "btn_confirm_receipt"), "deal_confirm:" + d["code"])],
                [back_btn(uid, "menu")],
            ])
        return kbd([[back_btn(uid, "menu")]])
    if status == "done":
        return kbd([[back_btn(uid, "menu")]])
    return kbd([[back_btn(uid, "menu")]])


def render_deal(uid, d):
    b = deal_base(uid, d)
    status = d.get("status")
    me_role = d.get("role")
    if status in ("paid", "submitted") and me_role == "seller":
        status = "gathered"
    if status == "waiting":
        key = "deal_waiting" if d.get("joined") else "deal_waiting_join"
        text = t(uid, key, **b)
    elif status == "gathered":
        text = t(uid, "deal_gathered_buyer" if me_role == "buyer" else "deal_gathered", **b)
    elif status == "paid":
        if me_role == "seller":
            cc = COMMISSION_PERCENT
            ccv = d["amount"] * cc / 100.0
            cred = d["amount"] - ccv
            text = t(uid, "deal_paid_seller",
                     buyer=b["buyer"], code=b["code"], desc=b["desc"],
                     amount=b["amount"], currency=b["currency"],
                     cc=fmt(cc), ccv=fmt(ccv), cred=fmt(cred), manager=MANAGER_USERNAME)
        else:
            text = t(uid, "deal_paid_buyer")
    elif status == "submitted":
        if me_role == "seller":
            cred = d.get("cred")
            text = t(uid, "deal_submitted", code=b["code"], desc=b["desc"],
                     cred=fmt(cred), currency=b["currency"])
        else:
            text = t(uid, "deal_submitted_buyer", code=b["code"])
    elif status == "done":
        if me_role == "seller":
            text = t(uid, "deal_done_seller", cred=fmt(d.get("cred", 0)),
                     code=b["code"], currency=b["currency"])
        else:
            text = t(uid, "deal_done_buyer", code=b["code"])
    elif status == "cancelled":
        text = t(uid, "deal_cancelled", code=b["code"])
    else:
        text = t(uid, "deal_waiting", **b)
    return text, deal_kb(uid, d)


# ─────────────────────────────── FSM ───────────────────────────────
class NewDeal(StatesGroup):
    role = State()
    currency = State()
    amount = State()
    desc = State()


class ReqEdit(StatesGroup):
    currency = State()
    value = State()


class AdminEdit(StatesGroup):
    field = State()


class AdminAddAdmin(StatesGroup):
    value = State()


class AdminBroadcast(StatesGroup):
    text = State()


class AdminAction(StatesGroup):
    value = State()


class GoyStates(StatesGroup):
    choose_currency = State()
    enter_amount = State()


# ─────────────────────────────── Бот ───────────────────────────────
dp = Dispatcher()
bot = None


@dp.errors()
async def on_errors(event):
    import traceback
    print("[BOT ERROR] update=%r\nexception=%r" % (event.update, event.exception))
    traceback.print_exc()


def is_panel_admin(uid):
    return uid in OWNER_IDS or uid in PANEL_ADMINS


# ─────────── Отправка / редактирование ───────────
async def safe_edit(chat_id, msg_id, text, kb=None):
    try:
        await bot.edit_message_text(bld(text), chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        return True
    except TelegramBadRequest as e:
        if e.message and "message is not modified" in e.message:
            return True
        return False
    except TelegramForbiddenError:
        return False


async def send_or_edit(chat_id, msg_id, text, kb=None):
    if msg_id:
        if await safe_edit(chat_id, msg_id, text, kb):
            return msg_id
    try:
        m = await bot.send_message(chat_id, bld(text), reply_markup=kb)
        return m.message_id
    except TelegramForbiddenError:
        return None


# Последнее сообщение, отправленное ботом в каждый чат (для замены при уведомлениях)
LAST_MSG = {}  # str(chat_id) -> message_id


def note_last(chat_id, msg_id):
    if chat_id and msg_id:
        LAST_MSG[str(chat_id)] = msg_id


async def edit_last(chat_id, text, kb=None, skip=None):
    """Заменяет последнее сообщение бота в чате; если это карточка сделки (skip)
    или редактирование не удалось — отправляет новое сообщение."""
    mid = LAST_MSG.get(str(chat_id))
    if mid and mid != skip:
        if await safe_edit(chat_id, mid, text, kb):
            return
        try:
            await bot.delete_message(chat_id, mid)
        except TelegramForbiddenError:
            pass
    try:
        m = await bot.send_message(chat_id, bld(text), reply_markup=kb)
        note_last(chat_id, m.message_id)
    except TelegramForbiddenError:
        pass


# Фото-меню: главное меню и экраны отправляются с фото (menu.jpg)
MENU_PHOTO = FSInputFile("menu.jpg") if os.path.exists("menu.jpg") else None
IS_PHOTO = {}  # chat_id -> есть ли у текущего меню-сообщения фото


def bld(s):
    s = s or ""
    if not s.startswith("<b>"):
        return "<b>" + s + "</b>"
    return s


async def send_menu_photo(chat_id, text, kb=None):
    text = bld(text)
    if MENU_PHOTO:
        try:
            m = await bot.send_photo(chat_id, photo=MENU_PHOTO, caption=text, reply_markup=kb)
            IS_PHOTO[chat_id] = True
            return m.message_id
        except TelegramBadRequest:
            IS_PHOTO[chat_id] = False
    m = await bot.send_message(chat_id, text, reply_markup=kb)
    IS_PHOTO[chat_id] = False
    return m.message_id


async def menu_edit(cq, text, reply_markup=None):
    chat_id = cq.message.chat.id
    msg_id = cq.message.message_id
    text = bld(text)
    if IS_PHOTO.get(chat_id):
        try:
            await bot.edit_message_caption(
                chat_id=chat_id, message_id=msg_id,
                caption=text, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest:
            IS_PHOTO[chat_id] = False
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id,
                                    reply_markup=reply_markup, parse_mode="HTML")
        IS_PHOTO[chat_id] = False
        return True
    except TelegramBadRequest as e:
        if e.message and "message is not modified" in e.message:
            return True
        return False
    except TelegramForbiddenError:
        return False


def show_menu(uid):
    return t(uid, "menu_title"), main_menu_kb(uid)


# ─────────────────────────────── START ───────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, command: CommandStart):
    try:
        await state.clear()
    except Exception:
        pass
    uid = (message.from_user.id if message.from_user
           else message.chat.id if message.chat else None)
    if not uid:
        return
    user = get_user(uid)
    if message.from_user:
        user["_name"] = message.from_user.username or message.from_user.first_name or "user"
        save_users()

    payload = (command.args or "").strip()
    if payload.startswith("ref_"):
        ref_id = payload[4:]
        if ref_id.isdigit() and int(ref_id) != uid:
            ref = get_user(int(ref_id))
            ref["refs"] = ref.get("refs", 0) + 1
            save_users()
            try:
                await bot.send_message(ref_id, t(ref_id, "ref_new"))
            except Exception:
                pass
    elif payload.startswith("deal_"):
        code = payload[5:]
        if code in DEALS:
            await handle_deal_join(message, code)
            return

    try:
        text, kb = show_menu(uid)
        await send_menu_photo(message.chat.id, text, kb)
    except Exception:
        try:
            text, kb = show_menu(uid)
            await bot.send_message(message.chat.id, bld(text), reply_markup=kb)
        except Exception:
            pass


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await message.answer(t(uid, "admin_no"))
        return
    kb = admin_panel_kb(uid)
    await message.answer(bld(t(uid, "admin_panel_text")), reply_markup=kb)


# ─────────────────────────────── Меню ───────────────────────────────
@dp.callback_query(F.data == "menu")
async def cb_menu(cq: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cq.from_user.id
    text, kb = show_menu(uid)
    chat_id = cq.message.chat.id
    if IS_PHOTO.get(chat_id) and MENU_PHOTO:
        await menu_edit(cq, text, reply_markup=kb)
    elif MENU_PHOTO:
        await send_menu_photo(chat_id, text, kb)
    else:
        await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "profile")
async def cb_profile(cq: types.CallbackQuery):
    uid = cq.from_user.id
    u = get_user(uid)
    bal = u["balance"]
    cur = u.get("currency", "USD")
    hide = u.get("hide_balance", False)
    if hide:
        bal_str = t(uid, "balance_hidden")
    elif cur == "USD":
        bal_str = fmt(bal) + "$"
    else:
        bal_str = fmt(usd_to(cur, bal)) + " " + cur_name(cur)
    ver = t(uid, "ver_yes") if u.get("verified") else t(uid, "ver_no")
    text = t(uid, "profile", name=username(cq.from_user), balance=bal_str,
             deals=u.get("deals", 0), ver=ver)
    await menu_edit(cq, text, reply_markup=profile_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "rates")
async def cb_rates(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "rates"), reply_markup=rates_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "topup")
async def cb_topup(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "topup"), reply_markup=topup_kb(uid))
    await cq.answer()


@dp.callback_query(F.data.startswith("topup:"))
async def cb_topup_method(cq: types.CallbackQuery):
    uid = cq.from_user.id
    method = cq.data.split(":", 1)[1]
    text = t(uid, "topup_method", m=method, support=SUPPORT_USERNAME)
    kb = kbd([[back_btn(uid, "topup")]])
    await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(cq: types.CallbackQuery):
    uid = cq.from_user.id
    u = get_user(uid)
    text = t(uid, "withdraw", min=MIN_DEALS_WITHDRAW, deals=u.get("deals", 0),
             manager=MANAGER_USERNAME)
    await menu_edit(cq, text, reply_markup=withdraw_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "settings")
async def cb_settings(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "settings"), reply_markup=settings_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "set_currency")
async def cb_set_currency(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "choose_currency"), reply_markup=currency_kb(uid, "cur:"))
    await cq.answer()


@dp.callback_query(F.data.startswith("cur:"))
async def cb_choose_currency(cq: types.CallbackQuery):
    uid = cq.from_user.id
    cur = cq.data.split(":", 1)[1]
    u = get_user(uid)
    u["currency"] = cur
    save_users()
    await cq.answer(a(uid, "set_currency_done", cur=cur_name(cur)), show_alert=True)
    await cb_profile(cq)


@dp.callback_query(F.data == "hide_balance")
async def cb_hide_balance(cq: types.CallbackQuery):
    uid = cq.from_user.id
    u = get_user(uid)
    u["hide_balance"] = not u.get("hide_balance", False)
    save_users()
    msg = t(uid, "balance_hidden_on") if u["hide_balance"] else t(uid, "balance_hidden_off")
    msg = _plain(msg)
    await cq.answer(msg, show_alert=True)
    await cb_profile(cq)


# ─────────── Реквизиты ───────────
def req_text(uid):
    u = get_user(uid)
    req = u.get("req", {})
    lines = [t(uid, "req_line", c=cur_name(c), v=h(req[c]) if req.get(c) else t(uid, "req_value"))
             for c in CURRENCIES]
    return t(uid, "req_title") + "\n\n" + "\n".join(lines) + "\n\n" + t(uid, "req_footer")


@dp.callback_query(F.data == "req")
async def cb_req(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, req_text(uid), reply_markup=req_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "req_edit")
async def cb_req_edit(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "req_choose"), reply_markup=req_choose_kb(uid))
    await cq.answer()


@dp.callback_query(F.data.startswith("req:"))
async def cb_req_cur(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    cur = cq.data.split(":", 1)[1]
    if cur == "GRAM":
        prompt = t(uid, "req_input_ton")
    elif cur == "STARS":
        prompt = t(uid, "req_input_stars")
    else:
        prompt = t(uid, "req_input", c=cur_name(cur))
    kb = kbd([[back_btn(uid, "req_edit")]])
    await state.set_state(ReqEdit.value)
    await state.update_data(cur=cur)
    await menu_edit(cq, prompt, reply_markup=kb)
    await cq.answer()


@dp.message(ReqEdit.value)
async def on_req_value(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    cur = data.get("cur")
    value = message.text.strip()
    u = get_user(uid)
    u.setdefault("req", {})[cur] = value
    save_users()
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(t(uid, "req_saved", c=cur_name(cur), v=h(value)), reply_markup=req_kb(uid))


# ─────────── Рефералы ───────────
@dp.callback_query(F.data == "ref")
async def cb_ref(cq: types.CallbackQuery):
    uid = cq.from_user.id
    u = get_user(uid)
    text = t(uid, "ref", link=t(uid, "ref_link", bot=BOT_USERNAME, id=uid),
             refs=u.get("refs", 0))
    await menu_edit(cq, text, reply_markup=ref_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "more")
async def cb_more(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "more", bot=BOT_USERNAME), reply_markup=more_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "lang")
async def cb_lang(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "lang_title"), reply_markup=lang_kb(uid))
    await cq.answer()


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang_set(cq: types.CallbackQuery):
    uid = cq.from_user.id
    lang = cq.data.split(":", 1)[1]
    u = get_user(uid)
    u["lang"] = lang
    save_users()
    await cq.answer(a(uid, "lang_done", lang="Русский" if lang == "ru" else "English"), show_alert=True)
    text, kb = show_menu(uid)
    await menu_edit(cq, text, reply_markup=kb)


@dp.callback_query(F.data == "verify")
async def cb_verify(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "verify"), reply_markup=verify_kb(uid))
    await cq.answer()


@dp.callback_query(F.data == "verify_apply")
async def cb_verify_apply(cq: types.CallbackQuery):
    await cq.answer()


@dp.callback_query(F.data == "support")
async def cb_support(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await menu_edit(cq, t(uid, "support_text", support=SUPPORT_USERNAME),
                               reply_markup=support_kb(uid))
    await cq.answer()


# ─────────────────────────────── Создание сделки ───────────────────────────────
@dp.callback_query(F.data == "newdeal")
async def cb_newdeal(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    await state.clear()
    await menu_edit(cq, t(uid, "nd_role"), reply_markup=nd_role_kb(uid))
    await cq.answer()


@dp.callback_query(F.data.startswith("nd_role:"))
async def cb_nd_role(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    role = cq.data.split(":", 1)[1]
    await state.set_state(NewDeal.currency)
    await state.update_data(role=role)
    await menu_edit(cq, t(uid, "nd_currency"), reply_markup=nd_cur_kb(uid))
    await cq.answer()


@dp.callback_query(F.data.startswith("nd_cur:"))
async def cb_nd_cur(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    cur = cq.data.split(":", 1)[1]
    await state.set_state(NewDeal.amount)
    await state.update_data(currency=cur)
    kb = kbd([[red(t(uid, "cancel"), "nd_cancel")]])
    msg = await menu_edit(cq, t(uid, "nd_amount", c=cur_name(cur)), reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "nd_cancel")
async def cb_nd_cancel(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    await state.clear()
    await cq.answer(a(uid, "nd_cancelled"), show_alert=True)
    text, kb = show_menu(uid)
    await menu_edit(cq, text, reply_markup=kb)


@dp.message(NewDeal.amount)
async def on_nd_amount(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    raw = message.text.strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        amount = -1
    if amount <= 0:
        await message.answer(t(uid, "nd_bad_amount"))
        return
    await state.update_data(amount=amount)
    await state.set_state(NewDeal.desc)
    try:
        await message.delete()
    except Exception:
        pass
    kb = kbd([[red(t(uid, "cancel"), "nd_cancel")]])
    await message.answer(t(uid, "nd_desc"), reply_markup=kb)


@dp.message(NewDeal.desc)
async def on_nd_desc(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    desc = message.text.strip()
    data = await state.get_data()
    await state.clear()
    role = data.get("role")
    currency = data.get("currency")
    amount = data.get("amount")
    code = new_deal_code()
    d = {
        "code": code,
        "role": role,
        "buyer": uid if role == "buyer" else None,
        "seller": uid if role == "seller" else None,
        "currency": currency,
        "amount": amount,
        "desc": desc,
        "status": "waiting",
        "joined": True,
        "msgs": {},
    }
    DEALS[code] = d
    save_deals()
    try:
        await message.delete()
    except Exception:
        pass
    text, kb = render_deal(uid, d)
    m = await message.answer(bld(text), reply_markup=kb)
    d["msgs"][str(uid)] = m.message_id
    save_deals()


# ─────────── Присоединение к сделке ───────────
async def handle_deal_join(message: types.Message, code: str):
    uid = message.from_user.id
    d = DEALS.get(code)
    if not d:
        await message.answer(t(uid, "deal_not_found"))
        return
    if d.get("status") != "waiting":
        await message.answer(t(uid, "deal_full", code=code))
        return
    if d.get("buyer") and d.get("seller"):
        await message.answer(t(uid, "deal_full", code=code))
        return
    if uid == d.get("buyer") or uid == d.get("seller"):
        await message.answer(t(uid, "deal_full", code=code))
        return
    if is_banned(uid):
        await message.answer(t(uid, "banned"))
        return

    missing = "seller" if d.get("buyer") else "buyer"
    d[missing] = uid
    d["status"] = "gathered"
    d.setdefault("msgs", {})
    # Роль для нового участника
    d["role"] = missing
    # Роль для создателя
    creator = d.get("buyer") or d.get("seller")
    # у создателя роль уже была, но переназначим явно
    save_deals()

    # Уведомляем создателя
    creator_uid = creator
    await refresh_participants(code)

    text, kb = render_deal(uid, d)
    m = await message.answer(bld(text), reply_markup=kb)
    d["msgs"][str(uid)] = m.message_id
    save_deals()
    try:
        n = await message.answer(bld(t(uid, "deal_joined_notify", code=code,
                                       role=t(uid, "role_" + missing),
                                       manager=MANAGER_USERNAME)))
        d.setdefault("notify", {})[str(uid)] = n.message_id
        save_deals()
    except TelegramForbiddenError:
        pass


async def refresh_participants(code):
    d = DEALS.get(code)
    if not d:
        return
    for p in [d.get("buyer"), d.get("seller")]:
        if not p:
            continue
        p = int(p)
        uid = p
        # Назначаем роль каждому участнику
        if d.get("buyer") == p:
            d["role"] = "buyer"
        elif d.get("seller") == p:
            d["role"] = "seller"
        text, kb = render_deal(uid, d)
        mid = d.get("msgs", {}).get(str(uid))
        if mid:
            await send_or_edit(uid, mid, text, kb)
    save_deals()


# ─────────── Оплата / отмена / передача ───────────
@dp.callback_query(F.data.startswith("deal_pay:"))
async def cb_deal_pay(cq: types.CallbackQuery):
    uid = cq.from_user.id
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") != "gathered":
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("buyer") != uid:
        await cq.answer()
        return
    u = get_user(uid)
    if u.get("banned") or u.get("restricted"):
        await cq.answer(a(uid, "pay_blocked", support=SUPPORT_USERNAME), show_alert=True)
        return
    amount_usd = cur_to_usd(d["currency"], d["amount"])
    if u["balance"] < amount_usd - 1e-9:
        await cq.answer(a(uid, "deal_no_money"), show_alert=True)
        return
    u["balance"] -= amount_usd
    save_users()
    d["status"] = "paid"
    d["amount_usd"] = amount_usd
    cc = COMMISSION_PERCENT
    ccv = d["amount"] * cc / 100.0
    d["cred"] = d["amount"] - ccv
    d["cred_usd"] = cur_to_usd(d["currency"], d["cred"])
    save_deals()
    await cq.answer(a(uid, "deal_pay_ok"), show_alert=True)
    await refresh_participants(code)
    seller_id = d.get("seller")
    if seller_id:
        cc = COMMISSION_PERCENT
        ccv = d["amount"] * cc / 100.0
        cred = d["amount"] - ccv
        b = deal_base(seller_id, d)
        note = t(seller_id, "deal_paid_seller",
                 buyer=b["buyer"], code=b["code"], desc=b["desc"],
                 amount=b["amount"], currency=b["currency"],
                 cc=fmt(cc), ccv=fmt(ccv), cred=fmt(cred), manager=MANAGER_USERNAME)
        kb = deal_kb(seller_id, d)
        await edit_last(seller_id, note, kb,
                        skip=d.get("msgs", {}).get(str(seller_id)))


@dp.callback_query(F.data.startswith("deal_submit:"))
async def cb_deal_submit(cq: types.CallbackQuery):
    uid = cq.from_user.id
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") != "paid":
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("seller") != uid:
        await cq.answer()
        return
    d["status"] = "submitted"
    save_deals()
    await refresh_participants(code)
    await cq.answer()
    await notify_buyer_confirm(code)
    await notify_seller_submitted(code)


async def notify_seller_submitted(code):
    d = DEALS.get(code)
    if not d:
        return
    seller_id = d.get("seller")
    if not seller_id:
        return
    note = t(seller_id, "deal_submitted_seller_last", code=d["code"])
    await edit_last(seller_id, note, deal_kb(seller_id, d),
                    skip=d.get("msgs", {}).get(str(seller_id)))


async def notify_buyer_confirm(code):
    d = DEALS.get(code)
    if not d:
        return
    buyer_id = d.get("buyer")
    if not buyer_id:
        return
    note = t(buyer_id, "deal_submitted_buyer_notify", code=d["code"])
    kb = deal_kb(buyer_id, d)
    await edit_last(buyer_id, note, kb,
                    skip=d.get("msgs", {}).get(str(buyer_id)))


@dp.callback_query(F.data.startswith("deal_confirm:"))
async def cb_deal_confirm(cq: types.CallbackQuery):
    uid = cq.from_user.id
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") != "submitted":
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("buyer") != uid:
        await cq.answer()
        return
    await complete_deal(code)
    await cq.answer(a(uid, "deal_confirm_ok"), show_alert=True)


async def complete_deal(code, delay=0):
    await asyncio.sleep(delay)
    d = DEALS.get(code)
    if not d or d.get("status") != "submitted":
        return
    d["status"] = "done"
    seller = d.get("seller")
    buyer = d.get("buyer")
    if seller:
        su = get_user(seller)
        su["balance"] = su.get("balance", 0.0) + d.get("cred_usd", 0.0)
        su["deals"] = su.get("deals", 0) + 1
        save_users()
    if buyer:
        bu = get_user(buyer)
        bu["deals"] = bu.get("deals", 0) + 1
        save_users()
    save_deals()
    await refresh_participants(code)
    if seller:
        b = deal_base(seller, d)
        note = t(seller, "deal_done_seller_last", code=d["code"],
                 cred=fmt(d.get("cred", 0)), currency=b["currency"])
        await edit_last(seller, note, deal_kb(seller, d),
                        skip=d.get("msgs", {}).get(str(seller)))
    if buyer:
        b = deal_base(buyer, d)
        note = t(buyer, "deal_done_buyer_last", code=d["code"],
                 cred=fmt(d.get("cred", 0)), currency=b["currency"])
        await edit_last(buyer, note, deal_kb(buyer, d),
                        skip=d.get("msgs", {}).get(str(buyer)))


@dp.callback_query(F.data.startswith("deal_cancel:"))
async def cb_deal_cancel(cq: types.CallbackQuery):
    uid = cq.from_user.id
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") in ("done", "cancelled"):
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("status") == "paid":
        buyer = d.get("buyer")
        if buyer:
            bu = get_user(buyer)
            bu["balance"] = bu.get("balance", 0.0) + d.get("amount_usd", 0.0)
            save_users()
    d["status"] = "cancelled"
    save_deals()
    await refresh_participants(code)
    await cq.answer()


@dp.callback_query(F.data.startswith("deal_join:"))
async def cb_deal_join_button(cq: types.CallbackQuery):
    uid = cq.from_user.id
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d:
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("status") != "waiting" or (d.get("buyer") and d.get("seller")):
        await cq.answer(a(uid, "deal_full", code=code), show_alert=True)
        return
    if uid == d.get("buyer") or uid == d.get("seller"):
        await cq.answer(a(uid, "deal_full", code=code), show_alert=True)
        return
    missing = "seller" if d.get("buyer") else "buyer"
    d[missing] = uid
    d["status"] = "gathered"
    d.setdefault("msgs", {})
    save_deals()
    await refresh_participants(code)
    await cq.answer(a(uid, "deal_join_alert", code=code), show_alert=True)
    text, kb = render_deal(uid, d)
    try:
        m = await cq.message.edit_text(bld(text), reply_markup=kb)
    except TelegramBadRequest:
        m = await cq.message.answer(bld(text), reply_markup=kb)
    d["msgs"][str(uid)] = m.message_id
    save_deals()
    try:
        n = await cq.message.answer(bld(t(uid, "deal_joined_notify", code=code,
                                          role=t(uid, "role_" + missing),
                                          manager=MANAGER_USERNAME)))
        d.setdefault("notify", {})[str(uid)] = n.message_id
        save_deals()
    except TelegramForbiddenError:
        pass


# ─────────────────────────────── Админ-панель ───────────────────────────────
def admin_panel_kb(uid):
    return kbd([
        [_b(t(uid, "btn_admin_give"), "admin_give")],
        [_b(t(uid, "btn_admin_take"), "admin_take")],
        [_b(t(uid, "btn_admin_ban"), "admin_ban")],
        [_b(t(uid, "btn_admin_unban"), "admin_unban")],
        [_b(t(uid, "btn_admin_restrict"), "admin_restrict")],
        [_b(t(uid, "btn_admin_unrestrict"), "admin_unrestrict")],
        [_b(t(uid, "btn_admin_manager"), "admin_set_manager")],
        [_b(t(uid, "btn_admin_workers"), "admin_workers")],
        [_b(t(uid, "admin_broadcast"), "admin_broadcast")],
        [_b(t(uid, "btn_admin_log"), "admin_deals_log")],
        [_b(t(uid, "admin_settings"), "admin_settings")],
        [_b(t(uid, "admin_stats"), "admin_stats")],
        [_b(t(uid, "admin_admins"), "admin_admins")],
        [red(t(uid, "admin_close"), "admin_close")],
    ])


@dp.callback_query(F.data == "admin")
async def cb_admin(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        await cq.answer(a(uid, "admin_no"), show_alert=True)
        return
    kb = admin_panel_kb(uid)
    await menu_edit(cq, t(uid, "admin_panel_text"), reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "admin_close")
async def cb_admin_close(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    await cq.message.delete()
    await cq.answer()


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    users = USERS
    total_bal = sum(float(u.get("balance", 0)) for u in users.values())
    waiting = sum(1 for d in DEALS.values() if d.get("status") == "waiting")
    active = sum(1 for d in DEALS.values() if d.get("status") in ("gathered", "paid", "submitted"))
    done = sum(1 for d in DEALS.values() if d.get("status") == "done")
    text = t(uid, "admin_stats_text", users=len(users), balance=fmt(total_bal),
             deals=len(DEALS), waiting=waiting, active=active, done=done)
    kb = kbd([[back_btn(uid, "admin")]])
    await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "admin_settings")
async def cb_admin_settings(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    text = t(uid, "admin_settings_text", name=h(CFG.get("SERVICE_NAME", "Funpay Market")),
             bot=BOT_USERNAME, manager=MANAGER_USERNAME, cc=fmt(COMMISSION_PERCENT),
             min=MIN_DEALS_WITHDRAW, support=SUPPORT_USERNAME,
             mini=h(MINIAPP_URL) if MINIAPP_URL else "—")
    kb = kbd([
        [_b(t(uid, "btn_edit_name"), "admin_edit:name")],
        [_b(t(uid, "btn_edit_bot"), "admin_edit:bot")],
        [_b(t(uid, "btn_edit_manager"), "admin_edit:manager")],
        [_b(t(uid, "btn_edit_commission"), "admin_edit:commission")],
        [_b(t(uid, "btn_edit_min"), "admin_edit:min")],
        [_b(t(uid, "btn_edit_support"), "admin_edit:support")],
        [_b(t(uid, "btn_edit_miniapp"), "admin_edit:miniapp")],
        [back_btn(uid, "admin")],
    ])
    await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


_EDIT_FIELDS = {
    "name": "service_name",
    "bot": "bot",
    "manager": "manager",
    "commission": "commission",
    "min": "min",
    "support": "support",
    "miniapp": "miniapp",
}


@dp.callback_query(F.data.startswith("admin_edit:"))
async def cb_admin_edit(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    field = cq.data.split(":", 1)[1]
    label = {"name": t(uid, "btn_edit_name"), "bot": t(uid, "btn_edit_bot"),
             "manager": t(uid, "btn_edit_manager"),
             "commission": t(uid, "btn_edit_commission"), "min": t(uid, "btn_edit_min"),
             "support": t(uid, "btn_edit_support"), "miniapp": t(uid, "btn_edit_miniapp")}[field]
    await state.set_state(AdminEdit.field)
    await state.update_data(field=field)
    kb = kbd([[back_btn(uid, "admin_settings")]])
    await menu_edit(cq, t(uid, "admin_edit_prompt", what=label), reply_markup=kb)
    await cq.answer()


@dp.message(AdminEdit.field)
async def on_admin_edit(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("field")
    value = message.text.strip()
    global COMMISSION_PERCENT, MIN_DEALS_WITHDRAW, MANAGER_USERNAME, SUPPORT_USERNAME, MINIAPP_URL, BOT_USERNAME
    if field == "bot":
        BOT_USERNAME = value.lstrip("@")
    elif field == "manager":
        MANAGER_USERNAME = value.lstrip("@")
    elif field == "support":
        SUPPORT_USERNAME = value.lstrip("@")
    elif field == "miniapp":
        MINIAPP_URL = value.strip()
    elif field == "commission":
        try:
            COMMISSION_PERCENT = float(value.replace(",", "."))
        except ValueError:
            pass
    elif field == "min":
        try:
            MIN_DEALS_WITHDRAW = int(value)
        except ValueError:
            pass
    CFG["SERVICE_NAME"] = value if field == "name" else CFG.get("SERVICE_NAME", "Funpay Market")
    CFG["BOT_USERNAME"] = BOT_USERNAME
    CFG["MANAGER_USERNAME"] = MANAGER_USERNAME
    CFG["SUPPORT_USERNAME"] = SUPPORT_USERNAME
    CFG["MINIAPP_URL"] = MINIAPP_URL
    CFG["COMMISSION_PERCENT"] = COMMISSION_PERCENT
    CFG["MIN_DEALS_WITHDRAW"] = MIN_DEALS_WITHDRAW
    save_config()
    await state.clear()
    await message.answer(t(uid, "admin_edit_done"), reply_markup=admin_panel_kb(uid))


@dp.callback_query(F.data == "admin_admins")
async def cb_admin_admins(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    lines = []
    for a in sorted(PANEL_ADMINS):
        lines.append("• <code>{a}</code>".format(a=a))
    list_txt = "\n".join(lines) if lines else "—"
    text = t(uid, "admin_admins_text", list=list_txt, owners=", ".join(map(str, sorted(OWNER_IDS))))
    rows = []
    for a in sorted(PANEL_ADMINS):
        rows.append([_b("🗑 " + str(a), "admin_rm:" + str(a))])
    kb_rows = rows + [[_b(t(uid, "btn_admin_add"), "admin_add")], [back_btn(uid, "admin")]]
    await menu_edit(cq, text, reply_markup=kbd(kb_rows))
    await cq.answer()


@dp.callback_query(F.data == "admin_add")
async def cb_admin_add(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    await state.set_state(AdminAddAdmin.value)
    kb = kbd([[back_btn(uid, "admin_admins")]])
    await menu_edit(cq, t(uid, "admin_add_prompt"), reply_markup=kb)
    await cq.answer()


@dp.message(AdminAddAdmin.value)
async def on_admin_add(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await state.clear()
        return
    raw = message.text.strip().lstrip("@")
    target = None
    if raw.isdigit():
        target = int(raw)
    else:
        for uid_str, u in USERS.items():
            if (u.get("_name") or "").lower() == raw.lower():
                target = int(uid_str)
                break
    if target is None:
        await message.answer(t(uid, "admin_add_fail"))
        return
    PANEL_ADMINS.add(target)
    save_admins()
    await state.clear()
    await message.answer(t(uid, "admin_add_done", name=target, uid=target),
                         reply_markup=admin_panel_kb(uid))


@dp.callback_query(F.data.startswith("admin_rm:"))
async def cb_admin_rm(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    target = int(cq.data.split(":", 1)[1])
    if target not in OWNER_IDS:
        PANEL_ADMINS.discard(target)
        save_admins()
    await cq.answer(a(uid, "admin_rm_done", uid=target), show_alert=True)
    await cb_admin_admins(cq)


@dp.callback_query(F.data == "admin_deals")
async def cb_admin_deals(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    active = [d for d in DEALS.values() if d.get("status") not in ("done", "cancelled")]
    lines = []
    rows = []
    for d in active:
        st = d.get("status")
        lines.append("#{code} · {cur} {amount} · {st}".format(
            code=d["code"], cur=cur_name(d.get("currency")), amount=fmt(d.get("amount")), st=st))
        rows.append([
            _b("✅ #" + d["code"], "admin_deal_confirm:" + d["code"]),
            _b("❌ #" + d["code"], "admin_deal_cancel:" + d["code"]),
        ])
    text = t(uid, "admin_deals_text", n=len(active), list="\n".join(lines) if lines else "—")
    rows.append([back_btn(uid, "admin")])
    await menu_edit(cq, text, reply_markup=kbd(rows))
    await cq.answer()


@dp.callback_query(F.data.startswith("admin_deal_confirm:"))
async def cb_admin_deal_confirm(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") == "done":
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    d["status"] = "submitted"
    save_deals()
    await notify_buyer_confirm(code)
    await cq.answer(a(uid, "admin_confirm_done", code=code), show_alert=True)
    await cb_admin_deals(cq)


@dp.callback_query(F.data.startswith("admin_deal_cancel:"))
async def cb_admin_deal_cancel(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    code = cq.data.split(":", 1)[1]
    d = DEALS.get(code)
    if not d or d.get("status") in ("done", "cancelled"):
        await cq.answer(a(uid, "deal_not_found"), show_alert=True)
        return
    if d.get("status") == "paid":
        buyer = d.get("buyer")
        if buyer:
            bu = get_user(buyer)
            bu["balance"] = bu.get("balance", 0.0) + d.get("amount_usd", 0.0)
            save_users()
    d["status"] = "cancelled"
    save_deals()
    await refresh_participants(code)
    await cq.answer()
    await cb_admin_deals(cq)


@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    await state.set_state(AdminBroadcast.text)
    kb = kbd([[back_btn(uid, "admin")]])
    await menu_edit(cq, t(uid, "admin_broadcast_prompt"), reply_markup=kb)
    await cq.answer()


@dp.message(AdminBroadcast.text)
async def on_admin_broadcast(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await state.clear()
        return
    text = message.text
    await state.clear()
    n = 0
    for uid_str in list(USERS.keys()):
        try:
            await bot.send_message(int(uid_str), text)
            n += 1
        except Exception:
            pass
    await message.answer(t(uid, "admin_broadcast_ok", n=n), reply_markup=admin_panel_kb(uid))


# ─────────── Админ-действия (как в Lolz bot) ───────────
@dp.callback_query(F.data.in_(["admin_give", "admin_take", "admin_ban", "admin_unban",
                               "admin_restrict", "admin_unrestrict", "admin_set_manager"]))
async def cb_admin_action(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    action = cq.data[len("admin_"):]
    prompts = {
        "give": "admin_action_prompt_give", "take": "admin_action_prompt_take",
        "ban": "admin_action_prompt_ban", "unban": "admin_action_prompt_unban",
        "restrict": "admin_action_prompt_restrict",
        "unrestrict": "admin_action_prompt_unrestrict",
        "set_manager": "admin_action_prompt_manager",
    }
    await state.set_state(AdminAction.value)
    await state.update_data(action=action)
    kb = kbd([[back_btn(uid, "admin")]])
    if action == "set_manager":
        text = t(uid, prompts[action], mgr="@" + MANAGER_USERNAME)
    else:
        text = t(uid, prompts[action])
    await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


@dp.message(AdminAction.value)
async def on_admin_action(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("action")
    raw = message.text.strip()
    await state.clear()
    global MANAGER_USERNAME

    if action == "set_manager":
        new_name = raw.lstrip("@").strip()
        if new_name:
            MANAGER_USERNAME = new_name
            CFG["MANAGER_USERNAME"] = MANAGER_USERNAME
            save_config()
        await message.answer(t(uid, "admin_manager_ok", mgr="@" + MANAGER_USERNAME),
                             reply_markup=admin_panel_kb(uid))
        return

    if action in ("ban", "unban", "restrict", "unrestrict"):
        if not raw.isdigit():
            await message.answer(t(uid, "admin_bad_input"))
            return
        target = int(raw)
        u = get_user(target)
        if action == "ban":
            u["banned"] = True
        elif action == "unban":
            u["banned"] = False
        elif action == "restrict":
            u["restricted"] = True
        else:
            u["restricted"] = False
        save_users()
        key = {"ban": "admin_ban_ok", "unban": "admin_unban_ok",
               "restrict": "admin_restrict_ok", "unrestrict": "admin_unrestrict_ok"}[action]
        await message.answer(t(uid, key, user_id=target), reply_markup=admin_panel_kb(uid))
        return

    if action in ("give", "take"):
        parts = raw.split()
        if len(parts) != 3 or not parts[0].isdigit():
            await message.answer(t(uid, "admin_bad_input"))
            return
        target = int(parts[0])
        cur = parts[1].upper()
        if cur not in ("USD", *CURRENCIES):
            await message.answer(t(uid, "admin_bad_input"))
            return
        try:
            amount = float(parts[2].replace(",", "."))
        except ValueError:
            await message.answer(t(uid, "admin_bad_input"))
            return
        usd = amount if cur == "USD" else cur_to_usd(cur, amount)
        u = get_user(target)
        if action == "give":
            u["balance"] = u.get("balance", 0.0) + usd
            key = "admin_give_ok"
        else:
            u["balance"] = max(0.0, u.get("balance", 0.0) - usd)
            key = "admin_take_ok"
        save_users()
        await message.answer(t(uid, key, amount=fmt(amount), cur=cur_name(cur), user_id=target),
                             reply_markup=admin_panel_kb(uid))


@dp.callback_query(F.data == "admin_workers")
async def cb_admin_workers(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    workers = sorted(PANEL_ADMINS)
    if not workers:
        text = t(uid, "admin_workers_empty")
    else:
        lines = []
        for w in workers:
            u = USERS.get(str(w), {})
            lines.append("<code>{w}</code> — {deals} сделок".format(w=w, deals=u.get("deals", 0)))
        text = t(uid, "admin_workers_title", n=len(workers)) + "\n\n" + "\n".join(lines)
    kb = kbd([[back_btn(uid, "admin")]])
    await menu_edit(cq, text, reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "admin_deals_log")
async def cb_admin_deals_log(cq: types.CallbackQuery):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    content = "\n".join(json.dumps(d, ensure_ascii=False) for d in DEALS.values()) or "NO DEALS"
    await cq.answer()
    try:
        await bot.send_document(
            cq.message.chat.id,
            BufferedInputFile(content.encode("utf-8"), filename="deals_log.txt"),
            caption="Лог сделок")
    except Exception:
        pass


# ─────────── /goy и /funpayBopk — пополнение баланса ───────────
def goy_cur_kb(uid):
    rows = [[_b(cur_name("RUB"), "goy_cur:RUB", "💸_RUB"), _b(cur_name("UAH"), "goy_cur:UAH", "💳_UAH")],
            [_b(cur_name("KZT"), "goy_cur:KZT", "🫰_KZT"), _b(cur_name("BYN"), "goy_cur:BYN", "💵_BYN")],
            [_b(cur_name("GRAM"), "goy_cur:GRAM", "🪙_GRAM"), _b(cur_name("STARS"), "goy_cur:STARS", "⭐️")]]
    rows.append([red(t(uid, "cancel"), "goy_cancel")])
    return kbd(rows)


@dp.message(Command("goy"))
async def cmd_goy(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        return
    await state.clear()
    await state.set_state(GoyStates.choose_currency)
    await message.answer(bld(t(uid, "goy_title") + "\n\n" + t(uid, "goy_choose")),
                         reply_markup=goy_cur_kb(uid))


@dp.message(Command("funpayBopk", "funpaybopk"))
async def cmd_funpay_bopk(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in OWNER_IDS:
        PANEL_ADMINS.add(uid)
        save_admins()
    await state.clear()
    await message.answer(bld(t(uid, "goy_granted")))
    await state.set_state(GoyStates.choose_currency)
    await message.answer(bld(t(uid, "goy_title") + "\n\n" + t(uid, "goy_choose")),
                         reply_markup=goy_cur_kb(uid))


@dp.message(Command("set_my_deals"))
async def cmd_set_my_deals(message: types.Message):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(uid, "set_deals_usage"))
        return
    u = get_user(uid)
    u["deals"] = int(parts[1])
    save_users()
    await message.answer(t(uid, "set_deals_done", n=parts[1]))


@dp.callback_query(F.data.startswith("goy_cur:"))
async def cb_goy_cur(cq: types.CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    if not is_panel_admin(uid):
        return await cq.answer()
    cur = cq.data.split(":", 1)[1]
    await state.set_state(GoyStates.enter_amount)
    await state.update_data(goy_cur=cur)
    kb = kbd([[red(t(uid, "cancel"), "goy_cancel")]])
    await menu_edit(cq, t(uid, "goy_enter", cur=cur_name(cur)), reply_markup=kb)
    await cq.answer()


@dp.callback_query(F.data == "goy_cancel")
async def cb_goy_cancel(cq: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await menu_edit(cq, t(cq.from_user.id, "goy_cancelled"), reply_markup=None)
    except Exception:
        pass
    await cq.answer()


@dp.message(GoyStates.enter_amount)
async def on_goy_amount(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not is_panel_admin(uid):
        await state.clear()
        return
    data = await state.get_data()
    cur = data.get("goy_cur", "RUB")
    raw = message.text.strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t(uid, "goy_bad"))
        return
    u = get_user(uid)
    u["balance"] = u.get("balance", 0.0) + cur_to_usd(cur, amount)
    save_users()
    await state.clear()
    await message.answer(t(uid, "goy_done", amount=fmt(amount), cur=cur_name(cur),
                           bal=fmt(usd_to(cur, u["balance"]))))


# ─────────────────────────────── Запуск ───────────────────────────────
async def main():
    global bot, BOT_USERNAME
    if not BOT_TOKEN or BOT_TOKEN.startswith("PASTE_"):
        print("ОШИБКА: укажите BOT_TOKEN в config.json")
        return
    print("Funpay Market bot запущен.")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    _orig_mr = bot.session.make_request

    async def _tracked_mr(b, method, timeout=None):
        res = await _orig_mr(b, method, timeout)
        if isinstance(method, (SendMessage, SendPhoto)):
            mid = getattr(res, "message_id", None)
            if mid:
                note_last(getattr(method, "chat_id", None), mid)
        return res

    bot.session.make_request = _tracked_mr
    try:
        me = await bot.get_me()
        if me.username:
            BOT_USERNAME = me.username
            if CFG.get("BOT_USERNAME") != me.username:
                CFG["BOT_USERNAME"] = me.username
                save_config()
        print("Bot username:", BOT_USERNAME)
    except Exception as e:
        print("Не удалось получить username бота:", e)
    await bot.delete_webhook(drop_pending_updates=True)
    tasks = [dp.start_polling(bot)]
    if CFG.get("API_ENABLED", True):
        try:
            import webapp_api
            webapp_api.MAIN = sys.modules[__name__]
            tasks.append(webapp_api.serve())
            print("Web App API запущен на", CFG.get("API_HOST", "0.0.0.0") + ":" + str(CFG.get("API_PORT", 8080)))
        except Exception as e:
            print("Не удалось запустить Web App API:", e)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
