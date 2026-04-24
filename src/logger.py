#!/usr/bin/env python3
"""
日志模块
Logging Module
"""

import logging
import logging.handlers
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .config import Config


class JSONFormatter(logging.Formatter):
    """JSON格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为JSON"""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, 'biz'):
            log_data['biz'] = record.biz
        if hasattr(record, 'article_id'):
            log_data['article_id'] = record.article_id
        if hasattr(record, 'duration'):
            log_data['duration'] = record.duration
        if hasattr(record, 'extra'):
            log_data.update(record.extra)

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogAdapter(logging.LoggerAdapter):
    """结构化日志适配器"""

    def process(self, msg, kwargs):
        """处理日志消息"""
        extra = kwargs.get('extra', {})

        # 添加结构化字段
        if 'biz' in kwargs:
            extra['biz'] = kwargs.pop('biz')
        if 'article_id' in kwargs:
            extra['article_id'] = kwargs.pop('article_id')
        if 'duration' in kwargs:
            extra['duration'] = kwargs.pop('duration')

        kwargs['extra'] = extra
        return msg, kwargs


def setup_logger(config: Config) -> logging.Logger:
    """
    设置日志记录器

    Args:
        config: 配置对象

    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger('wechat_subscriber')
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # 清除现有处理器
    logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if config.log_file:
        try:
            log_path = Path(config.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用TimedRotatingFileHandler实现日志轮转
            file_handler = logging.handlers.TimedRotatingFileHandler(
                config.log_file,
                when='midnight',
                interval=1,
                backupCount=config.log_retention_days,
                encoding='utf-8'
            )
            file_handler.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

            # 使用JSON格式化器
            json_formatter = JSONFormatter()
            file_handler.setFormatter(json_formatter)

            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件 {config.log_file}: {e}")

    return logger


def get_logger(name: str = 'wechat_subscriber') -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        Logger实例
    """
    return logging.getLogger(name)
