# EasyMail API 文档

EasyMail 提供 `/api/v1` 公开接口，用于外部系统查询邮箱、邮件、验证码，并执行有限、安全、可审计的管理操作。

## 认证方式

所有 `/api/v1` 接口都需要 API Token。

```http
Authorization: Bearer em_xxxxxxxxxxxxxxxxx
```

API Token 在后台管理端创建。Token 只在创建时显示一次，请妥善保存。

## 通用响应

成功：

```json
{
  "success": true,
  "message": "ok",
  "data": {},
  "request_id": "req_xxx"
}
```

失败：

```json
{
  "detail": "错误原因"
}
```

分页接口通用参数：

```text
page=1
page_size=50
```

## 权限范围

| 权限 | 用途 |
| --- | --- |
| `read:accounts` | 查询邮箱、分组、标签、队列、系统版本 |
| `read:mails` | 查询邮件、邮件详情、验证码 |
| `write:accounts` | 导入账号 |
| `write:taxonomy` | 修改分组、标签、旗标、邮箱分组和邮箱标签 |
| `task:receive` | 执行收件任务 |
| `task:login` | 执行重新登录任务 |
| `task:backup` | 执行备份 |
| `notify:send` | 手动发送通知 |
| `read:logs` | 查询日志 |

## 查询接口

### 查询概览

```http
GET /api/v1/overview
```

返回总邮箱数、登录成功数量、未读数量、队列状态和安全设置摘要。

需要权限：`read:accounts`

### 查询邮箱列表

```http
GET /api/v1/accounts
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `group` | 按分组筛选 |
| `tag` | 按标签筛选 |
| `status` | 按登录状态筛选 |
| `auth_method` | 按认证方式筛选 |
| `keyword` | 搜索邮箱、分组、状态 |
| `page` | 页码 |
| `page_size` | 每页数量，最大 200 |

示例：

```bash
curl -H "Authorization: Bearer em_xxx" \
  "http://127.0.0.1:3000/api/v1/accounts?group=未分组&page=1&page_size=50"
```

需要权限：`read:accounts`

### 查询单个邮箱

```http
GET /api/v1/accounts/{email}
```

不会返回密码、refresh token、access token 明文，只返回是否存在这些字段。

需要权限：`read:accounts`

### 查询邮件列表

```http
GET /api/v1/mails
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `account` | 邮箱地址 |
| `group` | 分组 |
| `tag` | 标签 |
| `folder` | 文件夹，例如 `收件箱`、`垃圾邮件` |
| `starred` | 是否星标，`true` 或 `false` |
| `unread` | 是否未读，`true` 或 `false` |
| `has_code` | 是否包含验证码，`true` 或 `false` |
| `keyword` | 搜索邮箱、主题、发件人 |
| `date_from` | 起始时间，ISO 格式 |
| `date_to` | 结束时间，ISO 格式 |
| `page` | 页码 |
| `page_size` | 每页数量，最大 200 |

需要权限：`read:mails`

### 查询邮件详情

```http
GET /api/v1/mails/{local_key}
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `include_body` | 是否返回正文，默认 `true` |
| `wait_seconds` | `include_body=true` 时等待正文下载的秒数，默认 `8`，范围 `0-30` |

说明：

- 当 `include_body=true` 且正文尚未缓存时，接口会自动触发正文下载。
- `wait_seconds` 只影响本次接口等待时间，不会取消后台正文下载任务。

需要权限：`read:mails`

### 查询单封邮件验证码

```http
GET /api/v1/mails/{local_key}/codes
```

返回该邮件已提取出的验证码列表。

需要权限：`read:mails`

### 查询全局验证码

```http
GET /api/v1/codes
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `account` | 邮箱地址 |
| `keyword` | 搜索主题、发件人、邮箱 |
| `date_from` | 起始时间，ISO 格式 |
| `date_to` | 结束时间，ISO 格式 |
| `limit` | 返回数量，最大 200 |
| `ensure_body` | 是否自动确保疑似验证码邮件正文已下载，默认 `true` |
| `wait_seconds` | 等待正文下载和验证码提取的秒数，默认 `8`，范围 `0-30` |

说明：

- 默认情况下，接口会对疑似验证码邮件触发正文下载，并短暂等待验证码提取完成后返回。
- 如果只想立即读取当前缓存结果，可传 `ensure_body=false&wait_seconds=0`。
- 原有调用方式保持兼容，例如 `GET /api/v1/codes?account=user@example.com&limit=10` 不需要修改。

需要权限：`read:mails`

### 查询分组

```http
GET /api/v1/groups
```

需要权限：`read:accounts`

### 查询标签

```http
GET /api/v1/tags
```

需要权限：`read:accounts`

### 查询任务队列

```http
GET /api/v1/tasks
```

返回登录、收件、正文加载队列状态。

需要权限：`read:accounts`

### 查询日志

```http
GET /api/v1/logs
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `category` | 日志分类 |
| `level` | 日志等级 |
| `keyword` | 关键词 |
| `limit` | 返回数量，最大 1000 |

需要权限：`read:logs`

### 查询系统版本

```http
GET /api/v1/system/version
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `force` | 是否强制重新检查更新 |

需要权限：`read:accounts`

## 分组接口

### 创建分组

```http
POST /api/v1/groups
```

```json
{
  "name": "私有组",
  "color": "#38bdf8",
  "priority": 100,
  "locked": false
}
```

需要权限：`write:taxonomy`

### 修改分组

```http
PATCH /api/v1/groups/{group_name}
```

```json
{
  "name": "新分组名",
  "color": "#06b6d4",
  "priority": 200,
  "locked": true
}
```

`locked=true` 后，该分组下邮箱禁止转移分组、删除、重新登录、收件、修改标签、修改旗标、重新授权等风险操作。后台与 `/api/v1` 接口都会执行相同拦截。

需要权限：`write:taxonomy`

### 删除分组

```http
DELETE /api/v1/groups/{group_name}
```

删除分组不会删除邮箱，邮箱会自动归入“未分组”。

需要权限：`write:taxonomy`

## 标签接口

### 创建标签

```http
POST /api/v1/tags
```

```json
{
  "name": "重要",
  "color": "#f59e0b",
  "priority": 100
}
```

需要权限：`write:taxonomy`

### 修改标签

```http
PATCH /api/v1/tags/{tag_name}
```

```json
{
  "name": "新标签名",
  "color": "#22c55e",
  "priority": 200
}
```

需要权限：`write:taxonomy`

### 删除标签

```http
DELETE /api/v1/tags/{tag_name}
```

删除标签只会从邮箱上移除该标签，不会删除邮箱。

需要权限：`write:taxonomy`

## 邮箱分组、标签、旗标

### 修改单个邮箱分组

```http
PATCH /api/v1/accounts/{email}/group
```

```json
{
  "group_name": "私有组"
}
```

需要权限：`write:taxonomy`

### 批量修改邮箱分组

```http
PATCH /api/v1/accounts/batch/group
```

```json
{
  "emails": ["a@example.com", "b@example.com"],
  "group_name": "私有组"
}
```

需要权限：`write:taxonomy`

### 覆盖单个邮箱标签

```http
PUT /api/v1/accounts/{email}/tags
```

```json
{
  "tags": ["重要", "待处理"]
}
```

需要权限：`write:taxonomy`

### 添加单个邮箱标签

```http
POST /api/v1/accounts/{email}/tags
```

```json
{
  "tags": ["重要"]
}
```

需要权限：`write:taxonomy`

### 移除单个邮箱标签

```http
DELETE /api/v1/accounts/{email}/tags
```

```json
{
  "tags": ["重要"]
}
```

需要权限：`write:taxonomy`

### 批量添加标签

```http
POST /api/v1/accounts/batch/tags
```

```json
{
  "emails": ["a@example.com", "b@example.com"],
  "tags": ["重要"]
}
```

需要权限：`write:taxonomy`

### 批量覆盖标签

```http
PUT /api/v1/accounts/batch/tags
```

```json
{
  "emails": ["a@example.com", "b@example.com"],
  "tags": ["重要", "待处理"]
}
```

需要权限：`write:taxonomy`

### 批量移除标签

```http
DELETE /api/v1/accounts/batch/tags
```

```json
{
  "emails": ["a@example.com", "b@example.com"],
  "tags": ["重要"]
}
```

需要权限：`write:taxonomy`

### 设置单个邮箱旗标

```http
PATCH /api/v1/accounts/{email}/flag
```

```json
{
  "flag_color": "blue"
}
```

需要权限：`write:taxonomy`

### 取消单个邮箱旗标

```http
DELETE /api/v1/accounts/{email}/flag
```

需要权限：`write:taxonomy`

### 批量设置旗标

```http
PATCH /api/v1/accounts/batch/flag
```

```json
{
  "emails": ["a@example.com", "b@example.com"],
  "flag_color": "blue"
}
```

需要权限：`write:taxonomy`

### 批量取消旗标

```http
DELETE /api/v1/accounts/batch/flag
```

```json
{
  "emails": ["a@example.com", "b@example.com"]
}
```

需要权限：`write:taxonomy`

## 导入账号

### 文本导入

```http
POST /api/v1/accounts/import
```

```json
{
  "mode": "text",
  "content": "a@outlook.com----password----client_id----refresh_token",
  "group_name": "私有组"
}
```

`group_name` 可选；不传时按默认导入规则归入“未分组”或保留已有分组。若目标邮箱当前位于已锁定分组，导入时不能把它转移到其他分组。

导入后会自动加入登录队列。

需要权限：`write:accounts`

### 文件导入

```http
POST /api/v1/accounts/import-file
Content-Type: multipart/form-data
```

字段：

| 字段 | 说明 |
| --- | --- |
| `file` | txt 文件 |
| `group_name` | 可选 query 参数，导入到指定分组 |

需要权限：`write:accounts`

## 任务接口

### 执行收件

```http
POST /api/v1/tasks/receive
```

按邮箱：

```json
{
  "emails": ["a@example.com"]
}
```

全部邮箱：

```json
{
  "include_all": true
}
```

按分组：

```json
{
  "group_name": "私有组"
}
```

按标签：

```json
{
  "tag_name": "重要"
}
```

需要权限：`task:receive`

### 执行重新登录

```http
POST /api/v1/tasks/relogin
```

参数同收件接口。

需要权限：`task:login`

## 备份接口

### 执行备份

```http
POST /api/v1/backups/run
```

```json
{
  "include_accounts": true,
  "include_settings": true,
  "include_taxonomy": true,
  "include_logs": false
}
```

当前版本会执行完整 ZIP 备份，邮件缓存不会备份。

需要权限：`task:backup`

## 通知接口

### 手动发送通知

```http
POST /api/v1/notifications/send
```

```json
{
  "title": "外部任务",
  "content": "任务已完成"
}
```

通知会通过后台已配置的 Telegram Bot 发送。

需要权限：`notify:send`

## 后台 API Token 管理接口

以下接口使用后台登录 JWT，不使用公开 API Token。

### 查询 Token

```http
GET /api/api-tokens
```

### 创建 Token

```http
POST /api/api-tokens
```

```json
{
  "name": "外部查码服务",
  "scopes": ["read:mails", "read:accounts"]
}
```

### 禁用 Token

```http
POST /api/api-tokens/{token_id}/disable
```

## 安全说明

- API 不返回邮箱密码、refresh token、access token 明文。
- API 不提供删除邮箱、删除邮件、清空缓存、恢复备份、修改管理员密码、在线更新、重启服务等高风险能力。
- 所有写操作都会写入日志，方便审计。
- 建议给不同外部系统创建不同 Token，并只授予最小权限。
