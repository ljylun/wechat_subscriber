# 微信公众号文章自动订阅系统

简体中文 | [English](README_EN.md)

## 项目简介

微信公众号文章自动订阅系统是一款功能强大的公众号内容监控与采集工具。该系统能够实时监控指定微信公众号的新文章发布，自动完成文章下载、内容解析、结构化存储，并支持通过企业微信机器人或邮件推送通知。

### 核心特性

- **实时监控**：采用轮询+增量哈希双重策略，每5分钟自动检查公众号更新
- **反爬对抗**：自动轮换User-Agent、支持代理池、随机延迟、302跳转处理
- **智能解析**：Readability算法+正则双通道提取正文，自动过滤广告噪音
- **资源下载**：完整下载封面图、正文图片、视频、音频，统一UTF-8编码
- **本地化存储**：标准化目录结构，生成manifest.json元数据文件
- **去重机制**：基于biz+sn唯一键的SQLite去重表，避免重复下载
- **通知推送**：企业微信机器人/邮件实时推送文章摘要
- **容器化部署**：Docker一键部署，镜像体积小于120MB

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     微信公众号文章订阅系统                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   配置模块    │    │   监控模块    │    │  下载模块    │       │
│  │   config.py  │───▶│  monitor.py  │───▶│downloader.py│       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                 │
│         ▼                   ▼                   ▼                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   存储模块    │    │   解析模块    │    │  通知模块    │       │
│  │  storage.py  │◀───│  parser.py   │◀───│ notifier.py │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
wechat_subscriber/
├── src/                      # 源代码目录
│   ├── __init__.py
│   ├── config.py             # 配置管理模块
│   ├── monitor.py           # 公众号监控模块
│   ├── downloader.py        # 文章下载模块
│   ├── parser.py            # 内容解析模块
│   ├── notifier.py          # 通知推送模块
│   ├── storage.py           # 存储去重模块
│   ├── logger.py            # 日志记录模块
│   └── scheduler.py         # 调度主程序
├── tests/                    # 测试目录
│   ├── test_config.py
│   ├── test_monitor.py
│   ├── test_downloader.py
│   ├── test_parser.py
│   └── test_storage.py
├── docs/                     # 文档目录
├── data/                     # 数据存储目录
├── main.py                   # 程序入口
├── config.yaml.example       # 配置示例
├── requirements.txt          # Python依赖
├── Dockerfile                # Docker镜像构建文件
├── docker-compose.yml        # Docker编排配置
└── README.md                 # 项目说明文档
```

## 快速开始

### 环境要求

- Python 3.11+
- Docker 20.10+（可选）
- Docker Compose 2.0+（可选）

### 安装依赖

```bash
# 克隆项目
git clone https://github.com/ljylun/wechat_subscriber.git
cd wechat_subscriber

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置系统

复制配置文件并进行修改：

```bash
# 复制配置示例
cp config.yaml.example config.yaml

# 编辑配置文件
vim config.yaml
```

配置说明：

```yaml
# 公众号配置
accounts:
  - biz: "你的公众号biz标识"
    name: "公众号名称"

# 轮询间隔（秒）
poll_interval: 300

# 通知配置
notification:
  enabled: true
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的KEY"
```

### 运行系统

```bash
# 前台运行
python main.py --config config.yaml run

# 后台运行（守护进程模式）
python main.py --config config.yaml start --daemon

# 单次检查
python main.py --config config.yaml check
```

## Docker部署

### 构建镜像

```bash
docker build -t wechat_subscriber:latest .
```

### 使用Docker Compose启动

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 手动Docker运行

```bash
# 创建数据目录
mkdir -p /data/wechat_data

# 运行容器
docker run -d \
  --name wechat_subscriber \
  -v /path/to/config.yaml:/etc/wechat_subscriber/config.yaml:ro \
  -v /data/wechat_data:/data \
  -v /var/log:/var/log \
  wechat_subscriber:latest \
  python main.py --config /etc/wechat_subscriber/config.yaml start --daemon
```

## 使用说明

### 获取公众号biz

1. 打开公众号任意文章
2. 点击右上角「...」菜单
3. 选择「复制链接」
4. 链接格式：`https://mp.weixin.qq.com/s/xxxx?__biz=这里就是biz&mid=...`

### CLI命令

```bash
# 启动守护进程
python main.py --config config.yaml start

# 停止守护进程
python main.py --config config.yaml stop

# 查看运行状态
python main.py --config config.yaml status

# 前台运行
python main.py --config config.yaml run

# 单次检查新文章
python main.py --config config.yaml check
```

### 查看日志

```bash
# 实时查看日志
tail -f /var/log/wechat_subscriber.log

# 查看最近100行
tail -n 100 /var/log/wechat_subscriber.log

# 搜索关键词
grep "新文章" /var/log/wechat_subscriber.log
```

## 数据存储结构

文章下载后按以下结构存储：

```
/data/
├── dedup.db                    # SQLite去重数据库
└── {biz}/
    └── {yyyy-mm-dd}/
        └── {article_id}/
            ├── index.html      # 文章HTML原文
            ├── manifest.json   # 元数据文件
            ├── images/         # 图片目录
            │   ├── img_xxx1.jpg
            │   └── img_xxx2.png
            ├── videos/         # 视频目录
            └── audios/        # 音频目录
```

manifest.json示例：

```json
{
  "title": "文章标题",
  "author": "作者名称",
  "publish_time": "2024-01-15",
  "original_url": "https://mp.weixin.qq.com/s/...",
  "article_id": "article_id",
  "biz": "biz_id",
  "resources": [
    {
      "type": "image",
      "original_url": "https://mmbiz.qpic.cn/...",
      "local_path": "images/img_xxx.jpg",
      "file_size": 1024
    }
  ]
}
```

## 测试

### 运行单元测试

```bash
# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=src --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 测试示例文章解析

```bash
# 确保文章HTML文件存在
python -c "
from src.parser import ArticleParser
from src.config import Config
from src.downloader import DownloadedArticle
from src.monitor import Article

config = Config()
parser = ArticleParser(config)

# 创建测试数据
article = Article(
    article_id='test',
    biz='test_biz',
    title='测试文章'
)

# 执行解析
# ... (需要先有下载的HTML文件)
"
```

## 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| CPU使用率 | <10% | 24小时平均 |
| 内存占用 | <200MB | 持续运行 |
| 响应时间 | <5秒 | 单次检查 |
| 并发处理 | 10个公众号 | 同时监控 |

## 常见问题

### Q: 提示"反爬拦截"怎么办？

确保配置了多个User-Agent，并启用代理池：

```yaml
anti_crawl:
  user_agents:
    - "Mozilla/5.0 ..."
    - "Mozilla/5.0 ..."

proxy:
  enabled: true
  api_url: "http://your-proxy-api"
```

### Q: 如何增加公众号监控数量？

编辑config.yaml添加更多账户：

```yaml
accounts:
  - biz: "biz1"
    name: "公众号1"
  - biz: "biz2"
    name: "公众号2"
  - biz: "biz3"
    name: "公众号3"
```

### Q: 通知没有收到？

1. 检查webhook_url是否正确
2. 确认企业微信机器人没有被禁用
3. 查看日志中的错误信息

### Q: 如何查看已下载的文章？

```bash
# 查看所有已下载的文章
find /data -name "manifest.json" | head -20

# 统计文章数量
find /data -name "manifest.json" | wc -l
```

## 开发指南

### 代码规范

```bash
# 代码格式化
black src/ tests/

# 代码检查
flake8 src/ tests/

# 类型检查
mypy src/
```

### 添加新功能

1. 在对应模块中添加功能代码
2. 编写单元测试
3. 更新文档
4. 提交Pull Request

## 许可证

本项目采用 MIT 许可证。

## 贡献指南

欢迎提交Issue和Pull Request！

## 更新日志

### v1.0.0 (2024-01-15)

- 初始版本发布
- 实现基础监控功能
- 实现文章下载与解析
- 支持企业微信通知
- 支持Docker部署
