---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 304602210086a61f05e7be7bf137e507821edf7e12a81d25923a8e623c7998eed69be287b10221009d7a987d5ea3e0620e47c5fa00f8ea231f3ff6205fc325a5fa5d5d3e03b06a10
    ReservedCode2: 3045022100a04b12a089ab8874d5f56c90a875eae04dc375d6a6aa78aacf939891eb8a7259022007c4150c53521b84bcc06d8d71ea5182cbb9883fa8b07da9601cc3d81d86ffd8
---

# 部署与运维文档

## 目录

- [环境准备](#环境准备)
- [安装部署](#安装部署)
- [配置说明](#配置说明)
- [运维操作](#运维操作)
- [日志查看](#日志查看)
- [监控告警](#监控告警)
- [备份恢复](#备份恢复)
- [常见问题排查](#常见问题排查)

## 环境准备

### 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 1核 | 2核+ |
| 内存 | 512MB | 1GB+ |
| 磁盘 | 10GB | 50GB+ |
| 系统 | CentOS 7+ / Ubuntu 18+ / Docker环境 | |

### 依赖软件

```bash
# Python环境 (Python 3.11+)
python --version

# Docker (可选)
docker --version

# Docker Compose (可选)
docker-compose --version
```

## 安装部署

### 方式一：Docker部署（推荐）

#### 1. 拉取代码

```bash
git clone https://github.com/your-repo/wechat_subscriber.git
cd wechat_subscriber
```

#### 2. 创建配置目录

```bash
# 创建配置目录
sudo mkdir -p /etc/wechat_subscriber
sudo mkdir -p /data/wechat_subscriber
sudo mkdir -p /var/log/wechat_subscriber

# 设置权限
sudo chown -R $USER:$USER /data/wechat_subscriber /var/log/wechat_subscriber
```

#### 3. 配置文件

```bash
# 复制配置示例
cp config.yaml.example /etc/wechat_subscriber/config.yaml

# 编辑配置
vim /etc/wechat_subscriber/config.yaml
```

#### 4. 启动服务

```bash
# 使用Docker Compose启动
docker-compose up -d

# 或使用Docker启动
docker build -t wechat_subscriber:latest .
docker run -d \
  --name wechat_subscriber \
  --restart unless-stopped \
  -v /etc/wechat_subscriber:/etc/wechat_subscriber:ro \
  -v /data/wechat_subscriber:/data \
  -v /var/log/wechat_subscriber:/var/log \
  wechat_subscriber:latest \
  python main.py --config /etc/wechat_subscriber/config.yaml start --daemon
```

### 方式二：直接部署

#### 1. 安装Python依赖

```bash
# 安装Python 3.11
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置并运行

```bash
# 复制配置
cp config.yaml.example config.yaml
vim config.yaml

# 前台运行测试
python main.py --config config.yaml run

# 确认正常后，改为后台运行
nohup python main.py --config config.yaml start --daemon &
```

## 配置说明

### 完整配置示例

```yaml
# ===========================================
# 公众号配置
# ===========================================
accounts:
  - biz: "MjM5OTIxNTg4MA=="        # 必填，公众号唯一标识
    name: "科技每日推送"            # 可选，显示名称
    alias: "tech_daily"            # 可选，别名

# ===========================================
# 监控配置
# ===========================================
poll_interval: 300          # 轮询间隔（秒），建议范围60-3600
batch_size: 10              # 每次处理的最大文章数

# ===========================================
# 反爬配置
# ===========================================
anti_crawl:
  user_agents:               # User-Agent列表，越多越好
    - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
    - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
  min_delay: 2.0            # 最小请求延迟
  max_delay: 5.0            # 最大请求延迟

# ===========================================
# 重试配置
# ===========================================
retry:
  max_retries: 3            # 最大重试次数
  base_delay: 60             # 基础重试延迟（秒）
  max_delay: 1800            # 最大重试延迟（秒），支持指数退避

# ===========================================
# 存储配置
# ===========================================
data_root: "/data"          # 数据存储根目录
db_path: "/data/dedup.db"   # SQLite数据库路径
enable_dedup: true          # 启用去重（强烈建议开启）

# ===========================================
# 日志配置
# ===========================================
log_file: "/var/log/wechat_subscriber.log"
log_level: "INFO"          # DEBUG/INFO/WARNING/ERROR/CRITICAL
log_retention_days: 30      # 日志保留天数

# ===========================================
# 代理配置（可选）
# ===========================================
proxy:
  enabled: false
  api_url: "http://proxy-api.example.com/get"  # 代理API地址
  min_delay: 1.0
  max_delay: 3.0

# ===========================================
# 通知配置
# ===========================================
notification:
  enabled: true
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
```

### 配置验证

```bash
# 启动前验证配置
python -c "
from src.config import Config
config = Config.from_yaml('/etc/wechat_subscriber/config.yaml')
errors = config.validate()
if errors:
    print('配置错误:')
    for e in errors:
        print(f'  - {e}')
else:
    print('配置验证通过')
"
```

## 运维操作

### 服务管理

```bash
# 启动服务
python main.py --config config.yaml start

# 停止服务
python main.py --config config.yaml stop

# 查看状态
python main.py --config config.yaml status

# 重启服务
python main.py --config config.yaml stop && python main.py --config config.yaml start
```

### Docker运维

```bash
# 查看容器状态
docker ps | grep wechat_subscriber

# 查看容器日志
docker logs -f wechat_subscriber

# 进入容器
docker exec -it wechat_subscriber /bin/bash

# 重启容器
docker restart wechat_subscriber

# 重新构建并启动
docker-compose down && docker-compose up -d --build
```

### 进程管理

```bash
# 查看进程
ps aux | grep wechat_subscriber

# 查看PID文件
cat /var/run/wechat_subscriber.pid

# 强制终止
kill -9 $(cat /var/run/wechat_subscriber.pid)
```

## 日志查看

### 日志位置

- 默认日志：`/var/log/wechat_subscriber.log`
- Docker日志：`docker logs wechat_subscriber`
- 临时日志：容器内 `/var/log/wechat_subscriber.log`

### 查看日志

```bash
# 实时查看日志
tail -f /var/log/wechat_subscriber.log

# 查看最近100行
tail -n 100 /var/log/wechat_subscriber.log

# 搜索关键词
grep "新文章" /var/log/wechat_subscriber.log
grep "ERROR" /var/log/wechat_subscriber.log

# 按时间范围查看
grep "2024-01-15 10:" /var/log/wechat_subscriber.log

# 查看JSON格式日志
cat /var/log/wechat_subscriber.log | jq
```

### 日志格式

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "level": "INFO",
  "biz": "MjM5OTIxNTg4MA==",
  "article_id": "abc123",
  "message": "文章下载完成",
  "duration": 2.5
}
```

### 日志轮转

日志文件自动在每天午夜进行轮转，保留30天：

```bash
# 查看轮转的日志文件
ls -la /var/log/wechat_subscriber*

# 手动轮转日志
kill -USR1 $(cat /var/run/wechat_subscriber.pid)
```

## 监控告警

### 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| 进程状态 | 进程是否存活 | 停止即告警 |
| 内存使用 | 内存占用 | >200MB |
| CPU使用 | CPU占用 | 持续>50% |
| 磁盘空间 | 剩余空间 | <1GB |
| 失败次数 | 连续失败 | 3次 |

### 告警配置示例

```yaml
# 企业微信告警
notification:
  enabled: true
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

### 外部监控脚本

```bash
#!/bin/bash
# check_health.sh - 健康检查脚本

LOG_FILE="/var/log/wechat_subscriber.log"

# 检查进程
if ! ps aux | grep -v grep | grep -q "wechat_subscriber"; then
    echo "进程未运行"
    exit 1
fi

# 检查内存
MEM=$(ps aux | grep wechat_subscriber | awk '{print $6}')
if [ "$MEM" -gt 204800 ]; then  # 200MB = 204800KB
    echo "内存占用过高: ${MEM}KB"
    exit 1
fi

# 检查日志错误
ERRORS=$(tail -n 100 "$LOG_FILE" | grep -c "ERROR")
if [ "$ERRORS" -gt 10 ]; then
    echo "错误日志过多: $ERRORS"
    exit 1
fi

echo "健康检查通过"
exit 0
```

## 备份恢复

### 数据备份

```bash
# 备份数据目录
tar -czvf backup_$(date +%Y%m%d).tar.gz /data/wechat_subscriber

# 备份配置
cp /etc/wechat_subscriber/config.yaml config_backup.yaml

# 备份日志
cp /var/log/wechat_subscriber.log wechat_subscriber.log.bak
```

### 数据恢复

```bash
# 停止服务
python main.py --config config.yaml stop

# 恢复数据
tar -xzvf backup_20240115.tar.gz -C /

# 启动服务
python main.py --config config.yaml start
```

### 自动备份脚本

```bash
#!/bin/bash
# backup.sh - 自动备份脚本

BACKUP_DIR="/backup/wechat_subscriber"
DATA_DIR="/data/wechat_subscriber"
DATE=$(date +%Y%m%d)

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份数据
tar -czvf "$BACKUP_DIR/data_$DATE.tar.gz" "$DATA_DIR"

# 备份配置
cp /etc/wechat_subscriber/config.yaml "$BACKUP_DIR/config_$DATE.yaml"

# 保留最近30天备份
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "config_*.yaml" -mtime +30 -delete

echo "备份完成: $DATE"
```

### 定时任务

```bash
# 编辑crontab
crontab -e

# 添加备份任务（每天凌晨3点）
0 3 * * * /path/to/backup.sh >> /var/log/backup.log 2>&1

# 添加健康检查（每5分钟）
*/5 * * * * /path/to/check_health.sh
```

## 常见问题排查

### 问题1：服务启动失败

**症状**：执行start命令后立即退出

**排查步骤**：

```bash
# 1. 检查配置文件是否存在
ls -la /etc/wechat_subscriber/config.yaml

# 2. 检查配置语法
python -c "from src.config import Config; Config.from_yaml('/etc/wechat_subscriber/config.yaml')"

# 3. 查看详细错误
python main.py --config config.yaml run

# 4. 检查端口占用
lsof -i :8080
```

**解决方案**：

- 确保配置文件存在且格式正确
- 检查依赖是否完整安装
- 检查端口是否被占用

### 问题2：反爬拦截

**症状**：日志显示"检测到反爬拦截"

**排查步骤**：

```bash
# 1. 检查User-Agent配置
grep -A5 "user_agents" config.yaml

# 2. 增加更多User-Agent
# 3. 启用代理池
```

**解决方案**：

```yaml
anti_crawl:
  user_agents:
    - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
    - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
    - "Mozilla/5.0 (X11; Linux x86_64)..."

proxy:
  enabled: true
  api_url: "http://your-proxy-api"
```

### 问题3：文章下载失败

**症状**：特定文章下载失败

**排查步骤**：

```bash
# 1. 查看错误日志
grep "下载失败" /var/log/wechat_subscriber.log

# 2. 检查网络连接
curl -I https://mp.weixin.qq.com/s/xxxxx

# 3. 检查磁盘空间
df -h
```

**解决方案**：

- 检查网络是否正常
- 增加重试次数
- 清理磁盘空间

### 问题4：通知发送失败

**症状**：企业微信通知没有收到

**排查步骤**：

```bash
# 1. 检查webhook URL
echo $webhook_url

# 2. 测试webhook
curl -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"msgtype": "text", "text": {"content": "test"}}'

# 3. 检查日志
grep "通知" /var/log/wechat_subscriber.log
```

**解决方案**：

- 确认webhook URL正确
- 确认机器人没有被禁用
- 检查企业微信群是否正常

### 问题5：内存占用过高

**症状**：进程内存持续增长

**排查步骤**：

```bash
# 1. 查看内存使用
ps aux | grep wechat_subscriber

# 2. 检查是否有内存泄漏
watch -n 1 'ps aux | grep wechat_subscriber | awk "{print \$6}"'

# 3. 检查SQLite数据库大小
ls -lh /data/wechat_subscriber/dedup.db
```

**解决方案**：

```bash
# 清理旧记录
python -c "
from src.storage import ArticleStorage
from src.config import Config
storage = ArticleStorage(Config())
storage.cleanup_old_records(7)
"

# 重启服务释放内存
python main.py --config config.yaml stop
python main.py --config config.yaml start
```

### 问题6：无法停止服务

**症状**：stop命令无响应

**排查步骤**：

```bash
# 1. 查看PID文件
cat /var/run/wechat_subscriber.pid

# 2. 强制终止
kill -9 $(cat /var/run/wechat_subscriber.pid)

# 3. 清理PID文件
rm -f /var/run/wechat_subscriber.pid
```

## 性能优化

### 参数调优

```yaml
# 调整轮询间隔
poll_interval: 600  # 从300秒调整为600秒，减少资源消耗

# 调整并发数
batch_size: 5       # 减少每次处理数量
```

### 数据库优化

```bash
# 定期清理旧记录
# 建议每周执行一次
python -c "
from src.storage import ArticleStorage
from src.config import Config
storage = ArticleStorage(Config())
storage.cleanup_old_records(30)  # 保留30天
"

# 重建索引
sqlite3 /data/wechat_subscriber/dedup.db "REINDEX;"
```

### 系统优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# 调整网络参数
echo "net.ipv4.tcp_tw_reuse = 1" >> /etc/sysctl.conf
sysctl -p
```

## 技术支持

- GitHub Issues: https://github.com/your-repo/wechat_subscriber/issues
- 文档: https://your-docs-url.com
- 邮箱: support@example.com
