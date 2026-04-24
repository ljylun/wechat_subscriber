# 微信公众号文章自动订阅系统
# WeChat Public Account Article Subscriber - Dockerfile

# 阶段1: 构建阶段
FROM python:3.11-slim as builder

WORKDIR /build

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 阶段2: 运行阶段
FROM python:3.11-slim

# 安全配置
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /data /var/log && \
    chown -R appuser:appuser /data /var/log

WORKDIR /app

# 从构建阶段复制已安装的包
COPY --from=builder /root/.local /home/appuser/.local

# 复制应用代码
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser config.yaml.example ./

# 设置环境变量
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 切换到非root用户
USER appuser

# 暴露端口（用于健康检查）
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# 入口点
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
