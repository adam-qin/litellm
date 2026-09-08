# XHub v1.95.29：可用性、超时与全局故障转移

对照代码：`litellm-xhub` / `xhub-qiniu` HEAD `fb9cd0e81f`（annotated tag `v1.95.29` peeled `4677741ff4`）。  
对照 Dashboard：**Routing 系统设置 → Reliability & Retries**。本文只记录现网语义，不改 Router。

配套图示（SVG HTML，浏览器直接打开）：

| 图 | 文件 | 说明 |
|---|---|---|
| 超时解析 | `images/超时解析优先级.html` | 请求 → 节点 → `request_timeout` → 全局 `timeout=120` |
| 链上路时延 | `images/全局故障转移与超时叠加.html` | 跨公开名 fallback 每跳重开 120s，kwargs timeout 会粘住 |
| 同名 vs 跨名 | `images/同名负载与跨模型_fallback.html` | 同名是 LB；`fallbacks` 只换不同公开名 |

相关文档：

- 组内廉价优先 / 超时切官方：`xhub_v1.95.15_cheap_first_timeout_fallback.md`
- Router / LB / Access Group 总览：`xhub_v1.95.15_architecture.md`

---

## 0. 结论先行

Dashboard 的 **TIMEOUT=120 是每次尝试（per-attempt）的默认 HTTP 超时，不是整条 fallback 链的总预算。**

全局故障转移里的多个模型：

1. **默认值相同**：没有节点级 timeout 时，A / B / C 都用 `router_settings.timeout=120`。
2. **时钟不共享**：A 超时后切 B，B 重新计时 120s。墙钟相加，不是 120s 内切完。
3. **kwargs 会粘住**：第一跳把解析结果写入 `kwargs["timeout"]`，后续 hop 优先读 kwargs，fallback 模型自己的 `litellm_params.timeout` 不再生效。
4. **`num_retries=2` 按公开名各自再套**：每个模型都是 1 次原请求 + 2 次重试，不是整条链总共 2 次。
5. **同名写进 `fallbacks` 无效**：`run_async_fallback()` 对字符串 `mg == original_model_group` 直接 `continue`。同名换供应商靠组内 LB / `order` / `enable_weighted_failover`。

截图配置下 `A → B` 两边都挂死：客户端最坏约 **732s（12 分钟）**，不是 120s。

---

## 1. Dashboard 字段语义

截图当时值：

| 字段 | 截图值 | 作用 | 和跨模型 fallback 的关系 |
|---|---|---|---|
| Routing strategy | `simple-shuffle` | 同一公开名多 deployment 时随机挑 | 不负责换公开名 |
| Enable tag filtering | off | 不按 tag 选路 | 无关 |
| Enable weighted failover | `false` | 关掉同组加权换节点 | 同名换供应商只能靠 shuffle + 重试 / `order` |
| Timeout | **120** | **每次尝试**的 HTTP 超时 | fallback 下一跳再套一遍 120s |
| Number of retries | **2** | 当前公开名：1 次原请求 + 2 次重试 | **每个公开名各自 2 次** |
| Retry after | 3 | 组内没健康节点时，重试最少等 3s | 同组还有健康节点则立刻重试（sleep=0） |
| Allowed fails | 2 | 连续失败 2 次才进 cooldown | 跨请求熔断，不是本请求切模型的条件 |
| Cooldown time | **0** | 代码 `cooldown_time or DEFAULT(5)` | **0 是 falsy，实际冷却 5s**，不是「不冷却」 |
| Model group alias | `{}` | 无别名 | 不影响 |

这页 **没有** `fallbacks` 列表。全局故障转移要另配 `router_settings.fallbacks`，例如 `gpt-5.4 → gpt-5.4-mini`。`max_fallbacks` 默认 5，截图未展示。

源码：

- 字段元数据：`litellm/types/management_endpoints/router_settings_endpoints.py`
- UI 表单：`ui/litellm-dashboard/src/components/common_components/RouterSettingsAccordion.tsx`

---

## 2. 超时解析优先级

打开 `images/超时解析优先级.html`。

每次真正打上游前，`_update_kwargs_with_deployment()` 调用 `_get_timeout()`：

流式先走 `_get_stream_timeout()`，没有再回落到 `_get_non_stream_timeout()`。

非流式顺序（`router.py`）：

```
kwargs.timeout / request_timeout          # 请求体；一旦写入会粘到后续 hop
  → deployment.litellm_params.timeout     # 该节点
  → self.request_timeout                  # litellm_settings.request_timeout（仅 Router 也配了 timeout 时）
  → self.timeout                          # router_settings.timeout = 120
  → default_litellm_params.timeout
```

关键实现：

```python
# router.py  _update_kwargs_with_deployment()
kwargs["timeout"] = self._get_timeout(kwargs=kwargs, data=deployment["litellm_params"])

# _get_non_stream_timeout()
timeout = (
    kwargs.get("timeout", None)
    or kwargs.get("request_timeout", None)
    or data.get("timeout", None)
    or data.get("request_timeout", None)
    or self.request_timeout
    or self.timeout
    or self.default_litellm_params.get("timeout", None)
)
```

`run_async_fallback()` 只改 `kwargs["model"]`（或把 dict 条目 `update` 进 kwargs），**不 pop timeout**。所以：

- 没有节点级 timeout → 每跳都落到全局 120。
- 第一跳解析出 8 或 120 后写入 kwargs → 第二跳即使节点配了 60，也会继续用 8 / 120。

未配 Router `timeout` 时，`self.timeout = timeout or litellm.request_timeout`，社区默认是 6000s sentinel。现网截图已经显式 120，不会走到 6000。

---

## 3. 失败顺序与全局故障转移

打开 `images/同名负载与跨模型_fallback.html` 和 `images/全局故障转移与超时叠加.html`。

调用链（async 网关路径）：

```
client  →  Router.acompletion()
       →  async_function_with_fallbacks()
       →  async_function_with_retries()      # 当前公开名；num_retries=2
       →  _acompletion()
       →  async_get_available_deployment()
            1. team overlay / 健康 / cooldown
            2. _get_order_filtered_deployments()   # 默认只留 min(order)
            3. simple-shuffle 在剩余池挑 1 个
       →  litellm.acompletion(**deployment.litellm_params)
              timeout 来自 _get_timeout()
失败（含 Timeout）
       →  async_function_with_fallbacks_common_utils()
            A. 多个 order → {model: 原公开名, _target_order: 下一档}
            B. 否则 enable_weighted_failover（截图 false，跳过）
            C. context_window / content_policy 专用链
            D. router_settings.fallbacks 换另一个公开名
       →  run_async_fallback() 再进 async_function_with_fallbacks
```

同名 vs 跨名：

| 机制 | 换什么 | 截图是否启用 |
|---|---|---|
| `simple-shuffle` | 同一公开名的不同 credentials | 是，组内 LB |
| `num_retries` | 再进 `_acompletion()`，可重选同组节点；**不升 order** | 2 |
| `order` | 同公开名升档（廉价→官方） | 看模型是否配了 `litellm_params.order` |
| `enable_weighted_failover` | 同组排除刚失败的 id 再加权挑 | **关** |
| `fallbacks` | **不同**公开 `model_name` | 另页配置；同名字符串被 skip |

`order` 能同名升档，是因为 fallback 条目是 dict `{"model": ..., "_target_order": 2}`，字符串相等检查对不上。跨名 `fallbacks` 传的是字符串，同名会被跳过。

---

## 4. 截图参数下的墙钟

假设 `fallbacks: [{A: [B]}]`，A / B 都没有节点级 timeout，上游都挂死，单节点组（会吃 `retry_after=3`）：

| 阶段 | 计算 | 墙钟 |
|---|---|---|
| A：1 次 + 2 次重试 | `3 × 120s` | 360s |
| A 两次 retry wait | `2 × 3s` | 6s |
| 切到 B，重新计时 | 再 `3 × 120 + 2 × 3` | 366s |
| **客户端最坏** | 串行相加 | **732s ≈ 12 min** |

同组还有健康节点时，`_time_to_sleep_before_retry()` 返回 0，retry wait 可省掉，但仍是 `3 × 120` 每公开名。

`max_fallbacks` 默认 5：链上第 3、4、5 个公开名继续加 366s。这是串行 abort 再发，不是 hedge。

流式注意：`stream_timeout` 管的是流式调用等到首 token。已经开始吐 token 后中途卡住，不会因为「总时长 120」自动切下一个公开名。

---

## 5. cooldown / allowed_fails 不要和本请求切流搞混

| 旋钮 | 作用范围 |
|---|---|
| `timeout` + `num_retries` | **本请求**内：当前公开名重试，再跨名 fallback |
| `allowed_fails` + `cooldown_time` | **跨请求**：坏节点从健康池拿掉 |

`cooldown_time=0` 在 `Router.__init__`：

```python
self.cooldown_time = cooldown_time or DEFAULT_COOLDOWN_TIME_SECONDS  # 5
```

要关掉冷却，设 `disable_cooldowns: true`，不要写 0。现网建议显式 `cooldown_time: 30`。冷却跨 Slave 共享需要 Router Redis。

---

## 6. 风险

1. **120 不是端到端 SLA。** 两个模型都超时，客户端要等十几分钟。前面 Nginx / OpenResty / 网关若只有 120s，会先掐客户端，XHub 还在后台打 B。
2. **`cooldown_time=0` 没关掉冷却。** 实际 5s。
3. **想「廉价 8s 切官方」不能靠这页 120。** 必须写在廉价节点 `litellm_params.timeout`，且 `num_retries: 0`。全局 120 会套到官方。详见 `xhub_v1.95.15_cheap_first_timeout_fallback.md`。
4. **第一跳 timeout 会粘到 fallback。** 廉价 8s 写进 kwargs 后，跨名官方也会被当成 8s。廉价优先用同名 `order`，不要用跨名 `fallbacks` 干这件事。
5. **同名写进 `fallbacks` 无效。** 必须不同公开名。

---

## 7. 配置建议

- **A（推荐，匹配截图语义）**：把 `timeout=120` 理解成「单次上游上限」。跨模型 fallback 接受时延相加。把 `num_retries` 降到 0 或 1，避免每个模型都 3×120。`cooldown_time` 改成明确的 30，不要写 0。
- **B**：每个模型自己配 `litellm_params.timeout`（廉价短、官方长），全局 timeout 只当兜底。跨名 fallback 不要指望第二跳还能用自己的 timeout。同名廉价→官方用 `order` + `num_retries: 0`。
- **C**：保持现状。能 failover，但故障时客户端 P99 到分钟级，和页面上的「120 秒」观感不一致。

示例（跨名降级，接受相加时延）：

```yaml
router_settings:
  routing_strategy: simple-shuffle
  timeout: 120
  num_retries: 1                 # 每公开名最多 2 次尝试
  retry_after: 3
  allowed_fails: 2
  cooldown_time: 30              # 不要写 0
  enable_weighted_failover: false
  max_fallbacks: 5
  fallbacks:
    - gpt-5.4: ["gpt-5.4-mini"]
    - deepseek-v4-pro: ["deepseek-v4-flash"]
```

示例（同名廉价优先，不要用上面的 fallbacks 干这事）：

```yaml
# 同一 model_name，order 1 / 2；廉价 timeout=8，官方 60；num_retries: 0
# 见 xhub_v1.95.15_cheap_first_timeout_fallback.md
```

落地检查：

1. 压测 A 成功：日志无 `Falling back to model_group`。
2. 压测 A 强制 timeout：出现 fallback 日志，B 成功；客户端时延 ≈ A 超时 + B 时延，不是 max(A, B)。
3. 确认上游 / 网关超时大于「单跳 120 × (1+retries) × 链长」，否则客户端先断。
4. 有 team overlay 时，fallback 目标公开名也要在该 team 可见，否则切过去直接找不到部署。
