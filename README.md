# Telegram qBittorrent Bot

A lightweight, self-hosted Telegram bot that searches the Jackett indexers you configure and submits selected torrents to an **existing qBittorrent** instance. It does not manage Jellyfin, rename or move media, scrape metadata, or create subscriptions.

- 简体中文说明：[README.zh-CN.md](README.zh-CN.md)

## 1. What it does

- `/search <keyword>`: search Jackett's Torznab `all` endpoint and retain up to `SEARCH_LIMIT` results, displayed 10 per page with Previous/Next buttons.
- Inline buttons: submit a selected result to qBittorrent.
- Send a magnet URI: submit it to qBittorrent.
- Send a direct HTTP(S) torrent URL: ask qBittorrent to fetch it. This is **not** a general web-page parser.
- Send a `.torrent` document: upload it to qBittorrent.
- `/list`: show up to 20 current qBittorrent tasks.
- Completion notifications: poll qBittorrent and notify allowlisted users when a task's progress changes from below 100% to 100%.
- Access control: only Telegram numeric user IDs in `TELEGRAM_ALLOWED_USER_IDS` can use the bot.

## 2. Components and network flow

- **Jackett** searches only the indexers you add and enable. It does not discover or provide tracker accounts for you.
- **Telegram bot** uses Telegram long polling, so it does not need an inbound webhook port.
- **qBittorrent** remains your existing downloader and is accessed through its WebUI API.
- **Jellyfin** and your existing media/download directories are not modified by this stack.

The bot and Jackett share the Compose network. The bot reaches Jackett at `http://jackett:9117`. The bot reaches qBittorrent using `QBIT_BASE_URL`.

## 3. Files and storage layout

For a split system-disk / media-disk setup, keep this Compose project directory on the LXC system disk. The default relative paths (`./data/jackett`, `./data/bot`, and `./data/jackett-downloads`) will then keep Jackett configuration and bot state on the system disk. **Do not point these paths at `/data/media`.**

The bot does not need a media-directory bind mount: it submits tasks through qBittorrent's WebUI API. Keep the existing qBittorrent container's download/save path mapped to your HDD-backed `/data/media` directory. qBittorrent—not this bot—writes the downloaded media to that location. No changes to Jellyfin or its existing media mount are required.

Example layout (the project path is illustrative; use the actual directory where you cloned the repository):

```text
LXC system disk
└── /opt/telegram-qbit-bot/
    ├── docker-compose.yml
    ├── .env
    └── data/
        ├── jackett/             # Jackett settings and indexers
        ├── jackett-downloads/   # Optional Jackett blackhole workflow
        └── bot/                 # Bot state

HDD mounted in LXC
└── /data/media/                 # Existing qBittorrent download/save location
```

The `JACKETT_DOWNLOADS_PATH` mount is only for Jackett's optional blackhole workflow; it is not qBittorrent's download folder. You can leave it at the default on the system disk if you do not use that workflow.

## 3. Files

```text
telegram-qbit-bot/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── README.zh-CN.md
└── bot/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py
```

Runtime data is stored under the paths configured by `JACKETT_CONFIG_PATH`, `JACKETT_DOWNLOADS_PATH`, and `BOT_DATA_PATH`. With the project directory on the system disk, the defaults keep these files there. The real `.env` file and runtime data are ignored by Git.

## 4. All configurable parameters

Copy `.env.example` to `.env` and replace the placeholders. Compose reads `.env` from the directory containing `docker-compose.yml`.

| Variable | Required? | Default / example | Meaning and what to enter |
|---|---:|---|---|
| `TZ` | No | `Asia/Shanghai` | Time zone used by containers and log timestamps. Use an IANA time zone such as `Asia/Shanghai` or `Asia/Tokyo`. |
| `PUID` | No | `1000` | Linux UID used by the LinuxServer Jackett container for file access. Set to the owner UID of the host folders you mount, if needed. |
| `PGID` | No | `1000` | Linux GID used by Jackett. Set to the owner group of the host folders you mount, if needed. |
| `TELEGRAM_BOT_TOKEN` | **Yes** | placeholder | Token issued by Telegram's official `@BotFather` after creating a bot. Treat it as a password. |
| `TELEGRAM_ALLOWED_USER_IDS` | **Yes** | placeholder | Numeric Telegram user ID(s), comma-separated, e.g. `123456789,987654321`. This is **not** a username or phone number. Only listed IDs may run commands, send links/files, or select results. |
| `QBIT_BASE_URL` | **Yes** | `http://192.168.50.x:8080` | Base URL of the existing qBittorrent WebUI/API, reachable **from inside the bot container**. Include scheme and port; do not append `/api/v2`. Do not use `localhost` unless qBittorrent shares the bot container's network namespace. |
| `QBIT_USERNAME` | **Yes** | placeholder | qBittorrent WebUI username. |
| `QBIT_PASSWORD` | **Yes** | placeholder | qBittorrent WebUI password. |
| `QBIT_CATEGORY` | No | `telegram-bot` | qBittorrent category assigned to tasks added by the bot. It is a category label, not a filesystem path. |
| `JACKETT_API_KEY` | **Yes** | placeholder | API key shown in Jackett's dashboard. Keep it private. |
| `JACKETT_WEBUI_PORT` | No | `9117` | Host-side loopback port for Jackett's WebUI. The container listens on port 9117. Published as `127.0.0.1:<value>:9117`, not exposed to the LAN by default. |
| `JACKETT_CONFIG_PATH` | No | `./data/jackett` | Host path for Jackett configuration and indexer settings. Keep this persistent. Relative paths are resolved from the Compose project directory. |
| `JACKETT_DOWNLOADS_PATH` | No | `./data/jackett-downloads` | Host path mounted at `/downloads` inside Jackett, for optional Jackett blackhole/download workflows. The bot's normal Torznab search does not require this directory. |
| `BOT_DATA_PATH` | No | `./data/bot` | Host path for bot state, including completion-notification progress history. Must be writable by the bot container's runtime user. |
| `SEARCH_LIMIT` | No | `20` | Maximum number of results retained per search. Code clamps this value to 1–20; Telegram displays 10 results per page. |
| `POLL_INTERVAL_SECONDS` | No | `60` | Seconds between qBittorrent task polls for completion notifications. Code enforces a minimum of 20 seconds. |

### Important qBittorrent connectivity note

Because qBittorrent runs in a **different container / Compose project**, `http://localhost:8080` inside this bot container would refer to the bot container itself, not qBittorrent.

Choose one of these approaches:

1. **Use a published qBittorrent WebUI port on the LXC host.** Set `QBIT_BASE_URL` to an address reachable from the bot container, such as `http://<LXC-LAN-IP>:<published-port>`. The qBittorrent port must be published on an interface reachable from the bot container; a host binding limited to `127.0.0.1` is generally not reachable from a bridge-network container.
2. **Use a shared external Docker network.** Connect the qBittorrent service and this stack to the same user-defined external network, then set `QBIT_BASE_URL` to `http://<qBittorrent-service-or-container-name>:<container-WebUI-port>`. Ensure the service name is resolvable on that network.

Do not expose the qBittorrent WebUI to the public Internet. Prefer a private Docker network or LAN-only access and use a strong WebUI password.

## 5. Deployment

Run these commands from the directory containing `docker-compose.yml`:

```bash
cp .env.example .env
# Edit .env and replace every REPLACE_WITH_* value.
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs -f telegram-qbit-bot
```

Before starting, create the host directories if necessary and ensure the bot data directory is writable by the container process. The bot image runs as UID/GID 10001 by default; if your host bind-mounted `BOT_DATA_PATH` is not writable by that user, either change its ownership/permissions or adapt the container user in the Compose file. Jackett uses `PUID`/`PGID` for its mounted directories.

### Open Jackett WebUI

The default mapping binds Jackett to the LXC host's loopback interface only. To open it from your own computer, create an SSH tunnel to the LXC:

```bash
ssh -L 9117:127.0.0.1:9117 <user>@<LXC-LAN-IP>
```

Then open `http://127.0.0.1:9117` on your computer. Alternatively, deliberately change the port binding if you understand the LAN exposure implications.

In Jackett:

1. Open its dashboard and copy the API key into `JACKETT_API_KEY`.
2. Add and configure the indexers you are authorized to use.
3. Test each indexer in Jackett before testing bot search.

Create the Telegram bot with `@BotFather`, obtain your numeric Telegram user ID using a trusted ID utility bot, fill the allowlist, and send `/start` to your bot.

## 6. Bot commands and usage

| Action | Result |
|---|---|
| `/start` | Show basic usage. |
| `/search movie title` | Search configured Jackett indexers and display selectable results. |
| Tap `Download #n` | Submit that result's magnet or direct torrent URL to qBittorrent. |
| Send a `magnet:` URI | Add the magnet task. |
| Send a direct `http://` or `https://` torrent URL | Ask qBittorrent to fetch the URL. |
| Send a `.torrent` file | Upload the torrent file to qBittorrent. |
| `/list` | Show current tasks and progress. |

## 7. Current limitations and behavior

- This is a starter implementation, not a hardened production application. Test it with non-critical tasks first.
- Search depends on the indexers you configure in Jackett. Indexer availability, login, cookies, rate limits, and result quality are external to this bot.
- Some private trackers require authentication or passkey-bearing download URLs. Configure them in Jackett where supported, and never publish those URLs or credentials.
- The bot does not parse arbitrary detail pages, scrape search engines, or infer download links from a web page.
- Search results are sorted by seeders descending, then publication date descending. Results with unknown seeder counts sort after results with known counts; ties retain Jackett's original order. The bot retains up to `SEARCH_LIMIT` results and displays 10 per Telegram page. Publication dates and indexer names are shown when Jackett provides them.
- The search result cache is in memory. Buttons from before a bot restart will no longer work.
- Completion notifications are based on a detected progress transition from below 100% to 100%. Tasks already at 100% when first observed are treated as existing and do not trigger a notification. If the bot is offline while a task completes, the transition may be missed.
- The bot currently provides `/list` but not pause, resume, delete, or per-task progress commands.
- The `.torrent` upload is passed to qBittorrent; the bot does not inspect the torrent contents.
- The bot uses one configured qBittorrent account and one category for all authorized users.

## 8. Security and privacy

- Never commit the real `.env` file. Do not send bot tokens, API keys, passwords, tracker passkeys, or private download URLs in chat.
- Keep the Telegram allowlist restrictive. Anyone added to it can search and create downloads through your qBittorrent account.
- Keep Jackett and qBittorrent WebUIs off the public Internet.
- Use strong unique passwords and keep the LXC, Docker images, and applications updated.
- Only access, download, and share content you are legally authorized to use.
