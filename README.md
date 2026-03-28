# AgentOS — AI 视频自动化剪辑系统

## 📝 项目概述

AgentOS 是一款 AI 自动化视频剪辑系统。项目采用前后端分离架构，基于 Docker 容器化部署。

**架构说明**：前端直接对接 OpenStoryline 服务进行视频剪辑，后端仅提供认证和用户管理服务。

---

## ✨ 核心特性

### 🔐 认证与授权
- JWT Token 认证
- 基于角色的访问控制 (RBAC)：admin / user / viewer

### 🏗️ 简洁架构
- 后端仅保留核心功能：认证 + 用户管理
- 前端直接调用 OpenStoryline API 进行视频剪辑

---

## 🚀 技术栈

**前端技术**
- React 19 + TypeScript + Vite
- Tailwind CSS + Framer Motion
- Matx 组件库

**后端技术**
- FastAPI + Python 3.11+
- psycopg2 (PostgreSQL)

**数据库**
- PostgreSQL 15（用户数据）

**基础设施**
- Nginx 反向代理
- Docker 容器化部署

**外部服务**
- OpenStoryline (:7860/:8001) - 视频剪辑引擎

---

## 🏢 后端架构

当前后端为极简架构，仅保留认证模块：

```
backend/
├── src/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接池
│   ├── exceptions.py        # 全局异常处理
│   ├── auth/                # 认证模块
│   │   ├── router.py        # 登录接口
│   │   ├── service.py       # 认证逻辑
│   │   ├── dependencies.py  # JWT 依赖注入
│   │   ├── utils.py         # Token 加解密
│   │   └── schemas.py       # 请求/响应模型
│   ├── users/               # 用户模块
│   │   ├── models.py        # UserRepository
│   │   └── schemas.py       # 用户模型定义
│   └── repositories/
│       └── base.py          # Repository 基类
├── scripts/
│   ├── init_tables.py       # 初始化用户表
│   └── seed_users.py        # 初始化用户数据
└── tests/                   # 测试文件
```

### 后端核心功能

| 模块 | 功能 |
|:---|:---|
| **Auth** | 登录、JWT Token 颁发与验证 |
| **Users** | 用户 CRUD、角色管理 |

**注意**：视频剪辑功能由前端直接对接 OpenStoryline，后端不再提供 Bridge。

---

## 🖥️ 端口访问指南

| 门户 | 访问地址 | 说明 |
|:---|:---|:---|
| **用户端口** | `http://localhost:80` | 前端应用 |
| **管理端口** | `http://localhost:81` | 管理后台 |
| **后端 API** | `http://localhost:8000` | FastAPI 服务入口 |
| **API 文档** | `http://localhost:8000/docs` | Swagger 接口调试 |
| **OpenStoryline** | `http://localhost:7860` | 视频剪辑引擎 Web |
| **OpenStoryline API** | `http://localhost:8001` | 视频剪辑 API（前端直接调用） |
| **PostgreSQL** | `localhost:5432` | 数据库 |

---

## 🛠️ 快速启动

### 1. 克隆项目
```bash
git clone <repo-url>
cd Ai_Autoclip_System
```

### 2. 环境配置
复制 `.env.example` 并重命名为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量：
```env
DATABASE_URL=postgresql://user:password@db:5432/agentos
SECRET_KEY=your-secret-key-here
```

### 3. 一键部署 (Docker Compose)
```bash
# 生产/交付环境
docker compose up -d --build
```

本地开发（热重载）：
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

首次启动时 `web` 容器会自动执行：
- 初始化数据库表结构
- 初始化默认用户

如需关闭自动初始化：
- `RUN_DB_INIT=false` - 跳过建表
- `RUN_DB_SEED=false` - 跳过用户 seed

### 4. 账号登录
系统预设账号：

| 账号 | 密码 | 角色 |
|:---|:---|:---|
| `root@agentos.io` | `ChangeMe!Root@2026` | admin |
| `admin@agentos.io` | `ChangeMe!Admin@2026` | admin |
| `user@agentos.io` | `ChangeMe!User@2026` | user |
| `viewer@agentos.io` | `ChangeMe!Viewer@2026` | viewer |

### 5. 前端开发模式（可选）
```bash
cd frontend && npm install && npm run dev
```

前端配置中需直接指向 OpenStoryline API：
```typescript
// 前端配置示例
const OPENSTORYLINE_API = 'http://localhost:8001'
```

---

## 📁 目录指南

```
/
├── /frontend              React 前端（用户端/管理端）
├── /backend               FastAPI 后端（仅认证+用户）
│   ├── /src               源码
│   ├── /scripts           数据库初始化脚本
│   └── /tests             测试文件
├── /AgentOs-OpenStoryline OpenStoryline 视频剪辑引擎
├── /storage               运行期存储
│   ├── /exports           视频成片输出
│   ├── /openstoryline     OpenStoryline 工作目录
│   └── /raw               原始素材上传
├── docker-compose.yml     Docker 编排配置
└── .env                   环境变量配置
```

---

## 🔌 后端 API 概览

### 认证接口
```
POST /api/admin/auth/login          # 用户登录
```

详细 API 文档请访问：`http://localhost:8000/docs`

---

## 🔗 OpenStoryline 集成

前端直接调用 OpenStoryline API (:8001) 进行视频剪辑：

```
# 示例：前端直接调用
POST http://localhost:8001/sessions              # 创建剪辑会话
POST http://localhost:8001/sessions/{id}/execute # 执行节点
GET  http://localhost:8001/sessions/{id}/stream  # SSE 进度流
```

详见 OpenStoryline 文档。

---

## 🧪 测试

```bash
cd backend
pytest tests/ -v
```

---

## 📝 注意事项

1. **安全性**：生产环境请务必修改默认密码和 `SECRET_KEY`
2. **存储**：视频素材和成片默认存储在 `/storage` 目录
3. **OpenStoryline**：视频剪辑核心功能依赖 OpenStoryline 服务，请确保其正常运行

---

## 📄 License

MIT License
