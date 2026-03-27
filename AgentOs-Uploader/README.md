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

本目录为仓库根下的**独立包**（与 `AgentOs-OpenStoryline/` 同级），构建上下文为**仓库根目录**。

- 镜像由 [`Dockerfile`](./Dockerfile) 构建，`docker-compose.yml` 中服务名为 **`uploader`**；进程入口为 **`uploader.main:app`**（[`main.py`](./main.py)）。
- **鉴权**：独立服务内仅校验 **JWT**（与主站共用 `SECRET_KEY` / `ALGORITHM`），**不**每次请求查库；停用用户后已签发 token 在过期前仍可能调用 uploader。
- **存储**：必须与主 API 挂载**同一** `storage` 卷（含 `uploader/cookies`、`uploader/videos`），否则无法读取成片路径与账号数据。
- **横向扩展**：扫码登录与持久化会话状态在**进程内存**中；多副本会导致会话落到错误实例，请保持 **uploader 单副本**，或后续引入 sticky session / 共享会话存储。
- **本地运行**：在仓库根目录执行 `PYTHONPATH=backend:. uvicorn uploader.main:app --reload --port 8002`（需已安装 `backend/requirements-uploader.txt` 与 `playwright install chromium`）。
- **本地 pytest**：在 `backend/` 目录运行测试；`pytest.ini` 已配置 `pythonpath` 以解析顶层 `uploader` 包。含 uploader 的测试需：`pip install -r requirements-uploader.txt`。
