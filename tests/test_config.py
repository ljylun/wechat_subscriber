#!/usr/bin/env python3
"""
配置模块测试
Configuration Module Tests
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import Config, WeChatAccount, ProxyConfig, NotificationConfig


class TestConfig(unittest.TestCase):
    """配置类测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.yaml')

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config(self):
        """测试默认配置"""
        config = Config()

        self.assertEqual(config.poll_interval, 300)
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.data_root, '/data')
        self.assertIsInstance(config.accounts, list)
        self.assertEqual(len(config.user_agents), 3)

    def test_wechat_account_creation(self):
        """测试公众号账户创建"""
        account = WeChatAccount(biz='test_biz_123', name='测试公众号')

        self.assertEqual(account.biz, 'test_biz_123')
        self.assertEqual(account.name, '测试公众号')
        self.assertEqual(account.alias, '')

    def test_proxy_config(self):
        """测试代理配置"""
        proxy = ProxyConfig(
            enabled=True,
            api_url='http://proxy.example.com/api',
            min_delay=1.0,
            max_delay=3.0
        )

        self.assertTrue(proxy.enabled)
        self.assertEqual(proxy.api_url, 'http://proxy.example.com/api')

    def test_notification_config(self):
        """测试通知配置"""
        notification = NotificationConfig(
            webhook_url='https://qyapi.weixin.qq.com/webhook/send',
            enabled=True
        )

        self.assertTrue(notification.enabled)
        self.assertIn('qyapi.weixin.qq.com', notification.webhook_url)

    def test_from_yaml(self):
        """测试从YAML加载配置"""
        yaml_content = """
accounts:
  - biz: biz123
    name: 测试公众号1
  - biz: biz456
    name: 测试公众号2
    alias: 测试

poll_interval: 600
data_root: /tmp/data
log_level: DEBUG

proxy:
  enabled: true
  api_url: http://proxy.example.com

notification:
  enabled: true
  webhook_url: https://example.com/webhook

anti_crawl:
  user_agents:
    - Mozilla/5.0 Test1
    - Mozilla/5.0 Test2
  min_delay: 1.0
  max_delay: 5.0

retry:
  max_retries: 5
  base_delay: 30
  max_delay: 600
"""

        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        config = Config.from_yaml(self.config_path)

        self.assertEqual(len(config.accounts), 2)
        self.assertEqual(config.accounts[0].biz, 'biz123')
        self.assertEqual(config.accounts[1].alias, '测试')
        self.assertEqual(config.poll_interval, 600)
        self.assertTrue(config.proxy.enabled)
        self.assertTrue(config.notification.enabled)
        self.assertEqual(config.max_retries, 5)

    def test_to_yaml(self):
        """测试保存配置到YAML"""
        config = Config()
        config.accounts = [
            WeChatAccount(biz='test_biz', name='测试')
        ]
        config.poll_interval = 600

        config.to_yaml(self.config_path)

        # 验证文件存在
        self.assertTrue(os.path.exists(self.config_path))

        # 重新加载验证
        loaded = Config.from_yaml(self.config_path)
        self.assertEqual(len(loaded.accounts), 1)
        self.assertEqual(loaded.poll_interval, 600)

    def test_validate(self):
        """测试配置验证"""
        config = Config()
        config.data_root = self.temp_dir

        # 无公众号配置
        errors = config.validate()
        self.assertIn('至少需要配置一个公众号', errors)

        # 添加公众号
        config.accounts = [WeChatAccount(biz='test_biz')]
        errors = config.validate()
        self.assertEqual(len(errors), 0)

    def test_get_storage_path(self):
        """测试存储路径生成"""
        config = Config()
        config.data_root = '/data'

        path = config.get_storage_path('biz123', 'article456', '2024-01-15')

        self.assertEqual(
            str(path),
            '/data/biz123/2024-01-15/article456'
        )

    def test_get_storage_path_default_date(self):
        """测试存储路径生成（默认日期）"""
        config = Config()
        config.data_root = '/data'

        path = config.get_storage_path('biz123', 'article456')

        # 应该使用当前日期
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        expected = f'/data/biz123/{today}/article456'

        self.assertEqual(str(path), expected)


if __name__ == '__main__':
    unittest.main()
