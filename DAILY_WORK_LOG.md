# 工作日志

## 2026年3月28日 - 后端架构简化与微前端架构重构

今天完成了系统架构的大规模重构与简化，将 Storyline 与 Uploader 模块从后端核心解耦，全面转向微前端与独立服务的协作模式。主要包括以下几个方面：

### 1. 架构去中心化与后端精简
- **[核心逻辑重构]**: 移除了后端中的 Storyline 桥接逻辑（Bridge Service），后端现在仅负责核心的认证（Auth）与用户管理（User Management），显著降低了服务间的耦合度。
- **[数据模型优化]**: 删除了用户偏好设置（User Preferences）等冗余模型，精简了数据库 Schema。
- **[初始化流程合并]**: 将零散的数据库初始化脚本（`init_new_tables.py`, `seed_data.py` 等）合并为统一的 `init_tables.py`，提升了基础设施的可维护性。

### 2. 前端微应用化集成
- **[微前端重構]**: 完成了 Storyline 与 Uploader 的微前端（Micro-frontend）改造，集成 Vite SPA 并支持 qiankun 生命周期，使得各子应用可以独立开发与部署。
- **[界面统一化]**: 统一了 Storyline 与 Uploader 跨应用的头部（Header）设计，提升了用户体验的一致性。
- **[依赖解耦]**: 移除了前端旧有的 `VideoDistributor` 等强耦合逻辑，通过独立的 URL 和 build-arg 实现了子应用间的松耦合。

### 3. 基础设施与构建优化
- **[容器化增强]**: 在 Dockerfile 和 docker-compose 中引入了 `APT_USE_TENCENT_MIRROR` 构建参数，优化了国内环境下的构建速度。
- **[多阶段构建]**: 为 Uploader 集成了多阶段构建（Multi-stage build），减小了最终镜像体积。
- **[文档同步]**: 大幅更新了 `README.md`，反映了最新的“AI Terminal + 独立 SDK”架构愿景，为后续开发者提供了清晰的指引。

### 4. 未来进度 (Future Progress)
- [ ] 验证微前端在生产环境下的容器间路由跳转与通信稳定性
- [ ] 补齐精简后后端的单元测试与安全审计
- [ ] 
