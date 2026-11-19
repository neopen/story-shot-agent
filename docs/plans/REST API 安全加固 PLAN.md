# REST API 安全加固 PLAN

> 状态：待审核（plan-ok 后进入 TASKS 阶段）  
> 日期：2026-11-09  
> 基础版本：0.4.3  
> 目标修复版本：0.4.4  
> 依据：[REST-API安全加固-SPEC.md](./REST-API安全加固-SPEC.md)（已 spec-ok）  
> 本文档用途：定义实现架构、模块职责、接口契约、风险控制与验证策略；审核通过后再拆分 TASKS。

---

## 1. 目标与范围

本次改造针对 REST API 和 Webhook 处理链路中的安全边界，重点解决：

1. 外部 REST 请求提交的配置不应触发服务端环境变量展开，也不应覆盖受保护的服务端配置。
2. Webhook 回调目标必须经过严格校验，阻止 SSRF、DNS rebinding、重定向绕过及代理环境干扰。
3. 公共配置接口不得暴露服务器内部路径、数据库连接信息及其他内部配置。
4. 修复配置加载器中环境变量复杂类型解析问题，并确保不改变既有配置源优先级。

本次以当前正式版本 `0.4.3` 为修复基线，修复完成后按发布流程发布 `0.4.4`。不回溯维护 `0.3.x`，除非项目另行决定继续支持旧维护分支。

### 1.1 范围内

- REST API 请求配置安全校验。
- Webhook URL 校验与唯一安全发送实现。
- Webhook DNS 解析、IP 分类、白名单和 IP pinning。
- `GET /config` 公共响应脱敏。
- `ConfigLoader` 环境变量复杂类型解析修复。
- 对应单元测试、API 测试、网络集成测试和回归测试。
- 安全文档、迁移说明及发布说明。

### 1.2 范围外

- 不改变 MCP、CLI、工作流层的配置行为，除非共享安全模块被明确复用且有回归测试支持。
- 不改变 `ShotConfig` / `AIConfig` 的既有字段定义及本地可信配置能力。
- 不移除 SDK 进程内 BYOK（Bring Your Own Key）能力。
- 不改变任务状态机、任务生命周期语义和任务结果格式。
- 不新增第三方依赖；如实现验证证明现有 HTTPX/httpcore 无法可靠实现 pinning，必须先更新方案并说明依赖或传输层调整理由，不得降级安全要求。
- 不在本次改造中调整配置源优先级。

---

## 2. 高层架构与模块划分

```text
接入层  src/penshot/api/rest_api.py
  ├─ 请求模型 / 请求入口：检查原始请求中是否显式提交受保护字段
  ├─ 配置安全校验：拒绝不允许的服务端配置覆盖
  └─ GET /config：仅输出 PublicConfigResponse 白名单字段
        |
        v
任务提交层  src/penshot/neopen/task/task_factory.py
  └─ TaskFactory.submit()：在 create_task 之前校验 callback_url
        |
        v
任务生命周期层  src/penshot/neopen/task/
  ├─ TaskLifecycleService.set_callback：SDK 直接调用时再次校验
  ├─ TaskLifecycleService._trigger_callback_async：委托统一安全发送器
  └─ CallbackHandler.notify_callback：委托同一安全发送器
        |
        v
安全基础设施层  src/penshot/neopen/task/callback_security.py
  ├─ URL 解析与规范化
  ├─ DNS 解析（超时、并发上限、资源控制）
  ├─ IP 分类与白名单精确匹配
  ├─ 目标 IP pinning
  └─ 唯一 Webhook HTTP 发送实现
        |
        v
配置层  src/penshot/config/
  ├─ config_models.APIConfig：callback_allowed_hosts
  ├─ config.Settings：白名单访问器
  └─ config_loader.ConfigLoader：复杂类型环境变量 JSON 解析
```

### 2.1 模块职责

| 模块 | 主要职责 | 不应承担的职责 |
|---|---|---|
| `rest_api.py` | REST 输入边界、HTTP 状态码映射、公共响应 | DNS 解析、Webhook 网络发送 |
| `config_security.py`（可选独立模块） | 识别和拒绝受保护配置覆盖 | 直接读取或展开请求中的环境变量 |
| `task_factory.py` | 在任务创建前执行回调目标校验 | 实现 URL/IP/TLS 细节 |
| `task_lifecycle_service.py` | 生命周期入口复验、触发回调 | 自行实现 HTTP 请求 |
| `task_handler.py` | 兼容原有公共通知出口 | 保留第二套未受保护的发送逻辑 |
| `callback_security.py` | 统一校验、解析、pinning 和发送 | 处理任务状态或业务编排 |
| `config_loader.py` | 按目标字段类型解析环境变量叶子值 | 改变配置源优先级 |

---

## 3. 关键设计决策

### D-1：REST 请求配置必须基于原始输入检测受保护字段

**结论：不使用“请求值是否等于默认值”来判断字段是否被覆盖。**

原方案通过默认实例逐字段比较，存在显式传入默认值时无法识别的问题。例如客户端显式提交 `temperature` 的默认值，比较结果可能误判为未覆盖。安全策略不应依赖默认值的具体取值。

调整为：

1. 在 Pydantic 模型转换、嵌套字段 validator 和 `ShotConfig` 构造之前，读取原始请求数据。
2. 对原始请求字典检查是否显式出现受保护字段。
3. 对批量端点中的每个配置对象使用同一共享 helper。
4. `{}` 视为未提交配置覆盖；只要显式出现受保护字段，即使值为 `null`、空字符串或默认值，也按受保护字段处理。
5. 错误响应只返回字段路径和通用原因，不回显请求值、密钥或连接串。

建议保护字段至少包括：

- `llm`：按 SPEC 的字段粒度确定是否整体禁止，或仅禁止其凭据、服务端地址等敏感子字段；不得未经确认就扩大到普通模型参数。
- `embed`：同上。
- `checkpoint_dir`
- `postgres_uri`

**重要：普通模型参数是否允许 REST 覆盖，必须以已批准的 SPEC 为准。** 如果 SPEC 要求整个 `llm` / `embed` 对象均禁止覆盖，则按对象级拒绝；如果允许普通参数，则使用明确的敏感子字段白名单/黑名单策略，不得通过默认值比较推断。

建议抽取纯 Python helper，例如：

```python
class ConfigOverrideError(ValueError):
    """REST 请求尝试覆盖受保护的服务端配置。"""

def validate_request_config_overrides(raw_config: dict) -> None:
    """仅检查原始输入结构，不实例化 ShotConfig，不展开环境变量。"""
```

REST 层将 `ConfigOverrideError` 映射为 HTTP 400。不要在 Pydantic `model_validator` 中直接抛 `HTTPException`，避免请求模型与 FastAPI 强耦合。

如果校验必须挂接在请求模型入口，应确保执行顺序早于嵌套字段校验；异常通过统一异常处理器映射为 400。以 TestClient 的端点测试验证实际行为，不能仅凭框架理论假设。

### D-2：回调提交校验必须发生在任务创建之前

**结论：保留 `TaskFactory.submit()` 单点前置校验，并在生命周期入口复验。**

现状：任务提交流程先 `create_task`，之后再 `set_task_callback`。若回调 URL 无效，可能已经产生任务记录，不符合“非法回调时不创建任务”的要求。

调整：

- `TaskFactory.submit()` 在调用 `create_task` 之前校验 callback_url。
- `batch`、`batch_async`、`batch_submit` 等提交入口必须继续汇入 `submit()`，确保统一覆盖。
- `TaskLifecycleService.set_callback()` 再次校验，防止 SDK 或内部调用绕过任务工厂。
- 提交侧校验失败抛出 `CallbackValidationError`（继承 `ValueError`）。
- REST 层将该异常映射为 HTTP 400；SDK 调用方收到明确的异常。
- 无 callback_url 的任务不执行 DNS 解析，保持零额外开销。

必须通过测试证明：非法 callback_url 被拒绝时，`create_task` 未被调用，数据库中也没有新增任务。

### D-3：新增统一 `callback_security.py`，所有 Webhook 出口共用

**结论：保留单一安全发送实现；HTTPX pinning 必须经版本级源码确认和真实网络集成测试。**

`callback_security.py` 是 URL 校验、DNS 解析、IP 分类、白名单匹配和 HTTP 发送的唯一实现。以下出口均委托它：

- `TaskLifecycleService._trigger_callback_async`
- `CallbackHandler.notify_callback`

禁止任何其他模块直接对用户提供的 callback_url 发起 HTTP 请求。

#### 3.1 推荐接口

```python
class CallbackValidationError(ValueError):
    """回调 URL 校验失败。"""

@dataclass(frozen=True)
class PinnedTarget:
    scheme: str
    hostname: str       # 原始主机名，用于 Host / SNI / 证书校验
    port: int
    ip: str             # 已校验并固定的目标 IP
    path: str           # path + query
    # 如实现需要，可增加规范化后的 authority 等字段

def validate_callback_url(
    callback_url: str,
    allowed_hosts: Optional[Sequence[str]] = None,
) -> PinnedTarget:
    """提交侧同步校验；失败时 fail-closed。"""

async def send_verified_callback(
    callback_url: str,
    payload: Dict[str, Any],
    timeout: float = 30.0,
) -> bool:
    """派发侧重新校验并通过受控连接发送；失败返回 False 并记录安全日志。"""
```

接口可按实现需要调整，但必须保留以下安全语义：提交前校验、派发前复验、实际连接目标固定、禁止重定向、禁止非预期代理。

#### 3.2 HTTPX / httpcore pinning 的实现约束

不能仅通过“URL 主机名替换成 IP + 设置 Host 头”就认定实现安全。HTTPS 还必须正确处理 SNI 和证书主机名验证。

当前方案拟采用：

- 将实际连接目标固定到已校验 IP。
- HTTP `Host` 使用原始域名（非默认端口时包含正确端口）。
- TLS SNI 使用原始域名。
- 证书主机名校验使用原始域名，而不是 IP。
- `follow_redirects=False`。
- `trust_env=False`，禁止 HTTPX 自动读取 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 等环境代理。
- 禁止不受控重试导致重新解析域名或连接到未经校验的 IP。

`extensions={"sni_hostname": ...}` 不能仅凭参数名称或 mock 调用认定同时保证 SNI 与证书校验。实现前必须：

1. 检查项目锁定/实际安装的 HTTPX 与 httpcore 版本。
2. 检查对应版本对 `sni_hostname` 的真实处理路径，确认它如何传递到 TLS `server_hostname` 及证书主机名校验。
3. 用本地受控 HTTPS 服务和域名证书进行集成测试，验证 TCP 目标 IP、HTTP Host、TLS SNI、证书验证均符合预期。
4. 验证 DNS 在校验后发生变化时，连接仍只能到已 pin 的 IP。
5. 验证 HTTP 和 HTTPS 两种情况。

如果现有版本不能可靠实现上述要求，应改用受控自定义 Transport / 连接器，或重新评估传输实现。不得以只做 DNS 检查、随后仍让客户端按域名自行解析的方式替代 pinning。

#### 3.3 重定向、代理和重试

- 显式 `follow_redirects=False`。
- 不跟随 301、302、303、307、308；收到重定向视为本次回调失败。
- `trust_env=False`。
- 不允许环境代理或外部代理改变实际连接目标。
- 如启用重试，每次重试都必须重新执行完整 DNS/IP 校验与 pinning；不得复用未验证的新目标。
- 建议本次先不实现自动重试，避免扩大安全状态空间。

### D-4：DNS 解析必须同时具备超时和资源上限

**结论：5 秒超时之外，还必须限制并发解析任务数量。**

原方案使用 daemon 线程配合 `join(5)`，虽然能限制调用方等待时间，但 `join()` 超时不会终止底层 `getaddrinfo`。大量慢解析请求可能留下大量后台线程，造成资源耗尽。

异步 `asyncio.wait_for(loop.getaddrinfo(...), timeout=5)` 同样不能保证底层线程池中的系统 DNS 调用立即停止。

调整要求：

- DNS 解析超时目标不超过 5 秒，超时即 fail-closed。
- 同步和异步调用共享明确的并发资源上限/解析调度策略。
- 限制同时进行的解析数量；超过上限时快速拒绝，不继续创建无界线程或任务。
- 对 DNS 解析结果设置合理上限，避免异常庞大的结果集合。
- 同一 hostname 的短时间重复解析可考虑有界缓存，但缓存不得绕过派发时复验；缓存 TTL 必须明确且保守。
- 不得把“取消等待”误认为“底层解析已终止”。
- 解析失败、空结果、超时、结果中包含任何不允许的地址时，全部 fail-closed。
- 记录必要的安全日志，但不记录 URL 中的敏感 query、用户信息或 payload。

实现可选用受限线程池/信号量和有界队列；具体实现应结合项目同步/异步运行模型确定。不得使用每个请求无界创建 daemon thread 的方式。

### D-5：白名单只代表管理员显式信任目标，不得绕过其他安全约束

**结论：保留 `callback_allowed_hosts`，但收紧其匹配和例外语义。**

配置字段：

```python
callback_allowed_hosts: List[str] = Field(
    default_factory=list,
    description="可信回调主机白名单：主机名或 IP 字面量，精确匹配，默认空",
)
```

配置示例：

```yaml
api:
  callback_allowed_hosts:
    - localhost
    - 192.168.1.50
```

环境变量示例：

```bash
PENSHOT_API__CALLBACK_ALLOWED_HOSTS='["localhost","192.168.1.50"]'
```

白名单约束：

1. 白名单仅来自服务端管理员配置（YAML / 环境变量等可信配置源），不能由 REST 请求或普通任务 payload 修改。
2. 域名采用小写、规范化后的精确匹配；禁止隐式子域名匹配和通配符，除非未来另行设计并经过安全审核。
3. IP 字面量通过 `ipaddress.ip_address()` 规范化后精确比较，兼容 IPv6 压缩形式。
4. 明确端口策略：建议支持按 host 精确授权，并提供可选端口限制；如果当前配置格式不包含端口，必须在文档中明确其代表该主机允许的端口范围，并评估是否应改为 `host:port` 规则。
5. 白名单命中仅允许访问明确授权的非公网目标；不放宽 URL scheme、userinfo、DNS 解析、重定向、超时、代理、payload 或请求大小等约束。
6. 对域名白名单，必须明确授权该域名解析到哪些 IP。建议白名单域名仍执行解析，并只允许解析结果符合管理员授权策略的地址；不能仅凭 hostname 命中就无条件连接任意解析地址。
7. 白名单命中不代表可以跳过 DNS/IP pinning；实际连接仍必须固定到已验证的解析 IP。
8. 对混合解析结果（同时包含公网和非公网 IP），默认 fail-closed，除非规则明确、可审计地授权了具体目标 IP。

**特别说明：** `callback_allowed_hosts` 是管理员配置的可信目标，不是用户提交的可信声明。任何普通 API 用户都不得通过请求修改该白名单。

### D-6：`GET /config` 使用 PublicConfigResponse 白名单序列化

**结论：不再采用“序列化完整 ShotConfig 后删除两个字段”的黑名单方式。**

原方案通过 `TypeAdapter(ShotConfig).dump_python(..., mode="json")` 后剔除 `checkpoint_dir` 和 `postgres_uri`，虽然能处理当前明确字段，但未来新增内部配置字段时容易遗漏。

调整为专用公共响应模型：

```python
class PublicConfigResponse(BaseModel):
    # 仅声明确实允许公开的配置字段
    # 字段及类型以当前 API 契约和 SPEC 为准
    ...
```

实现要求：

- `GET /config` 只从内部配置对象映射 PublicConfigResponse。
- 不直接返回或序列化 `ShotConfig`。
- 不返回 `checkpoint_dir`、`postgres_uri`、API Key、数据库密码、内部 Token、私有服务地址等内部信息。
- 公开模型必须显式声明允许输出的字段；内部模型新增字段不会自动出现在响应中。
- 保持现有 API 客户端所依赖的公开字段兼容，确需移除的字段在文档中说明。
- 使用端点测试检查完整 JSON 响应，断言敏感字段及敏感值均不出现。
- `SecretStr` 掩码可作为纵深防御，但不能替代公共响应白名单。

### D-7：修复 ConfigLoader 环境变量复杂类型解析

**结论：保留此项修复，但作为独立子任务实施和验证。**

发现的问题：

- `_load_env_config` 对环境变量叶子值仅执行 bool/int/float 转换，没有对复杂类型执行 JSON 解析。
- `ConfigLoader` 在 pydantic-settings sources 中优先级较高，其原始字符串覆盖标准环境变量源的 JSON 解码结果。
- 可能导致 `cors_origins`、`supported_styles`、`routing.rules` 等 List/Dict/嵌套模型字段的环境变量配置失效。

修复策略：

1. 在叶子值转换前，根据键路径在 `settings_cls.model_fields` 中定位目标字段注解。
2. 对复杂类型（容器 origin、BaseModel 子类）尝试 `json.loads`。
3. 正确处理 `Optional` / Union 解包后的目标类型。
4. JSON 解析失败时保留原始值，交由 Pydantic 进行类型校验并给出明确错误。
5. 字符串、布尔、整数、浮点数的既有转换行为保持不变。
6. 不改变 sources 顺序及优先级语义。

必须增加独立测试，覆盖：

| 类型 | 测试内容 |
|---|---|
| `List[str]` | JSON 数组解析 |
| `List[BaseModel]` | 嵌套模型数组解析 |
| `Optional[List[str]]` | Optional 解包 |
| `Dict[str, Any]` | JSON 对象解析 |
| 嵌套 `BaseModel` | 多层字段路径定位 |
| `str` | 原字符串行为不变 |
| `bool` | 原布尔转换不变 |
| `int` / `float` | 原数值转换不变 |
| 非法 JSON | 交由 Pydantic 报错，不静默吞错 |

验证配置源优先级、YAML 行为、`.env` 行为及原有配置加载行为不变。

### D-8：Webhook HTTP 客户端必须禁用环境代理

**结论：统一发送器显式使用 `trust_env=False`。**

HTTPX 可能默认读取 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 等环境变量。若 Webhook 发送使用环境代理，实际网络路径可能与应用层 pinning 设计不一致。

要求：

- 统一发送器创建 HTTPX 客户端时设置 `trust_env=False`。
- 显式设置 `follow_redirects=False`。
- 不接受请求参数指定代理。
- 不允许用户 payload 或 callback_url 控制代理配置。
- 测试环境设置代理环境变量，确认发送器不会使用该代理。
- `trust_env=False` 不能替代 IP pinning、TLS 校验和出口网络控制。

---

## 4. 文件清单

### 4.1 新建文件

| 文件 | 职责 |
|---|---|
| `src/penshot/neopen/task/callback_security.py` | 回调 URL 校验、DNS/IP 安全、白名单、pinning 和唯一发送实现 |
| `src/penshot/api/schemas/public_config.py`（或项目现有 schema 目录） | `PublicConfigResponse` 公共配置响应白名单模型 |
| `src/penshot/api/config_security.py`（如有必要） | REST 原始配置字段检查与 `ConfigOverrideError` |
| `tests/api/test_rest_config_hardening.py` | REST 敏感覆盖拒绝、环境变量不展开、`/config` 脱敏 |
| `tests/task/test_callback_security.py` | URL/IP/白名单/DNS/发送器安全测试 |
| `tests/task/test_callback_security_integration.py` | HTTP/HTTPS pinning、Host/SNI/证书校验及代理隔离集成测试 |
| `tests/config/test_config_loader_complex_env.py` | ConfigLoader 复杂类型环境变量解析回归测试 |
| `docs/api/REST-API安全加固.md` | 行为变更、白名单配置、迁移与安全说明 |

实际路径可按项目现有目录结构调整，但不得因此分散或复制安全实现。

### 4.2 修改文件

| 文件 | 改动 |
|---|---|
| `src/penshot/api/rest_api.py` | REST 原始输入安全校验；`GET /config` 映射 PublicConfigResponse |
| `src/penshot/neopen/task/task_factory.py` | `submit()` 在 `create_task` 前校验 callback_url |
| `src/penshot/neopen/task/task_lifecycle_service.py` | `set_callback` 入口复验；异步派发委托统一发送器 |
| `src/penshot/neopen/task/task_handler.py` | `notify_callback` 委托统一发送器 |
| `src/penshot/config/config_models.py` | 仅 `APIConfig` 新增 `callback_allowed_hosts` 字段 |
| `src/penshot/config/config.py` | 新增 `Settings.get_callback_allowed_hosts()`，返回副本 |
| `src/penshot/config/config_loader.py` | D-7：按目标字段类型解析复杂类型环境变量 |
| `.env.example` | 新增 `PENSHOT_API__CALLBACK_ALLOWED_HOSTS` 合法 JSON 示例 |
| 相关 CHANGELOG | 记录安全修复与配置行为变更 |

### 4.3 删除

无。

### 4.4 明确不改

- `ShotConfig` / `AIConfig` 的本地可信配置字段及其既有环境变量解析能力。
- `PenshotFunction`。
- MCP / CLI 的既有接口行为。
- 工作流层、任务状态机和任务结果结构。
- 配置源顺序及优先级。
- SDK 进程内 BYOK 能力。
- 不必要的第三方依赖。

---

## 5. 数据模型与接口契约

### 5.1 REST 配置安全契约

端点：

- `POST /storyboard`
- `POST /storyboard/sync`
- `POST /storyboard/batch`
- `POST /storyboard/batch/sync`

要求：

- 原始请求配置必须在嵌套配置模型校验和环境变量展开之前接受安全检查。
- 显式提交受保护字段时返回 HTTP 400。
- 错误信息仅包含字段路径及通用原因，不包含字段值。
- 对批量请求逐项校验，任一项不合法时按既有批量接口契约决定整体拒绝或逐项拒绝；该行为必须在 SPEC/接口文档中明确，不得在实现中临时决定。
- 非法 callback_url 返回 HTTP 400，且不得创建任务。
- 不影响本地可信配置读取环境变量的能力。

### 5.2 SDK 行为契约

- `ShotConfig(llm=..., embed=...)` 进程内 BYOK 能力保持不变。
- SDK 直接提交非法或未授权私网 callback_url 时，抛出 `CallbackValidationError`。
- 需要访问内网回调目标时，管理员必须在本地可信配置中明确配置白名单。
- SDK 不得通过请求参数修改服务端白名单。

### 5.3 Callback 安全模块契约

```python
class CallbackValidationError(ValueError):
    """回调 URL 校验失败。"""

@dataclass(frozen=True)
class PinnedTarget:
    scheme: str
    hostname: str
    port: int
    ip: str
    path: str

def validate_callback_url(
    callback_url: str,
    allowed_hosts: Optional[Sequence[str]] = None,
) -> PinnedTarget:
    ...

async def send_verified_callback(
    callback_url: str,
    payload: Dict[str, Any],
    timeout: float = 30.0,
) -> bool:
    ...
```

安全语义：

- 只允许 `http` / `https`。
- 拒绝 userinfo。
- 拒绝不合法端口、主机名、URL 编码混淆及不支持的 IP 表示。
- 解析全部 DNS A/AAAA 结果。
- 默认要求全部解析结果均为允许的公网地址；白名单例外按 D-5 严格处理。
- 拒绝 loopback、private、link-local、reserved、multicast、unspecified 等非公网目标。
- IPv4-mapped IPv6 必须映射回 IPv4 后再分类。
- DNS 解析超时、失败、空结果、并发资源耗尽均 fail-closed。
- 实际连接固定到已校验 IP。
- HTTP Host、TLS SNI、证书主机名校验使用原始域名。
- 禁止重定向、非预期代理和不受控重试。
- 发送失败返回 `False` 并记录脱敏日志，不改变任务状态。
- 不记录 callback URL 中的敏感 query、userinfo 或 webhook payload。

### 5.4 白名单配置契约

`APIConfig`：

```python
callback_allowed_hosts: List[str] = Field(
    default_factory=list,
    description="管理员配置的可信回调主机白名单，精确匹配，默认空",
)
```

`Settings`：

```python
def get_callback_allowed_hosts(self) -> List[str]:
    """返回管理员配置的回调主机白名单副本。"""
```

白名单格式、端口策略、域名/IP 规范化规则必须在实现前确定并写入文档。默认空白名单，不默认允许 localhost 或任何私网地址。

### 5.5 PublicConfigResponse 契约

- 只允许显式列出的公开字段。
- 禁止从内部配置对象自动 dump 全部字段。
- 不包含 `checkpoint_dir`、`postgres_uri`、API Key、Token、密码、私有服务地址等。
- 公共字段与现有客户端兼容；字段删改必须记录。
- 以完整响应快照/字段断言测试防止未来新增内部字段被意外暴露。

---

## 6. 风险点与应对方案

| # | 风险 | 应对 |
|---|---|---|
| R-1 | 原始请求字段检查未早于嵌套配置校验 | 在请求入口先检查原始 dict；用端点测试证明敏感值不会触发环境变量展开 |
| R-2 | 受保护字段策略误伤普通模型参数 | 严格按已批准 SPEC 定义字段粒度；为允许覆盖的参数增加兼容测试 |
| R-3 | 默认值比较漏掉显式传入默认值 | 不使用默认值比较；基于原始输入字段是否出现判断 |
| R-4 | `HTTPException` 与 Pydantic 校验异常耦合 | 使用纯 Python `ConfigOverrideError`，由 REST 异常处理器映射 HTTP 400 |
| R-5 | `TaskFactory.submit()` 校验位置过晚 | 测试断言非法 URL 时 `create_task` 未调用 |
| R-6 | HTTPX `sni_hostname` 行为随版本变化 | 检查实际 HTTPX/httpcore 版本源码；以真实 HTTPS 集成测试验证 SNI 和证书主机名 |
| R-7 | DNS 校验后重新解析导致 rebinding | pinning 到已校验 IP；验证实际 TCP 连接目标 |
| R-8 | DNS `join` / `wait_for` 超时后底层解析仍运行 | 有界解析线程池/并发限制；队列满时拒绝；不得无界创建 daemon thread |
| R-9 | 混合 DNS 结果中包含私网地址 | 默认全部解析结果均须通过检查；否则 fail-closed |
| R-10 | 白名单匹配过宽或被普通用户控制 | 精确匹配；只读管理员配置；不得由 REST payload 修改 |
| R-11 | 白名单绕过 scheme、端口、代理或重定向限制 | 白名单只授权明确目标，不放宽其他安全约束；明确端口策略 |
| R-12 | HTTPX 自动读取环境代理 | 统一客户端 `trust_env=False`，并设置代理环境变量进行测试 |
| R-13 | 重定向或重试绕过校验 | `follow_redirects=False`；本次默认不启用自动重试 |
| R-14 | `/config` 未来新增字段意外暴露 | 使用 PublicConfigResponse 白名单模型 |
| R-15 | `SecretStr` 序列化行为差异 | 不依赖 SecretStr 单独脱敏；公共响应只映射允许字段 |
| R-16 | ConfigLoader JSON 解析影响原配置行为 | 独立测试复杂类型、标量类型、YAML、`.env` 和优先级 |
| R-17 | 安全日志记录敏感信息 | 仅记录错误类型、目标主机的必要脱敏信息；不记录 payload、凭据和完整敏感 query |

---

## 7. 验证策略与验收标准

### 7.1 REST 配置输入测试

- 四个 REST 提交端点均覆盖。
- 显式提交每个受保护字段时返回 400。
- 显式提交受保护字段的默认值、`null`、空字符串等仍然被拒绝（按字段契约适用）。
- 空配置对象 `{}` 正常通过。
- 恶意 `$ENV_VAR` / `${ENV_VAR}` 请求不会读取或展开服务端环境变量。
- 允许的普通模型参数行为保持不变。
- 错误响应不泄露原始值、密钥或数据库 URI。
- 批量端点符合明确的整体/逐项拒绝契约。

### 7.2 Webhook URL 校验测试

至少覆盖：

- `http`、`https` 合法公网目标。
- 非 HTTP(S) scheme。
- URL userinfo。
- 缺失 hostname。
- 非法端口。
- localhost / loopback。
- RFC1918 私网 IPv4。
- link-local IPv4 / IPv6。
- IPv6 loopback、ULA、IPv4-mapped IPv6。
- multicast、reserved、unspecified。
- 混淆编码 IP、异常 IPv4 表示。
- DNS A/AAAA 多记录。
- DNS 返回公网与私网混合结果。
- DNS 失败、空结果、超时。
- DNS 并发上限和队列满场景。
- 白名单精确命中、相似域名不命中、大小写和 IP 规范化。
- 白名单不能由 REST 请求覆盖。
- 白名单不绕过 scheme、userinfo、端口策略、redirect 和代理限制。

### 7.3 IP Pinning 与 HTTPS 集成测试

必须使用受控本地测试服务验证真实网络行为，不得只依赖 mock：

1. 测试域名解析到测试服务的受控 IP。
2. 连接实际到达预期 pinning IP。
3. HTTP Host 为原始域名及正确端口。
4. HTTPS SNI 为原始域名。
5. 证书主机名验证针对原始域名成功。
6. 错误证书或域名不匹配时连接失败。
7. DNS 在初次校验后变化，连接仍不能访问新解析到的未验证 IP。
8. 重定向响应不会触发第二次请求。
9. 设置 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 后仍不使用环境代理。
10. 发送器不存在其他绕过安全模块的 HTTP 请求出口。

### 7.4 任务生命周期测试

- `TaskFactory.submit()` 在创建任务前校验。
- 非法 URL 时 `create_task` 未被调用。
- `batch` / `batch_async` / `batch_submit` 均受保护。
- `TaskLifecycleService.set_callback()` 直接调用也受保护。
- `TaskLifecycleService` 和 `CallbackHandler` 均委托唯一发送器。
- 回调发送失败不改变既有任务状态和任务结果。
- 无 callback_url 的任务不触发 DNS 解析。

### 7.5 `/config` 脱敏测试

- 响应只包含 PublicConfigResponse 声明的字段。
- 不包含 `checkpoint_dir`、`postgres_uri`。
- 不包含 API Key、Token、密码、私有服务地址等敏感信息。
- 内部 ShotConfig 增加额外字段时，公共响应不会自动增加字段。
- 现有公开字段类型及兼容性符合 API 契约。

### 7.6 ConfigLoader 测试

按 D-7 覆盖 List、Dict、Optional、嵌套 BaseModel、标量类型、非法 JSON、YAML、`.env` 和 sources 优先级。

### 7.7 全量回归

- 新增测试映射 SPEC 中对应 AC。
- 运行相关 API、task、config 测试。
- 运行完整 `pytest`。
- 运行 `pre-commit run --all-files`。
- 检查依赖锁定版本及 HTTPX/httpcore 实际版本。
- 检查所有 callback HTTP 发送调用点，确认不存在旁路。
- 检查公开 API schema 与文档一致。

---

## 8. 文档与兼容性说明

新增 `docs/api/REST-API安全加固.md`，至少说明：

1. REST API 不再允许提交哪些服务端敏感配置字段。
2. 原有 REST BYOK 调用方的迁移方式（使用服务端本地配置或 SDK 进程内 BYOK，具体以项目能力为准）。
3. callback_url 支持的 scheme、域名、IP、端口和 DNS 规则。
4. 默认禁止私网回调目标。
5. 如何由管理员配置 `callback_allowed_hosts`。
6. 白名单只对明确配置的目标生效，不会关闭其他安全限制。
7. `/config` 响应字段变化。
8. 失败时的 HTTP 状态码 / SDK 异常行为。
9. 版本升级建议。

`.env.example` 示例：

```bash
# Optional: explicitly trusted webhook callback hosts.
# Keep empty unless private/internal callback targets are intentionally required.
PENSHOT_API__CALLBACK_ALLOWED_HOSTS='[]'
```

如果示例展示内网主机，必须明确说明这是管理员主动授权的示例，不应作为默认值。

---

## 9. 发布计划

当前正式版本：`0.4.3`。

建议发布版本：`0.4.4`。

发布前检查：

- 所有安全测试通过。
- 全量回归通过。
- 文档和 `.env.example` 已更新。
- CHANGELOG 已记录安全修复。
- 检查依赖版本和实际 Transport 行为。
- 确认无 Webhook 发送旁路。
- 对外说明受影响版本范围及升级建议。

建议 Release Notes：

```markdown
## Security Improvements

- Prevented untrusted REST API request configurations from overriding protected server-side settings or triggering environment variable expansion.
- Added SSRF protection for webhook callback URLs, including DNS/IP validation and pinned connections.
- Disabled redirect following and environment proxy inheritance for webhook delivery.
- Replaced internal configuration serialization with an explicit public configuration response model.
- Fixed complex environment variable parsing in ConfigLoader.

## Tests

- Added REST configuration security regression tests.
- Added webhook URL, DNS, IP pinning, TLS, and proxy isolation tests.
- Added ConfigLoader complex environment variable parsing tests.
```

只有在实现和测试确实覆盖对应行为后，才将相应条目写入正式 Release Notes。

---

## 10. 实施顺序建议

建议 TASKS 按以下顺序拆分，降低相互影响：

1. **T-001：ConfigLoader 复杂类型环境变量解析修复**（独立测试、独立验收）。
2. **T-002：REST 原始请求配置安全校验**（先建立敏感字段边界和 `$ENV` 回归测试）。
3. **T-003：PublicConfigResponse 与 `/config` 脱敏**。
4. **T-004：Webhook URL 解析、DNS/IP 分类与白名单规则**。
5. **T-005：DNS 资源上限和超时控制**。
6. **T-006：HTTPX/httpcore pinning Transport 实现与 HTTPS 集成测试**。
7. **T-007：TaskFactory / Lifecycle / CallbackHandler 统一接入安全模块**。
8. **T-008：全量安全回归、文档、CHANGELOG 和发布检查**。

如果 T-006 的版本级验证证明现有 HTTPX/httpcore 无法满足安全要求，应暂停后续发送器接入，先更新设计并重新审核，不得用不完整的 pinning 实现继续推进。

---

## 11. 审核结论与进入 TASKS 的门槛

本 PLAN 在以下条件全部满足后方可标记 `plan-ok`：

- [ ] REST 敏感字段清单及字段粒度与已批准 SPEC 完全一致。
- [ ] 原始请求检查能够早于嵌套配置 validator 执行。
- [ ] 不再通过默认值比较判断是否覆盖配置。
- [ ] HTTPX/httpcore pinning 的具体版本行为已验证，或已确定替代 Transport 方案。
- [ ] DNS 超时与并发资源上限有明确实现方案。
- [ ] 白名单精确匹配规则、端口策略和信任边界已明确。
- [ ] `GET /config` 采用公共响应白名单模型。
- [ ] `trust_env=False`、禁止重定向及重试策略已纳入统一发送器。
- [ ] D-7 复杂类型解析有独立回归测试计划。
- [ ] 任务创建前校验及所有 Webhook 发送出口已覆盖。
- [ ] 测试计划包含真实 HTTP/HTTPS pinning 集成验证。
- [ ] 版本基线为 `0.4.3`，目标修复版本为 `0.4.4`。

**当前状态：待审核。** 完成上述调整并确认技术实现细节后，再标记 `plan-ok`，进入 TASKS 阶段。
