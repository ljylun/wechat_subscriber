#!/usr/bin/env python3
"""
下载器模块测试
Downloader Module Tests
"""

import os
import sys
import unittest
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from downloader import ArticleDownloader, ResourceInfo, DownloadedArticle
from monitor import Article
from config import Config


class TestResourceInfo(unittest.TestCase):
    """ResourceInfo类测试"""

    def test_resource_info_creation(self):
        """测试资源信息创建"""
        resource = ResourceInfo(
            original_url='https://example.com/image.jpg',
            local_path='images/image_abc123.jpg',
            resource_type='image',
            file_size=1024,
            mime_type='image/jpeg'
        )

        self.assertEqual(resource.original_url, 'https://example.com/image.jpg')
        self.assertEqual(resource.resource_type, 'image')
        self.assertEqual(resource.file_size, 1024)


class TestArticleDownloader(unittest.TestCase):
    """ArticleDownloader类测试"""

    def setUp(self):
        """测试前准备"""
        self.config = Config()
        self.config.data_root = tempfile.mkdtemp()

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.config.data_root, ignore_errors=True)

    @patch('downloader.requests.Session')
    def test_downloader_init(self, mock_session):
        """测试下载器初始化"""
        mock_session.return_value = Mock()
        downloader = ArticleDownloader(self.config)

        self.assertIsNotNone(downloader.session)
        self.assertEqual(len(downloader.downloaded_resources), 0)

    def test_get_file_extension(self):
        """测试文件扩展名获取"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()

        # 测试各种URL
        self.assertEqual(downloader._get_file_extension('https://example.com/image.jpg'), '.jpg')
        self.assertEqual(downloader._get_file_extension('https://example.com/image.png'), '.png')
        self.assertEqual(downloader._get_file_extension('https://example.com/video.mp4'), '.mp4')
        self.assertEqual(downloader._get_file_extension('https://example.com/audio.mp3'), '.mp3')

    def test_generate_resource_filename(self):
        """测试资源文件名生成"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()

        filename = downloader._generate_resource_filename(
            'https://example.com/image.jpg',
            'image'
        )

        # 验证格式
        self.assertTrue(filename.startswith('image_'))
        self.assertTrue(filename.endswith('.jpg'))
        self.assertEqual(len(filename.split('_')[1].split('.')[0]), 12)  # 12位哈希

    def test_extract_resources(self):
        """测试资源URL提取"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()

        html = '''
        <html>
        <body>
            <img src="https://example.com/image1.jpg">
            <img data-src="https://example.com/image2.png">
            <video src="https://example.com/video.mp4"></video>
            <audio src="https://example.com/audio.mp3"></audio>
            <div style="background-image: url('https://example.com/bg.jpg')"></div>
        </body>
        </html>
        '''

        resources = downloader.extract_resources(html)

        self.assertEqual(len(resources['images']), 3)  # 2个src + 1个data-src
        self.assertIn('https://example.com/image1.jpg', resources['images'])
        self.assertIn('https://example.com/image2.png', resources['images'])

        self.assertEqual(len(resources['videos']), 1)
        self.assertIn('https://example.com/video.mp4', resources['videos'])

        self.assertEqual(len(resources['audios']), 1)
        self.assertIn('https://example.com/audio.mp3', resources['audios'])

    def test_ensure_directory(self):
        """测试目录创建"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()

        test_path = Path(self.config.data_root) / 'test' / 'nested' / 'dir'
        downloader._ensure_directory(test_path)

        self.assertTrue(test_path.exists())
        self.assertTrue(test_path.is_dir())

    @patch('downloader.requests.Session.get')
    @patch('downloader.requests.Session.head')
    def test_download_file(self, mock_head, mock_get):
        """测试文件下载"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()

        # 模拟响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Length': '100'}
        mock_response.iter_content = Mock(return_value=[b'test content'])
        mock_get.return_value = mock_response

        # 模拟HEAD请求
        mock_head_response = Mock()
        mock_head_response.headers = {'Content-Type': 'image/jpeg'}
        mock_head.return_value = mock_head_response

        save_path = Path(self.config.data_root) / 'test.jpg'
        success, error = downloader._download_file(
            'https://example.com/image.jpg',
            save_path,
            'image'
        )

        self.assertTrue(success)
        self.assertEqual(error, '')
        self.assertTrue(save_path.exists())

    def test_is_duplicate(self):
        """测试重复检查"""
        downloader = ArticleDownloader.__new__(ArticleDownloader)
        downloader.config = self.config
        downloader.session = Mock()
        downloader.config.enable_dedup = True

        article = Article(
            article_id='test_123',
            biz='biz_456',
            publish_date='2024-01-15'
        )

        # 不存在的文章
        self.assertFalse(downloader.is_duplicate(article))

        # 创建文章目录和manifest
        article_path = self.config.get_storage_path(
            article.biz, article.article_id, article.publish_date
        )
        article_path.mkdir(parents=True, exist_ok=True)

        manifest = {
            'title': '测试文章',
            'article_id': article.article_id,
            'biz': article.biz,
        }

        with open(article_path / 'manifest.json', 'w', encoding='utf-8') as f:
            json.dump(manifest, f)

        # 现在应该检测为重复
        self.assertTrue(downloader.is_duplicate(article))


class TestDownloadedArticle(unittest.TestCase):
    """DownloadedArticle类测试"""

    def test_downloaded_article_creation(self):
        """测试下载结果创建"""
        article = Article(
            article_id='test_123',
            biz='biz_456',
            title='测试文章'
        )

        result = DownloadedArticle(
            article=article,
            html_path='/data/test.html',
            manifest={'title': '测试文章'},
            success=True
        )

        self.assertEqual(result.article.article_id, 'test_123')
        self.assertTrue(result.success)
        self.assertEqual(len(result.resources), 0)


if __name__ == '__main__':
    unittest.main()
