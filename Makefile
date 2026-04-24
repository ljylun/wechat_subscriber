# Makefile for WeChat Subscriber

.PHONY: help install test run docker-build docker-up docker-down clean lint format

# 默认目标
help:
	@echo "微信公众号文章订阅系统 - Makefile"
	@echo ""
	@echo "可用命令:"
	@echo "  make install      - 安装依赖"
	@echo "  make test         - 运行单元测试"
	@echo "  make test-cov     - 运行测试并生成覆盖率报告"
	@echo "  make run          - 前台运行"
	@echo "  make start        - 后台启动"
	@echo "  make stop         - 停止服务"
	@echo "  make status       - 查看状态"
	@echo "  make docker-build - 构建Docker镜像"
	@echo "  make docker-up    - 启动Docker服务"
	@echo "  make docker-down  - 停止Docker服务"
	@echo "  make clean        - 清理临时文件"
	@echo "  make lint         - 代码检查"
	@echo "  make format       - 代码格式化"

# 安装依赖
install:
	pip install -r requirements.txt

# 运行测试
test:
	pytest tests/ -v

# 运行测试并生成覆盖率
test-cov:
	pytest tests/ --cov=src --cov-report=html --cov-report=term

# 查看覆盖率报告
cov-report:
	open htmlcov/index.html

# 前台运行
run:
	python main.py --config config.yaml run

# 后台启动
start:
	python main.py --config config.yaml start

# 停止服务
stop:
	python main.py --config config.yaml stop

# 查看状态
status:
	python main.py --config config.yaml status

# 单次检查
check:
	python main.py --config config.yaml check

# 构建Docker镜像
docker-build:
	docker build -t wechat_subscriber:latest .

# 启动Docker服务
docker-up:
	docker-compose up -d
	@echo "服务已启动，使用 'make docker-logs' 查看日志"

# 停止Docker服务
docker-down:
	docker-compose down

# 查看Docker日志
docker-logs:
	docker-compose logs -f

# 进入Docker容器
docker-exec:
	docker exec -it wechat_subscriber /bin/bash

# 清理临时文件
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf *.egg-info/
	rm -rf dist/
	rm -rf build/

# 代码检查
lint:
	flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503

# 代码格式化
format:
	black src/ tests/ --line-length=120

# 类型检查
type-check:
	mypy src/ --ignore-missing-imports

# 运行完整检查
check-all: lint format test

# 安装开发依赖
dev-install:
	pip install -r requirements.txt
	pip install black flake8 mypy pytest-cov

# 生成测试覆盖率HTML
htmlcov:
	pytest tests/ --cov=src --cov-report=html

# Docker日志清理
docker-clean:
	docker-compose down -v
	docker system prune -f

# 重启服务
restart: stop start

# 查看帮助
.DEFAULT_GOAL := help
