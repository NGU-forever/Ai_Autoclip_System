# 发布任务编号修复与验证

检查基线：默认分支 `main`，提交 `95ca3d95f61e6329c69d4862c4b76c0868b45bc8`。

## 已验证的影响

使用基线原始模型和 Repository，在真实 SQLite 内存数据库创建任务后：整数主键为 `1`；用 API 生成的 UUID 查询返回 `None`；`set_running`、`set_success` 返回 `False`；`increment_retry` 返回 `0`。原始 `to_dict()` 还缺少响应模型要求的 `task_id/create_time/update_time`，且账号 ID 类型不符。因此影响不只静态类型不一致：SQLite 实测无法通过 UUID 关联记录，列表/详情存在响应校验问题。PostgreSQL 的整数/UUID 比较还可能直接报类型错误，本次未运行 PostgreSQL 验证。

这些结果证明代码路径缺陷，不证明线上发布已经失败。Worker 原来没有检查数据库更新是否命中，所以平台操作仍可能成功，而记录仍是 pending。不能据此重新发布历史 pending 任务。

仓库已有测试只覆盖 backend 登录和路由行为，没有 Uploader 数据库、Worker 或重试测试；本次新增独立 Uploader 测试，不改动 backend 测试。

## 编号流转及修复

- API 仍生成并返回 UUID hex，Celery 通过业务参数 `task_id` 携带它。Celery 自身 delivery/result ID 与业务编号仍独立。
- 保留自增整数 `id`、账号外键及所有旧记录；新增可空、唯一索引的 `task_id VARCHAR(32)`。新记录保存 UUID；所有 Repository 查询和更新统一按业务编号定位。
- 历史 `task_id IS NULL` 记录继续支持规范数字形式的整数主键查询；列表返回字符串形式的旧主键作为 `task_id`。新 UUID 记录不能通过其内部整数主键寻址；32 位纯数字 UUID 也不会误匹配旧主键。
- `to_dict()` 保留已有字段，并提供 API 要求的任务编号、时间别名和字符串账号 ID。
- Worker 在任何账号、视频和平台操作前，提交 `pending + retry_count=attempt → running` 的原子条件更新。未命中则跳过，拦截缺失任务、并发重复投递、已成功任务和旧重试消息。
- 手动重试只允许 failed；通过状态和期望 retry_count 原子预留一个新 attempt，同一请求快照只能有一个成功预留者。旧 attempt 消息不能领取新 attempt。
- 账号/文件预检查异常会记录为 failed；平台登录 setup 返回 False 也记为失败，避免假成功。三个平台的构造参数与实际发布代码保持原样。
- 平台调用完成后的成功回写若失败，异常向上传递，保留 running，避免自动开放重试。
- API 重启不再把独立 Worker 的 running 任务自动改为 failed。数据库初始化/迁移失败会阻止服务启动，避免进入并不存在的 JSON 回退路径。
- 队列投递异常返回 503，detail 包含现有 task_id；保留 pending，因为 Broker 错误不能证明消息没有送达。不要自动再次 POST /publish 或将它改为 failed。

## 回归测试

在 `AgentOs-Uploader` 目录执行：

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q tests
```

测试使用文件 SQLite、独立 SQLAlchemy 会话、HTTP ASGITransport、Celery eager 本地执行和模拟平台边界。没有连接 Redis、打开浏览器、使用真实账号或发布实际视频。

覆盖创建、列表/详情 HTTP 响应、UUID 状态更新、三平台 Worker 调用、失败重试次数、旧 attempt 拦截、重复投递、并发领取/重试、成功回写异常、预检查失败、失效 Cookie、Broker 异常、唯一性、旧表幂等迁移、已有整数记录查询和更新、并发初始化，以及三平台定时/草稿/封面/商品等参数转发。

本地结果：19 passed；另通过 compileall 和 git diff --check。仅有已有 Pydantic/multipart 弃用提示。

本地验证环境：Python 3.12、SQLAlchemy 2.0.55、FastAPI 0.115.0、Playwright 1.48.0、Celery 5.6.3。未执行真实 PostgreSQL、Redis Broker 或真实平台端到端测试；不能从模拟测试推断平台 UI 当前可用性。

## 部署与历史数据处理

1. 先备份数据库，协调停用发布入口并停止旧 Worker，记录未确认完成的任务和队列消息；不要盲目重放旧消息或清空队列。
2. 启动新 API 完成增量迁移，再启动新 Worker，随后恢复发布入口。不要混跑新 API 和旧 Worker（旧 Worker 不支持 attempt/新领取规则）。迁移只增列和索引，不删除、不重编号，也不猜测历史关联。
3. 历史 UUID 没有写入数据库，无法仅凭现存记录可靠恢复。旧 UUID 消息会因找不到任务而被跳过；由人工结合日志/平台结果确认处理。已存在的历史任务仍可通过列表和数字 task_id 查看；有原始请求且确认未发布的 failed 任务可手动重试。
4. running、投递结果不确定的 pending、或疑似平台成功但回写失败的任务，先确认所有相关 Worker 已停止，再核对平台结果。确认已发布则按记录编号修正为 success；确认未发布再由运维将对应记录改为 failed 并使用重试接口。不要在 Worker 运行时批量调用旧 reconcile 方法。
5. 回滚时可以保留新增列/索引；旧版本仍存在原编号缺陷，不能作为安全的发布路径回退。

## 防重复边界

原子领取防止同一个业务任务/attempt 被重复或并发执行，不对两次独立 POST /publish 生成的两个 UUID 做内容去重。用户有意再次发布同一视频仍可建立新任务。

平台不提供统一幂等事务；点击发布后浏览器超时或 Worker 崩溃，无法仅靠本地数据库确定平台是否收到。保留 max_retries=0，不自动重试；此类情况必须先核实平台结果再手动重试，不能承诺跨外部平台的 exactly-once。此次修复没有添加超时后自动接管或过期锁，以免重复发布。
