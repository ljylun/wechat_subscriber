#!/usr/bin/env python3
"""
解析器模块测试
Parser Module Tests
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

from parser import ArticleParser, ParsedArticle, ReadabilityExtractor, HTMLCleaner
from downloader import DownloadedArticle, ResourceInfo
from monitor import Article
from config import Config


class TestParsedArticle(unittest.TestCase):
    """ParsedArticle类测试"""

    def test_parsed_article_creation(self):
        """测试解析结果创建"""
        article = ParsedArticle(
            title='测试文章标题',
            author='测试作者',
            publish_time='2024-01-15',
            content_text='这是文章正文内容',
            images=['https://example.com/img1.jpg'],
            videos=['https://example.com/video.mp4'],
            audios=['https://example.com/audio.mp3'],
        )

        self.assertEqual(article.title, '测试文章标题')
        self.assertEqual(article.author, '测试作者')
        self.assertEqual(len(article.images), 1)
        self.assertEqual(article.word_count, 0)  # 未设置

    def test_parsed_article_summary(self):
        """测试摘要生成"""
        article = ParsedArticle(
            title='测试',
            content_text='这是很长的文章内容，至少超过200个字符。' * 20
        )

        summary = article.summary

        self.assertTrue(len(summary) <= 210)  # 200 + "..."
        self.assertTrue(summary.endswith('...'))

    def test_parsed_article_to_dict(self):
        """测试转字典"""
        article = ParsedArticle(
            title='测试',
            author='作者',
            content_text='正文'
        )

        data = article.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data['title'], '测试')
        self.assertEqual(data['author'], '作者')
        self.assertIn('content_html', data)
        self.assertIn('images', data)

    def test_parsed_article_to_json(self):
        """测试转JSON"""
        article = ParsedArticle(
            title='测试',
            author='作者',
            content_text='正文'
        )

        json_str = article.to_json()

        self.assertIsInstance(json_str, str)
        data = json.loads(json_str)
        self.assertEqual(data['title'], '测试')


class TestHTMLCleaner(unittest.TestCase):
    """HTMLCleaner类测试"""

    def test_clean_allowed_tags(self):
        """测试保留允许的标签"""
        cleaner = HTMLCleaner()
        cleaner.feed('<p>这是段落</p><br><strong>粗体</strong>')
        result = cleaner.get_result()

        self.assertIn('<p>', result)
        self.assertIn('</p>', result)
        self.assertIn('<br>', result)
        self.assertIn('<strong>', result)

    def test_remove_blocked_tags(self):
        """测试移除禁止的标签"""
        cleaner = HTMLCleaner()
        cleaner.feed('<script>alert("xss")</script><p>正常内容</p>')
        result = cleaner.get_result()

        self.assertNotIn('alert', result)
        self.assertIn('<p>', result)

    def test_remove_noise_elements(self):
        """测试移除噪音元素"""
        cleaner = HTMLCleaner()
        cleaner.feed('<div class="qr_code">二维码</div><p>正文内容</p>')
        result = cleaner.get_result()

        self.assertNotIn('二维码', result)
        self.assertIn('正文内容', result)

    def test_handle_img_tag(self):
        """测试处理img标签"""
        cleaner = HTMLCleaner()
        cleaner.feed('<img src="https://example.com/image.jpg" alt="测试图片">')
        result = cleaner.get_result()

        self.assertIn('src="https://example.com/image.jpg"', result)

    def test_handle_entityref(self):
        """测试处理HTML实体"""
        cleaner = HTMLCleaner()
        cleaner.feed('&nbsp;&amp;&lt;&gt;')
        result = cleaner.get_result()

        self.assertIn(' ', result)  # &nbsp;
        self.assertIn('&', result)  # &amp;


class TestReadabilityExtractor(unittest.TestCase):
    """ReadabilityExtractor类测试"""

    def setUp(self):
        """测试前准备"""
        self.extractor = ReadabilityExtractor()

    def test_extract_content_with_beautifulsoup(self):
        """测试使用BeautifulSoup提取内容"""
        html = '''
        <html>
        <head><title>测试页面</title></head>
        <body>
            <nav>导航栏</nav>
            <article class="article-content">
                <h1>文章标题</h1>
                <p>这是第一段内容。</p>
                <p>这是第二段内容。</p>
                <p>这是第三段内容。</p>
            </article>
            <footer>页脚</footer>
        </body>
        </html>
        '''

        content_html, content_text = self.extractor.extract_content(html)

        self.assertIn('文章标题', content_html)
        self.assertIn('第一段', content_text)
        self.assertIn('第二段', content_text)
        self.assertNotIn('导航栏', content_text)
        self.assertNotIn('页脚', content_text)

    def test_extract_content_fallback(self):
        """测试降级提取方法"""
        # 没有BeautifulSoup时使用正则
        html = '''
        <div id="content">
            <p>这是段落内容。</p>
        </div>
        '''

        content_html, content_text = self.extractor._extract_with_regex(html)

        self.assertIn('段落内容', content_text)


class TestArticleParser(unittest.TestCase):
    """ArticleParser类测试"""

    def setUp(self):
        """测试前准备"""
        self.config = Config()
        self.temp_dir = tempfile.mkdtemp()
        self.config.data_root = self.temp_dir

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parser_init(self):
        """测试解析器初始化"""
        parser = ArticleParser(self.config)

        self.assertIsNotNone(parser.readability)
        self.assertIsNotNone(parser.config)
        self.assertIsNotNone(parser.title_pattern)
        self.assertIsNotNone(parser.author_patterns)

    def test_extract_title(self):
        """测试标题提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        # 测试从title标签提取
        html = '<title>测试标题 - 微信公众平台</title>'
        title = parser._extract_title(html)
        self.assertEqual(title, '测试标题')

        # 测试从h1标签提取
        html = '<html><body><h1>H1标题</h1></body></html>'
        title = parser._extract_title(html)
        self.assertEqual(title, 'H1标题')

    def test_extract_author(self):
        """测试作者提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        html = '<div class="author">测试作者</div>'
        author = parser._extract_author(html)
        self.assertEqual(author, '测试作者')

    def test_extract_time(self):
        """测试时间提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        # 测试标准日期格式
        html = '<span class="time">2024-01-15</span>'
        time_str = parser._extract_time(html)
        self.assertEqual(time_str, '2024-01-15')

        # 测试中文日期格式
        html = '<span>2024年1月15日</span>'
        time_str = parser._extract_time(html)
        self.assertEqual(time_str, '2024-1-15')

    def test_extract_images(self):
        """测试图片提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        html = '''
        <img src="https://example.com/img1.jpg">
        <img src="https://example.com/img2.png">
        <img src="data:image/png;base64,xxxxx">
        '''

        images = parser._extract_images(html)

        self.assertEqual(len(images), 2)  # 不包含data URI
        self.assertIn('https://example.com/img1.jpg', images)
        self.assertIn('https://example.com/img2.png', images)

    def test_extract_videos(self):
        """测试视频提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        html = '<video src="https://example.com/video.mp4"></video>'

        videos = parser._extract_videos(html)

        self.assertEqual(len(videos), 1)
        self.assertIn('https://example.com/video.mp4', videos)

    def test_extract_audios(self):
        """测试音频提取"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        html = '<audio src="https://example.com/audio.mp3"></audio>'

        audios = parser._extract_audios(html)

        self.assertEqual(len(audios), 1)
        self.assertIn('https://example.com/audio.mp3', audios)

    def test_clean_text(self):
        """测试文本清理"""
        parser = ArticleParser.__new__(ArticleParser)
        parser.config = self.config
        parser.logger = Mock()
        parser.readability = Mock()
        parser._compile_patterns()

        # 测试HTML实体解码
        text = '测试&nbsp;&amp;&lt;script&gt;'
        cleaned = parser._clean_text(text)

        self.assertEqual(cleaned, '测试 &<>script>')

    def test_parse_article(self):
        """测试完整文章解析"""
        parser = ArticleParser(self.config)

        # 创建测试HTML文件
        html_content = '''
        <!DOCTYPE html>
        <html>
        <head><title>测试文章</title></head>
        <body>
            <h1>测试文章标题</h1>
            <div class="author">测试作者</div>
            <article>
                <p>这是文章的第一段内容。</p>
                <p>这是文章的第二段内容。</p>
                <img src="https://example.com/image.jpg">
            </article>
        </body>
        </html>
        '''

        # 创建文章目录
        article_dir = Path(self.temp_dir) / 'biz123' / '2024-01-15' / 'art_456'
        article_dir.mkdir(parents=True, exist_ok=True)

        html_path = article_dir / 'index.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 创建下载结果
        article = Article(
            article_id='art_456',
            biz='biz123',
            title='测试文章',
            author='测试作者',
            publish_date='2024-01-15'
        )

        downloaded = DownloadedArticle(
            article=article,
            html_path=str(html_path),
            manifest={'title': '测试文章'},
            success=True
        )

        # 解析
        parsed = parser.parse_article(downloaded)

        # 验证结果
        self.assertIsNotNone(parsed)
        self.assertTrue(len(parsed.title) > 0)
        self.assertTrue(parsed.word_count > 0)


if __name__ == '__main__':
    unittest.main()
