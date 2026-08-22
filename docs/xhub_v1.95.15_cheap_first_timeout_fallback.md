# XHub v1.95.15：同模型多供应商「廉价优先 + 超时切官方」

对照代码：`litellm-xhub` / `xhub-qiniu` HEAD `92706b19af`（tag `v1.95.15`）。本文只分析现有 Router 能否实现该语义，不改代码。

## 结论（先看这个）

**能做，但是「先等廉价超时，再串行切官方」，不是对赌竞速。**

| 诉求 | v1.95.15 是否原生支持 | 怎么配 |
|---|---|---|
| 同一公开名、优先廉价 | 支持 | 同 `model_name` 两套 credentials，`litellm_params.order: 1` / `2` |
| 廉价 T 秒内无返回则切官方 | 支持（串行） | 廉价节点 `timeout`/`stream_timeout` = T，`num_retries: 0`，`max_retries: 0` |
| 超时后仍打同一廉价节点 | 会，若 `num_retries > 0` | **必须把廉价节点和 Router 的 `num_retries` 都设为 0** |
| 廉价与官方同时发、谁先回用谁（hedge） | **不支持** | 没有 speculative / racing 路径 |
| 等 T 秒后官方并行起飞、廉价继续跑 | **不支持** | timeout 会 abort 廉价请求，然后才发起官方 |
| `cost-based-routing` 单独完成「超时切官方」 | **不能** | 只在健康池里永远选最便宜；超时重试仍会再选廉价 |
| `router_settings.fallbacks` 切同一公开名 | **不能** | `run_async_fallback()` 对字符串 `mg == original_model_group` 直接 `continue` |

推荐路径：**`order` + 每节点 `timeout` + `num_retries: 0`**。  
不要指望 `cost-based-routing` 或跨组 `fallbacks` 来做这件事。

## 调用链（网关 async 路径）

Proxy 走 `router.acompletion()`（`router.py`），不是 FastAPI 自己选供应商：

```
client  →  acompletion()
       →  async_function_with_fallbacks()
       →  async_function_with_retries()      # 同一 kwargs 重试，不升 order
       →  _acompletion()
       →  async_get_available_deployment()
            1. 健康/冷却过滤
            2. _get_order_filtered_deployments()   # 默认只留 min(order)
            3. simple-shuffle / cost-based 等在剩余池里挑 1 个
       →  litellm.acompletion(**deployment.litellm_params)
              timeout 取自该节点 litellm_params
失败（含 Timeout）
       →  async_function_with_fallbacks_common_utils()
            A. 若存在多个 order：构造
               {model: 原公开名, _target_order: 下一档}
            B. 否则若 enable_weighted_failover：同组加权再挑
            C. 否则跨公开名 fallbacks
       →  run_async_fallback() 再进 acompletion，重新选节点
```

关键点：

1. **选路发生在 `_acompletion` 里**，每次 fallback  hop 都会重新 `async_get_available_deployment()`。
2. **`num_retries` 重试也会再进 `_acompletion`**，但 **不会设置 `_target_order`**，所以仍只在当前档（廉价）里挑。超时后立刻切官方，必须 `num_retries: 0`。
3. `run_async_fallback()` 对 **字符串** 同名会 skip；`order` fallback 传的是 **dict** `{"model": ..., "_target_order": 2}`，比较不相等，所以同公开名可以升档。这是 order 机制能工作的原因。

测试覆盖：`tests/test_litellm/test_router_order_fallback.py`（健康时永不碰 order=2；order=1 失败则切 2；1/2 都失败切 3；全部失败再走外部 fallback）。

## 各旋钮分别做什么

### 1. `litellm_params.order`（要的就是这个）

读写位置：

- 取值：`litellm.utils._get_deployment_order()` — 先 `litellm_params.order`，再 `model_info.order`（Admin UI / API 加的动态模型走后者）。
- 过滤：`_get_order_filtered_deployments()`
  - 无 `_target_order` → 只保留 **最小 order**  
  - 有 `_target_order` → 只保留该档
- 升档：`async_function_with_fallbacks_common_utils()` 把剩余更高档 prepend 到 fallback 列表，**排在跨组 fallbacks 前面**。

语义：**同一公开名内部的优先级 failover**，不是负载均衡。order=1 健康时，order=2 **永远不会被选**（测试里 50 次全部打到 id=1）。

`ContextWindowExceededError` / `ContentPolicyViolationError` **不会**走 order 升档，它们有自己的 fallback 列表。

### 2. 每节点 `timeout` / `stream_timeout`（廉价的「一定时间」）

解析顺序（`Router._get_non_stream_timeout()` / `_get_stream_timeout()`）：

非流式：

```
请求 timeout / request_timeout
  → 节点 litellm_params.timeout / request_timeout
  → litellm_settings.request_timeout（仅显式配置时）
  → router_settings.timeout
```

流式：先 `stream_timeout` 链，没有再回落到非流式 timeout。

廉价节点把 `timeout`（以及流式的 `stream_timeout`）设成 T，官方节点设更长（如 60）。廉价超时抛 `litellm.Timeout`，进入 order 升档。

这是 **HTTP 请求超时 abort**，不是「T 秒后另开一条并行官方」。廉价 inflight 会被取消。

流式注意：`stream_timeout` 管的是流式调用的请求超时（通常等价于等到首 token）。**已经开始吐 token 后中途卡住，不会自动因「总时长 T」切官方**；那种要靠上游断连或后续 `MidStreamFallbackError`，和本需求的「一定时间没返回」不是同一件事。

### 3. `num_retries` / `max_retries`（必须关掉廉价重试）

两层重试容易叠在一起：

| 层 | 字段 | 作用 |
|---|---|---|
| Router | `router_settings.num_retries` 或节点 `litellm_params.num_retries` | 失败后对 **同一 kwargs** 再跑 `_acompletion`；节点值通过 exception.num_retries 覆盖全局 |
| SDK/httpx | `litellm_params.max_retries` | OpenAI 兼容客户端内部重试，**会把廉价 timeout 乘几次** |

廉价超时后立刻升档：

- 廉价节点：`num_retries: 0`，`max_retries: 0`
- `router_settings.num_retries: 0`（或至少不要让廉价 exception 带出 >0）

否则时间线变成 `T × (1 + num_retries)` 之后才切官方。

### 4. `cost-based-routing`（不要单独用来做超时切流）

`LowestCostLoggingHandler.async_get_available_deployments()`：

- 用 `input_cost_per_token + output_cost_per_token`（节点自定义价，否则 `litellm.model_cost`，再否则默认 5.0）
- **sort 后取 `[0]`，永远最便宜的健康节点**
- 只实现 **async**；sync `completion()` 路径被刻意省略
- 日志里记的 tpm/rpm 不参与「谁更便宜」决策，只用于打满限额后剔除

超时之后如果廉价仍健康，下一次选择还是它。除非 `allowed_fails` 把它冷却掉，后续请求才会「跳过廉价」——那是熔断，不是本请求的 T 秒切流。

**可以和 order 叠用**：order 过滤在 strategy 之前。多个廉价渠道都标 `order: 1`，组内用 `cost-based-routing` 选最便宜；失败后再升 `order: 2` 官方。这是合理组合，前提仍是廉价 `num_retries: 0`。

### 5. `enable_weighted_failover`（同组乱序再挑，不是廉价→官方）

仅 `simple-shuffle` + async。失败后排除刚失败的 `model_info.id`，在同组剩余节点加权再挑。  
**没有价格顺序**。廉价、官方若同组且都没设 `order`，第一次完全可能打到官方。  
有 `order` 时，这段 **排在 order 升档之后**；order 机制一旦接手，weighted failover 不会跑。

### 6. `allowed_fails` + `cooldown_time`（跨请求熔断，不是单请求切流）

廉价连续超时达到 `allowed_fails` 后进入 cooldown，后续请求的健康池里只剩官方，**不再先等 T 秒**。  
这对「廉价渠道大面积故障」是好事。不要用它替代本请求的 timeout；两者应一起配：单请求靠 timeout 升档，持续故障靠 cooldown 跳过廉价。

### 7. 跨组 `fallbacks`（换公开名，不是换供应商）

```python
# fallback_event_handlers.py
if mg == original_model_group:
    continue
```

`{"deepseek-v4-flash": ["deepseek-v4-flash"]}` **无效**。  
只有换成另一个公开名才走这条路，例如 `deepseek-v4-flash → gpt-5.4-mini`。那是模型降级，不是「同一模型换官方价」。

## 推荐配置（同一公开名）

以 `deepseek-v4-flash` 为例：渠道 A 低价、渠道 B 官方。客户端仍只传 `model=deepseek-v4-flash`。

```yaml
model_list:
  - model_name: deepseek-v4-flash
    litellm_params:
      model: openai/deepseek-chat
      api_base: https://cheap-gateway.example/v1
      api_key: os.environ/CHEAP_DEEPSEEK_KEY
      order: 1
      timeout: 8                 # 廉价等待上限 T
      stream_timeout: 8          # 流式等到首 token
      num_retries: 0
      max_retries: 0
      input_cost_per_token: 0.00000014
      output_cost_per_token: 0.00000028
    model_info:
      id: deepseek-v4-flash-cheap

  - model_name: deepseek-v4-flash
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_OFFICIAL_KEY
      order: 2
      timeout: 60
      stream_timeout: 60
      num_retries: 0
      max_retries: 0
      input_cost_per_token: 0.00000028
      output_cost_per_token: 0.00000110
    model_info:
      id: deepseek-v4-flash-official

router_settings:
  routing_strategy: simple-shuffle   # 有 order 时组内通常每档只有 1 个节点
  num_retries: 0                     # 全局也关掉，避免廉价超时被再打一遍
  timeout: 60                        # 官方兜底；廉价节点自己的 8s 优先
  allowed_fails: 2
  cooldown_time: 30
  enable_pre_call_checks: true
  enable_weighted_failover: false    # 有 order 时不要开，避免语义打架
```

多个廉价渠道（都比官方便宜）时：

```yaml
# 三个廉价都 order: 1，官方 order: 2
router_settings:
  routing_strategy: cost-based-routing   # 只在 order=1 池里选最便宜
  routing_groups:
    - group_name: deepseek-cheap-first
      models: ["deepseek-v4-flash"]
      routing_strategy: cost-based-routing
  num_retries: 0
```

`routing_groups` 不会「把供应商捆成一组」——同名部署本来就是一组。它只是给这个公开名指定选路策略。

## 延迟账

假设 T=8s，官方 P50=2s。

| 场景 | 客户端感知时延 |
|---|---|
| 廉价 3s 成功 | ~3s，官方 0 次调用 |
| 廉价 8s 超时，官方 2s 成功 | **~10s**（8+2，串行） |
| 廉价持续故障且已 cooldown | ~2s（直接官方） |
| 误把 `num_retries: 2` 留在廉价上 | 最坏 ~8×3 + 2 = 26s 才回官方 |

没有「8s 时官方已经在飞、总时延 max(廉价, 官方)」这种路径。若产品要 hedge，必须改 Router（并行 task + 首个成功 cancel 另一个），v1.95.15 没有。

## 和 Team overlay / Access Group 的交叉

- **Team overlay**（`model_info.team_id`）：该 team 已有同名专用部署时，Router **排除全局同名部署**。廉价/官方必须都挂在这个 team 的 overlay 上，或全局组不要被 overlay 盖掉，否则 team 流量根本进不了这套 order。
- **Access Group**：只扩展 KEY/TEAM 的 `models` 白名单，**不选供应商**。KEY 能调 `deepseek-v4-flash` 即可走廉价+官方；无法用 Access Group 单独禁止官方。
- 成本硬限制仍靠 KEY `max_budget` / `tpm_limit` / `rpm_limit`。超时切官方会增加单价，预算要按官方价估峰值。

## 明确做不到的（避免配错）

1. **Hedged request / speculative execution**：无并行双发。
2. **「廉价还在跑，T 秒后官方再发，谁先回用谁」**：timeout abort 廉价。
3. **流式已经出 token 后，因为总时长超过 T 切官方**：`stream_timeout` 不是端到端墙钟。
4. **用 `fallbacks: [{deepseek-v4-flash: [deepseek-v4-flash]}]`**：同名字符串被 skip。
5. **只开 `cost-based-routing` 当超时切流**：选最便宜，不会因本请求超时改道官方。
6. **Sync `router.completion()` + `cost-based-routing`**：该 strategy 无 sync selector。order 过滤在 sync 路径仍然生效，所以 **纯 order+timeout 的 sync 可用**；不要再叠 cost-based。
7. **`router_settings.timeout` 当廉价 T**：全局 timeout 会套到官方。T 必须写在廉价节点 `litellm_params.timeout`。

## 落地检查清单

1. 廉价、官方 **相同 `model_name`**，不同 `model_info.id`、不同 `api_base`/`api_key`。
2. `order: 1` 廉价，`order: 2` 官方；不要只配一个 order。
3. 廉价 `timeout`/`stream_timeout` = T，官方更长。
4. 廉价和 Router 都 `num_retries: 0`，廉价 `max_retries: 0`。
5. 关闭 `enable_weighted_failover`（与 order 互斥优先级，开了也轮不到）。
6. 需要跨请求跳过坏廉价：`allowed_fails: 2`，`cooldown_time: 30`。
7. 有 team overlay 时，廉价+官方都挂同一 team，或确认全局组不会被排除。
8. 压测两种路径：廉价成功（官方 0 流量）、强制廉价 timeout（日志出现 Falling back 且命中 official id）。
9. 接受 P99 切流时延 ≈ T + 官方时延，而不是 max(T, 官方)。

## 若以后要真·对赌

需要新增 Router 能力，大致是：

- 选 order=1 与 order=2 各一个 deployment
- `asyncio.wait` FIRST_COMPLETED，廉价侧 `wait_for(T)`
- T 到仍无结果则启动官方，取消慢的一方
- 计费/日志要能标 `hedge_winner`

这不在 v1.95.15 范围。现网用 order+timeout 已经能「大部分走廉价、慢了才付官方价」，只是切流当次会多等一个 T。
