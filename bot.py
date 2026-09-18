import os
import sys
import json
import time
import signal
import asyncio
import aiohttp
import yarl
import urllib.parse

from utils.banner import show_banner

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"

MY_PROJECT = "Mango Farm Miniapp"
BASE_URL = "https://pepefarming.lovable.app"
REF_CODE = "6004380466"
SUPABASE_URL = "https://aoztzrijimfvghnppqwf.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFvenR6cmlqaW1mdmdobnBwcXdmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM2NDA3NzksImV4cCI6MjA5OTIxNjc3OX0.DVrOtGXaa3N7h_7AniaEQXhOhWQiR7mZHTmp1GC7HaI"
AUTH_FN = "b704aa5aac72e954c4a186b75e83021be2ffccef266746cdf67adabb87123eaa"
DEVICE_FILE = "device.json"

LOGIN_ATTEMPTS = 4
LOGIN_RETRY_SECONDS = 4
CALL_ATTEMPTS = 4
CALL_RETRY_SECONDS = 4
ROUND_PAUSE_SECONDS = 1
MINES_SAFE_TILES = 5

BANNED_CODES = (
    91, 93, 124, 35, 33, 64, 36, 37, 94, 38, 42, 40, 41,
    45, 44, 58, 59, 39, 34, 96, 126, 43, 61, 60, 62, 63, 47, 92,
)
BANNED_CHARS = tuple(chr(code) for code in BANNED_CODES)

BUSY_STATUS = (429, 500, 502, 503, 504)
REFUSED_WORDS = ("invalid telegram initdata", "missing telegram initdata", "unauthorized")

HEADERS_BASE = {
    "accept": "application/x-tss-framed, application/x-ndjson, application/json",
    "content-type": "application/json",
    "origin": BASE_URL,
    "referer": f"{BASE_URL}/",
    "x-tsr-serverfn": "true",
    "user-agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Mobile Safari/537.36",
}

SESSION_CACHE = {}
SESSION_MODE = {}


def log_green(msg):
    print(f"{GREEN}{BOLD}{msg}{RESET}")


def log_yellow(msg):
    print(f"{YELLOW}{BOLD}{msg}{RESET}")


def log_red(msg):
    print(f"{RED}{BOLD}{msg}{RESET}")


def signal_handler(sig, frame):
    print()
    log_red("Script stopped by user")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def clean_text(value, fallback):
    text = str(value)
    for symbol in BANNED_CHARS:
        text = text.replace(symbol, " ")
    text = " ".join(text.split())
    return text if text else str(fallback)


def unit_word(value, singular, plural):
    return singular if int(value) == 1 else plural


def format_duration(seconds):
    seconds = int(max(0, seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    rest = seconds % 60
    if hours:
        return f"{hours} {unit_word(hours, 'hour', 'hours')} {minutes} {unit_word(minutes, 'minute', 'minutes')}"
    if minutes:
        return f"{minutes} {unit_word(minutes, 'minute', 'minutes')} {rest} {unit_word(rest, 'second', 'seconds')}"
    return f"{rest} {unit_word(rest, 'second', 'seconds')}"


class Encoder:
    def __init__(self):
        self.index = -1

    def next_index(self):
        self.index += 1
        return self.index

    def encode(self, value):
        if value is None:
            return {"t": 2, "s": 0}
        if value is True:
            return {"t": 2, "s": 2}
        if value is False:
            return {"t": 2, "s": 3}
        if isinstance(value, (int, float)):
            return {"t": 0, "s": json.dumps(value)}
        if isinstance(value, str):
            return {"t": 1, "s": value}
        if isinstance(value, dict):
            node = {"t": 10, "i": self.next_index(), "p": {"k": [], "v": []}, "o": 0}
            for key, item in value.items():
                node["p"]["k"].append(str(key))
                node["p"]["v"].append(self.encode(item))
            return node
        if isinstance(value, (list, tuple)):
            node = {"t": 9, "i": self.next_index(), "a": [], "o": 0}
            for item in value:
                node["a"].append(self.encode(item))
            return node
        return {"t": 1, "s": str(value)}


def encode_request(value):
    return {"t": Encoder().encode(value)}


def decode_value(node):
    if node is None or not isinstance(node, dict):
        return node
    if "t" not in node:
        return {key: decode_value(item) for key, item in node.items()}
    kind = node.get("t")
    if kind == 0:
        raw = node.get("s")
        try:
            return int(raw)
        except (TypeError, ValueError):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw
    if kind == 1:
        return node.get("s")
    if kind == 2:
        return {0: None, 2: True, 3: False}.get(node.get("s"))
    if kind == 3:
        try:
            return int(node.get("s"))
        except (TypeError, ValueError):
            return node.get("s")
    if kind == 9:
        return [decode_value(item) for item in node.get("a") or []]
    if kind in (10, 11):
        payload = node.get("p") or {}
        keys = payload.get("k") or []
        values = payload.get("v") or []
        return {key: decode_value(item) for key, item in zip(keys, values)}
    if kind in (18, 23, 24, 25, 26):
        return decode_value(node.get("s"))
    return node


def decode_body(text):
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    return decode_value(parsed)


def load_config():
    defaults = {"settings": {"sleep_seconds": 3600}}
    if not os.path.exists("config.json"):
        return defaults
    try:
        with open("config.json") as handle:
            return json.load(handle)
    except Exception:
        return defaults


def load_data():
    if not os.path.exists("data.txt"):
        log_red("File data.txt was not found")
        sys.exit(1)
    lines = [line.strip() for line in open("data.txt").readlines() if line.strip()]
    if not lines:
        log_red("File data.txt is empty")
        sys.exit(1)
    return lines


def load_proxies():
    if not os.path.exists("proxy.txt"):
        return []
    try:
        return [line.strip() for line in open("proxy.txt").readlines() if line.strip()]
    except Exception:
        return []


def get_proxy(proxies, index):
    if not proxies:
        return None
    return proxies[index % len(proxies)]


def normalize_proxy(proxy_line):
    if not proxy_line:
        return None
    value = proxy_line.strip()
    if "://" in value:
        return value
    parts = value.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    if len(parts) == 3:
        host, port, user = parts
        return f"http://{user}@{host}:{port}"
    return f"http://{value}"


def mask_proxy(proxy_url):
    try:
        value = proxy_url.split("://")[-1]
        after_at = value.split("@")[-1]
        host_part = after_at.split(":")[0]
        port_part = after_at.split(":")[1] if ":" in after_at else ""
        octets = host_part.split(".")
        if len(octets) == 4:
            masked_host = f"{octets[0]}*****{octets[3]}"
        elif len(host_part) > 4:
            masked_host = f"{host_part[:2]}*****{host_part[-2:]}"
        else:
            masked_host = "***"
        suffix = f":{port_part}" if port_part else ""
        return f"http://user:pass@{masked_host}{suffix}"
    except Exception:
        return "http://user:pass@***:***"


def init_data_fields(init_data):
    try:
        return dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return {}


def parse_init_data(init_data):
    fields = init_data_fields(init_data)
    try:
        return json.loads(fields.get("user") or "{}")
    except Exception:
        return {}


def load_session_cache():
    global SESSION_CACHE
    SESSION_CACHE = {}
    if not os.path.exists(DEVICE_FILE):
        return
    try:
        with open(DEVICE_FILE) as handle:
            parsed = json.load(handle)
    except Exception:
        log_red("Session cache was unreadable so it will be rebuilt")
        return
    if isinstance(parsed, dict):
        SESSION_CACHE = parsed


def save_session_cache():
    try:
        with open(DEVICE_FILE, "w") as handle:
            json.dump(SESSION_CACHE, handle, indent=2, sort_keys=True)
    except Exception:
        log_red("The session cache could not be written to disk")


def cache_session(account_id, email, password, token, refresh_token, expires_at):
    account_id = str(account_id)
    if not account_id or not email:
        return
    record = {
        "email": email,
        "password": password or "",
        "token": token or "",
        "refresh_token": refresh_token or "",
        "expires_at": int(expires_at or 0),
        "saved_at": int(time.time()),
    }
    if SESSION_CACHE.get(account_id) == record:
        return
    SESSION_CACHE[account_id] = record
    save_session_cache()


def cached_session(account_id):
    record = SESSION_CACHE.get(str(account_id))
    return record if isinstance(record, dict) else {}


def error_message(payload):
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, dict):
                return str(message.get("s") or "")
            return str(message or error)
        if error:
            return str(error)
    return ""


def refused_error(status, payload):
    message = error_message(payload).lower()
    if status == 401:
        return True
    return any(word in message for word in REFUSED_WORDS)


def busy_error(status, payload):
    if status in BUSY_STATUS:
        return True
    message = error_message(payload).lower()
    return "busy" in message or "seroval" in message


async def server_call(session, fn_hash, method, payload=None, token=None, proxy=None):
    url = f"{BASE_URL}/_serverFn/{fn_hash}"
    headers = dict(HEADERS_BASE)
    if token:
        headers["authorization"] = f"Bearer {token}"
    body = None
    params = None
    if method == "POST":
        request = encode_request({"data": payload if payload is not None else {}})
        if token:
            request["f"] = 63
            request["m"] = []
        body = json.dumps(request)
    try:
        async with session.request(
            method,
            url,
            headers=headers,
            data=body,
            params=params,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as response:
            raw = await response.read()
            return response.status, decode_body(raw.decode("utf-8", "replace"))
    except Exception as error:
        log_red(f"Request to the game server failed with {clean_text(type(error).__name__, 'Error')}")
        return None, None


async def auth_exchange(session, init_data, proxy):
    for attempt in range(LOGIN_ATTEMPTS):
        status, payload = await server_call(
            session,
            AUTH_FN,
            "POST",
            {"initData": init_data, "startParam": REF_CODE},
            None,
            proxy,
        )
        result = (payload or {}).get("result") if isinstance(payload, dict) else None
        if status == 200 and isinstance(result, dict) and result.get("email"):
            return result
        if status is not None and refused_error(status, payload):
            return None
        if not busy_error(status, payload):
            return None
        if attempt < LOGIN_ATTEMPTS - 1:
            await asyncio.sleep(LOGIN_RETRY_SECONDS)
    return None


async def token_login(session, email, password, proxy):
    try:
        async with session.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_KEY,
                "authorization": f"Bearer {SUPABASE_KEY}",
                "content-type": "application/json;charset=UTF-8",
            },
            data=json.dumps({"email": email, "password": password, "gotrue_meta_security": {}}),
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as response:
            raw = await response.read()
            if response.status == 200:
                return json.loads(raw.decode("utf-8", "replace"))
    except Exception as error:
        log_red(f"Token request failed with {clean_text(type(error).__name__, 'Error')}")
    return None


async def token_refresh(session, refresh_token, proxy):
    try:
        async with session.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": SUPABASE_KEY,
                "authorization": f"Bearer {SUPABASE_KEY}",
                "content-type": "application/json;charset=UTF-8",
            },
            data=json.dumps({"refresh_token": refresh_token}),
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as response:
            raw = await response.read()
            if response.status == 200:
                return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    return None


async def login(session, init_data, account_id, proxy):
    record = cached_session(account_id)
    if record.get("token") and record.get("expires_at", 0) > time.time() + 60:
        SESSION_MODE[account_id] = "cached"
        return record.get("email"), record["token"]

    if record.get("refresh_token"):
        refreshed = await token_refresh(session, record["refresh_token"], proxy)
        if refreshed and refreshed.get("access_token"):
            cache_session(
                account_id,
                record.get("email"),
                record.get("password"),
                refreshed.get("access_token"),
                refreshed.get("refresh_token") or record.get("refresh_token"),
                refreshed.get("expires_at"),
            )
            SESSION_MODE[account_id] = "refresh"
            return record.get("email"), refreshed["access_token"]

    credentials = await auth_exchange(session, init_data, proxy)
    email = None
    password = None
    if credentials:
        email = credentials.get("email")
        password = credentials.get("password")
    elif record.get("email") and record.get("password"):
        email = record.get("email")
        password = record.get("password")
        if SESSION_MODE.get(account_id) != "fallback":
            SESSION_MODE[account_id] = "fallback"
            log_yellow("Init data was rejected so the cached session was reused")
    else:
        return None, None

    tokens = await token_login(session, email, password, proxy)
    if not tokens or not tokens.get("access_token"):
        return None, None
    cache_session(account_id, email, password, tokens.get("access_token"), tokens.get("refresh_token"), tokens.get("expires_at"))
    if account_id not in SESSION_MODE:
        SESSION_MODE[account_id] = "initdata"
    return email, tokens["access_token"]


async def call_fn(session, fn_hash, method, payload, token, proxy):
    for attempt in range(CALL_ATTEMPTS):
        status, body = await server_call(session, fn_hash, method, payload, token, proxy)
        if status == 200 and isinstance(body, dict) and body.get("result") is not None:
            return body.get("result")
        if status == 200 and isinstance(body, dict) and body.get("error") is None:
            return body.get("result")
        if busy_error(status, body) and attempt < CALL_ATTEMPTS - 1:
            await asyncio.sleep(CALL_RETRY_SECONDS)
            continue
        return None
    return None


async def run_farm(session, token, profile, proxy):
    claim = await call_fn(session, "fc230343682c5a7bafa545b0b61495cfb3a4ba5cb9118bfd2589ec4ea8ae08b4", "POST", {}, token, proxy)
    if isinstance(claim, dict) and claim.get("claimed"):
        log_green("Farm cycle was harvested for this account")
        return
    if isinstance(claim, dict) and claim.get("reason") == "not_ready":
        remaining = int((claim.get("remaining_ms") or 0) / 1000)
        if profile.get("farming_started_at"):
            log_yellow(f"Farm is still growing for {clean_text(format_duration(remaining), 'a while')}")
            return
    started = await call_fn(session, "31ba1d01cd3e2cb7187f7d30d12144467b60871780099b08275ed68f00af76a3", "POST", {}, token, proxy)
    if isinstance(started, dict) and started.get("started"):
        log_yellow("A new farm cycle was started for this account")
        return
    if isinstance(started, dict) and started.get("reason") == "already_farming":
        return
    log_yellow("Farm state could not be changed on this run")


async def run_ads(session, token, config, profile, proxy):
    coin = str(config.get("coin_name") or "Mango")
    limit = int(config.get("ads_daily_limit") or 0)
    watched = int(profile.get("ads_watched_today") or 0)
    if limit and watched >= limit:
        log_yellow("The daily advertisement limit was already reached")
        return
    paid = 0
    total = 0
    while not limit or watched < limit:
        reward = await call_fn(session, "0d331928ab305ed0ff89efaa9023475d61ef691c5c08e9b393b0450917903684", "POST", {}, token, proxy)
        if not isinstance(reward, dict):
            break
        if reward.get("rewarded"):
            amount = int(reward.get("reward") or 0)
            paid += 1
            total += amount
            watched = int(reward.get("watched") or watched + 1)
            limit = int(reward.get("limit") or limit)
            log_green(f"Reward advertisement number {clean_text(paid, 0)} paid {clean_text(amount, 0)} {clean_text(coin, 'coins')}")
            await asyncio.sleep(ROUND_PAUSE_SECONDS)
            continue
        reason = str(reward.get("reason") or "")
        if reason == "cooldown":
            await asyncio.sleep(int(reward.get("cooldown") or CALL_RETRY_SECONDS) + 1)
            continue
        if reason == "daily_limit":
            break
        break
    if paid:
        log_green(f"{clean_text(paid, 0)} reward {unit_word(paid, 'advertisement was', 'advertisements were')} credited for {clean_text(total, 0)} {clean_text(coin, 'coins')}")
    else:
        log_yellow("No reward advertisement could be credited on this run")


async def run_tasks(session, token, coin, proxy):
    tasks = await call_fn(session, "ad61b6e489a363d0ffba59698fe92b918457a1692e33bd45800947b514fc7315", "GET", None, token, proxy)
    if not isinstance(tasks, list) or not tasks:
        return
    pending = [item for item in tasks if isinstance(item, dict) and item.get("active") and not item.get("completed")]
    if not pending:
        log_green("Every available account task was already completed")
        return
    claimed = 0
    rewards = 0
    for task in pending:
        result = await call_fn(
            session,
            "198ec4c47a71099bb12f2e2bd00304fb6f6730dc9722be2a77a2e35edabc5040",
            "POST",
            {"taskId": task.get("id")},
            token,
            proxy,
        )
        if isinstance(result, dict) and result.get("rewarded"):
            claimed += 1
            rewards += int(result.get("reward") or 0)
        await asyncio.sleep(ROUND_PAUSE_SECONDS)
    if claimed:
        log_green(f"All available account tasks paid {clean_text(rewards, 0)} {clean_text(coin, 'coins')}")
    else:
        log_yellow("No account task could be credited on this run")


async def run_games(session, token, proxy):
    state = await call_fn(session, "de9e5bfee3c8ffe526605baee5102316b51b74769bd6436afec5f3fa13faaed5", "GET", None, token, proxy)
    if not isinstance(state, dict):
        log_yellow("Game state could not be retrieved on this run")
        return
    config = state.get("config") or {}
    coin = str(config.get("coinName") or "Mango")
    earned = 0
    rounds = 0
    if not config.get("enabled"):
        log_yellow("Games are disabled on the server for this app")
        return

    pending_spin = state.get("pendingSpin")
    if isinstance(pending_spin, dict) and int(pending_spin.get("reward") or 0) > 0:
        claimed = await call_fn(session, "09199c432b5f0dc47b459dd0cc798eab4f98459fdae0e2ffc9360856753a89d9", "POST", {"roundId": pending_spin.get("id")}, token, proxy)
        if isinstance(claimed, dict):
            earned += int(claimed.get("reward") or 0)
            rounds += 1
            log_green(f"An unclaimed spin wheel prize paid {clean_text(claimed.get('reward'), 0)} {clean_text(coin, 'coins')}")

    ttt_limit = int(config.get("tttDailyLimit") or 0)
    ttt_played = int(state.get("tttPlayed") or 0)
    while ttt_limit and ttt_played < ttt_limit:
        started = await call_fn(session, "fd14ed9838e121834663dc2419d5b6425ceaa3be5cdc502c7f85024ab2bde525", "POST", {}, token, proxy)
        if not isinstance(started, dict) or not started.get("id"):
            break
        round_id = started["id"]
        board = started.get("board") or []
        status = str(started.get("status") or "active")
        reward = int(started.get("reward") or 0)
        for cell in range(9):
            if status != "active":
                break
            if board and board[cell]:
                continue
            moved = await call_fn(session, "766eb6da3335b74c19907eb3d46d7f98636c1d063b840f0b5bd57a4ff68a67ea", "POST", {"roundId": round_id, "index": cell}, token, proxy)
            if not isinstance(moved, dict):
                status = "stopped"
                break
            board = moved.get("board") or board
            status = str(moved.get("status") or "active")
            reward = int(moved.get("reward") or 0)
        rounds += 1
        ttt_played += 1
        if status == "won":
            earned += reward
            log_green(f"Tic tac toe round was won for {clean_text(reward, 0)} {clean_text(coin, 'coins')}")
        elif status == "draw" and reward > 0:
            earned += reward
            log_green(f"Tic tac toe round ended in a draw for {clean_text(reward, 0)} {clean_text(coin, 'coins')}")
        await asyncio.sleep(ROUND_PAUSE_SECONDS)

    mines_limit = int(config.get("minesDailyLimit") or 0)
    mines_played = int(state.get("minesPlayed") or 0)
    while mines_limit and mines_played < mines_limit:
        started = await call_fn(session, "3ac13bae0b203c3b20b644a29a363c3e8512a352dd57309ab9e5aac523296391", "POST", {}, token, proxy)
        if not isinstance(started, dict) or not started.get("id"):
            break
        round_id = started["id"]
        grid = int(started.get("grid") or 25)
        pending = 0
        revealed = 0
        alive = True
        while revealed < MINES_SAFE_TILES and revealed < grid:
            moved = await call_fn(session, "b8fd7d9c5aa5cc938cae8f18f1a815cc65b9eead6017ae55bf0e30e9d87c8041", "POST", {"roundId": round_id, "index": revealed}, token, proxy)
            if not isinstance(moved, dict):
                alive = False
                break
            if moved.get("hit"):
                alive = False
                log_yellow("A mine was hit so the round was lost")
                break
            pending = int(moved.get("pending") or 0)
            revealed += 1
            if str(moved.get("status") or "active") != "active":
                alive = False
                break
        mines_played += 1
        if alive and revealed:
            cashed = await call_fn(session, "10f10d59906ae89d83bc872dbfaa5861f7d9ac256be4c7c27ebe63fe1f6f2343", "POST", {"roundId": round_id}, token, proxy)
            if isinstance(cashed, dict) and cashed.get("status") == "cashed":
                amount = int(cashed.get("reward") or pending)
                earned += amount
                rounds += 1
                log_green(f"A mines round was cashed out for {clean_text(amount, 0)} {clean_text(coin, 'coins')}")
        await asyncio.sleep(ROUND_PAUSE_SECONDS)

    spins_left = int(config.get("spinDailyLimit") or 0) - int(state.get("spinPlayed") or 0) + int(state.get("bonusSpins") or 0)
    while config.get("spinEnabled") and spins_left > 0:
        spin = await call_fn(session, "82d7106e0f93221e75abb4205cfad38a680bdf61d8e7572debf45c6da729b489", "POST", {}, token, proxy)
        if not isinstance(spin, dict) or not spin.get("id"):
            break
        spins_left -= 1
        reward = int(spin.get("reward") or 0)
        if reward > 0:
            claimed = await call_fn(session, "09199c432b5f0dc47b459dd0cc798eab4f98459fdae0e2ffc9360856753a89d9", "POST", {"roundId": spin.get("id")}, token, proxy)
            if isinstance(claimed, dict):
                reward = int(claimed.get("reward") or reward)
        earned += reward
        rounds += 1
        if reward > 0:
            log_green(f"Spin wheel paid {clean_text(reward, 0)} {clean_text(coin, 'coins')}")
        await asyncio.sleep(ROUND_PAUSE_SECONDS)

    if rounds:
        log_green(f"Games credited {clean_text(earned, 0)} {clean_text(coin, 'coins')} over {clean_text(rounds, 0)} {unit_word(rounds, 'round', 'rounds')}")


async def run_referral(session, token, profile, coin, proxy):
    referrals = await call_fn(session, "0894c4ebdfd7a278a46c9b7d3677da392ca050544484775854f17b0f8086c9fd", "GET", None, token, proxy)
    earned = int(profile.get("referral_earnings") or 0)
    if isinstance(referrals, list) and referrals:
        log_green(f"Referral list holds {clean_text(len(referrals), 0)} {unit_word(len(referrals), 'entry', 'entries')} for this account")
    if earned > 0:
        log_green(f"Referral earnings added {clean_text(earned, 0)} {clean_text(coin, 'coins')} to this account")


async def process_account(init_data, proxy, index):
    user_info = parse_init_data(init_data)
    account_id = str(user_info.get("id") or "")
    if not account_id:
        log_red(f"Account on line {clean_text(index, 1)} holds invalid init data and was skipped")
        return
    display = user_info.get("username") or user_info.get("first_name") or "Unknown"

    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        email, token = await login(session, init_data, account_id, proxy)
        if not token:
            log_red("Login failed for this account")
            return

        state = await call_fn(session, "99cadcde0d3c66afeb3d3b432f8307275d3f83f2c71b45146a46e667dcc9f063", "GET", None, token, proxy)
        if not isinstance(state, dict) or not state.get("profile"):
            log_red("Account state could not be loaded")
            return
        profile = state.get("profile") or {}
        config = state.get("config") or {}
        if profile.get("banned"):
            log_red("Account is banned and was skipped")
            return
        coin = str(config.get("coin_name") or "Mango")

        log_green(f"Account {clean_text(display, 'Unknown')} loaded successfully")
        log_yellow(f"Total balance is {clean_text(profile.get('balance'), 0)} {clean_text(coin, 'coins')}")

        gate = await call_fn(session, "0550606fa1414aa9873dcc64b51e6d624bbe67f46dd32f9339b259245ce7731e", "POST", {}, token, proxy)
        if isinstance(gate, dict) and gate.get("ok") is False:
            missing = len(gate.get("missing") or [])
            log_yellow(f"Channel join is still required so {clean_text(missing, 0)} {unit_word(missing, 'channel', 'channels')} were not passed")
            return

        await run_farm(session, token, profile, proxy)
        await run_ads(session, token, config, profile, proxy)
        await run_tasks(session, token, coin, proxy)
        await run_games(session, token, proxy)
        await run_referral(session, token, profile, coin, proxy)

        final = await call_fn(session, "99cadcde0d3c66afeb3d3b432f8307275d3f83f2c71b45146a46e667dcc9f063", "GET", None, token, proxy)
        final_profile = (final or {}).get("profile") or profile
        log_green(f"Final balance is {clean_text(final_profile.get('balance'), 0)} {clean_text(coin, 'coins')}")


async def main_async(accounts, proxies, sleep_secs):
    cycle = 1
    while True:
        log_yellow(f"Starting automation cycle number {clean_text(cycle, 0)}")

        for index, init_data in enumerate(accounts):
            if index > 0:
                print()

            proxy_line = get_proxy(proxies, index)
            proxy_url = normalize_proxy(proxy_line) if proxy_line else None
            if proxy_url:
                log_yellow(f"Using proxy {mask_proxy(proxy_url)}")

            await process_account(init_data, proxy_url, index + 1)

        log_yellow(f"Automation cycle number {clean_text(cycle, 0)} is complete")
        cycle += 1
        countdown(sleep_secs)
        show_banner(MY_PROJECT)


def countdown(seconds):
    for remaining in range(int(seconds), 0, -1):
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        rest = remaining % 60
        print(f"\r{YELLOW}{BOLD}Next cycle starts in {hours:02d}:{minutes:02d}:{rest:02d}{RESET}", end="", flush=True)
        time.sleep(1)
    print()


def main():
    show_banner(MY_PROJECT)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = load_config()
    sleep_secs = config.get("settings", {}).get("sleep_seconds", 3600)
    accounts = load_data()
    proxies = load_proxies()
    load_session_cache()
    asyncio.run(main_async(accounts, proxies, sleep_secs))


if __name__ == "__main__":
    main()
