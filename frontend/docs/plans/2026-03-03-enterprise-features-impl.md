# AgentOS Enterprise 企业级功能实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 为 AgentOS Enterprise 添加用户权限管理、数据分析报表、API集成设置三大企业级功能模块

**Architecture:** 使用 localStorage 存储数据，在现有 React + TypeScript + Tailwind 架构上扩展新页面和 API

**Tech Stack:** React, TypeScript, Tailwind CSS, Framer Motion, React Router, localStorage

---

## 任务概览

- 任务 1: 创建用户与权限 API (users.ts)
- 任务 2: 创建报表数据 API (reports.ts)
- 任务 3: 创建 API 密钥管理 API (api-keys.ts)
- 任务 4: 创建第三方集成 API (integrations.ts)
- 任务 5: 创建用户管理页面 (Users.tsx)
- 任务 6: 创建数据分析报表页面 (Reports.tsx)
- 任务 7: 创建 API 与集成设置页面 (ApiSettings.tsx)
- 任务 8: 更新路由配置 (App.tsx)
- 任务 9: 更新导航栏 (Layout.tsx)
- 任务 10: 构建验证

---

## 任务 1: 创建用户与权限 API

**Files:**
- Create: `src/api/users.ts`

**Step 1: 创建 API 文件**

```typescript
// src/api/users.ts
// ========================================
// AgentOS Enterprise - 用户与权限 API
// ========================================

import { delay } from './utils';

// 用户类型
export type UserRole = 'admin' | 'user' | 'viewer';
export type UserStatus = 'active' | 'disabled';

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  role: UserRole;
  status: UserStatus;
  createdAt: string;
  lastLogin?: string;
}

// 角色权限映射
export const rolePermissions: Record<UserRole, string[]> = {
  admin: ['*'],
  user: ['agents:read', 'agents:execute', 'workflows:read', 'workflows:execute', 'messages:read', 'messages:write', 'reports:read'],
  viewer: ['agents:read', 'workflows:read', 'messages:read', 'reports:read'],
};

// 默认用户数据
const defaultUsers: User[] = [
  { id: 'user-1', name: 'Administrator', email: 'admin@agentos.io', role: 'admin', status: 'active', createdAt: '2026-01-01', lastLogin: '刚刚' },
  { id: 'user-2', name: '张明', email: 'zhangming@company.com', role: 'user', status: 'active', createdAt: '2026-01-15', lastLogin: '2小时前' },
  { id: 'user-3', name: '李华', email: 'lihua@company.com', role: 'user', status: 'active', createdAt: '2026-02-01', lastLogin: '1天前' },
  { id: 'user-4', name: '王芳', email: 'wangfang@company.com', role: 'viewer', status: 'active', createdAt: '2026-02-10', lastLogin: '3天前' },
  { id: 'user-5', name: '赵强', email: 'zhaoqiang@company.com', role: 'user', status: 'disabled', createdAt: '2026-01-20', lastLogin: '2周前' },
];

const USERS_KEY = 'agentos-users';

const getStoredUsers = (): User[] => {
  try {
    const stored = localStorage.getItem(USERS_KEY);
    if (stored) return JSON.parse(stored);
  } catch (e) { console.error('Error reading users:', e); }
  localStorage.setItem(USERS_KEY, JSON.stringify(defaultUsers));
  return defaultUsers;
};

const saveStoredUsers = (users: User[]) => {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
};

export const fetchUsers = async (): Promise<User[]> => {
  await delay(300);
  return getStoredUsers();
};

export const createUser = async (user: Omit<User, 'id' | 'createdAt'>): Promise<User> => {
  await delay(500);
  const users = getStoredUsers();
  const newUser: User = {
    ...user,
    id: `user-${Date.now()}`,
    createdAt: new Date().toISOString().split('T')[0],
  };
  saveStoredUsers([newUser, ...users]);
  return newUser;
};

export const updateUser = async (id: string, updates: Partial<User>): Promise<User | null> => {
  await delay(300);
  const users = getStoredUsers();
  const index = users.findIndex(u => u.id === id);
  if (index === -1) return null;
  users[index] = { ...users[index], ...updates };
  saveStoredUsers(users);
  return users[index];
};

export const deleteUser = async (id: string): Promise<boolean> => {
  await delay(300);
  const users = getStoredUsers();
  saveStoredUsers(users.filter(u => u.id !== id));
  return true;
};

export const toggleUserStatus = async (id: string): Promise<User | null> => {
  await delay(200);
  const users = getStoredUsers();
  const user = users.find(u => u.id === id);
  if (!user) return null;
  user.status = user.status === 'active' ? 'disabled' : 'active';
  saveStoredUsers(users);
  return user;
};

export const checkPermission = (role: UserRole, permission: string): boolean => {
  const perms = rolePermissions[role];
  return perms.includes('*') || perms.includes(permission);
};
```

**Step 2: 验证文件创建**

Run: `ls -la src/api/users.ts`
Expected: 文件存在

**Step 3: 提交**

```bash
git add src/api/users.ts
git commit -m "feat: add user and permissions API"
```

---

## 任务 2: 创建报表数据 API

**Files:**
- Create: `src/api/reports.ts`

**Step 1: 创建 API 文件**

```typescript
// src/api/reports.ts
// ========================================
// AgentOS Enterprise - 报表数据 API
// ========================================

import { delay } from './utils';

export interface AgentReportStats {
  totalRuns: number;
  successRate: number;
  avgDuration: number;
  errorRate: number;
  byAgent: { name: string; runs: number; successRate: number }[];
}

export interface WorkflowReportStats {
  totalRuns: number;
  avgDuration: number;
  successRate: number;
  byWorkflow: { name: string; runs: number; successRate: number }[];
}

export interface CostReportStats {
  tasksProcessed: number;
  costSaved: number;
  timeSaved: number;
  roi: number;
}

export interface ReportData {
  period: 'today' | 'week' | 'month' | 'custom';
  startDate?: string;
  endDate?: string;
  agentStats: AgentReportStats;
  workflowStats: WorkflowReportStats;
  costStats: CostReportStats;
  dailyData: { date: string; tasks: number; cost: number }[];
}

// 模拟数据生成器
const generateDailyData = (days: number) => {
  const data = [];
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    data.push({
      date: date.toISOString().split('T')[0],
      tasks: Math.floor(Math.random() * 200) + 50,
      cost: Math.floor(Math.random() * 500) + 100,
    });
  }
  return data;
};

const generateReportData = (period: string): ReportData => {
  const dailyData = generateDailyData(period === 'today' ? 1 : period === 'week' ? 7 : period === 'month' ? 30 : 7);

  return {
    period: period as ReportData['period'],
    agentStats: {
      totalRuns: 1247,
      successRate: 98.5,
      avgDuration: 4.2,
      errorRate: 1.5,
      byAgent: [
        { name: 'Ingest-01', runs: 423, successRate: 99.2 },
        { name: 'Analyzer-02', runs: 356, successRate: 98.1 },
        { name: 'Research-03', runs: 289, successRate: 97.8 },
        { name: 'Drafter-04', runs: 179, successRate: 99.5 },
      ],
    },
    workflowStats: {
      totalRuns: 856,
      avgDuration: 12.5,
      successRate: 96.8,
      byWorkflow: [
        { name: 'B2B询盘处理', runs: 456, successRate: 98.5 },
        { name: '客户跟进', runs: 234, successRate: 97.2 },
        { name: '竞品监控', runs: 166, successRate: 92.8 },
      ],
    },
    costStats: {
      tasksProcessed: 1247,
      costSaved: 45820,
      timeSaved: 4988,
      roi: 312,
    },
    dailyData,
  };
};

export const fetchReport = async (period: string = 'week'): Promise<ReportData> => {
  await delay(500);
  return generateReportData(period);
};

export const exportReport = async (format: 'csv' | 'pdf'): Promise<boolean> => {
  await delay(1000);
  // 模拟导出
  console.log(`Exporting report as ${format}`);
  return true;
};
```

**Step 2: 验证文件创建**

Run: `ls -la src/api/reports.ts`
Expected: 文件存在

**Step 3: 提交**

```bash
git add src/api/reports.ts
git commit -m "feat: add reports data API"
```

---

## 任务 3: 创建 API 密钥管理 API

**Files:**
- Create: `src/api/api-keys.ts`

**Step 1: 创建 API 文件**

```typescript
// src/api/api-keys.ts
// ========================================
// AgentOS Enterprise - API 密钥管理 API
// ========================================

import { delay } from './utils';

export interface ApiKey {
  id: string;
  name: string;
  key: string;
  createdAt: string;
  lastUsed?: string;
  status: 'active' | 'disabled';
}

const generateApiKey = (): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = 'aoe_sk_';
  for (let i = 0; i < 24; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
};

const defaultApiKeys: ApiKey[] = [
  { id: 'key-1', name: '生产环境密钥', key: 'aoe_sk_xxxxxxxxxxxxxxxxxxxx', createdAt: '2026-01-15', lastUsed: '2小时前', status: 'active' },
  { id: 'key-2', name: '测试环境密钥', key: 'aoe_sk_yyyyyyyyyyyyyyyyyyyy', createdAt: '2026-02-01', status: 'active' },
];

const API_KEYS_KEY = 'agentos-api-keys';

const getStoredKeys = (): ApiKey[] => {
  try {
    const stored = localStorage.getItem(API_KEYS_KEY);
    if (stored) return JSON.parse(stored);
  } catch (e) { console.error('Error reading API keys:', e); }
  localStorage.setItem(API_KEYS_KEY, JSON.stringify(defaultApiKeys));
  return defaultApiKeys;
};

const saveStoredKeys = (keys: ApiKey[]) => {
  localStorage.setItem(API_KEYS_KEY, JSON.stringify(keys));
};

export const fetchApiKeys = async (): Promise<ApiKey[]> => {
  await delay(300);
  return getStoredKeys();
};

export const createApiKey = async (name: string): Promise<ApiKey> => {
  await delay(500);
  const keys = getStoredKeys();
  const newKey: ApiKey = {
    id: `key-${Date.now()}`,
    name,
    key: generateApiKey(),
    createdAt: new Date().toISOString().split('T')[0],
    status: 'active',
  };
  saveStoredKeys([newKey, ...keys]);
  return newKey;
};

export const deleteApiKey = async (id: string): Promise<boolean> => {
  await delay(300);
  const keys = getStoredKeys();
  saveStoredKeys(keys.filter(k => k.id !== id));
  return true;
};

export const toggleApiKeyStatus = async (id: string): Promise<ApiKey | null> => {
  await delay(200);
  const keys = getStoredKeys();
  const key = keys.find(k => k.id === id);
  if (!key) return null;
  key.status = key.status === 'active' ? 'disabled' : 'active';
  saveStoredKeys(keys);
  return key;
};
```

**Step 2: 验证文件创建**

Run: `ls -la src/api/api-keys.ts`
Expected: 文件存在

**Step 3: 提交**

```bash
git add src/api/api-keys.ts
git commit -m "feat: add API keys management API"
```

---

## 任务 4: 创建第三方集成 API

**Files:**
- Create: `src/api/integrations.ts`

**Step 1: 创建 API 文件**

```typescript
// src/api/integrations.ts
// ========================================
// AgentOS Enterprise - 第三方集成 API
// ========================================

import { delay } from './utils';

export type IntegrationPlatform = 'dingtalk' | 'feishu' | 'wecom';

export interface Integration {
  platform: IntegrationPlatform;
  enabled: boolean;
  config: Record<string, string>;
  status: 'connected' | 'disconnected' | 'error';
  lastSync?: string;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  events: string[];
  auth: 'none' | 'bearer' | 'basic';
  status: 'active' | 'disabled';
  createdAt: string;
}

const defaultIntegrations: Integration[] = [
  { platform: 'dingtalk', enabled: false, config: {}, status: 'disconnected' },
  { platform: 'feishu', enabled: true, config: { appId: 'cli_xxx', appSecret: '***' }, status: 'connected', lastSync: '10分钟前' },
  { platform: 'wecom', enabled: false, config: {}, status: 'disconnected' },
];

const defaultWebhooks: Webhook[] = [
  { id: 'wh-1', name: '任务完成通知', url: 'https://example.com/webhook/task', events: ['task.completed', 'task.failed'], auth: 'bearer', status: 'active', createdAt: '2026-01-20' },
  { id: 'wh-2', name: '异常告警', url: 'https://example.com/webhook/alert', events: ['agent.error', 'workflow.error'], auth: 'bearer', status: 'active', createdAt: '2026-02-01' },
];

const INTEGRATIONS_KEY = 'agentos-integrations';
const WEBHOOKS_KEY = 'agentos-webhooks';

const getStoredIntegrations = (): Integration[] => {
  try {
    const stored = localStorage.getItem(INTEGRATIONS_KEY);
    if (stored) return JSON.parse(stored);
  } catch (e) { console.error('Error reading integrations:', e); }
  localStorage.setItem(INTEGRATIONS_KEY, JSON.stringify(defaultIntegrations));
  return defaultIntegrations;
};

const saveStoredIntegrations = (data: Integration[]) => {
  localStorage.setItem(INTEGRATIONS_KEY, JSON.stringify(data));
};

const getStoredWebhooks = (): Webhook[] => {
  try {
    const stored = localStorage.getItem(WEBHOOKS_KEY);
    if (stored) return JSON.parse(stored);
  } catch (e) { console.error('Error reading webhooks:', e); }
  localStorage.setItem(WEBHOOKS_KEY, JSON.stringify(defaultWebhooks));
  return defaultWebhooks;
};

const saveStoredWebhooks = (data: Webhook[]) => {
  localStorage.setItem(WEBHOOKS_KEY, JSON.stringify(data));
};

// Integrations
export const fetchIntegrations = async (): Promise<Integration[]> => {
  await delay(300);
  return getStoredIntegrations();
};

export const updateIntegration = async (platform: IntegrationPlatform, updates: Partial<Integration>): Promise<Integration | null> => {
  await delay(500);
  const integrations = getStoredIntegrations();
  const index = integrations.findIndex(i => i.platform === platform);
  if (index === -1) return null;
  integrations[index] = { ...integrations[index], ...updates };
  saveStoredIntegrations(integrations);
  return integrations[index];
};

// Webhooks
export const fetchWebhooks = async (): Promise<Webhook[]> => {
  await delay(300);
  return getStoredWebhooks();
};

export const createWebhook = async (webhook: Omit<Webhook, 'id' | 'createdAt'>): Promise<Webhook> => {
  await delay(500);
  const webhooks = getStoredWebhooks();
  const newWebhook: Webhook = {
    ...webhook,
    id: `wh-${Date.now()}`,
    createdAt: new Date().toISOString().split('T')[0],
  };
  saveStoredWebhooks([newWebhook, ...webhooks]);
  return newWebhook;
};

export const updateWebhook = async (id: string, updates: Partial<Webhook>): Promise<Webhook | null> => {
  await delay(300);
  const webhooks = getStoredWebhooks();
  const index = webhooks.findIndex(w => w.id === id);
  if (index === -1) return null;
  webhooks[index] = { ...webhooks[index], ...updates };
  saveStoredWebhooks(webhooks);
  return webhooks[index];
};

export const deleteWebhook = async (id: string): Promise<boolean> => {
  await delay(300);
  const webhooks = getStoredWebhooks();
  saveStoredWebhooks(webhooks.filter(w => w.id !== id));
  return true;
};

export const testWebhook = async (url: string): Promise<boolean> => {
  await delay(1000);
  return true;
};
```

**Step 2: 验证文件创建**

Run: `ls -la src/api/integrations.ts`
Expected: 文件存在

**Step 3: 提交**

```bash
git add src/api/integrations.ts
git commit -m "feat: add integrations API (webhooks, third-party)"
```

---

## 任务 5: 创建用户管理页面

**Files:**
- Create: `src/pages/Users.tsx`

**Step 1: 创建页面文件**

由于代码较长，请创建完整的用户管理页面，包含：
- 用户列表展示（表格形式）
- 添加用户对话框
- 编辑用户对话框
- 角色筛选
- 搜索功能

**Step 2: 验证构建**

Run: `npm run build`
Expected: 无错误

**Step 3: 提交**

```bash
git add src/pages/Users.tsx
git commit -m "feat: add user management page"
```

---

## 任务 6: 创建数据分析报表页面

**Files:**
- Create: `src/pages/Reports.tsx`

**Step 1: 创建页面文件**

创建包含以下内容的报表页面：
- 时间范围选择器（今日/本周/本月/自定义）
- 统计卡片（Agent性能、工作流执行、成本节约）
- 纯 CSS 柱状图/折线图
- 导出按钮

**Step 2: 验证构建**

Run: `npm run build`
Expected: 无错误

**Step 3: 提交**

```bash
git add src/pages/Reports.tsx
git commit -m "feat: add reports page with analytics"
```

---

## 任务 7: 创建 API 与集成设置页面

**Files:**
- Create: `src/pages/ApiSettings.tsx`

**Step 1: 创建页面文件**

创建包含以下内容的 API 设置页面：
- Tab 切换（API 密钥 | Webhook | 第三方集成）
- API 密钥管理（创建、查看、复制、禁用）
- Webhook 配置（创建、编辑、测试、删除）
- 第三方集成（钉钉、飞书、企业微信开关和配置）

**Step 2: 验证构建**

Run: `npm run build`
Expected: 无错误

**Step 3: 提交**

```bash
git add src/pages/ApiSettings.tsx
git commit -m "feat: add API settings page"
```

---

## 任务 8: 更新路由配置

**Files:**
- Modify: `src/App.tsx`

**Step 1: 添加新路由**

```typescript
import { Users } from './pages/Users';
import { Reports } from './pages/Reports';
import { ApiSettings } from './pages/ApiSettings';

// 添加路由
<Route path="users" element={<Users />} />
<Route path="reports" element={<Reports />} />
<Route path="api-settings" element={<ApiSettings />} />
```

**Step 2: 验证构建**

Run: `npm run build`
Expected: 无错误

**Step 3: 提交**

```bash
git add src/App.tsx
git commit -m "feat: add routes for new pages"
```

---

## 任务 9: 更新导航栏

**Files:**
- Modify: `src/components/Layout.tsx`

**Step 1: 添加导航项**

在 navItems 数组中添加：
- { path: '/users', label: '用户管理', icon: Users }
- { path: '/reports', label: '数据报表', icon: BarChart3 }
- { path: '/api-settings', label: 'API设置', icon: Plug }

添加对应的图标导入。

**Step 2: 验证构建**

Run: `npm run build`
Expected: 无错误

**Step 3: 提交**

```bash
git add src/components/Layout.tsx
git commit -m "feat: add navigation items for new pages"
```

---

## 任务 10: 构建验证

**Step 1: 运行完整构建**

Run: `npm run build`
Expected: 成功构建，无 TypeScript 错误

**Step 2: 提交最终更改**

```bash
git add .
git commit -m "feat: add enterprise features - users, reports, API settings"
```

---

## 验收标准

1. 用户管理页面可正常访问，显示用户列表
2. 可添加、编辑、禁用用户
3. 报表页面显示统计数据和图表
4. 时间范围选择器正常工作
5. API 密钥管理正常（创建、禁用）
6. Webhook 配置可用
7. 第三方集成显示连接状态
8. 新页面正确添加到导航栏

---

**Plan complete and saved to `docs/plans/2026-03-03-enterprise-features-impl.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
