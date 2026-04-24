#!/usr/bin/env python3
"""
监控模块测试
Monitor Module Tests
"""

import os
import sys
import unittest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from monitor import WeChatMonitor, Article
from config import Config, WeChatAccount


class TestArticle(unittest.TestCase):
    """Article类测试"""

    def test_article_creation(self):
        """测试文章创建"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章标题',
            author='测试作者',
            content_url='https://mp.weixin.qq.com/s/test'
        )

        self.assertEqual(article.article_id, 'test_123')
        self.assertEqual(article.biz, 'biz_456')
        self.assertEqual(article.title, '测试文章标题')

    def test_article_hash_id(self):
        """测试文章哈希ID生成"""
        article = Article(
            article_id='test_123',
            biz='biz_456'
        )

        hash_id = article.hash_id

        # 验证哈希格式
        self.assertEqual(len(hash_id), 32)  # MD5哈希长度
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_id))

    def test_article_hash_id_uniqueness(self):
        """测试文章哈希ID唯一性"""
        article1 = Article(article_id='a1', biz='b1')
        article2 = Article(article_id='a1', biz='b2')
        article3 = Article(article_id='a2', biz='b1')

        # 不同组合应该产生不同的哈希
        self.assertNotEqual(article1.hash_id, article2.hash_id)
        self.assertNotEqual(article1.hash_id, article3.hash_id)

    def test_article_from_json(self):
        """测试从JSON创建文章"""
        data = {
            'id': 'article_123',
            'title': 'JSON测试文章',
            'author': 'JSON作者',
            'link': 'https://mp.weixin.qq.com/s/json_test',
            'pub_time': 1704067200,  # 2024-01-01 00:00:00
        }

        article = Article.from_json(data, 'biz_456')

        self.assertIsNotNone(article)
        self.assertEqual(article.article_id, 'article_123')
        self.assertEqual(article.title, 'JSON测试文章')
        self.assertEqual(article.biz, 'biz_456')
        self.assertEqual(article.publish_date, '2024-01-01')

    def test_article_to_dict(self):
        """测试文章转字典"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        data = article.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data['article_id'], 'test_123')
        self.assertEqual(data['biz'], 'biz_456')
        self.assertEqual(data['title'], '测试文章')


class TestWeChatMonitor(unittest.TestCase):
    """WeChatMonitor类测试"""

    def setUp(self):
        """测试前准备"""
        self.config = Config()
        self.config.accounts = [
            WeChatAccount(biz='test_biz_123', name='测试公众号')
        ]

    @patch('monitor.requests.Session')
    def test_monitor_init(self, mock_session):
        """测试监控器初始化"""
        mock_session.return_value = Mock()
        monitor = WeChatMonitor(self.config)

        self.assertIsNotNone(monitor.session)
        self.assertEqual(len(monitor.last_articles), 0)
        self.assertEqual(len(monitor.failure_count), 0)

    def test_get_random_user_agent(self):
        """测试随机User-Agent获取"""
        monitor = WeChatMonitor.__new__(WeChatMonitor)
        monitor.config = self.config
        monitor.session = Mock()

        user_agents = [monitor._get_random_user_agent() for _ in range(10)]

        # 验证所有UA都来自配置列表
        for ua in user_agents:
            self.assertIn(ua, self.config.user_agents)

    def test_get_random_delay(self):
        """测试随机延迟获取"""
        monitor = WeChatMonitor.__new__(WeChatMonitor)
        monitor.config = self.config
        monitor.session = Mock()

        delays = [monitor._get_random_delay() for _ in range(100)]

        # 验证延迟在指定范围内
        for delay in delays:
            self.assertGreaterEqual(delay, self.config.min_request_delay)
            self.assertLessEqual(delay, self.config.max_request_delay)

    @patch('monitor.requests.Session.get')
    def test_is_blocked_detection(self, mock_get):
        """测试反爬检测"""
        monitor = WeChatMonitor.__new__(WeChatMonitor)
        monitor.config = self.config
        monitor.session = Mock()

        # 测试正常响应
        response = Mock()
        response.status_code = 200
        response.text = '<html>正常页面</html>'
        self.assertFalse(monitor._is_blocked(response))

        # 测试被拦截
        response.text = '<html>请输入验证码</html>'
        self.assertTrue(monitor._is_blocked(response))

        # 测试非200状态码
        response.status_code = 403
        response.text = '<html>正常页面</html>'
        self.assertTrue(monitor._is_blocked(response))

    @patch('monitor.requests.Session')
    def test_parse_article_list_from_html(self, mock_session):
        """测试从HTML解析文章列表"""
        monitor = WeChatMonitor.__new__(WeChatMonitor)
        monitor.config = self.config
        monitor.session = Mock()

        # 模拟HTML内容
        html = '''
        <html>
        <script>
        var appmsgList = [
            {"id": "art1", "title": "文章1", "link": "https://mp.weixin.qq.com/s/a1"},
            {"id": "art2", "title": "文章2", "link": "https://mp.weixin.qq.com/s/a2"}
        ];
        </script>
        </html>
        '''

        account = WeChatAccount(biz='test_biz')
        articles = monitor._parse_article_list_from_html(html, account)

        # 验证解析结果
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].article_id, 'art1')
        self.assertEqual(articles[0].title, '文章1')

    @patch('monitor.requests.Session')
    def test_get_new_articles_first_run(self, mock_session):
        """测试首次运行获取新文章"""
        mock_session.return_value = Mock()

        monitor = WeChatMonitor(self.config)
        account = self.config.accounts[0]

        # 模拟文章列表
        mock_articles = [
            Article(
                article_id=f'art_{i}',
                biz=account.biz,
                title=f'测试文章{i}'
            )
            for i in range(5)
        ]

        with patch.object(monitor, 'fetch_article_list', return_value=mock_articles):
            new_articles = monitor.get_new_articles(account)

            # 首次运行应该返回所有文章
            self.assertEqual(len(new_articles), 5)

    @patch('monitor.requests.Session')
    def test_get_new_articles_incremental(self, mock_session):
        """测试增量获取新文章"""
        mock_session.return_value = Mock()

        monitor = WeChatMonitor(self.config)
        account = self.config.accounts[0]

        # 已有文章
        old_articles = [
            Article(article_id=f'art_{i}', biz=account.biz, title=f'旧文章{i}')
            for i in range(3)
        ]
        monitor.last_articles[account.biz] = old_articles

        # 新文章（包含1个新的）
        new_articles = old_articles + [
            Article(article_id='new_art', biz=account.biz, title='新文章')
        ]

        with patch.object(monitor, 'fetch_article_list', return_value=new_articles):
            result = monitor.get_new_articles(account)

            # 应该只返回1篇新文章
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].article_id, 'new_art')

    @patch('monitor.requests.Session')
    def test_check_all_accounts(self, mock_session):
        """测试检查所有公众号"""
        mock_session.return_value = Mock()

        # 配置多个公众号
        config = Config()
        config.accounts = [
            WeChatAccount(biz='biz1', name='公众号1'),
            WeChatAccount(biz='biz2', name='公众号2'),
        ]

        monitor = WeChatMonitor(config)

        # 模拟返回结果
        articles1 = [Article(article_id='a1', biz='biz1', title='文章1')]
        articles2 = [Article(article_id='a2', biz='biz2', title='文章2')]

        def mock_get_new(account, token=''):
            if account.biz == 'biz1':
                return articles1
            return articles2

        with patch.object(monitor, 'get_new_articles', side_effect=mock_get_new):
            results = monitor.check_all_accounts()

            self.assertIn('biz1', results)
            self.assertIn('biz2', results)


if __name__ == '__main__':
    unittest.main()
