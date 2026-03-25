# AgentOS Enterprise 企业级功能设计

**日期**: 2026-03-03

## 概述

为 AgentOS Enterprise 添加三大企业级功能模块：
1. 用户与权限管理 (RBAC)
2. 数据分析与报表
3. API 与集成设置

## 1. 用户与权限管理 (RBAC)

### 角色定义

| 角色 | 权限描述 |
|------|----------|
| 超级管理员 | 完全访问，可管理用户、设置、系统配置 |
| 普通用户 | 可使用 Agent、工作流、查看报表，无法管理用户 |
| 只读用户 | 仅可查看，无法执行操作 |

### 数据结构

```typescript
interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  role: 'admin' | 'user' | 'viewer';
  status: 'active' | 'disabled';
  createdAt: string;
  lastLogin?: string;
}

interface Role {
  id: string;
  name: string;
  permissions: string[];
}
```

### 页面设计

- **路径**: `/users`
- **布局**: 左侧角色列表 + 右侧用户表格
- **功能**: 添加用户、编辑角色、禁用/启用、搜索筛选

## 2. 数据分析与报表

### 报表类型

1. **Agent 性能统计**
   - 执行次数、成功率、平均耗时、错误率

2. **工作流执行报表**
   - 执行次数、平均耗时、成功率、触发频率分布

3. **成本与效率分析**
   - 任务数量、成本节约（按次计算）、时间节省、ROI 指标

4. **周期性报告**
   - 日报、周报、月报
   - 支持 PDF/CSV 导出

### 数据结构

```typescript
interface ReportData {
  agentStats: {
    totalRuns: number;
    successRate: number;
    avgDuration: number;
    errorRate: number;
  };
  workflowStats: {
    totalRuns: number;
    avgDuration: number;
    successRate: number;
  };
  costStats: {
    tasksProcessed: number;
    costSaved: number;
    timeSaved: number;
    roi: number;
  };
}
```

### 页面设计

- **路径**: `/reports`
- **布局**: 时间选择器 + 统计卡片 + 图表区域
- **图表**: 纯 CSS 柱状图/折线图

## 3. API 与集成设置

### 3.1 API 密钥管理

```typescript
interface ApiKey {
  id: string;
  name: string;
  key: string; // 格式: aoe_sk_xxxxx
  createdAt: string;
  lastUsed?: string;
  status: 'active' | 'disabled';
}
```

### 3.2 Webhook 配置

```typescript
interface Webhook {
  id: string;
  name: string;
  url: string;
  events: string[];
  auth: 'none' | 'bearer' | 'basic';
  status: 'active' | 'disabled';
}
```

### 3.3 第三方集成

支持平台：
- 钉钉 (DingTalk)
- 飞书 (Feishu)
- 企业微信 (WeCom)

```typescript
interface Integration {
  platform: 'dingtalk' | 'feishu' | 'wecom';
  enabled: boolean;
  config: Record<string, string>;
  status: 'connected' | 'disconnected';
}
```

### 页面设计

- **路径**: `/api-settings`
- **布局**: Tab 切换（API 密钥 | Webhook | 第三方集成）
- **功能**: CRUD 操作、状态切换、测试连接

## 技术实现

- **数据存储**: localStorage
- **状态管理**: React useState + Context
- **路由**: React Router（添加新路由）
- **样式**: Tailwind CSS（遵循现有设计系统）
- **动画**: Framer Motion

## 页面路由

```
/users          - 用户管理
/reports        - 数据报表
/api-settings   - API 与集成设置
```

## 验收标准

1. 用户管理：可添加、编辑、禁用用户，角色切换生效
2. 报表：时间范围筛选有效，图表正确显示，支持导出
3. API 设置：密钥创建/禁用正常，Webhook 测试成功，集成连接状态正确
