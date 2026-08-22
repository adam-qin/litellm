# XHub v1.95.15 系统设计、协议转化与全球部署

对照仓库：`litellm-xhub` / 分支 `xhub-qiniu`  
产品镜像：`ltoken-hub-registry.cn-shanghai.cr.aliyuncs.com/xhub_containers/xhub:v1.95.15`  
Git：`v1.95.15` @ `92706b19af`

结论先说：

- FastAPI 网关**不自己改协议**。它只做鉴权、预算、访问组、team 注入和选部署。
- 真正的协议变换在 SDK：`llms/*/chat/transformation.py`、Chat↔Responses 桥、Anthropic Messages 三路。
- **同一公开 `model_name` 的多 provider = 组内负载均衡**，不是 fallback。
- **Fallback 只在不同公开模型名之间发生**。`fallbacks` 里写同一个名字会被跳过。
- **Access Group 只做授权展开**，不选供应商。选供应商靠 Team overlay（`model_info.team_id`）。
- **没有 `allowed_providers` 字段**。限制成本和供应商靠 key/team `models`、访问组、team 绑定、`max_budget` / TPM / RPM。
- 现网 Master/Slave 是正确骨架：Master 写库 + UI，Slave 无状态推理。全球严格预算不能依赖各 Slave 本地 Redis。

---

## 1. 系统分层

```
Client SDK / Codex / Agent
        │  OpenAI / Anthropic / Responses / Gemini
        ▼
FastAPI Gateway  (litellm/proxy)
        │  user_api_key_auth → pre_call → route_request
        ▼
Router  (litellm/router.py)
        │  team overlay → cooldown → LB → fallback
        ▼
SDK adapters  (litellm/llms/* + completion_extras + responses/)
        ▼
Provider HTTP  (OpenAI / Azure / Anthropic / Bedrock / Qwen / Qiniu ...)
```

| 层 | 关键文件 | 职责 |
|---|---|---|
| FastAPI 入口 | `proxy/proxy_server.py` | YAML/DB 加载、chat 端点、挂 router |
| 公共管道 | `proxy/common_request_processing.py` | `ProxyBaseLLMRequestProcessing.base_process_llm_request()` |
| 预调用 | `proxy/litellm_pre_call_utils.py` | 清洗伪造字段，注入 `user_api_key_team_id` |
| 路由分发 | `proxy/route_llm_request.py` | 按 `route_type` 调 Router 方法 |
| 鉴权 | `proxy/auth/user_api_key_auth.py` + `auth_checks.py` | DualCache → Postgres；key/team/access group |
| Router | `litellm/router.py` | 选部署、LB、cooldown、fallback |
| Chat→Responses | `completion_extras/litellm_responses_transformation/` | `mode: responses` 桥 |
| Responses→Chat | `responses/litellm_completion_transformation/` | 无 native Responses 时降级 |
| Anthropic | `llms/anthropic/` | Chat 适配 + `/v1/messages` 三路 |
| 模型入库 | `management_endpoints/model_management_endpoints.py` | YAML + `LiteLLM_ProxyModelTable` |
| Access Group | `management_endpoints/access_group_endpoints.py` | `POST /v1/access_group` |
| 状态 | Postgres + Redis DualCache | keys/spend/models vs rpm/cooldown/cache |
| 管理面 | `ui/litellm-dashboard` | XHub 中文控制台；Slave 应关掉 |

XHub overlay 相对社区 1.95.x：

- Team 关联模型是一等能力，不再走 premium Team-BYOK。
- Access Group schema 缺失返回 **503** + 修表 migration，不是 400。
- 镜像内嵌重新编译的中文 Admin UI。

---

## 2. 网关协议转化：原理与调用链

### 2.1 所有协议共用的前半段

Chat / Responses / Anthropic Messages / Gemini 前半段相同，只换 `route_type`。

```
1. FastAPI + Depends(user_api_key_auth)
2. _read_request_body()
3. ProxyBaseLLMRequestProcessing.base_process_llm_request(route_type=...)
4. add_litellm_data_to_request()          # litellm_pre_call_utils.py
5. pre_call_hook()                        # 预算、并发、guardrail
6. route_request()                        # route_llm_request.py
7. Router.map_team_model(model, team_id)
8. Router.{acompletion|aresponses|anthropic_messages|agenerate_content}
9. SDK transform_request → HTTP → transform_response
10. cost headers + 异步 spend 写库
```

鉴权产物是 `UserAPIKeyAuth`（`team_id`、`models`、`access_group_ids`、budget）。  
`get_team_id_from_data()` 只认 `metadata.user_api_key_team_id`，客户端伪造的 `user_api_key_*` 会在预调用被剥掉。

### 2.2 `/v1/chat/completions`

有序函数：

1. `proxy_server.chat_completion()`
2. `user_api_key_auth()`
3. `base_process_llm_request(route_type="acompletion")`
4. `route_request()` → `Router.acompletion()` → `_acompletion()`
5. `get_available_deployment()` 选一台
6. `litellm.acompletion(**deployment.litellm_params)`
7. `main.completion()` → `responses_api_bridge_check()`
   - 命中 `mode: responses` / GPT-5 reasoning / `responses/` 前缀  
     → `LiteLLMResponsesTransformationHandler.transform_request()`  
     → `litellm.responses()`  
     → 再转回 OpenAI `ModelResponse`
   - 否则 `llms/{provider}/chat/transformation.py`

Chat 打 Claude：`AnthropicConfig.transform_request()` 把 OpenAI messages/tools 变成 Anthropic `/v1/messages` payload。

### 2.3 `/v1/responses`

1. `response_api_endpoints.endpoints.responses_api()`
2. `base_process_llm_request(route_type="aresponses")`
3. `Router._aresponses_with_streaming_fallbacks()`
4. `litellm.aresponses()` → `responses/main.py:responses()`

三选一：

| 条件 | 路径 |
|---|---|
| 有 native Responses config | `llms/*/responses/transformation.py` |
| `use_chat_completions_api=True` 或无 native | `LiteLLMCompletionTransformationHandler` → `litellm.completion()` |
| MCP gateway 工具 | 走 MCP 分支 |

Responses→Chat 必须设 `_skip_responses_api_bridge=True`，否则 Chat 侧再看到 `mode: responses` 会循环。

### 2.4 `/v1/messages`

懒加载：`proxy/_lazy_features.py` 按前缀挂 `anthropic_endpoints`。

`anthropic_messages_handler()` 三路：

| 目标 | Handler |
|---|---|
| Anthropic / Bedrock Claude / `supported_endpoints` 含 `/v1/messages` | native `BaseAnthropicMessagesConfig` |
| OpenAI / Azure（默认可关） | `LiteLLMMessagesToResponsesAPIHandler` |
| 其他 | `LiteLLMMessagesToCompletionTransformationHandler` |

### 2.5 协议桥总表

| 入站 | 触发 | 转换类 | 出站 |
|---|---|---|---|
| Chat | `mode: responses` 等 | `LiteLLMResponsesTransformationHandler` | Responses |
| Responses | 无 native / force chat | `LiteLLMCompletionTransformationHandler` | Chat |
| Messages | OpenAI/Azure | Messages→Responses | Responses |
| Messages | 其他 | Messages→Chat | Chat |
| Chat | Anthropic provider | `AnthropicConfig` | Anthropic Messages HTTP |

网关层不理解 provider 密钥。OpenResty 只选区域；vendor 选择永远在 Router。

---

## 3. 关键配置参数（高性能 / 高可用）

对照官方 Production Best Practices（LiteLLM 1.95 文档）+ 本仓库核对过的 `config.yaml`。

### 3.1 进程与密钥

| 配置 | 用途 | 生产建议 |
|---|---|---|
| `LITELLM_MASTER_KEY` | Admin API / UI 密码，必须以 `sk-` 开头 | Master/Slave **必须相同** |
| `LITELLM_SALT_KEY` | 加密入库的 provider key | **加模型后永不可改**；Slave 必须相同 |
| `STORE_MODEL_IN_DB` | 模型/router/key 落 Postgres，多实例靠轮询同步 | Master/Slave 都 True |
| `DISABLE_SCHEMA_UPDATE` | 启动不跑 Prisma migrate | **仅 Slave true**；Master 负责 schema |
| `DISABLE_ADMIN_UI` | 关掉管理面 | **仅 Slave true** |
| `--num_workers` / `NUM_WORKERS` | Uvicorn worker | K8s **每 Pod 1**；单机 = vCPU |
| `--max_requests_before_restart` | 防内存爬升 | 10000 起步 |
| `LITELLM_JOB_ROLE` | `serving` 不注册全局后台任务 | 流量面 serving + 1 副本 worker |
| `LITELLM_MODE=PRODUCTION` | 禁止 load_dotenv | 生产必开 |
| `LITELLM_LOG=ERROR` | 降日志 | 配合 `json_logs: true` |

资源下限：每 worker **1 CPU / 4Gi**。HPA 只跟 CPU 60%，不要跟 memory（Prisma RSS 只涨不缩）。

### 3.2 `litellm_settings`

| 键 | 用途 |
|---|---|
| `cache: true` + `cache_params.type: redis` | 响应缓存；多实例必须 Redis，否则命中只在本进程 |
| `cache_params.ttl` | 缓存秒数，现网常用 1800 |
| `cache_params.mode` | **必须写在 cache_params 内**。写到顶层会变成无用的 `litellm.mode` |
| `cache_params.supported_call_types` | 哪些调用可缓存 |
| `drop_params: true` | 丢弃上游不支持的可选参数。注意：公开 `metadata` 对 Responses 仍是合法字段，这条拦不住 #35780 |
| `num_retries` / `request_timeout` | SDK 级重试与超时。生产不要用默认 6000s，建议 60–600 |
| `return_response_headers` | 回 `x-litellm-response-cost` 等 |
| `json_logs: true` / `set_verbose: false` | 生产日志 |

### 3.3 `general_settings`

| 键 | 用途 |
|---|---|
| `use_redis_transaction_buffer: true` | spend 先入 Redis，持锁实例批量刷库。约 ≥1000 RPS 或 ≥10 实例必开，否则 Postgres 死锁 |
| `proxy_batch_write_at: 60` | spend 批量写间隔（秒） |
| `user_api_key_cache_ttl` | 虚拟 key DualCache TTL |
| `store_model_in_db: true` | 多实例配置源 |
| `proxy_config_reload_interval_seconds` | Slave 从 DB 拉模型和 router 设置，默认 30s |
| `database_connection_pool_limit` | 每 worker 连接数。公式 `MAX_DB / (maxReplicas × workers)` |
| `disable_error_logs: true` | 错误日志不进 spend 表 |
| `allow_requests_on_db_unavailable` | **仅 VPC 内网**。DB 挂了仍放行推理（预算检查会失效） |
| `scheduled_job_stagger.window_seconds` | 错开后台任务，避免 DB CPU 尖峰 |
| `alerting: ["slack"]` | 预算/宕机/慢请求 |

`router_settings.cache_params` **非法**：Router 不收这个键，`max_connections` 不会生效。Redis 连接池写在 `litellm_settings.cache_params`。

### 3.4 `router_settings`

| 键 | 用途 |
|---|---|
| `routing_strategy` | 未分组模型的默认 LB。高流量官方推荐 `simple-shuffle` |
| `routing_groups` | 按公开 `model_name` 覆盖策略。同名多 credentials 才值得建组 |
| `redis_host/port/password` | Router DualCache：cooldown、usage、latency |
| `num_retries` | **组内**同一部署重试 |
| `retry_after` | 重试等待 |
| `allowed_fails` | 进入 cooldown 前允许失败次数。现网建议 2 |
| `cooldown_time` | 坏节点冷却秒数。现网建议 30（官方默认 5 太短） |
| `timeout` | router 超时 |
| `fallbacks` | 跨 **不同公开名** 的通用降级 |
| `context_window_fallbacks` | 仅上下文超限 |
| `content_policy_fallbacks` | 仅内容策略拒绝 |
| `max_fallbacks` | 跨组深度，默认 5 |
| `enable_weighted_failover` | simple-shuffle 组内加权换节点（仍是同一公开名） |

XHub 现网约定：

- 默认 `simple-shuffle`。
- 只给 **同一 `model_name` 且有多套 credentials** 建 `routing_groups`。
- `deepseek-v3.2-251201` / `deepseek-v4-flash` / `deepseek-v4-pro` 用 `cost-based-routing`。
- 单 credentials 的 `gpt-5.4*` / `doubao-seed-2.0-lite` 不要建组。
- 不要把 flash+pro、sonnet+haiku 混进一个 group；跨档用 fallback。

---

## 4. Provider 之间如何负载均衡

`model_list` 里多条记录可以共用同一个公开 `model_name`，各自 `litellm_params.model` / `api_base` / `api_key` 不同。Router 把它们当成 **同一个 model group 的多个 deployment**。

选择顺序：

1. `should_include_deployment()` 按 team overlay 过滤
2. 去掉 health-check 不健康、cooldown、blocked
3. 可选 `order`（1 优先于 2）
4. 在剩余集合上跑 `routing_strategy`

这是组内 LB，请求仍然叫 `gpt-5.4`。

### 4.1 各策略

| 策略 | 实现 | 行为 | 适用 |
|---|---|---|---|
| `simple-shuffle` | `router_strategy/simple_shuffle.py` | 按 `weight`/`rpm`/`tpm` 加权随机，没有则纯随机。无 Redis lookup | **高流量默认** |
| `least-busy` | `LeastBusyLoggingHandler` | inflight 最少。默认偏本进程 DualCache | Azure TPM 紧张、单实例 |
| `latency-based-routing` | `LowestLatencyLoggingHandler` | 滑动窗口延迟最低；流式记 TTFT。args：`ttl`、`lowest_latency_buffer` | 同价同能力多区域 |
| `cost-based-routing` | `LowestCostLoggingHandler` | 每 token 成本最低。**只实现 async**；部署必须配 `model_info` 价格 | DeepSeek 多渠道差价 |
| `usage-based-routing` | `LowestTPMLoggingHandler` | 当前分钟 TPM 最低 | **已 deprecated** |
| `usage-based-routing-v2` | `LowestTPMLoggingHandler_v2` | 跨实例 Redis incr。请求路径多一次 Redis | 低中流量精细限流 |
| `provider-budget-routing` | 校验列表有，不在默认 selector | provider 预算用完切走 | 不建议作默认 |
| `lar1` | 独立分支 | 非 selector 模型 | 特殊场景 |

`routing_groups` 是 **给不同公开名指定不同策略**，不是“把多个 provider 捆成一组”。同一公开名的多个部署本来就在一组里。

Team overlay：`map_team_model()` + `should_include_deployment()`。某 team 已有 `(team_id, public_name)` 专用部署时，**排除同名全局部署**。A 团队 `gpt-5.4` 走 Fenno，B 团队走 Qiniu，互不串。

---

## 5. 模型端点 Fallback

失败顺序（`async_function_with_fallbacks`）：

1. **组内 `num_retries`**：同一台部署
2. **`allowed_fails` + `cooldown_time`**：坏节点从候选里拿掉（要 Redis 才跨 Slave 共享）
3. **`order` 分层** / **`enable_weighted_failover`**：仍是同一公开名，换另一套 credentials
4. **`context_window_fallbacks`** / **`content_policy_fallbacks`**
5. **`fallbacks`**：换另一个公开 `model_name`

`run_async_fallback()` 会跳过 `mg == original_model_group`。所以：

```yaml
# 有效：跨模型降级
router_settings:
  fallbacks:
    - gpt-5.4: ["gpt-5.4-mini"]
    - deepseek-v4-pro: ["deepseek-v4-flash"]

# 无效：不能指望 fallbacks 在「同一个 gpt-5.4」里从 Qiniu 切到 Fenno
# 那种场景必须配两条 model_name: gpt-5.4 的 deployment，走组内 LB + cooldown
```

流式 POST 一旦开始吐 token，OpenResty **不要**切区域，否则重复计费。区域级只允许连接未建立时的谨慎重试。

---

## 6. 访问组控制 TEAM 可调用的 provider 端点

两套机制，鉴权层都会看：

| 机制 | 存放 | 作用 |
|---|---|---|
| 统一 Access Group 表 | `LiteLLM_AccessGroupTable.access_model_names` + `assigned_team_ids` / `assigned_key_ids` | 把组展开成允许的公开模型名 |
| 部署标签 | `model_info.access_groups` | key/team `models` 里写组名时，按部署切开 |

管理 API：`POST /v1/access_group`，body `access_group_name` / `access_model_names`。  
XHub：Prisma 表/列缺失 → **HTTP 503**，跑 `20260817000000_repair_access_group_schema`。

请求时：

1. `can_key_call_model()`：key.models，失败再展开 key.access_group_ids
2. `can_team_access_model()`：team.models，同样可展开 team.access_group_ids
3. 通配：`openai/*`、`*`、`all-proxy-models`、`all-team-models`

**Access Group 不选供应商。** 只决定“能不能叫这个公开名”。  
真正绑 vendor 是 Team overlay：创建模型时勾选 **Associate with Team**，内部名变成 `model_name_{team_id}_{uuid}`，对外仍是 `team_public_model_name`。

如果要用访问组切开同一公开名的两个供应商，必须：

- 按 **deployment** 打不同 `access_groups`（不要按模型名打，否则所有同名部署被打进同一组）
- 调用方 `models` **只写组名、不写模型名**，否则过滤被跳过

更稳的做法永远是 Team 专属部署。

---

## 7. KEY 限制访问不同 provider、控制成本

没有 `allowed_providers`。落地组合：

1. **key.models 白名单**  
   - 精确公开名：`["gpt-5.4", "deepseek-v4-flash"]`  
   - 家族通配：`["openai/*"]`（限制 provider **家族**，不是某个 api_base）
2. **绑 `team_id`**，让 overlay 只能打到该团队的 Fenno/Qiniu 部署
3. **Access Group** 批发给一批 key
4. **预算与速率**（落 Postgres，计数靠 Redis）  
   - `max_budget` + `budget_duration`：硬窗口  
   - `tpm_limit` / `rpm_limit` / `max_parallel_requests`  
   - `model_max_budget`：按模型  
   - team 还有 `max_budget`，总额建议 `key_count × TEAM_BUDGET_UNIT`（门户默认 1500/月）
5. **Portal 提额**：申请人 → 上级 LDAP → 可选老板 → 提额管理员。只有最终管理员调用 `POST /key/update`，并按差值加 team `max_budget`。

Team `models` 是 ACL，不是 provider 绑定。不要把供应商写进 `LiteLLM_TeamTable.models` 当绑定用。

---

## 8. 全球分布式部署（对照现网 Master / Slave）

### 8.1 角色

| 角色 | 现网 compose | 职责 |
|---|---|---|
| Master | db + db-init + litellm + sub2api + prometheus | Postgres writer、schema、Admin UI、Key/模型变更、Spend 账本、监控 |
| Slave | redis + litellm | 无状态推理；本地 Redis；连 Master DB；关 UI / 关 schema |

镜像全部 pin：`xhub:v1.95.15`。不要用 `latest`。

### 8.2 Master 服务用途

| 服务 | 用途 | 注意 |
|---|---|---|
| `db` postgres:16 | LiteLLM 系统库，宿主机 `6432:5432` | `ulimit nofile=100000`；外挂 `postgresql.conf` |
| `db-init` | 一次性建 Sub2API 库/用户 | `restart: "no"`，等 db healthy |
| `litellm` | 数据面 + 管理面 | `STORE_MODEL_IN_DB=True`；config.yaml 挂进去；health `/health/liveliness` |
| `sub2api` | 独立订阅/账号服务，共用 Postgres 实例不同库 | JWT/TOTP 必填；`AUTO_SETUP=true` |
| `prometheus` | 抓 LiteLLM `/metrics`，TSDB 留 5 天 | 路径拼写 `promethues_data` 是历史笔误，改动要连带挂载 |

Master compose **没内置 Redis**。如果 Master 也跑多副本、或要和 Slave 共享全局预算/cooldown，Master 必须另接同一套 Redis，并在 `config.yaml` 写 `router_settings.redis_*` + `litellm_settings.cache`。

环境变量：`DATABASE_URL`、各 provider key、`HTTP(S)_PROXY`。**务必补 `LITELLM_MASTER_KEY` 和 `LITELLM_SALT_KEY`**，否则 Slave 对不齐，已入库的模型 key 解不开。

### 8.3 Slave 服务用途

| 项 | 用途 |
|---|---|
| 本地 `redis:7.0` | 本区 cache / cooldown / rpm。`maxmemory 512mb` + `allkeys-lru`，AOF 关闭（可丢，换正确性换延迟） |
| `DATABASE_URL` | 指向 Master writer `10.236.24.90:6432` |
| `DATABASE_URL_READ_REPLICA` | 读走本区/就近副本。现网占位仍是 `10.236.24.90`，真正多活要改成各区只读库 |
| `DISABLE_SCHEMA_UPDATE=true` | 禁止 Slave 跑 migrate，避免多 writer 抢 schema |
| `DISABLE_ADMIN_UI=true` | 管理面单写，避免从边缘改 Key |
| `LITELLM_MASTER_KEY` / `SALT_KEY` | 与 Master **逐字节相同** |
| `STORE_MODEL_IN_DB=true` | 轮询加载 Master 写入的模型与 Key |

健康检查用 `/health/liveliness` 合理（不打真实模型、不产生费用）。K8s readiness 更推荐 `/health/readiness`，`initialDelaySeconds` 120。

### 8.4 推荐全球拓扑

```
客户
 ├─ 公网：DNS 延迟 / Global Accelerator
 └─ 内网：区域 VIP
          ▼
   OpenResty（只选区域，不持有 provider key）
     cn 模型 → 优先 HK LiteLLM
     global 模型 → US/SG/JP，禁止 HK 转发全球模型
          ▼
   各区 XHub:v1.95.15 + 本地 Redis
          ▼
   就近 Provider（Qwen/DeepSeek 走 HK；OpenAI/Claude/Bedrock 走 US/JP/SG）
          ▼
   Postgres：Master writer + 各区只读（或 Aurora Global）
```

OpenResty 职责止于「这个请求去哪个区域的 `:4000`」。  
LiteLLM 职责：组内 LB、cooldown、模型 fallback、team/vendor、预算。

### 8.5 现网风险与补强

1. **Slave 本地 Redis 不能做全球硬预算。** 各区独立计数，超预算会晚一拍甚至超卖。需要全局限额就把 Router Redis 指到同一套（接受跨区 RTT），或接受「区域软限流 + Postgres 账本最终一致」。
2. **Master 缺 Redis + `use_redis_transaction_buffer`。** 多 Slave 同时刷 spend 容易打爆 `llmproxy` 连接。config 应开 buffer，Postgres `max_connections` 按 `replicas × workers × pool` 留余量。
3. **`DATABASE_URL_READ_REPLICA` 与 writer 同 IP** 等于没读写分离。SG/JP 应配本地 replica。
4. **nofile 100000** 对高并发正确；同时要调 Postgres/Redis 连接上限，否则只是把 fd 耗在 CLOSE_WAIT。
5. **Sub2API 与 LiteLLM 同机抢 Postgres。** 用独立库对，但连接池和备份策略要分开算。
6. **严格 Responses 上游**仍需部署级 `additional_drop_params: [metadata]`（#35780，1.95.15 未系统修）。
7. 流式请求不要在 OpenResty 做 `proxy_next_upstream`。

### 8.6 建议的 `config.yaml` 核心（Master/Slave 共用一份，靠环境变量区分 Redis）

```yaml
litellm_settings:
  return_response_headers: true
  drop_params: true
  json_logs: true
  set_verbose: false
  num_retries: 3
  request_timeout: 60
  cache: true
  cache_params:
    type: redis
    host: os.environ/REDIS_HOST
    port: os.environ/REDIS_PORT
    password: os.environ/REDIS_PASSWORD
    ttl: 1800
    mode: default_on
    max_connections: 100
    supported_call_types: ["acompletion", "aembedding"]

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  store_model_in_db: true
  proxy_batch_write_at: 60
  use_redis_transaction_buffer: true
  user_api_key_cache_ttl: 60
  disable_error_logs: true
  database_connection_pool_limit: 10
  proxy_config_reload_interval_seconds: 30

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 3
  retry_after: 5
  timeout: 60
  allowed_fails: 2
  cooldown_time: 30
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD
  fallbacks:
    - gpt-5.4: ["gpt-5.4-mini"]
    - deepseek-v4-pro: ["deepseek-v4-flash"]
  routing_groups:
    - group_name: deepseek-v3-2-group
      models: ["deepseek-v3.2-251201"]
      routing_strategy: cost-based-routing
    - group_name: deepseek-v4-flash-group
      models: ["deepseek-v4-flash"]
      routing_strategy: cost-based-routing
    - group_name: deepseek-v4-pro-group
      models: ["deepseek-v4-pro"]
      routing_strategy: cost-based-routing
```

`routing_groups` 里的别名必须已在 `model_list` / DB 中存在，否则 Router 启动失败。`cost-based-routing` 的每个部署都要有价格。

---

## 9. 权限与成本：一次请求的完整决策

```
虚拟 Key
  ├─ models / access_group_ids     → 能不能叫这个公开名
  ├─ team_id                       → 用哪套 team overlay 供应商
  ├─ max_budget / tpm / rpm        → 花多少、多快
  └─ Router
        ├─ 同名多 deployment       → simple-shuffle / cost-based
        ├─ 坏节点                  → allowed_fails + cooldown
        └─ 整组失败                → fallbacks 换公开名
```

操作手册级对应关系：

- 控制 **谁能用哪些模型**：Access Group + key/team `models`
- 控制 **同一模型走哪家供应商**：Team 关联模型，不要混用全局同名部署
- 控制 **钱**：key/team `max_budget`，门户提额改的也是这两个
- 控制 **可用性**：同名多 credentials + cooldown；跨档用 fallbacks
- 控制 **全球延迟**：OpenResty 选区域 + 就近 provider，不把全球模型送到 HK

## 架构图示

本文档配套的架构图已归档在 `docs/images/`（含 1 张交互式 HTML，需用浏览器打开）：

| 图 | 文件 | 说明 |
|---|---|---|
| 网关协议转化调用链 | `images/网关协议转化调用链.png` | 网关分层与 Chat / Responses / Messages 协议转化调用链 |
| 同名负载与跨模型 fallback | `images/同名负载与跨模型_fallback.html` | 交互式：同名多供应商负载均衡 vs 跨公开模型名 fallback 对比 |
| 访问组 / TEAM / KEY 权限分层 | `images/访问组_TEAM_KEY_权限分层.png` | Access Group（白名单）、Team overlay（绑供应商）、Virtual Key（models + 预算/限速）三套控制面 |
| 全球 Master / Slave 部署 | `images/全球_Master_Slave_部署架构.png` | Master（PG/UI/Sub2API/Prometheus）+ 无状态 Slave + OpenResty 全球选区域部署 |
