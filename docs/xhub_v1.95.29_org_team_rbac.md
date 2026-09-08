# XHub v1.95.29 组织 / 团队 / 成员 / 角色 / 权限边界

对照代码：`xhub-qiniu` `4677741ff4`（annotated tag `v1.95.29`）。
对照文档：LiteLLM 1.95 Access Control、Multi-Tenant Architecture、Team Model Add（2026-09 官方页）。

本文档配套图示已归档在 `docs/images/`（SVG HTML，浏览器直接打开）：

| 图 | 文件 | 说明 |
|---|---|---|
| 四层嵌套 | `images/组织团队用户Key_四层嵌套.html` | Organization → Team → User → Key；团队模型绑 `team_id` |
| 三平面角色 | `images/三平面角色不继承.html` | 全局 `user_role` / 组织 membership / 团队 `admin\|user` 互不继承 |
| 委派自管 | `images/团队自管委派链.html` | Proxy Admin → Org Admin → Team Admin → 成员 |
| 独享路由 | `images/团队独享模型路由.html` | 同名公开模型按 `team_id` 走各自凭据 |

## 0. 结论先行

XHub 的多租户是四层嵌套：**组织 → 团队 → 用户 → 虚拟 Key**。权限不是一条继承链，而是 **三套互不继承的角色**：

| 维度 | 落点 | 枚举 |
|---|---|---|
| 全局代理角色 | `LiteLLM_UserTable.user_role` | `proxy_admin` / `proxy_admin_viewer` / `org_admin` / `internal_user` / `internal_user_viewer`(弃用) / `team` / `customer` |
| 组织成员角色 | `LiteLLM_OrganizationMembership.user_role` | `org_admin` / `internal_user` / `internal_user_viewer` |
| 团队成员角色 | `LiteLLM_TeamTable.members_with_roles[].role` | `admin` / `user` |

**要让「一个组织下的某个团队自己管自己的成员、Key、模型与端点，并且独享自己的模型」**，正确路径是：

1. Proxy Admin 建组织并指定 `org_admin`
2. Org Admin 在组织内建团队并指定 `members_with_roles.role=admin`（Team Admin）
3. Team Admin 管成员、Key、`team_member_permissions`、团队模型（`model_info.team_id` + `team_public_model_name`）
4. 推理时 Router 按 `team_id` 过滤部署，别的团队看不到这条端点

XHub 相对上游的关键 overlay：**组织 / org_admin / team_admin / team_member_permissions / 团队绑定模型，不走 Enterprise `premium_user` 门控**。上游文档仍把它们标成 Premium。

---

## 1. 四层实体与关联

官方多租户文档把租户写成四级：Organizations contain Teams, Teams contain Users, Users and Teams own Keys。支出同时归因到 Key / User / Team / Organization；路径上任一层超预算即拦截。

打开 `images/组织团队用户Key_四层嵌套.html` 看同一组织下 Team A / Team B 各自的成员、服务账号和同名 `gpt-4o` 端点。

```
Organization  1 ──*  Team  1 ──*  TeamMembership  *──1  User
     │                  │                                  │
     │                  │                                  │
     └──* OrganizationMembership *── User                  │
                                                           │
Key.user_id ────────────────────────── User                │
Key.team_id ────────────────────────── Team                │
Key.org_id  ────────────────────────── Organization        │
Deployment.model_info.team_id ──────── Team                │
```

### 1.1 组织 `LiteLLM_OrganizationTable`

源码：`litellm/models/organization.py`

- `organization_id` / `organization_alias`
- `budget_id` + `litellm_budget_table`（max_budget / tpm / rpm）
- `models[]`：组织允许的模型白名单；含 `all-proxy-models` 时跳过校验
- `users` / `object_permission`

组织成员不在组织表里摊开，而在 `LiteLLM_OrganizationMembershipTable`：`user_id + organization_id + user_role + spend`。

创建组织：`POST /organization/new`，代码硬约束 **Only admins can create orgs**，即全局 `proxy_admin`。Org Admin UI 没有创建按钮。

### 1.2 团队 `LiteLLM_TeamTable`

源码：`litellm/models/team.py`

- `team_id` / `team_alias` / `organization_id`（可空 → 独立团队）
- `members_with_roles: List[Member]`，`Member.role ∈ {admin, user}`
- `team_member_permissions: Optional[List[str]]`
- `models[]`、`tpm_limit` / `rpm_limit` / `max_budget`
- `litellm_model_table.model_aliases`：团队公开名 → 内部 `model_name_{team_id}_{uuid}`
- `access_group_ids` / `default_team_member_models`

团队挂到组织后，`_check_org_team_limits()` 强制：

- 团队 `max_budget` 不得超过组织预算
- 团队 `models` 必须是组织白名单子集（除非组织是 `all-proxy-models`）
- 团队 TPM/RPM 不得超过组织限额

`team_id=litellm-dashboard` 是 UI session 哨兵，禁止作为真实团队 ID。

### 1.3 用户 `LiteLLM_UserTable`

源码：`litellm/models/user.py`

- `user_role`：全局代理角色
- `teams: List[str]`：加入过的团队
- `organization_memberships[]`：组织侧角色
- `team_id` / `organization_id`：历史兼容字段，**不是**当前权限判定主路径

一个用户可以同时：

- 全局是 `internal_user`
- 在 Org A 是 `org_admin`
- 在 Team T1 是 `admin`，在 Team T2 是 `user`

判定时必须看**当前操作对象**，不能只看 `user_role`。

### 1.4 虚拟 Key `LiteLLM_VerificationToken`

源码：`litellm/models/verification_token.py`

| 形态 | 绑定 | 行为 |
|---|---|---|
| User-only | `user_id` | 跟用户走，删用户会删 Key |
| Team / 服务账号 | `team_id` | 团队共享，成员离职不删 |
| User+Team | 两者都有 | 同时受用户预算和团队预算约束 |
| Org 归因 | `org_id` | 花费滚到组织 |

Key 还有自己的 `models[]` / `max_budget` / `tpm` / `rpm` / `permissions`。请求被拦截的条件是路径上**任意一层**超预算。

---

## 2. 角色清单

打开 `images/三平面角色不继承.html`：全局 / 组织 membership / 团队 `members_with_roles` 是三列，不是一条继承链。

### 2.1 全局代理角色 `LitellmUserRoles`

源码：`litellm/proxy/_types.py`

| 值 | 含义 | 平台级能力 |
|---|---|---|
| `proxy_admin` | 平台超管 | 建组织、管所有团队/用户/Key/模型；可抬高团队预算 |
| `proxy_admin_viewer` | 平台只读 | 看全部 Key 与全平台 spend；不能写 |
| `org_admin` | 组织管理员（也可作为全局 user_role） | 真正生效靠 **组织 membership**，不是单靠这个字符串 |
| `internal_user` | 内部用户 | 登录、管自己的 Key（还要过团队权限）、看自己的 spend |
| `internal_user_viewer` | 已弃用 | 官方建议改用团队/组织角色 |
| `team` | JWT 团队身份 | 给 JWT auth 用，不是 Dashboard 人账 |
| `customer` | 外部客户 | 外部租户，不参与内部委派链 |

官方 Access Control 表（OSS 全局角色）：

| Action | Proxy Admin | Proxy Admin Viewer | Internal User |
|---|---|---|---|
| Create organizations | 是 | 否 | 否 |
| Create teams | 是 | 否 | 否（XHub：Org Admin 可在本组织建） |
| Create/delete any keys | 是 | 否 | 否 |
| Create/delete own keys | 是 | 否 | 是（受 team_member_permissions） |
| View all platform spend | 是 | 是 | 否 |
| Add/remove users | 是 | 否 | 否 |

### 2.2 组织成员角色 `OrgMember.role`

源码：`OrgMember.role: Literal[ORG_ADMIN, INTERNAL_USER, INTERNAL_USER_VIEW_ONLY]`

判定函数：`_is_user_org_admin_for_team()`  
条件：团队有 `organization_id`，且调用者 `organization_memberships` 中对应组织的 `user_role == "org_admin"`。

Org Admin 能做：

- 本组织内建团队、给本组织团队加成员（含指定 Team Admin）
- 看本组织 spend、给本组织用户建 Key
- 保持或降低本组织团队 `max_budget`；抬高时仍受组织预算上限

Org Admin **不能**：

- 建组织（只有 Proxy Admin）
- 管其他组织
- 改组织自己的预算 / 速率 / 模型白名单（官方表）
- 仅凭 `userRole==="Admin"` 就变成某个团队的 Team Admin（v1.95.29 UI 已拆开）

### 2.3 团队角色 `LiteLLMTeamRoles`

源码：`TEAM_ADMIN = "admin"`，`TEAM_MEMBER = "user"`

判定函数：`_is_user_team_admin()`  
条件：`members_with_roles` 里存在 `user_id == 调用者 且 role == "admin"`。

UI：`isUserTeamAdminForTeamId(teams, model.team_id, userID)`，**不要**把 Proxy Admin 的 `userRole==="Admin"` 当成 Team Admin。

Team Admin 能做（本团队）：

- 增删成员、改成员预算/速率
- 改团队 TPM/RPM、允许模型列表
- 保持或降低 `max_budget`（`_check_team_budget_update_authority`：抬高或清空上限只有 Proxy Admin）
- 为成员创建/删除 Key
- 上架/编辑/删除本团队 DB 模型（XHub 不要求 premium）
- 配置 `team_member_permissions`

Team Admin **不能**：

- 建新团队
- 给团队挂全局代理模型（只能挂 `model_info.team_id = 本团队` 的部署）
- 看见或路由到其他团队的 `team_id` 部署

普通成员 `role=user`：默认只有 `/key/info`、`/key/health`；其余由 `team_member_permissions` 打开。Team Admin / Org Admin 不受该列表限制。

---

## 3. 权限边界（按资源）

### 3.1 组织

| 操作 | Proxy Admin | Org Admin | Team Admin | 成员 |
|---|---|---|---|---|
| 创建组织 | 是 | 否 | 否 | 否 |
| 看见组织菜单 | 是 | 是（membership 判定，无 premiumUser 隐藏） | 否 | 否 |
| 给组织加 org_admin | 是 | 本组织可以 | 否 | 否 |
| 改组织预算/模型白名单 | 是 | 否（官方） | 否 | 否 |

### 3.2 团队

| 操作 | Proxy Admin | Org Admin | Team Admin | 成员 |
|---|---|---|---|---|
| 创建团队 | 任意 | 仅本组织 + `organization_id` | 否 | 否 |
| 更新本团队设置 | 是 | 本组织团队 | 本团队 | 否 |
| 抬高 / 取消 max_budget | 是 | 组织范围内（仍受组织上限） | 否 | 否 |
| 添加 Team Admin | 是 | 本组织团队 | 本团队已有 admin 可继续加 | 否 |
| 成员自助加入 available team | — | — | — | 只能加自己且 `role=user`，禁止自提成 admin |

代码：`_validate_team_member_add_permissions()` 允许的三种管理员：Proxy Admin / 该团队 Team Admin / 该团队所属组织的 Org Admin。available-team 旁路禁止提权。

### 3.3 成员

用户加入团队 ≠ 获得全局角色。全局 `internal_user` 可以在 A 团队是 admin、B 团队是 user。

删除用户会删除其个人 Key，不删除团队服务账号 Key。

### 3.4 虚拟 Key

更新/删除 Key 的授权链（`key_management_endpoints.py`）：

1. 调用者是 `PROXY_ADMIN`，或
2. `_is_user_team_admin(...)`，或
3. `TeamMemberPermissionChecks.does_team_member_have_permissions_for_endpoint(...)`

并且 Key 所属用户必须是该团队成员。

`team_member_permissions` 可选项：

| 路由 | 默认 | 说明 |
|---|---|---|
| `/key/info` | 基线，不可去掉 | 查看 |
| `/key/health` | 基线，不可去掉 | 健康检查 |
| `/key/list` | 关 | 列出团队 Key |
| `/key/generate` | 关 | 创建用户 Key |
| `/key/service-account/generate` | 关 | 创建服务账号 Key |
| `/key/update` `/key/delete` `/key/regenerate` | 关 | 改 / 删 / 轮换 |
| `/key/block` `/key/unblock` | 关 | 封禁 |
| `/key/access_group_assignment` | 关 | 成员给 Key 挂 access group |

`[]` 仍会并上基线。`None` 回落到默认基线。谁能改这份列表：Proxy Admin、本组织 Org Admin、本团队 Team Admin。

推荐配置：

- 只读（默认）：`["/key/info", "/key/health"]`
- 可建不可删：再加 `/key/generate` `/key/update`
- 团队完全自管：再加 `/key/delete` `/key/regenerate` `/key/block` `/key/unblock` `/key/list` `/key/service-account/generate`

### 3.5 模型与端点

两层完全不同：

**A. 团队允许调用哪些公开名** — `team.models[]`（以及组织白名单、Key.models）。这是 ACL。

**B. 某条部署属于哪个团队** — `model_info.team_id` + `team_public_model_name`。这是路由隔离。

添加/修改团队模型：`ModelManagementAuthChecks.can_user_make_team_model_call()`

XHub overlay 原文：associating a model with a team so the same public `model_name` can use different providers per team is a **core routing feature, not an enterprise-only BYOK gate**。

- Proxy Admin → 允许
- 否则必须 `_is_user_team_admin`
- **没有** `premium_user` 检查

内部命名：

```
对外：team_public_model_name = "gpt-4o"（调用方仍写这个名字）
对内：model_name = "model_name_{team_id}_{uuid}"
ACL：team.litellm_model_table.model_aliases["gpt-4o"] → 内部名
```

打开 `images/团队独享模型路由.html`。Router `should_include_deployment()`：

1. 请求带 `team_id`，且部署 `team_id` 相同，且请求名 == `team_public_model_name` → 命中团队部署
2. 否则按内部 `model_name` 回退：无团队约束 / 全局部署且该团队没有同名 override / 部署就属于该团队
3. 其他团队的部署一律 False

因此：**Team A 的 `gpt-4o` 端点，Team B 即使用同一个公开名也路由不到 A 的凭据。** 若 A 已有同名 override，A 也不会落到全局 `gpt-4o`。

Dashboard Playground 的 JWT 永远带 `team_id=litellm-dashboard`。v1.95.29 `route_request` 把哨兵当 no-team，再用 `resolve_ui_session_team_ids()` + `map_team_model()` 解析：恰好一个真实团队拥有该公开名才写入 `metadata.user_api_key_team_id`；0 或 >1 保持 no-team。

UI 编辑按钮：`canEditModel = Proxy Admin 显示名 Admin || created_by == 自己 || isUserTeamAdminForTeamId(teams, model.team_id, userID)`，且必须是 DB 模型。`created_by` 在 `get_model_info_with_id` 始终返回，不再 `premium_user` 门控。

`GET /model_group/info` 通过 `_team_byok_internal_names()` 把调用者可见的团队内部名展开，避免 Team fallback 选不到自己的公开名。

---

## 4. 角色如何叠加（常见误区）

1. **全局角色 ≠ 团队角色。** `user_role=proxy_admin` 能管一切，但 UI 编辑某条团队模型仍应看该模型的 `team_id` 是否匹配 Team Admin；v1.95.29 已按模型 `team_id` 判断，不再把 Proxy Admin 误当成任意 Team Admin。
2. **`org_admin` 写在 user_role 上不够。** 必须有对应组织的 membership。
3. **Org Admin 不能给团队加全局模型。** 只能管组织内团队对象；团队独享模型要由该团队 Team Admin（或 Proxy Admin）写 `model_info.team_id`。
4. **成员权限列表管不了 Admin。** `role=admin` 在 `does_team_member_have_permissions_for_endpoint` 直接 True。
5. **Team Admin 不能自我扩权预算。** 抬高 `max_budget` 是平台级动作。

---

## 5. 落地：组织下的团队自管 + 独享模型

官方委派链：Proxy Admin 建组织并指定 Org Admin → Org Admin 建团队并指定 Team Admin → Team Admin 管成员 / 限额 / Key，不再每件事找平台。打开 `images/团队自管委派链.html`。

### 5.1 一次性平台动作（Proxy Admin）

```bash
# 1. 建组织
curl -X POST "$XHUB/organization/new" \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"organization_alias":"dept-ml","models":["gpt-4o","claude-sonnet"],"max_budget":1000}'

# 2. 指定组织管理员
curl -X POST "$XHUB/organization/member_add" \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"organization_id":"<org_id>","member":{"role":"org_admin","user_id":"alice@corp"}}'

# 3. 给 alice 发一把管理 Key（后续她自己操作）
curl -X POST "$XHUB/key/generate" \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"user_id":"alice@corp","models":["all-proxy-models"]}'
```

### 5.2 组织管理员动作

```bash
# 4. 在组织内建团队
curl -X POST "$XHUB/team/new" \
  -H "Authorization: Bearer $ORG_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"team_alias":"ml-serving","organization_id":"<org_id>","max_budget":200,"models":["gpt-4o"]}'

# 5. 指定团队管理员
curl -X POST "$XHUB/team/member_add" \
  -H "Authorization: Bearer $ORG_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"team_id":"<team_id>","member":{"role":"admin","user_id":"bob@corp"}}'
```

### 5.3 团队管理员自管（之后平台不用介入）

```bash
# 6. 加普通成员
curl -X POST "$XHUB/team/member_add" \
  -H "Authorization: Bearer $TEAM_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"team_id":"<team_id>","member":{"role":"user","user_id":"carol@corp"}}'

# 7. 打开成员自助建 Key（可选）
curl -X POST "$XHUB/team/update" \
  -H "Authorization: Bearer $TEAM_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"team_id":"<team_id>","team_member_permissions":["/key/info","/key/health","/key/generate","/key/update"]}'

# 8. 上架本团队独享端点（同一公开名、本团队凭据）
curl -X POST "$XHUB/model/new" \
  -H "Authorization: Bearer $TEAM_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{
    "model_name":"gpt-4o",
    "litellm_params":{"model":"openai/gpt-4o","api_key":"sk-team-own-key","api_base":"https://team-endpoint"},
    "model_info":{"team_id":"<team_id>"}
  }'

# 9. 给团队发服务账号 Key（生产流量用这个，不跟个人走）
curl -X POST "$XHUB/key/service-account/generate" \
  -H "Authorization: Bearer $TEAM_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"team_id":"<team_id>","models":["gpt-4o"],"key_alias":"ml-serving-prod"}'
```

### 5.4 独享如何生效

| 步骤 | 机制 |
|---|---|
| 写入 | `model_info.team_id` 绑定；内部改名为 `model_name_{team_id}_{uuid}`；公开名进 `team_public_model_name` 和 team ACL |
| 管理面 | 只有 Proxy Admin 或该 Team Admin 能 PATCH/删除；Dashboard 按 `isUserTeamAdminForTeamId` 亮按钮 |
| 数据面 | 请求 Key 的 `team_id` 进入 Router；`should_include_deployment` 只留下本团队部署 |
| UI 试玩 | 哨兵 `litellm-dashboard` 被解析成真实团队（唯一匹配时） |
| 解绑 | PATCH `team_id: null`（必须显式 null，不能省略）。后端 `_explicit_patch_team_id`：省略 = 不动，null = `_clear_team_model_assignment` + `_drop_team_acl_if_unbacked` |

同一公开名多团队：Team A 走 A 的 provider/key，Team B 走 B 的；没有 override 的团队才可能落到全局部署。这就是 XHub「按团队拆供应商」的核心，不是 Enterprise BYOK 装饰。

---

## 6. XHub v1.95.29 与 LiteLLM 1.95 官方差异

| 能力 | 官方 1.95 | XHub v1.95.29 |
|---|---|---|
| Organization / org_admin | Enterprise | 保留，无许可证门控 |
| team_admin 指派 | Premium | 授权检查（Proxy/Org/Team Admin），不是 premium 检查 |
| team_member_permissions | Premium | 代码路径可用 |
| 团队绑定模型 / BYOK | Enterprise（`/docs/proxy/team_model_add`） | 核心路由能力，去掉 premium 门控 |
| 组织菜单 | 常跟 premium 绑定 | Admin / Org Admin 可见，无 `premiumUser` 隐藏；创建仍仅 Proxy Admin |
| `created_by` 回传 | premium 才给 | `get_model_info_with_id` 始终复制 |
| Dashboard 哨兵 team_id | 未按真实团队解析 | v1.95.29 解析唯一团队公开名 |
| Team Admin 编辑团队模型 | 视许可证 | UI + 后端都按 membership，不把 Proxy Admin 当成 Team Admin |

上游句子仍成立、XHub 未改的部分：预算向上汇总、Team Admin 不能自行抬高 `max_budget`、OSS 若不用组织则 Team 就是顶层边界。

---

## 7. 风险与约束

1. **一人多团队同名模型**：Playground 哨兵在 0 或 >1 个匹配时保持 no-team，可能打到全局部署而不是团队部署。生产请用带真实 `team_id` 的 Virtual Key，不要用 Dashboard session Key。
2. **Team Admin 不能扩预算**：要加额度必须找 Proxy Admin（组织内可由 Org Admin 在组织上限内调整，独立团队不行）。
3. **解绑必须显式 `team_id: null`**：Dashboard 漏传会被当成 no-op，模型继续独占。
4. **config.yaml 里的模型不是 DB 模型**：`canEditModel` 要求 `db_model`，Team Admin 改不了文件部署。
5. **组织白名单仍罩着团队模型公开名**：团队独享端点的 `team_public_model_name` 必须出现在组织 `models[]`（或组织为 `all-proxy-models`）。
6. **不要给员工 Key 开 `auto_rotate` 走 skip-vault 路径**：Portal Scheme C 的约束，与 RBAC 正交但运维上容易踩。

---

## 8. 推荐落地形态

对「一个组织、多个团队、各管各的模型与 Key」：

- **A（推荐）**：组织 = 部门；每个产品线一个 Team；每 Team 一个 Team Admin；生产用 team service account；模型全部 `model_info.team_id` 绑定；成员默认只读 Key，按需打开 generate。
- **B**：不用组织，直接用独立 Team 当租户。更扁，失去部门级预算汇总。适合还没准备好 Org Admin 的阶段。
- **C**：所有模型保持全局，只靠 `team.models[]` 做 ACL。隔离的是「能不能点名」，不是「会不会用到别人的凭据」。**做不到独享端点。**

选 A。B 是过渡。C 不满足本题。
