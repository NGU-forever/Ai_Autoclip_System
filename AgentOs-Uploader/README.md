# AgentOS Uploader

> 专为抖音、视频号、小红书等平台设计的视频自动上传服务，基于 Playwright 实现的自动化上传解决方案，支持多平台视频发布、账号管理、会话持久化等功能。

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

## 📖 项目概述

AgentOS Uploader 是一个功能完整的视频自动上传平台，专为需要批量发布视频到多个社交平台的用户设计。它通过浏览器自动化技术实现视频上传流程，支持完整的账号管理和会话持久化，让你能够轻松管理多个平台的视频发布任务。

## ✨ 核心特性

### 多平台支持
- 📱 **抖音**：全自动视频上传、标题编辑、标签添加、封面设置
- 📺 **视频号**：支持视频发布、状态监控和内容管理
- 📱 **小红书**：内容发布、账号管理和互动数据监控

### 账号管理
- 📋 多账号统一管理，支持不同平台的账号配置
- 🔐 自动Cookie验证和续期机制
- 🔄 账号状态实时监控和异常检测
- 📊 详细的账号使用统计和健康度报告

### 会话持久化
- 🌐 浏览器实例池化，提高资源利用率
- 🔄 二维码自动刷新和登录状态保持
- 💾 会话数据持久化存储和备份
- 🔄 智能会话恢复机制

### 任务管理
- 📋 发布任务队列，支持优先级设置和并发控制
- 📊 状态实时监控和进度跟踪
- 📧 WebSocket实时状态通知
- 📝 详细的任务日志和错误记录

## 🚀 快速开始

### 环境准备

#### 1. 系统要求

- Python 3.8+
- Docker (用于启动 PostgreSQL 和 Redis)
- Chrome 浏览器（或 Chromium，用于 Playwright）

#### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/NGU-forever/Ai_Autoclip_System.git
cd AgentOs-Uploader

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装Python依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium
```

#### 3. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量（至少修改 SECRET_KEY）
nano .env
```

**环境变量说明：**

| 变量名 | 描述 | 默认值 | 必填 |
|--------|------|--------|------|
| `DATABASE_URL` | PostgreSQL数据库连接URL | `postgresql://uploader:uploader@localhost:5433/uploader` | ✅ |
| `REDIS_URL` | Redis缓存连接URL | `redis://localhost:6380/0` | ✅ |
| `SECRET_KEY` | JWT加密密钥（生产环境请使用强密钥） | - | ✅ |
| `STORAGE_ROOT` | 存储根目录，用于保存视频、Cookie等文件 | `./storage` | ✅ |
| `UPLOADER_HEADLESS` | 是否使用无头模式（生产环境建议开启） | `false` | ❌ |
| `UPLOADER_CHROME_PATH` | Chrome浏览器路径 | `""` | ❌ |
| `BROWSER_HEARTBEAT_TIMEOUT` | 浏览器心跳超时（秒） | `300` | ❌ |
| `MAX_CONCURRENT_BROWSERS` | 最大并发浏览器数量 | `5` | ❌ |
| `TASK_QUEUE_MAX_SIZE` | 任务队列最大大小 | `100` | ❌ |

### 启动服务

#### 方式一：使用启动脚本（推荐本地开发）

我们提供了两个启动脚本，**无需编写 YML 配置文件**，一键启动所有服务：

**Shell 脚本（推荐 Linux/Mac）：**

```bash
# 一键启动所有服务（自动启动 PostgreSQL、Redis、Uploader）
./start.sh

# 查看服务状态
./start.sh --status

# 同时启动 Celery Worker
./start.sh --worker

# 查看所有选项
./start.sh --help
```

**Python 脚本（推荐 Windows 或更熟悉 Python）：**

```bash
# 功能与 start.sh 完全一致
python start.py

# 查看所有选项
python start.py --help
```

**脚本特点：**
- 🐳 自动使用 Docker 启动 PostgreSQL 和 Redis
- 📦 自动初始化数据库表结构
- 📁 自动创建存储目录
- 🔄 支持热重载（代码修改自动生效）
- ⚙️ 可选启动 Celery Worker 处理异步任务

**常用命令：**

```bash
# 启动所有服务
./start.sh        # 或: python start.py

# 停止所有服务（包括 PostgreSQL 和 Redis）
./start.sh --stop

# 仅初始化数据库
./start.sh --init

# 重启依赖服务
./start.sh --restart-deps

# 删除依赖容器（会丢失数据！）
./start.sh --remove-deps
```

#### 方式二：手动启动

如果你希望手动控制每个步骤：

```bash
# 1. 启动 PostgreSQL (Docker)
docker run -d --name uploader-postgres-local \
  -e POSTGRES_USER=uploader \
  -e POSTGRES_PASSWORD=uploader \
  -e POSTGRES_DB=uploader \
  -p 5433:5432 \
  -v $(pwd)/.data/postgres:/var/lib/postgresql/data \
  pgvector/pgvector:pg15-trixie

# 2. 启动 Redis (Docker)
docker run -d --name uploader-redis-local \
  -p 6380:6379 \
  redis:7-alpine

# 3. 初始化存储目录
mkdir -p storage/{raw,intermediate,exports,openstoryline,uploader/cookies,uploader/videos}

# 4. 启动 Uploader 服务
uvicorn src.main:app --reload --port 8002
```

#### 方式三：使用项目级 Docker Compose

如果你已经启动了项目的整体 Docker Compose：

```bash
# 在项目根目录
cd ..
docker-compose up -d uploader
```

服务启动后，你可以通过 `http://localhost:8002/docs` 访问API文档，通过 `http://localhost:8002/redoc` 访问Redoc文档。

## 📦 项目结构

```
AgentOs-Uploader/
├── src/                    # 核心源代码
│   ├── upload/             # 上传服务模块
│   │   ├── service.py      # 业务逻辑层
│   │   ├── router.py       # API路由定义
│   │   └── schemas.py      # 数据模型定义
│   ├── config.py           # Pydantic 配置类
│   ├── config_manager.py   # 统一配置管理
│   ├── exception_handler.py # 异常处理体系
│   ├── douyin_uploader/    # 抖音平台适配器
│   ├── tencent_uploader/   # 视频号平台适配器
│   └── xhs_uploader/      # 小红书平台适配器
├── persistent_browser_service.py # 浏览器会话管理
├── qr_login_service.py     # 二维码登录服务
├── start.sh               # 🚀 本地启动脚本（推荐）
├── config.py              # 配置管理工具
├── requirements.txt       # Python依赖包
├── requirements-dev.txt   # 开发依赖包
├── Dockerfile             # Docker构建配置
├── .env.example           # 环境变量模板
└── .dockerignore          # Docker构建忽略文件
```

**核心配置文件说明：**

| 文件 | 说明 |
|------|------|
| `start.sh` | 本地一键启动脚本，自动管理 PostgreSQL、Redis 和 Uploader 服务 |
| `config.py` | 配置管理工具，支持查看、验证和生成配置文件 |
| `.env.example` | 环境变量模板，复制为 `.env` 后修改即可使用 |
| `src/config.py` | Pydantic Settings 配置类，定义所有配置项和默认值 |

## 🛠️ 使用指南

### 基本上传流程

#### 1. 添加账号

```python
import asyncio
from src.upload.service import UploaderService

async def add_account():
    service = UploaderService()
    
    # 添加抖音账号
    account = await service.add_account(
        platform="douyin",
        user_name="your_douyin_username",
        cookie_file="cookies/douyin.json"
    )
    
    print(f"账号添加成功: {account.id}")
    print(f"账号状态: {account.status}")
    return account

asyncio.run(add_account())
```

#### 2. 上传视频

```python
async def upload_video(account_id):
    service = UploaderService()
    
    # 上传视频到抖音
    result = await service.publish_video(
        account_id=account_id,
        video_path="path/to/your/video.mp4",
        title="测试视频标题",
        tags=["测试", "demo", "视频号"],
        description="这是一个测试视频描述",
        cover_path="path/to/cover.jpg"  # 可选：封面图片路径
    )
    
    print(f"上传结果: {result.status}")
    if result.success:
        print(f"视频ID: {result.video_id}")
        print(f"发布链接: {result.publish_url}")
    else:
        print(f"错误信息: {result.error}")
        print(f"错误详情: {result.error_details}")

# 假设已有账号ID
asyncio.run(upload_video(1))
```

### 二维码登录

```python
from src.qr_login import QRLoginService

async def login_process():
    service = QRLoginService()
    
    # 创建登录任务
    task = await service.create_login_task("douyin")
    print(f"请扫描二维码: {task.qr_code_path}")
    
    # 等待登录完成（最多等待300秒）
    await task.wait_for_login(timeout=300)
    
    if task.status == "success":
        print(f"登录成功！Cookie已保存到: {task.cookie_file}")
        print(f"账号信息: {task.account_info}")
    else:
        print(f"登录失败: {task.error_msg}")
        print(f"错误详情: {task.error_details}")

asyncio.run(login_process())
```

### WebSocket状态监控

```javascript
// 客户端WebSocket连接示例
const ws = new WebSocket('ws://localhost:8002/ws/status');

ws.onopen = function() {
    console.log('WebSocket连接已建立');
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('收到状态更新:', data);
    
    // 处理不同类型的消息
    if (data.type === 'task_update') {
        console.log(`任务 ${data.task_id} 状态更新: ${data.status}`);
    } else if (data.type === 'account_update') {
        console.log(`账号 ${data.account_id} 状态更新: ${data.status}`);
    }
};

ws.onclose = function() {
    console.log('WebSocket连接已关闭');
};
```

## 🔧 配置详解

### 配置管理

```python
from src.config_manager import config_manager

# 获取全局配置
storage_root = config_manager.get("storage_root")
browser_timeout = config_manager.get("browser_heartbeat_timeout")

# 获取平台特定配置
douyin_config = config_manager.get_platform_config("douyin")
douyin_config.get("login_url")  # 获取抖音登录URL
douyin_config.get("upload_url")  # 获取抖音上传URL
```

### 环境变量配置最佳实践

1. **生产环境配置**
```bash
# 生产环境.env文件示例
DATABASE_URL=postgresql://uploader:secure_password@db.example.com:5432/uploader
REDIS_URL=redis://redis.example.com:6379/0
SECRET_KEY=your_very_strong_secret_key_here
STORAGE_ROOT=/var/data/agentos_storage
UPLOADER_HEADLESS=true
MAX_CONCURRENT_BROWSERS=10
```

2. **开发环境配置**
```bash
# 开发环境.env文件示例
DATABASE_URL=postgresql://uploader:uploader@localhost:5432/uploader_dev
REDIS_URL=redis://localhost:6379/1
SECRET_KEY=dev_secret_key
STORAGE_ROOT=./storage
UPLOADER_HEADLESS=false
```

## 🐳 Docker部署

### 快速部署

#### 1. 构建镜像

```bash
# 构建Docker镜像
docker build -t agentos-uploader .

# 或者使用Docker Compose（推荐）
docker-compose up --build
```

#### 2. 运行容器

```bash
docker run -d \
  --name agentos-uploader \
  -p 8002:8002 \
  -v $(pwd)/storage:/app/storage \
  -e SECRET_KEY=your-secret-key \
  agentos-uploader
```

### Docker Compose配置

```yaml
version: '3.8'

services:
  uploader:
    build: ./AgentOs-Uploader
    ports:
      - "8002:8002"
    volumes:
      - ./storage:/app/storage
    environment:
      - DATABASE_URL=postgresql://uploader:uploader@postgres:5432/uploader
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=your-production-secret-key
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:13
    environment:
      - POSTGRES_USER=uploader
      - POSTGRES_PASSWORD=uploader
      - POSTGRES_DB=uploader
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:6-alpine

volumes:
  postgres_data:
```

## 📊 API参考

### 账号管理

- `GET /uploader/accounts` - 获取账号列表
- `POST /uploader/accounts` - 添加账号
- `PUT /uploader/accounts/{account_id}` - 更新账号
- `DELETE /uploader/accounts/{account_id}` - 删除账号

### 视频上传

- `POST /uploader/publish` - 发布视频
- `GET /uploader/tasks` - 获取任务列表
- `GET /uploader/tasks/{task_id}` - 获取任务详情
- `DELETE /uploader/tasks/{task_id}` - 取消任务

### 二维码登录

- `POST /uploader/qr-login` - 创建登录任务
- `GET /uploader/qr-login/{task_id}` - 获取登录状态
- `DELETE /uploader/qr-login/{task_id}` - 取消登录任务

### WebSocket

- `ws://localhost:8002/ws/status` - 实时状态通知

## 🔍 最佳实践

### 1. 生产环境部署建议

- **使用无头模式**：设置 `UPLOADER_HEADLESS=true` 减少资源消耗
- **配置持久化存储**：确保 `STORAGE_ROOT` 指向持久化目录
- **设置强密钥**：使用复杂的 `SECRET_KEY` 保护JWT
- **监控资源**：定期检查浏览器会话内存使用情况
- **备份会话数据**：定期备份Cookie和会话文件

### 2. 性能优化

- **批量上传**：使用异步任务队列处理多个上传请求
- **会话复用**：合理配置浏览器会话超时时间（建议300-600秒）
- **错误重试**：实现自动重试机制处理临时网络问题
- **并发控制**：根据服务器性能调整 `MAX_CONCURRENT_BROWSERS`

### 3. 安全建议

- **敏感信息保护**：不要在代码中硬编码敏感信息
- **定期更新Cookie**：设置Cookie自动刷新策略（建议每7-14天）
- **访问控制**：实现API密钥或OAuth认证
- **网络隔离**：将服务部署在隔离的网络环境中

### 4. 故障排除

- **常见问题**：浏览器崩溃或无响应
  - 检查 `BROWSER_HEARTBEAT_TIMEOUT` 配置
  - 确保Chrome版本与Playwright兼容
  - 检查系统内存和CPU使用情况

- **Cookie失效**：登录失败或上传失败
  - 重新生成Cookie（通过二维码登录）
  - 检查账号状态是否正常
  - 验证Cookie文件权限

## 🧪 测试方法

### 运行测试

```bash
# 安装测试依赖
pip install -r requirements-dev.txt

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_upload.py

# 生成测试覆盖率报告
pytest --cov=src tests/
```

### 测试数据准备

1. 创建测试数据库
2. 准备测试Cookie文件
3. 配置测试环境变量

## 🤝 贡献指南

我们欢迎社区贡献！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

### 开发环境设置

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 代码格式化
black .

# 代码检查
flake8 .

# 运行测试
pytest
```

## 📈 版本历史

### v1.0.0 (当前版本)
- 初始版本发布
- 支持抖音、视频号、小红书平台
- 完整的账号管理和任务系统
- WebSocket实时状态通知

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系方式

- 项目维护者：Frank XIONG
- 邮箱：xty_frank@qq.com
- GitHub：https://github.com/NGU-forever/Ai_Autoclip_System

## 🙏 致谢

- [Playwright](https://github.com/microsoft/playwright) - 自动化测试工具
- [FastAPI](https://github.com/tiangolo/fastapi) - Web框架
- [Social Auto Upload](https://github.com/dreammis/social-auto-upload) - 原始项目灵感来源
- [Docker](https://www.docker.com/) - 容器化解决方案
- [PostgreSQL](https://www.postgresql.org/) - 数据库系统
- [Redis](https://redis.io/) - 缓存系统

## 📋 常见问题解答

### Q: 如何解决Cookie失效问题？
A: 当Cookie失效时，需要重新通过二维码登录获取新的Cookie。可以使用 `qr-login` 接口创建登录任务，扫描二维码完成登录后，系统会自动保存新的Cookie文件。

### Q: 如何监控上传进度？
A: 可以通过WebSocket连接 `ws://localhost:8002/ws/status` 实时接收任务状态更新，或者在API中查询任务详情。

### Q: 支持哪些视频格式？
A: 支持常见的视频格式，包括MP4、MOV、AVI等。建议使用MP4格式，分辨率建议为720p或1080p。

### Q: 如何处理上传失败？
A: 上传失败时，系统会记录详细的错误信息。可以通过任务详情接口查看错误原因，并根据错误类型采取相应措施（如重新上传、检查网络等）。

### Q: 如何扩展支持新平台？
A: 可以通过实现新的平台适配器来扩展支持。需要创建新的平台模块，实现相应的登录和上传逻辑。