# AAP (Automated Article Publisher)

> 微信公众号文章自动化发布工具 —— 将 Markdown 内容按可定制模板渲染为微信图文兼容 HTML，支持 API 自动上传草稿箱与手动拷贝导出双路径。

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-159%20passed-brightgreen.svg)](#测试)

## 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [安装](#安装)
- [配置初始化](#配置初始化)
- [撰写文章](#撰写文章)
- [本地预览](#本地预览)
- [模板管理](#模板管理)
- [发布到微信公众号](#发布到微信公众号)
- [解决 IP 白名单问题（SCF 代理）](#解决-ip-白名单问题scf-代理)
- [查看发布历史](#查看发布历史)
- [常用工作流](#常用工作流)
- [命令速查表](#命令速查表)
- [项目结构](#项目结构)
- [故障排查](#故障排查)
- [测试](#测试)
- [许可协议](#许可协议)

---

## 功能特性

### 核心能力

- **Markdown 解析**：支持 Front Matter 元数据 + 标题/段落/列表/表格/图片/代码块/引用块
- **模板系统**：配置文件 + 可视化编辑器双轨，CSS 与 YAML 配置分离
- **HTML 渲染**：自动内联 CSS、过滤微信不支持的标签与属性、图片占位符替换
- **双路径发布**：
  - **API 自动发布（主）**：自动上传图片到素材库 + 调用草稿箱 API
  - **手动导出（备）**：导出 HTML + ZIP + 图片清单 + 操作指南
- **本地预览**：FastAPI + WebSocket 热重载，支持微信样式模拟模式
- **兼容性检测**：9 项检查（危险标签、不支持属性、占位符、必填字段等）
- **SCF 代理**：腾讯云云函数代理，解决家庭宽带 IP 白名单问题
- **发布历史**：JSONL 格式记录每次发布的元数据

### 技术亮点

- access_token 缓存与自动刷新（提前 5 分钟续期）
- access_token 失效自动重试（40001/42001/40014）
- 图片并发上传（Semaphore=3）+ 指数退避重试（3 次）
- 配置深度合并（全局 + 项目级）+ 类型自动转换
- 模板三级优先级：项目模板 > 用户全局模板 > 内置模板

---

## 快速开始

```powershell
# 1. 安装
git clone <repo-url>
cd auto_article
pip install -e .

# 2. 初始化配置
aap config init
aap config set account.app_id "wx你的AppID"
aap config set account.app_secret "你的AppSecret"

# 3. 预览文章
aap preview article.md

# 4. 发布到草稿箱
aap publish article.md
```

---

## 安装

### 前置要求

- Python 3.10+
- 微信公众号 AppID 与 AppSecret（[获取方式](https://mp.weixin.qq.com) → 设置与开发 → 基本配置）

### 安装步骤

```powershell
git clone <repo-url>
cd auto_article

# 安装核心依赖
pip install -e .

# 可选：安装 SCF 部署依赖（用于绕开 IP 白名单）
pip install -e ".[scf]"

# 可选：安装开发依赖（测试、lint、类型检查）
pip install -e ".[dev]"
```

验证安装：

```powershell
aap --help
```

应显示 9 个子命令：`publish / export / preview / template / config / scf / image / history / test`。

---

## 配置初始化

### 1. 创建配置文件

```powershell
# 全局配置（写入 ~/.aap/config.yaml）
aap config init

# 或项目级配置（写入 ./.aap/config.yaml，会覆盖全局）
aap config init --target project
```

### 2. 填写微信公众号凭据

登录 [微信公众平台](https://mp.weixin.qq.com) → 设置与开发 → 基本配置，获取 `AppID` 和 `AppSecret`。

```powershell
aap config set account.app_id "wx你的AppID"
aap config set account.app_secret "你的AppSecret"
aap config set account.nickname "我的公众号"
```

### 3. 查看与读取配置

```powershell
# 显示所有配置（敏感字段自动脱敏）
aap config show

# 读取单个值
aap config get account.app_id
```

配置文件支持点号分隔的嵌套键，值的类型会自动转换（`true/false` → bool，`123` → int，`3.14` → float）。

---

## 撰写文章

文章使用 Markdown + YAML Front Matter 格式：

```markdown
---
title: 我的第一篇文章
author: 张三
summary: 这是文章摘要
template: minimal
cover: images/cover.jpg
tags:
  - 技术
  - 教程
---

# 文章标题

正文段落，支持 **加粗**、*斜体*、[链接](https://example.com)。

## 二级标题

![示例图片](images/sample.png)

> 引用文本

- 列表项一
- 列表项二

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| A   | B   | C   |

```python
def hello():
    print("Hello, AAP!")
```
```

### Front Matter 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `title` | 是 | 文章标题 |
| `template` | 否 | 使用的模板名（默认 `minimal`） |
| `cover` | API 发布必填 | 封面图路径（相对文章文件） |
| `summary` | 否 | 摘要（不填则自动取正文前 54 字） |
| `author` | 否 | 作者名 |
| `tags` | 否 | 标签列表 |

---

## 本地预览

发布前先本地预览渲染效果：

```powershell
# 启动预览服务（默认端口 8000，自动打开浏览器）
aap preview article.md

# 指定端口与模式
aap preview --port 8080 --mode wechat article.md

# 不自动打开浏览器
aap preview --no-browser article.md
```

预览模式：
- `wechat`（默认）：模拟微信编辑器外观
- `html`：纯 HTML 调试模式

支持 WebSocket 热重载，修改 Markdown 文件后页面自动刷新。

> **注意**：选项需放在位置参数之前（`aap preview [选项] <md>`）。

---

## 兼容性检测

发布前检查文章是否符合微信编辑器规范：

```powershell
aap test compatibility article.md
```

检测 9 项内容并输出 `✅/⚠️/❌` 报告：

- 危险标签过滤（script/iframe/form 等 13 种）
- 不支持属性检测
- HTML 注释检测
- 占位符未替换检测
- Front Matter 必填字段（title/cover）
- 内联 CSS 属性白名单
- 正文图片文件存在性
- 标题层级合理性
- 正文长度合理性

---

## 模板管理

### 1. 查看可用模板

```powershell
aap template list
# minimal
```

### 2. 可视化编辑模板

```powershell
# 启动模板编辑器（默认端口 7000）
aap template edit minimal

# 指定示例文章与端口
aap template edit --sample article.md --port 7001 minimal

# 不自动打开浏览器
aap template edit --no-browser minimal
```

编辑器界面：
- **左侧**：CSS 与 YAML 配置双 Tab 编辑
- **右侧**：实时预览渲染效果
- **Ctrl+S**：刷新预览
- **保存按钮**：写入 `~/.aap/templates/<name>/`

### 3. 查看模板详情

```powershell
aap template show minimal
```

### 模板优先级

加载模板时按以下顺序查找，找到即用：

1. **项目模板**：`./.aap/templates/<name>/`
2. **用户全局模板**：`~/.aap/templates/<name>/`
3. **内置模板**：随包分发（当前内置 `minimal`）

---

## 发布到微信公众号

### 方式 A：API 自动发布（推荐）

**前置条件**：微信公众号 IP 白名单需包含你的出口 IP。

```powershell
# 一键发布
aap publish article.md

# 指定模板（覆盖 Front Matter）
aap publish --template custom article.md

# 不自动复制到剪贴板
aap publish --no-clipboard article.md
```

发布流程：
1. 解析 Markdown + Front Matter
2. 渲染 HTML + 内联 CSS
3. 上传正文图片到微信素材库（并发 3 张，自动重试 3 次）
4. 上传封面图
5. 调用草稿箱 API 创建草稿
6. 本地留存 `article.html` + `manifest.json` + `publish_log.json`
7. 记录到历史

发布成功后，登录微信公众平台 → 草稿箱即可看到文章。

> **注意**：选项需放在位置参数之前（`aap publish [选项] <md>`）。

### 方式 B：手动导出（备路径）

当 API 不可用（如 IP 白名单受限）时使用：

```powershell
# 导出为 ZIP 包
aap export --output ./my_export article.md

# 不打包 ZIP，不复制到剪贴板
aap export --no-zip --no-clip article.md
```

导出包含：
- `article.html`：待粘贴的 HTML
- `images/`：所有图片（重命名为 `01.png`、`02.png`…）
- `manifest.json`：图片清单（记录占位符、原路径、待填 media_id）
- `INSTRUCTIONS.txt`：操作指南
- `<name>.zip`：打包文件（便于传输）

**手动发布步骤**：
1. 登录微信公众平台 → 素材管理 → 上传 `images/` 下所有图片
2. 记下每个图片 URL，运行 `aap image bind manifest.json` 交互式绑定
3. 浏览器打开 `article.html`，全选复制
4. 粘贴到微信公众号编辑器，保存草稿

---

## 解决 IP 白名单问题（SCF 代理）

家庭宽带 IP 不固定时，部署腾讯云 SCF 代理。

### 1. 部署 SCF 函数

```powershell
# 需要腾讯云 SecretId/SecretKey（在腾讯云控制台 → 访问管理获取）
aap scf deploy --secret-id "AKIDxxx" --secret-key "xxx"

# 输出示例：
# 触发 URL: https://servicexxxxx.ap-shanghai.apigw.tencentcs.com/release/aap-proxy
# SCF_SECRET: xYz123...
```

### 2. 写入配置

```powershell
aap config set scf.url "https://servicexxxxx.ap-shanghai.apigw.tencentcs.com/release/aap-proxy"
aap config set scf.secret "xYz123..."
aap config set scf.enabled true
```

### 3. 获取出口 IP 并加入白名单

```powershell
aap scf ip
# 输出：SCF 出口 IP: 150.109.123.45
```

登录微信公众平台 → 设置与开发 → 基本配置 → IP 白名单 → 添加该 IP。

### 4. 查询 SCF 状态

```powershell
aap scf status --secret-id "AKIDxxx" --secret-key "xxx"
```

---

## 查看发布历史

```powershell
# 列出最近 10 条发布记录（倒序，最新在前）
aap history list

# 查看更多
aap history list --limit 20

# 查看第 3 条详情
aap history show 3

# 显示历史文件路径
aap history path

# 清空历史（跳过确认）
aap history clear --force
```

历史记录存储在 `~/.aap/history.jsonl`，每行一条 JSON。

---

## 常用工作流

### 工作流 1：日常发布（已配置 SCF）

```powershell
# 1. 写文章（用任意编辑器）
# 2. 本地预览
aap preview my-article.md

# 3. 兼容性检查
aap test compatibility my-article.md

# 4. 一键发布
aap publish my-article.md
```

### 工作流 2：首次配置

```powershell
# 1. 初始化配置
aap config init
aap config set account.app_id "wxXXX"
aap config set account.app_secret "XXX"

# 2. （可选）部署 SCF 代理
aap scf deploy --secret-id "AKIDxxx" --secret-key "xxx"
aap config set scf.enabled true

# 3. 添加 IP 白名单
aap scf ip
# → 复制输出 IP 到微信公众平台白名单

# 4. 测试发布
aap publish tests/fixtures/sample.md
```

### 工作流 3：无 API 时的手动发布

```powershell
# 1. 导出
aap export --output ./out article.md

# 2. 上传图片到微信素材库，填入 manifest.json

# 3. 绑定图片 URL
aap image bind ./out/article_xxx/manifest.json

# 4. 复制 article_final.html 内容到微信编辑器
```

---

## 命令速查表

| 命令 | 用途 |
|------|------|
| `aap config init` | 初始化配置文件 |
| `aap config set <key> <value>` | 设置配置项（支持点号分隔） |
| `aap config get <key>` | 读取配置项 |
| `aap config show` | 显示所有配置 |
| `aap preview [选项] <md>` | 本地预览 |
| `aap test compatibility <md>` | 兼容性检测 |
| `aap template list` | 列出模板 |
| `aap template edit [选项] <name>` | 编辑模板 |
| `aap template show <name>` | 查看模板详情 |
| `aap publish [选项] <md>` | 发布到草稿箱 |
| `aap export [选项] <md>` | 导出 HTML 包 |
| `aap image bind <manifest>` | 绑定图片 URL |
| `aap scf deploy` | 部署 SCF 代理 |
| `aap scf ip` | 获取 SCF 出口 IP |
| `aap scf status` | 查询 SCF 状态 |
| `aap history list` | 发布历史列表 |
| `aap history show <n>` | 查看历史详情 |
| `aap history path` | 显示历史文件路径 |
| `aap history clear` | 清空历史 |

---

## 项目结构

```
auto_article/
├── docs/                          # 设计文档
│   ├── 需求文档.md
│   └── 技术设计.md
├── src/aap/                       # 源代码
│   ├── cli/                       # CLI 命令
│   │   ├── main.py                # 主入口
│   │   ├── config_cli.py          # config 命令
│   │   ├── publish.py             # publish 命令
│   │   ├── export.py              # export 命令
│   │   ├── preview.py             # preview 命令
│   │   ├── template.py            # template 命令
│   │   ├── scf.py                 # scf 命令
│   │   ├── image.py               # image 命令
│   │   ├── history.py             # history 命令
│   │   └── test_cmd.py            # test 命令
│   ├── core/                      # 核心模块
│   │   ├── parser.py              # Markdown 解析
│   │   ├── renderer.py            # HTML 渲染
│   │   ├── html_utils.py          # HTML 工具函数
│   │   ├── template_engine.py     # Jinja2 封装
│   │   └── models.py              # 数据模型
│   ├── config/                    # 配置管理
│   │   └── manager.py
│   ├── templates/                 # 模板系统
│   │   ├── manager.py             # 模板管理器
│   │   ├── editor/                # 可视化编辑器
│   │   │   └── server.py
│   │   └── builtin/minimal/       # 内置模板
│   ├── preview/                   # 预览服务
│   │   └── server.py
│   ├── publish/                   # 发布模块
│   │   ├── publisher.py           # API 发布
│   │   └── exporter.py            # 手动导出
│   ├── wechat/                    # 微信 API
│   │   ├── auth.py                # access_token 管理
│   │   ├── client.py              # 统一客户端
│   │   ├── material.py            # 素材上传
│   │   └── draft.py               # 草稿箱
│   ├── scf/                       # 腾讯云 SCF
│   │   ├── proxy.py               # SCF 代理客户端
│   │   ├── deployer.py            # 部署器
│   │   └── function_src/main.py   # 云函数入口
│   ├── image/                     # 图片处理
│   │   ├── scanner.py             # 图片扫描
│   │   ├── packer.py              # 打包器
│   │   └── binder.py              # 绑定器
│   └── utils/                     # 工具函数
│       ├── path.py                # 路径工具
│       └── clipboard.py           # 剪贴板
├── tests/                         # 测试（159 项）
├── .aap/                          # 项目级配置
│   ├── config.example.yaml        # 示例配置
│   └── output/                    # 发布本地留存
├── pyproject.toml                 # 项目配置
└── README.md                      # 本文档
```

---

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| `access_token` 获取失败 | 检查 `app_id/app_secret`；确认 IP 已加入白名单 |
| `40001 invalid credential` | IP 不在白名单 → 部署 SCF 代理 |
| `40164 invalid ip` | 出口 IP 不在白名单，运行 `aap scf ip` 获取并添加 |
| 图片上传失败 | 检查图片格式（支持 jpg/png/gif）；文件不超过 10MB |
| 草稿数超限 | 微信限制每公众号 100 条草稿，清理旧草稿 |
| 模板渲染异常 | `aap template edit` 实时调试 CSS |
| SCF 部署失败 | 确认腾讯云账号已开通 SCF 服务 |
| 配置文件不生效 | 检查项目级配置是否覆盖了全局配置 |
| 选项报错 `No such option` | 选项需放在位置参数之前 |

更多帮助：每个命令加 `--help` 查看详细参数，例如 `aap publish --help`。

---

## 测试

项目包含 159 项单元测试，覆盖所有核心模块：

```powershell
# 运行全部测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/core/test_template_engine.py -v

# 查看覆盖率
python -m pytest tests/ --cov=aap --cov-report=term-missing
```

测试覆盖范围：
- `core/`：parser、renderer、html_utils、template_engine
- `config/`：ConfigManager
- `templates/`：TemplateManager、EditorServer
- `wechat/`：DraftAPI
- `scf/`：main_handler、SCFDeployer
- `image/`：ImageBinder
- `cli/`：history 命令

---

## 许可协议

[MIT License](LICENSE)
