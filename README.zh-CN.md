# Telegram qBittorrent 下载机器人（简体中文）

这是一个轻量级、自托管的 Telegram 机器人：通过 **Jackett 搜索你自行配置的资源站索引器**，把你选择的资源提交给**现有 qBittorrent** 下载器。它不负责 Jellyfin 媒体库管理、不刮削元数据、不重命名或移动媒体文件，也不提供订阅管理。

英文说明：[README.md](README.md)

## 1. 功能

- `/search 关键词`：通过 Jackett 的 Torznab `all` 接口搜索，最多保留 `SEARCH_LIMIT` 条结果；Telegram 每页显示 10 条，可用上一页/下一页按钮翻页。
- 搜索结果以 Telegram 按钮展示，点击后才提交给 qBittorrent。
- 直接发送磁力链接：提交给 qBittorrent。
- 发送直接 HTTP(S) 种子下载地址：让 qBittorrent 自行获取。**这不等于通用网页解析器**。
- 发送 `.torrent` 文件：上传给 qBittorrent。
- `/list`：查看当前 qBittorrent 下载任务（最多显示 20 条）。
- 下载完成通知：定期查询 qBittorrent，当任务进度从低于 100% 变为 100% 时通知白名单用户。
- 用户权限：只有配置在 `TELEGRAM_ALLOWED_USER_IDS` 中的 Telegram 数字用户 ID 可以操作机器人。

## 2. 组件和网络关系

- **Jackett**：只搜索你手动添加并启用的索引站点；它不会自动提供站点账号，也不会凭空发现资源站。
- **Telegram Bot**：使用 Long Polling（长轮询），不需要从公网访问家庭网络的 Webhook 端口。
- **qBittorrent**：继续使用你现有的下载器，通过 WebUI API 接收任务和提供状态。
- **Jellyfin**：本项目不会修改 Jellyfin 配置，也不会移动或整理你现有的媒体目录。

机器人和 Jackett 处于同一个 Compose 网络，机器人通过 `http://jackett:9117` 访问 Jackett。机器人通过 `QBIT_BASE_URL` 访问现有 qBittorrent。

## 3. 文件结构和存储分离

如果你的 LXC 已经把系统盘和媒体 HDD 分开，建议将本项目整个目录放在 **LXC 系统盘**。这样默认相对路径 `./data/jackett`、`./data/bot` 和 `./data/jackett-downloads` 都会落在系统盘，用来保存 Jackett 配置和机器人状态。**不要把这些配置目录指向 `/data/media`。**

机器人通过 qBittorrent WebUI API 添加任务，不需要挂载媒体目录。保持你现有 qBittorrent 容器的下载保存路径配置，让它继续映射到 HDD 上的 `/data/media` 即可。实际下载文件由 qBittorrent 写入该目录，机器人不直接读写媒体文件，也不需要修改 Jellyfin 或它现有的媒体挂载。

示例目录结构（`/opt/telegram-qbit-bot` 只是示例，请替换成你实际 clone 仓库的位置）：

```text
LXC 系统盘
└── /opt/telegram-qbit-bot/
    ├── docker-compose.yml
    ├── .env
    └── data/
        ├── jackett/             # Jackett 配置和索引站点设置
        ├── jackett-downloads/   # Jackett 可选 blackhole 工作流目录
        └── bot/                 # 机器人状态文件

LXC 内挂载的 HDD
└── /data/media/                 # 现有 qBittorrent 下载/保存目录
```

注意：`JACKETT_DOWNLOADS_PATH` 是 Jackett 可选 blackhole 工作流使用的目录，不是 qBittorrent 的下载目录。不使用该工作流时，保持默认在系统盘即可。

## 3. 文件结构

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

运行数据保存在 `JACKETT_CONFIG_PATH`、`JACKETT_DOWNLOADS_PATH` 和 `BOT_DATA_PATH` 指定的宿主机目录。只要本项目目录放在系统盘，默认路径就会将这些配置和状态保存在系统盘。真正使用的 `.env` 和运行数据已加入 Git 忽略规则，不应提交到仓库。

## 4. 所有需要配置的参数

部署前，将 `.env.example` 复制为 `.env`，再按下表修改。Docker Compose 默认从 `docker-compose.yml` 所在目录读取 `.env`。

| 参数 | 是否必填 | 默认值 / 示例 | 作用及填写说明 |
|---|---:|---|---|
| `TZ` | 否 | `Asia/Shanghai` | 容器时区，影响日志时间等。填写 IANA 时区，例如 `Asia/Shanghai`、`Asia/Tokyo`。 |
| `PUID` | 否 | `1000` | LinuxServer Jackett 容器访问挂载目录时使用的宿主机 UID。若目录属主不是 1000，可改为目录属主 UID。 |
| `PGID` | 否 | `1000` | Jackett 使用的宿主机 GID。按挂载目录所属用户组调整。 |
| `TELEGRAM_BOT_TOKEN` | **是** | 占位符 | 在 Telegram 官方机器人 `@BotFather` 创建机器人后取得的 Token。等同密码，不能公开或提交 Git。 |
| `TELEGRAM_ALLOWED_USER_IDS` | **是** | 占位符 | 允许使用机器人的 Telegram **数字用户 ID**，多个 ID 用英文逗号分隔，例如 `123456789,987654321`。不是用户名，也不是手机号。白名单内用户可以搜索、添加下载及选择资源。 |
| `QBIT_BASE_URL` | **是** | `http://192.168.50.x:8080` | 现有 qBittorrent WebUI/API 的基础地址，必须能从**机器人容器内部**访问。要包含协议和端口，但不要添加 `/api/v2`。通常不能填 `localhost`，因为容器里的 localhost 指向机器人容器自身。 |
| `QBIT_USERNAME` | **是** | 占位符 | qBittorrent WebUI 登录用户名。 |
| `QBIT_PASSWORD` | **是** | 占位符 | qBittorrent WebUI 登录密码。 |
| `QBIT_CATEGORY` | 否 | `telegram-bot` | 机器人添加任务时给 qBittorrent 设置的分类名称。它是分类标签，不是下载目录路径。 |
| `JACKETT_API_KEY` | **是** | 占位符 | Jackett Dashboard 页面显示的 API Key。不要公开。 |
| `JACKETT_WEBUI_PORT` | 否 | `9117` | Jackett WebUI 映射到 LXC 宿主机回环地址的端口。容器内部固定监听 9117。默认映射为 `127.0.0.1:<此端口>:9117`，局域网其他设备不能直接访问。 |
| `JACKETT_CONFIG_PATH` | 否 | `./data/jackett` | Jackett 配置和索引站点设置的宿主机持久化目录。不要随意删除。相对路径以 Compose 项目目录为基准。 |
| `JACKETT_DOWNLOADS_PATH` | 否 | `./data/jackett-downloads` | 映射到 Jackett 容器内 `/downloads` 的宿主机目录，供可选的 Jackett blackhole 等下载工作流使用。机器人正常调用 Torznab 搜索并不依赖此目录。 |
| `BOT_DATA_PATH` | 否 | `./data/bot` | 机器人状态文件的宿主机持久化目录，包括下载完成通知的进度记录。必须允许机器人容器运行用户写入。 |
| `SEARCH_LIMIT` | 否 | `20` | 每次搜索最多保留多少条结果。程序会限制在 1–20 条之间；Telegram 每页显示 10 条。 |
| `POLL_INTERVAL_SECONDS` | 否 | `60` | 机器人轮询 qBittorrent 检查下载完成状态的间隔秒数。程序强制最小值为 20 秒。 |

### 特别注意：机器人如何连接另一个 Docker 项目里的 qBittorrent

因为 qBittorrent 在**另一个容器或 Compose 项目**中，机器人容器里的 `http://localhost:8080` 指向机器人自身，并不是 qBittorrent。

有两种连接方式：

1. **通过 LXC 宿主机发布的 WebUI 端口访问。** 将 `QBIT_BASE_URL` 设置为机器人容器可访问的地址，例如 `http://<LXC局域网IP>:<qBittorrent已发布端口>`。qBittorrent 端口必须发布在机器人容器能够访问的宿主机网卡上；如果只绑定到宿主机 `127.0.0.1`，通常无法从 bridge 网络里的机器人容器访问。
2. **两个 Compose 项目加入同一个外部 Docker 网络。** 将现有 qBittorrent 服务和本项目加入同一个 user-defined external network，然后把 `QBIT_BASE_URL` 设置为 `http://<qBittorrent服务名或容器名>:<容器内WebUI端口>`。确保该服务名在共享网络中可解析。

不要把 qBittorrent WebUI 暴露到公网。优先使用私有 Docker 网络或仅限局域网访问，并设置强密码。

## 5. 部署步骤

在包含 `docker-compose.yml` 的目录中执行：

```bash
cp .env.example .env
# 编辑 .env，替换所有 REPLACE_WITH_* 占位值
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs -f telegram-qbit-bot
```

启动前，按需创建宿主机挂载目录，并确保机器人容器运行用户有权限写入 `BOT_DATA_PATH`。当前 Dockerfile 默认以 UID/GID 10001 运行机器人；如果宿主机 bind mount 目录不允许该用户写入，需要调整目录属主/权限，或修改 Compose 中机器人容器的运行用户。Jackett 的目录权限由 `PUID`/`PGID` 控制。

### 打开 Jackett WebUI

默认端口只绑定在 LXC 宿主机的回环地址。若要从自己的电脑访问，可在电脑上建立 SSH 隧道：

```bash
ssh -L 9117:127.0.0.1:9117 <SSH用户名>@<LXC局域网IP>
```

然后在电脑浏览器打开 `http://127.0.0.1:9117`。也可以自行修改端口绑定，但要先理解相应的局域网暴露风险。

进入 Jackett 后：

1. 在 Dashboard 中复制 API Key，填入 `JACKETT_API_KEY`。
2. 添加并配置你有权使用的资源站索引器。
3. 先在 Jackett 页面逐个测试索引器，再测试机器人搜索。

通过 Telegram 的 `@BotFather` 创建机器人；使用可信的 ID 查询机器人获取自己的数字用户 ID，填写白名单后，给机器人发送 `/start`。

## 6. 机器人命令和使用方式

| 操作 | 效果 |
|---|---|
| `/start` | 显示基本使用说明。 |
| `/search 电影名称` | 搜索 Jackett 已配置的索引站点，并展示可选结果。 |
| 点击 `Download #n` | 将对应结果的磁力链接或直接种子下载地址提交给 qBittorrent。 |
| 发送 `magnet:` 链接 | 添加磁力下载任务。 |
| 发送直接的 `http://` 或 `https://` 种子地址 | 让 qBittorrent 获取该地址。 |
| 发送 `.torrent` 文件 | 上传种子文件给 qBittorrent。 |
| `/list` | 查看当前任务和进度。 |

## 7. 当前版本的限制和行为

- 这是第一版基础实现，不是经过完整安全加固的成熟产品。请先用不重要的任务测试。
- 搜索结果取决于你在 Jackett 中配置的索引站点。站点可用性、登录状态、Cookie、访问频率限制和资源质量均由外部站点决定。
- 部分私有站需要认证或带 passkey 的下载地址。可在 Jackett 支持的范围内配置，切勿公开这些地址或凭据。
- 机器人不会解析任意影视详情网页，不会爬取通用搜索引擎，也不会从普通网页中猜测下载地址。
- 搜索结果按做种数降序、发布时间降序排列；做种数未知的结果排在已知做种数的结果之后。两项相同时保留 Jackett 原始顺序。机器人最多保留 `SEARCH_LIMIT` 条结果，Telegram 每页显示 10 条。Jackett 提供发布时间和索引站点名称时会一并显示。
- 搜索结果按钮缓存于机器人内存中，机器人重启前产生的旧按钮将失效。
- 完成通知依赖检测到任务进度从低于 100% 变为 100%。机器人首次观察到时已经完成的任务不会触发通知；如果任务完成期间机器人离线，也可能漏报。
- 当前只有 `/list`，还没有暂停、继续、删除任务或单任务进度查询命令。
- `.torrent` 文件会直接转交 qBittorrent，机器人不会检查种子文件内容。
- 所有白名单用户共用同一个 qBittorrent 账号和同一个任务分类。

## 8. 安全和隐私

- 不要提交真正使用的 `.env`。不要在聊天或公开仓库中发送 Bot Token、API Key、密码、Tracker passkey 或私有下载链接。
- 白名单应尽量收紧。被加入白名单的人可以通过你的 qBittorrent 账号搜索并创建下载任务。
- 不要将 Jackett 或 qBittorrent WebUI 暴露到公网。
- 使用强且唯一的密码，并及时更新 LXC、Docker 镜像和应用。
- 只搜索、下载和分享你有权访问和使用的内容。
