# EasyMail

EasyMail 是一个基于 `FastAPI + Vue 3 + Docker Compose` 的多邮箱管理工具，面向 Outlook / Hotmail / IMAP 邮箱的批量导入、登录、收件、正文查看、分组标签管理、任务调度与日志排查。

## 功能

- 多邮箱批量导入与管理
- Outlook `Graph API -> IMAP` 自动回退
- 三分屏邮件工作台
- 分组 / 标签 / 星标
- Token 全量刷新与定时刷新
- 自动收件与账号备份
- 结构化日志页面
- Docker Compose 一键部署

## 快速启动

### 1. 复制环境变量模板

```bash
cp .env.example .env
```

按需修改：

- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `JWT_SECRET`

### 2. 启动服务

```bash
docker compose up -d --build
```

默认访问地址：

- `http://127.0.0.1:3000`

## 项目结构

```text
backend/   FastAPI 后端
frontend/  Vue 前端
data/      运行时数据目录
```

## 公开发布建议

- 不要提交 `.env`
- 不要提交 `data/` 中的数据库、缓存和备份
- 不要提交 `frontend/node_modules` 和 `frontend/dist`

## 发布到 Docker Hub

### 构建单镜像

```bash
docker build -t vivibudong/easymail:latest .
```

### 登录并推送

```bash
docker login
docker push vivibudong/easymail:latest
```

## 在线拉取版 Compose

公开发布后，用户可以直接使用仓库里的 `docker-compose.release.yml`：

```bash
cp .env.example .env
docker compose -f docker-compose.release.yml up -d
```

这个版本会直接拉取 `vivibudong/easymail:latest`，无需本地构建。
