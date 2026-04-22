# 安全策略

## 支持的版本

| 版本  | 支持状态 |
| ----- | -------- |
| 1.x.x | 支持     |
| < 1.0 | 不支持   |

## 报告安全漏洞

我们非常重视安全问题。感谢您负责任地披露您的发现。

### 如何报告

1. **请勿**在 GitHub 上公开创建 issue 报告安全漏洞
2. 发送邮件至 **security@penshot.ai**（请替换为您的实际邮箱）
3. 或者通过 **GitHub 安全通告**（私密披露）进行报告

请在报告中包含以下信息：
- 漏洞描述
- 复现步骤
- 潜在影响
- 修复建议（如有）

### 预期响应

- **首次响应**：48 小时内确认收到您的报告
- **进度更新**：每 5-7 天提供一次状态更新
- **问题解决**：问题修复并发布新版本时会通知您

## 生产环境安全实践

在生产环境使用 PenShot 时，请遵循以下指南：

### API 安全

```python
# 切勿硬编码 API 密钥
# 错误做法
api_key = "sk-1234567890"

# 正确做法
import os
api_key = os.getenv("PENSHOT_API_KEY")
```



### 环境变量配置

```bash
# 生产环境部署必需配置
export PENSHOT_API_KEY="your-api-key"
export PENSHOT_REDIS_URL="redis://localhost:6379"
export PENSHOT_SECRET_KEY="your-secret-key"
```



### 限流配置

生产环境部署建议启用限流：

```python
# 使用 slowapi 示例
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)
```



### 输入验证

始终验证和清理用户输入：

```python
from penshot import validate_script

# 处理前验证剧本
if not validate_script(user_script):
    raise ValueError("剧本格式无效")
```



## 数据隐私

PenShot 会处理用户提供的剧本并可能发送到 LLM API。请注意：

1. **自托管 LLM**：处理敏感数据时建议使用本地模型（Ollama、LocalAI）
2. **数据保留**：配置适当的数据保留策略
3. **加密传输**：所有 API 通信启用 TLS 加密

## 漏洞报告清单

- 确认该问题是否已知（搜索已有 issue/安全通告）
- 收集漏洞的详细信息
- 准备最小化可复现示例
- 发送报告至 [helpenx@gmail.com](mailto:helpenx+github@gmail.com)

## 负责任的披露

我们遵循负责任的披露实践：

- 及时修复已验证的漏洞
- 在发布说明中致谢报告者（经许可）
- 与报告者协调披露时间

## 联系方式

- **安全邮箱**：[helpenx@gmail.com](mailto:helpenx+github@gmail.com)
- **PGP 密钥**：

------

感谢您帮助维护 PenShot 及其用户的安全！