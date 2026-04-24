#!/usr/bin/env python3
"""
配置管理模块
Configuration Management Module
"""

import os
import yaml
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class ProxyConfig:
    """代理配置"""
    enabled: bool = False
    api_url: str = ""
    min_delay: float = 1.0
    max_delay: float = 3.0


@dataclass
class NotificationConfig:
    """通知配置"""
    webhook_url: str = ""
    enabled: bool = False


@dataclass
class WeChatAccount:
    """微信公众号账户"""
    biz: str
    name: str = ""
    alias: str = ""


@dataclass
class Config:
    """主配置类"""
    # 监控配置
    accounts: List[WeChatAccount] = field(default_factory=list)
    poll_interval: int = 300  # 5分钟
    batch_size: int = 10

    # 反爬配置
    user_agents: List[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ])
    min_request_delay: float = 2.0
    max_request_delay: float = 5.0

    # 重试配置
    max_retries: int = 3
    base_retry_delay: int = 60  # 60秒
    max_retry_delay: int = 1800  # 30分钟

    # 存储配置
    data_root: str = "/data"
    enable_dedup: bool = True
    db_path: str = "/data/dedup.db"

    # 日志配置
    log_file: str = "/var/log/wechat_subscriber.log"
    log_level: str = "INFO"
    log_retention_days: int = 30

    # 代理配置
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    # 通知配置
    notification: NotificationConfig = field(default_factory=NotificationConfig)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Config':
        """从YAML文件加载配置"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        config = cls()

        # 解析公众号列表
        if 'accounts' in data:
            config.accounts = [
                WeChatAccount(**acc) if isinstance(acc, dict) else acc
                for acc in data['accounts']
            ]

        # 解析顶层字段
        for key in ['poll_interval', 'batch_size', 'data_root', 'db_path',
                    'log_file', 'log_level', 'log_retention_days']:
            if key in data:
                setattr(config, key, data[key])

        # 解析代理配置
        if 'proxy' in data:
            config.proxy = ProxyConfig(**data['proxy'])

        # 解析通知配置
        if 'notification' in data:
            config.notification = NotificationConfig(**data['notification'])

        # 解析反爬配置
        if 'anti_crawl' in data:
            ac = data['anti_crawl']
            if 'user_agents' in ac:
                config.user_agents = ac['user_agents']
            if 'min_delay' in ac:
                config.min_request_delay = ac['min_delay']
            if 'max_delay' in ac:
                config.max_request_delay = ac['max_delay']

        # 解析重试配置
        if 'retry' in data:
            r = data['retry']
            if 'max_retries' in r:
                config.max_retries = r['max_retries']
            if 'base_delay' in r:
                config.base_retry_delay = r['base_delay']
            if 'max_delay' in r:
                config.max_retry_delay = r['max_delay']

        return config

    def to_yaml(self, yaml_path: str) -> None:
        """保存配置到YAML文件"""
        data = {
            'accounts': [asdict(acc) if isinstance(acc, WeChatAccount) else acc
                        for acc in self.accounts],
            'poll_interval': self.poll_interval,
            'batch_size': self.batch_size,
            'data_root': self.data_root,
            'db_path': self.db_path,
            'log_file': self.log_file,
            'log_level': self.log_level,
            'log_retention_days': self.log_retention_days,
            'proxy': asdict(self.proxy),
            'notification': asdict(self.notification),
            'anti_crawl': {
                'user_agents': self.user_agents,
                'min_delay': self.min_request_delay,
                'max_delay': self.max_request_delay,
            },
            'retry': {
                'max_retries': self.max_retries,
                'base_delay': self.base_retry_delay,
                'max_delay': self.max_retry_delay,
            },
        }

        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []

        if not self.accounts:
            errors.append("至少需要配置一个公众号")

        for acc in self.accounts:
            if not acc.biz:
                errors.append(f"公众号配置缺少biz字段: {acc}")

        if self.poll_interval < 60:
            errors.append("轮询间隔不能小于60秒")

        if self.data_root:
            Path(self.data_root).mkdir(parents=True, exist_ok=True)

        return errors

    def get_storage_path(self, biz: str, article_id: str, publish_date: str = None) -> Path:
        """获取文章存储路径"""
        if publish_date is None:
            publish_date = datetime.now().strftime("%Y-%m-%d")

        return Path(self.data_root) / biz / publish_date / article_id
