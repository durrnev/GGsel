# -*- coding: utf-8 -*-
"""
Web App API — связывает мини-ап (фронтенд на отдельном хостинге) с ботом.

Авторизация: каждый запрос из мини-апа передаёт Telegram.WebApp.initData
(заголовок X-Telegram-Init-Data или query-параметр init_data). Бэкенд проверяет
подпись HMAC-SHA256 от bot_token и узнаёт user_id (он же chat_id для сообщений).

MAIN задаётся из main.py при запуске (webapp_api.MAIN = sys.modules[__name__]),
чтобы API и бот жили в одном процессе и видели одни данные.
"""
import hashlib
import hmac
import json
import random
import time
import urllib.parse

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

MAIN = None

app = FastAPI(title="Funpay Market WebApp API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _m():
    if MAIN is None:
        raise HTTPException(status_code=503, detail="API is not connected to the bot")
    return MAIN


def validate_init_data(init_data, bot_token, max_age=86400):
    if not init_data or not bot_token:
        return None
    try:
        parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)
    except Exception:
        return None
    if "hash" not in parsed:
        return None
    received_hash = parsed.pop("hash")[0]
    data_check_string = "\n".join(
        "{0}={1}".format(k, parsed[k][0]) for k in sorted(parsed)
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None
    try:
        auth_date = int(parsed["auth_date"][0])
    except Exception:
        return None
    if time.time() - auth_date > max_age:
        return None
    try:
        user = json.loads(parsed["user"][0])
    except Exception:
        user = {}
    return user or None


def auth_user(
    init_data_h: str = Header(default=None, alias="X-Telegram-Init-Data"),
    init_data_q: str = Query(default=None, alias="init_data"),
):
    m = _m()
    user = validate_init_data(init_data_h or init_data_q, m.BOT_TOKEN)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid initData")
    return user


def _stats(u):
    deals = int(u.get("deals", 0))
    refs = int(u.get("refs", 0))
    return {
        "deals": deals,
        "reputation": min(100, deals * 4),
        "trust": min(100, refs * 2 + deals * 4),
    }


def _display_name(user):
    if user.get("username"):
        return "@" + str(user["username"])
    return user.get("first_name") or "Пользователь"


@app.get("/health")
def health():
    m = _m()
    return {"ok": True, "service": "Funpay Market", "bot": m.BOT_USERNAME}


@app.get("/profile")
def profile(user: dict = Depends(auth_user)):
    m = _m()
    uid = int(user["id"])
    u = m.get_user(uid)
    cur = u.get("currency") or "USD"
    bal = m.usd_to(cur, float(u.get("balance", 0.0)))
    s = _stats(u)
    return {
        "balance": round(bal, 2),
        "currency": cur,
        "currencySymbol": m.CURRENCY_SYM.get(cur, cur),
        "deals": s["deals"],
        "reputation": s["reputation"],
        "trust": s["trust"],
        "username": _display_name(user),
        "blurb": m.t(uid, "blurb"),
        "avatar": user.get("photo_url", ""),
        "bot_link": "https://t.me/" + m.BOT_USERNAME,
        "support_link": "https://t.me/" + m.SUPPORT_USERNAME,
    }


@app.get("/user")
def user_search(username: str, user: dict = Depends(auth_user)):
    m = _m()
    needle = (username or "").strip().lstrip("@").lower()
    if not needle:
        raise HTTPException(status_code=400, detail="username required")
    found = None
    for uid, u in m.USERS.items():
        nm = str(u.get("_name", "")).lstrip("@").lower()
        if nm and (nm == needle or nm.startswith(needle)):
            found = (uid, u)
            break
    if not found:
        return {"username": None}
    uid, u = found
    s = _stats(u)
    return {
        "username": "@" + str(u.get("_name", "")).lstrip("@"),
        "blurb": "Покупатель / Продавец",
        "balance": round(m.usd_to("RUB", float(u.get("balance", 0.0))), 2),
        "deals": s["deals"],
        "reputation": s["reputation"],
        "trust": s["trust"],
        "reviews": s["deals"],
    }


@app.get("/worker")
def worker(user: dict = Depends(auth_user)):
    m = _m()
    uid = int(user["id"])
    u = m.get_user(uid)
    cur = u.get("currency") or "USD"
    s = _stats(u)
    active = []
    for code, d in m.DEALS.items():
        if d.get("buyer") != uid and d.get("seller") != uid:
            continue
        if d.get("status") in ("completed", "cancelled"):
            continue
        role = "buyer" if d.get("buyer") == uid else "seller"
        other = d.get("seller") if role == "buyer" else d.get("buyer")
        other_name = "@" + str(m.USERS.get(str(other), {}).get("_name", "")) if other else "—"
        active.append({
            "code": code,
            "role": role,
            "currency": d.get("currency", "USD"),
            "amount": d.get("amount", 0),
            "status": d.get("status", "waiting"),
            "desc": d.get("desc", ""),
            "other": other_name,
        })
    active.sort(key=lambda x: x["code"])
    return {
        "balance": round(m.usd_to(cur, float(u.get("balance", 0.0))), 2),
        "currency": cur,
        "currencySymbol": m.CURRENCY_SYM.get(cur, cur),
        "deals": s["deals"],
        "reputation": s["reputation"],
        "trust": s["trust"],
        "username": _display_name(user),
        "active": active,
        "manager": m.MANAGER_USERNAME,
        "bot_link": "https://t.me/" + m.BOT_USERNAME,
    }


# ───────────── Отзывы (генерируются так же, как в фронтенде) ─────────────
_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

_SUBJECTS = {
    "ru": ["hft gift", "nft gift", "gift", "gift premium", "gift telegram",
           "подарок nft", "гифт", "gift nft"],
    "en": ["hft gift", "nft gift", "gift", "gift premium", "gift telegram",
           "nft gift", "gift", "gift nft"],
}

_TEXTS = {
    "ru": ["+реп всё чётко, спасибо", "+реп быстро и надёжно", "+реп отличный продавец",
           "+реп 10/10 рекомендую", "+реп быстрая сделка", "+реп не первый раз, всем советую",
           "+реп доволен, всё чисто", "+реп топ, моё почтение", "+реп лучший гарант",
           "+реп сделал всё молниеносно", "+реп честный и надёжный", "+реп приятно работать",
           "+реп вернусь ещё", "+реп одна из лучших сделок", "+реп всё супер, спасибо",
           "+реп без единой проблемы", "+реп рекомендую всем", "+реп гарант от бога",
           "+реп быстро и без нервов"],
    "en": ["+rep all good, thanks", "+rep fast and reliable", "+rep great seller",
           "+rep 10/10 recommended", "+rep smooth, thanks", "+rep quick deal",
           "+rep not the first time, recommend", "+rep happy, all clean", "+rep top seller",
           "+rep best escrow", "+rep lightning fast", "+rep honest and reliable",
           "+rep nice to deal with", "+rep will be back", "+rep one of the best deals",
           "+rep all super, thanks", "+rep zero problems", "+rep recommend to everyone",
           "+rep god-tier escrow", "+rep fast and smooth"],
}

_ENDINGS = [" ❤️", " ❤️", " ❤️", " 💚", " ✅", ""]


def _rid(n=10):
    return "".join(random.choice(_ALPHABET) for _ in range(n))


def _time_ago(old, lang):
    if old:
        r = random.randint(1, 100)
        if r <= 45:
            return "%d %s" % (random.randint(1, 6), "мес назад" if lang == "ru" else "mo ago")
        if r <= 75:
            return "%d %s" % (random.randint(1, 4), "нед назад" if lang == "ru" else "wk ago")
        if r <= 95:
            return "%d %s" % (random.randint(1, 30), "дн назад" if lang == "ru" else "d ago")
        return "%d %s" % (random.randint(1, 23), "ч назад" if lang == "ru" else "h ago")
    r = random.randint(1, 100)
    if r <= 8:
        if random.randint(0, 5) == 0:
            return "сейчас" if lang == "ru" else "now"
        return "%d %s" % (random.randint(1, 59), "мин назад" if lang == "ru" else "min ago")
    if r <= 35:
        return "%d %s" % (random.randint(1, 23), "ч назад" if lang == "ru" else "h ago")
    if r <= 75:
        return "%d %s" % (random.randint(1, 30), "дн назад" if lang == "ru" else "d ago")
    return "%d %s" % (random.randint(1, 8), "нед назад" if lang == "ru" else "wk ago")


def _make_review(old, lang):
    cur = random.choice(["ton", "usdt", "₽"])
    amount = random.randint(3, 150) if cur in ("ton", "usdt") else random.randint(15, 9000)
    return {
        "id": _rid(10),
        "subject": random.choice(_SUBJECTS[lang]),
        "currency": cur,
        "amount": amount,
        "text": random.choice(_TEXTS[lang]),
        "ending": random.choice(_ENDINGS),
        "name": _m().BOT_USERNAME,
        "bot": True,
        "time": _time_ago(old, lang),
    }


@app.get("/reviews")
def reviews(
    limit: int = Query(default=50, ge=1, le=500),
    lang: str = Query(default="ru"),
    user: dict = Depends(auth_user),
):
    lang = lang if lang in _TEXTS else "ru"
    return [_make_review(True, lang) for _ in range(min(limit, 200))]


async def serve():
    import uvicorn
    m = _m()
    host = str(m.CFG.get("API_HOST", "0.0.0.0"))
    port = int(m.CFG.get("API_PORT", 8080))
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
