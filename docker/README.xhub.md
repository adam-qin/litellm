# XHub Docker 构建方案

本方案基于 LiteLLM `v1.95.21` 的源码工作树构建 XHub 单体 Proxy 镜像。镜像在构建阶段重新编译 dashboard，因此不会复用工作区中可能存在的旧静态 UI bundle。

## 方案选择

| 场景 | Dockerfile | 说明 |
| --- | --- | --- |
| 开发、联调 | `Dockerfile` | 构建 XHub Proxy、Admin UI 和 `/get_image` Logo 端点 |
| 生产安全基线 | `docker/Dockerfile.non_root` | 非 root、只读根文件系统、预置静态 UI 和 Logo |
| 仅静态前端 | `ui/Dockerfile` | 只提供 nginx UI，不包含 Proxy API，不作为完整 XHub 部署 |

默认推荐根 `Dockerfile`；上线前建议使用 `docker/Dockerfile.non_root` 完成安全验收。

## 构建单体 XHub 镜像

在仓库根目录执行：

```bash
docker build \
  --file Dockerfile \
  --target runtime \
  --tag xhub/litellm:1.95.21 \
  .
```

生产安全镜像：

```bash
docker build \
  --file docker/Dockerfile.non_root \
  --target runtime \
  --build-arg PROXY_EXTRAS_SOURCE=local \
  --tag xhub/litellm:1.95.21-nonroot \
  .
```

构建阶段会执行：

1. 使用 Node 20 和 `ui/litellm-dashboard/package-lock.json` 安装前端依赖。
2. 执行 `npm run build` 生成静态 dashboard。
3. 用本次源码构建的 `out` 覆盖 `litellm/proxy/_experimental/out`。
4. 将 `litellm/proxy/logo.jpg` 打入镜像，由 `/get_image` 提供 XHub Logo。
5. 安装 Python Proxy extras 和 Prisma 运行依赖。

不要把 `.env`、API key 或数据库密码写入 Dockerfile、镜像层或 Git。

## 使用 Compose 启动

先在仓库根目录创建 `.env`，至少设置：

```dotenv
LITELLM_MASTER_KEY=请替换为随机强密钥
```

启动 XHub 单体服务和 PostgreSQL：

```bash
docker compose -f docker-compose.xhub.yml up -d --build
```

查看状态和日志：

```bash
docker compose -f docker-compose.xhub.yml ps
docker compose -f docker-compose.xhub.yml logs -f litellm
```

验证：

```bash
curl http://127.0.0.1:4000/health/liveliness
curl -I http://127.0.0.1:4000/get_image
curl -I http://127.0.0.1:4000/ui/
```

停止服务：

```bash
docker compose -f docker-compose.xhub.yml down
```

### 启用 HashiCorp Vault（无 Enterprise License 时）

LiteLLM 上游把 Vault secret manager 作为 Enterprise 付费特性：没有有效
`LITELLM_LICENSE` 时，管理后台保存 Vault 配置会报
`Hashicorp secret manager is only available for premium users`。

XHub 自托管可以在确认自身有权使用该特性后，显式开启开关：

```dotenv
XHUB_ALLOW_COMMUNITY_SECRET_MANAGERS=true
```

开关默认关闭（即保持 LiteLLM 上游行为）。开启后：

- 启动时 `general_settings.key_management_system: hashicorp_vault` 可以正常初始化；
- `POST /config_overrides/hashicorp_vault` 可以正常保存并跨 Pod 同步；
- 每次绕过都会打印一条 WARNING 日志，便于审计。

如果已购买 Enterprise 授权，直接设置 `LITELLM_LICENSE` 即可，不需要该开关。

改动后重启服务：

```bash
docker compose -f docker-compose.xhub.yml up -d
docker compose -f docker-compose.xhub.yml logs -f litellm | grep -i vault
```

如果需要删除 PostgreSQL 数据卷，必须明确确认后执行：

```bash
docker compose -f docker-compose.xhub.yml down -v
```

## Hardened 验收

生产安全镜像可以叠加仓库已有的 hardened Compose：

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.hardened.yml \
  build --no-cache

docker compose \
  -f docker-compose.yml \
  -f docker-compose.hardened.yml \
  up -d
```

该路径要求配置 `proxy_server_config.yaml` 中引用的外部环境变量，并依赖 Squid、PostgreSQL 等服务。它适合 CI/安全验收，不建议在没有补齐密钥和数据库配置的情况下直接用于生产。

## E2E 使用本地 XHub 镜像

```bash
docker build --file Dockerfile --target runtime --tag xhub/litellm:1.95.21 .
LITELLM_E2E_IMAGE=xhub/litellm:1.95.21 \
  docker compose -f tests/e2e/docker-compose.yml up -d
```

## 发布标识建议

正式发布时不要只使用 `latest`。建议使用：

```text
xhub/litellm:1.95.21-<git-commit>
xhub/litellm:1.95.21-nonroot-<git-commit>
```

并额外记录镜像 digest、Dockerfile、构建参数、`uv.lock` 和 `package-lock.json` 哈希，以及 UI 测试、镜像扫描和容器健康检查结果。
