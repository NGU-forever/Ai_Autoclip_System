# Uploader 模块

从 [social-auto-upload](https://github.com/dreammis/social-auto-upload) 迁移的抖音、视频号视频上传核心逻辑。

## 目录结构

```
uploader/
├── conf.py              # 配置 (BASE_DIR, LOCAL_CHROME_PATH)
├── douyin_uploader/     # 抖音上传
├── tencent_uploader/     # 视频号上传
├── utils/                # 工具 (stealth, files_times, constant, log)
│   └── stealth.min.js    # 反检测脚本
└── README.md
```

## 依赖

```bash
pip install playwright
playwright install chromium
```

## 配置

在 `conf.py` / 环境变量（见项目根目录 `Settings`）中可设置：
- `LOCAL_CHROME_PATH`: 本地 Chrome 路径（可选，提高成功率）
- `LOCAL_CHROME_HEADLESS`: 是否无头模式

### Docker / 网络说明

扫码登录与持久化会话会由后端用 **Playwright** 打开 `https://creator.douyin.com/` 等页面。若容器内出现 `net::ERR_CONNECTION_CLOSED` 等错误，多为**容器到目标站点的网络不可达**（地域、机房 IP、防火墙）。请先在容器或同等网络下确认能访问对应域名。

## 使用示例

```python
import asyncio
from uploader import douyin_setup, DouYinVideo, weixin_setup, TencentVideo
from uploader.utils import get_title_and_hashtags, TencentZoneTypes

async def upload_douyin():
    account_file = "backend/cookiesFile/douyin_xxx.json"
    await douyin_setup(account_file, handle=True)
    title, tags = get_title_and_hashtags("video.mp4")  # 需同名 .txt
    app = DouYinVideo(title, "video.mp4", tags, 0, account_file)
    await app.main()

async def upload_tencent():
    account_file = "backend/cookiesFile/xxx.json"
    await weixin_setup(account_file, handle=True)
    app = TencentVideo("标题", "video.mp4", ["话题"], 0, account_file,
                       category=TencentZoneTypes.LIFESTYLE.value)
    await app.main()

asyncio.run(upload_douyin())
```

## Cookie 获取

首次使用需扫码登录获取 Cookie：
- 抖音：访问 https://creator.douyin.com/ 扫码，保存 storage_state 到 cookiesFile
- 视频号：访问 https://channels.weixin.qq.com 扫码，保存 storage_state 到 cookiesFile

## Docker 独立服务（生产 Compose）

本目录为**独立构建上下文**（与 `AgentOs-OpenStoryline/` 相同：`docker-compose.yml` 中 `context: ./AgentOs-Uploader`），镜像内包含 **FastAPI + 分发 SPA**（`web/dist`）。

- 镜像由 [`Dockerfile`](./Dockerfile) 多阶段构建；进程入口为 **`uploader.main:app`**（[`main.py`](./main.py)），静态页与 API 同端口（默认 **8002**）。
- **内嵌 `src/`**：JWT 校验与配置与主 `backend/src` 对齐；部署时需与主站使用相同 **`SECRET_KEY`**（及算法），否则 token 无法通过校验。
- **鉴权**：仅校验 **JWT**，不查库；停用用户后已签发 token 在过期前仍可能调用 uploader。
- **存储**：与主 API 挂载**同一** `storage` 卷（含 `uploader/cookies`、`uploader/videos`）。
- **横向扩展**：扫码登录与持久化会话在**进程内存**中；多副本需 sticky session 或共享会话存储，否则请保持 **uploader 单副本**。
- **本地运行（API）**：仓库根目录若存在符号链接 `uploader` → `AgentOs-Uploader`，可执行 `PYTHONPATH=.:AgentOs-Uploader uvicorn uploader.main:app --reload --port 8002`；否则用 `docker compose` 或自行将 `AgentOs-Uploader` 加入 `PYTHONPATH` 并保证包名 `uploader` 可解析。依赖见本目录 [`requirements.txt`](./requirements.txt)，并执行 `playwright install chromium`。
- **本地运行（分发前端）**：`cd web && npm install && npm run dev`（默认代理 `/api` 到 `localhost:8002`）。生产环境由 FastAPI 托管 `web/dist`。
- **本地 pytest**：在 `backend/` 运行；`conftest` 会在无顶层 `uploader` 链接时注入 `AgentOs-Uploader` 包路径。
