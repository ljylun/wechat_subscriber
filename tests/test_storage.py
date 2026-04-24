#!/usr/bin/env python3
"""
存储模块测试
Storage Module Tests
"""

import os
import sys
import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storage import ArticleStorage, ArticleRecord
from monitor import Article
from config import Config


class TestArticleRecord(unittest.TestCase):
    """ArticleRecord类测试"""

    def test_record_creation(self):
        """测试记录创建"""
        record = ArticleRecord(
            id=1,
            biz='biz_123',
            article_id='art_456',
            sn='hash_789',
            title='测试文章',
            author='测试作者',
            status='parsed'
        )

        self.assertEqual(record.id, 1)
        self.assertEqual(record.biz, 'biz_123')
        self.assertEqual(record.status, 'parsed')

    def test_record_to_dict(self):
        """测试记录转字典"""
        record = ArticleRecord(
            biz='biz_123',
            article_id='art_456',
            title='测试'
        )

        data = record.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data['biz'], 'biz_123')
        self.assertEqual(data['article_id'], 'art_456')


class TestArticleStorage(unittest.TestCase):
    """ArticleStorage类测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.config = Config()
        self.config.db_path = os.path.join(self.temp_dir, 'test.db')
        self.storage = ArticleStorage(self.config)

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_storage_init(self):
        """测试存储初始化"""
        self.assertTrue(os.path.exists(self.config.db_path))

    def test_add_article(self):
        """测试添加文章"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章',
            author='测试作者'
        )

        result = self.storage.add_article(article)
        self.assertTrue(result)

    def test_add_duplicate_article(self):
        """测试添加重复文章"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        # 第一次添加
        self.assertTrue(self.storage.add_article(article))

        # 第二次添加应该返回False
        self.assertFalse(self.storage.add_article(article))

    def test_is_duplicate(self):
        """测试重复检查"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        # 添加前
        self.assertFalse(self.storage.is_duplicate(article))

        # 添加后
        self.storage.add_article(article)
        self.assertTrue(self.storage.is_duplicate(article))

    def test_get_article(self):
        """测试获取文章"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章',
            author='测试作者'
        )

        self.storage.add_article(article)

        # 获取文章
        record = self.storage.get_article('biz_456', 'test_123')

        self.assertIsNotNone(record)
        self.assertEqual(record.biz, 'biz_456')
        self.assertEqual(record.article_id, 'test_123')
        self.assertEqual(record.title, '测试文章')

    def test_get_nonexistent_article(self):
        """测试获取不存在的文章"""
        record = self.storage.get_article('biz_999', 'art_999')
        self.assertIsNone(record)

    def test_update_article(self):
        """测试更新文章"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        self.storage.add_article(article)

        # 更新状态
        result = self.storage.update_article(
            'biz_456',
            'test_123',
            status='parsed',
            local_path='/data/biz_456/test_123'
        )

        self.assertTrue(result)

        # 验证更新
        record = self.storage.get_article('biz_456', 'test_123')
        self.assertEqual(record.status, 'parsed')
        self.assertEqual(record.local_path, '/data/biz_456/test_123')

    def test_update_with_error(self):
        """测试更新错误信息"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        self.storage.add_article(article)

        result = self.storage.update_article(
            'biz_456',
            'test_123',
            status='failed',
            error_message='下载失败'
        )

        self.assertTrue(result)

        record = self.storage.get_article('biz_456', 'test_123')
        self.assertEqual(record.status, 'failed')
        self.assertEqual(record.error_message, '下载失败')

    def test_get_pending_articles(self):
        """测试获取待处理文章"""
        # 添加多个文章
        for i in range(5):
            article = Article(
                article_id=f'test_{i}',
                biz='biz_456',
                title=f'测试文章{i}'
            )
            self.storage.add_article(article)

        # 更新部分状态
        self.storage.update_article('biz_456', 'test_0', status='downloaded')
        self.storage.update_article('biz_456', 'test_1', status='parsed')

        # 获取待处理
        pending = self.storage.get_pending_articles()

        # 应该有3篇待处理
        self.assertEqual(len(pending), 3)

    def test_get_articles_by_biz(self):
        """测试获取指定公众号的文章"""
        # 添加不同公众号的文章
        biz1_articles = [
            Article(article_id=f'art_{i}', biz='biz_1', title=f'文章{i}')
            for i in range(3)
        ]
        biz2_articles = [
            Article(article_id=f'art_{i}', biz='biz_2', title=f'文章{i}')
            for i in range(2)
        ]

        for article in biz1_articles + biz2_articles:
            self.storage.add_article(article)

        # 获取biz_1的文章
        articles = self.storage.get_articles_by_biz('biz_1')
        self.assertEqual(len(articles), 3)

        # 获取biz_2的文章
        articles = self.storage.get_articles_by_biz('biz_2')
        self.assertEqual(len(articles), 2)

    def test_add_history(self):
        """测试添加历史记录"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        self.storage.add_article(article)

        # 获取文章ID
        record = self.storage.get_article('biz_456', 'test_123')
        self.assertIsNotNone(record)

        # 添加历史
        result = self.storage.add_history(
            record.id,
            'downloaded',
            {'size': 1024}
        )

        self.assertTrue(result)

    def test_get_statistics(self):
        """测试获取统计信息"""
        # 添加各种状态的文章
        articles = [
            Article(article_id=f'test_{i}', biz='biz_1', title=f'文章{i}')
            for i in range(5)
        ]

        for i, article in enumerate(articles):
            self.storage.add_article(article)

            # 设置不同状态
            if i < 2:
                self.storage.update_article('biz_1', f'test_{i}', status='downloaded')
            elif i < 3:
                self.storage.update_article('biz_1', f'test_{i}', status='parsed')

        stats = self.storage.get_statistics()

        self.assertIn('total', stats)
        self.assertEqual(stats['total'], 5)

        self.assertIn('by_status', stats)
        self.assertIn('downloaded', stats['by_status'])
        self.assertEqual(stats['by_status']['downloaded'], 2)

        self.assertIn('by_biz', stats)
        self.assertEqual(stats['by_biz']['biz_1'], 5)

    def test_cleanup_old_records(self):
        """测试清理旧记录"""
        # 添加一些文章
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        self.storage.add_article(article)
        self.storage.update_article('biz_456', 'test_123', status='parsed')

        # 清理7天前的记录（不会有任何删除）
        deleted = self.storage.cleanup_old_records(7)
        self.assertEqual(deleted, 0)


if __name__ == '__main__':
    unittest.main()
