<div align="center">

<img width="100%" alt="header" src="https://capsule-render.vercel.app/api?type=waving&height=210&text=Mango%20Farm%20Bot&fontAlign=50&fontAlignY=36&fontSize=56&desc=Daily%20Check-In%20%7C%20Auto%20Farm%20Auto%20%7C%20Watch%20ads%20%7C%20Auto%20Games%20%7C%20Multi-Account&descAlign=50&descAlignY=58"/>

<img alt="typing" src="https://readme-typing-svg.demolab.com?font=Inter&size=18&duration=3000&pause=650&center=true&vCenter=true&width=900&lines=Auto+Farm+%7C+One+Hour+Cycle+Harvested+And+Restarted;Auto+Ads+%7C+Credited+Until+The+Server+Daily+Limit;Auto+Tasks+%7C+Channel+And+Partner+Rewards+Claimed;Auto+Games+%7C+Tic+Tac+Toe+Mines+And+Spin+Wheel;Auto+Promo+Code+And+Referral+Reporting;Session+Cache+%7C+Runs+On+After+initData+Expires"/>

<p>
  <img alt="python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"/>
  <img alt="platform" src="https://img.shields.io/badge/Platform-Mango%20Farm%20Miniapp-111111"/>
  <img alt="multi-account" src="https://img.shields.io/badge/Multi--Account-Supported-111111"/>
  <img alt="proxy" src="https://img.shields.io/badge/Proxy-Supported-111111"/>
  <img alt="author" src="https://img.shields.io/badge/by-Yuurisandesu-111111"/>
</p>

<p>
  <b>Pepefarm Bot</b> is a full automation bot for the Mango Farm Telegram Miniapp of <code>@PepefarmApp_bot</code>.<br/>
  It handles the complete cycle for every account: exchanging the Telegram <code>initData</code> for the session the server issues, caching that session in <code>device.json</code> so the account keeps working after its <code>initData</code> expires, reporting the profile, harvesting and restarting the hourly farm cycle, claiming reward advertisements up to the server daily limit, completing every account task, playing tic tac toe, mines and the spin wheel up to the daily limits of the server, redeeming a promo code when one is configured, reporting the referral state, and printing the final balance, all running automatically across multiple accounts with proxy support, masked proxy logging, and a live countdown between cycles.<br/>
  Built and distributed by <b>Yuurisandesu</b>.
</p>

</div>

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Bot](#running-the-bot)
- [Features](#features)
- [File Structure](#file-structure)
- [Disclaimer](#disclaimer)

---

## Requirements

- Python `3.12+`
- Git

---

## Installation

**Clone the repository:**

```bash
git clone https://github.com/Yuurisan-N1/Pepefarm-Miniapp.git
cd Pepefarm-Miniapp
```

**Install dependencies:**

```bash
pip install aiohttp yuurisan
```

---

## Configuration

### 1. Accounts (data.txt)

Fill `data.txt` with Telegram WebApp `initData` for each account, one per line:

```
user=%7B%22id%22...&hash=abc123
user=%7B%22id%22...&hash=def456
```

> `initData` is obtained from the browser DevTools while the miniapp is open on Telegram Web, or from a WebView session of the bot. The credential line is the raw `initData` string as the miniapp receives it: the Telegram id, the username and the profile of the account all live inside that string, so one line is enough. A doubled encoding or a leading `tgWebAppData=` prefix is accepted as well. Accounts are processed sequentially and one blank line is printed between accounts to keep the log readable.

### 2. Proxy (proxy.txt)

Fill `proxy.txt` with proxies, one per line (optional, leave empty to run without proxy):

```
host:port
host:port:user:pass
http://user:pass@host:port
```

Proxies are assigned to accounts by index in round-robin order, so when there are fewer proxies than accounts the same proxy is reused for the remaining accounts. When `proxy.txt` is missing or empty the bot runs without any proxy. Credentials are never printed, the log only shows a masked form such as `http://user:pass@74*****81:10000`.

### 3. Bot Settings (config.json)

`sleep_seconds` controls how many seconds the bot waits between cycles. If `config.json` is missing, the bot falls back to a default of `3600` seconds.

### 4. Session Cache (device.json)

`device.json` is created automatically on the first run and is never part of the download. It stores one record per Telegram account, keyed by the telegram id, and holds the identity the server issued for that account: the account email, the derived account password, the refresh token and the access token expiry. Every later run reuses the same record, and the access token is refreshed in place whenever it has expired. When the `initData` of an account is no longer accepted by the server, the bot falls back to the cached identity of that account and keeps the whole cycle running, so a line only becomes useless once its cached session is gone as well. Delete the file only when a fresh session is really wanted.

> `device.json` holds a live session credential, so treat it like a password and never share it.

---

## Running the Bot

```bash
python bot.py
```

Press `Ctrl+C` at any time to stop the bot cleanly.

---

## Features

### Account Loading
Every line of `data.txt` is one account. The bot posts the `initData` to the authentication endpoint of the miniapp, receives the account identity the server derives from it, exchanges that identity for a session token, and logs the account name and coin balance before doing any work. When the server rejects the `initData`, the cached identity of that account is loaded instead and the cycle keeps running, which is reported once in the log.

### Force Join Gate
The required channel list is read from the server at the start of every account. When the server reports that the subscription is still missing, the account stops after one yellow line, which is the same behaviour the miniapp itself shows, and no reward is claimed for it.

### Auto Farm
The bot claims the farm cycle when the server says it is ready, otherwise it reports how long the field still needs to grow and starts a new cycle when the account has no active one. Every credit is taken from the server answer, so nothing is reported that the server did not really pay.

### Auto Ads
Reward advertisements are claimed one by one until the server daily limit is reached. The credited amount of every advertisement comes from the server answer, a cooldown is waited out using the seconds the server returns, and a reached daily limit, a cooldown that never ends and an advertisement the server refuses are each reported once instead of being retried blindly. The run closes with the number of advertisements credited and the total the server paid.

### Auto Tasks
Every active task of the account is completed through the server, including the channel tasks and the partner tasks, and the run closes with one aggregate line carrying the total reward. An account with nothing left to do prints a single green line instead of a list of skips.

### Auto Games
The game state is read first, so the daily limits are always the ones the server reports. Tic tac toe rounds are played to the end of the board, mines rounds reveal safe tiles and cash out the accumulated pot, and the spin wheel spins and claims the prize of the segment the server returns. An unclaimed prize that was left behind by an earlier session is claimed as well. The run closes with one aggregate line carrying the total credited by the games.

### Promo Code
The promo endpoint is wired into the bot for a code the operator configures, and the credited reward is reported in green. The code itself is never invented by the bot.

### Referral Reporting
The referral list of the account is read from the server and reported with the number of entries it holds, together with the referral earnings the profile carries.

### Final Balance Pass
After all features are done the bot reads the fresh account state once more and prints the final coin balance for the account.

### Multi Account
All accounts in `data.txt` are processed sequentially within every cycle, with one blank line between accounts so every account block stays easy to read.

### Proxy Support
Proxies are loaded from `proxy.txt`, normalized to a full URL and assigned to accounts by position in round-robin order. Proxy credentials are masked in log output. Running without proxies is fully supported.

### Auto Countdown
After all accounts complete a cycle, the bot displays a live `HH:MM:SS` countdown in place until the next cycle starts, then prints the banner again and begins the next cycle.

---

## File Structure

```text
Pepefarm-Miniapp/
├── bot.py             # Main bot, full cycle automation
├── config.json        # Sleep duration between cycles
├── data.txt           # Account initData, one per line
├── proxy.txt          # Proxy list, one per line (optional)
├── LICENSE            # Apache License 2.0
├── README.md          # This file
└── utils/
    ├── __init__.py    # Package marker
    └── banner.py      # Banner using yuurisan module
```

---

## Disclaimer

This tool is built for educational and technical exploration purposes. Use it wisely and at your own responsibility.

---

<div align="center">
<img width="100%" alt="footer" src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer"/>
</div>
