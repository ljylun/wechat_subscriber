#!/usr/bin/env python3
"""
内容解析与结构化提取模块
Content Parsing and Structured Extraction Module
"""

import re
import json
import hashlib
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from html.entities import name2codepoint
import unicodedata

from .config import Config
from .monitor import Article
from .downloader import DownloadedArticle


@dataclass
class ParsedArticle:
    """解析后的文章数据结构"""
    # 基本信息
    title: str = ""
    author: str = ""
    publish_time: str = ""
    publish_date: str = ""

    # 内容
    content_html: str = ""
    content_text: str = ""

    # 资源列表
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    audios: List[str] = field(default_factory=list)

    # 元信息
    original_url: str = ""
    local_path: str = ""
    digest: str = ""
    word_count: int = 0

    # 资源映射 (URL -> 本地路径)
    resource_map: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @property
    def summary(self) -> str:
        """生成摘要"""
        text = self.content_text[:200]
        if len(self.content_text) > 200:
            text += "..."
        return text.replace('\n', ' ').strip()


class HTMLCleaner(HTMLParser):
    """HTML清理器"""

    # 需保留的标签
    ALLOWED_TAGS = {
        'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'dl', 'dt', 'dd',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'blockquote', 'pre', 'code',
        'strong', 'b', 'em', 'i', 'u', 's', 'del',
        'a', 'img', 'figure', 'figcaption',
        'section', 'article', 'div', 'span',
        'video', 'audio', 'source',
    }

    # 需移除的标签
    REMOVE_TAGS = {
        'script', 'style', 'noscript', 'iframe', 'form',
        'input', 'button', 'select', 'textarea',
        'nav', 'footer', 'header', 'aside',
    }

    # 噪音元素选择器
    NOISE_SELECTORS = [
        '.qr_code', '#qr_code', '.qrcode',
        '.advertisement', '.ad', '#ad', '.ads',
        '.share', '.share-btn', '.share-box',
        '.comment', '#comment', '.comments',
        '.reward', '#reward',
        '.tool-bar', '.toolbar',
        '.popover', '.modal',
        '[class*="qr"]', '[class*="code"]',
        '[class*="advert"]', '[class*="ad-"]',
        '[id*="qr"]', '[id*="code"]',
        '[id*="advert"]', '[id*="ad-"]',
        '.js_feed', '.js_content',
        '#js_content',
    ]

    def __init__(self):
        super().__init__()
        self.result = []
        self.tag_stack = []
        self.skip_depth = 0
        self.current_attrs = {}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if self.skip_depth > 0:
            return

        # 检查是否需要跳过
        if tag in self.REMOVE_TAGS:
            self.skip_depth += 1
            return

        # 检查噪音元素
        for attr_name, attr_value in attrs:
            if attr_name == 'class' or attr_name == 'id':
                for selector in self.NOISE_SELECTORS:
                    selector_tag = selector.split('.')[0].split('#')[0]
                    if selector_tag == tag or selector_tag == '':
                        selector_class = selector.split('.')[1] if '.' in selector else ''
                        selector_id = selector.split('#')[1] if '#' in selector else ''

                        if selector_class and selector_class in (attr_value or '').lower():
                            self.skip_depth += 1
                            return
                        if selector_id and selector_id in (attr_value or '').lower():
                            self.skip_depth += 1
                            return

        # 处理允许的标签
        if tag in self.ALLOWED_TAGS:
            self.result.append(f'<{tag}>')
            self.tag_stack.append(tag)

        # 处理特殊标签
        elif tag == 'img':
            # 提取src属性
            src = dict(attrs).get('src', '')
            data_src = dict(attrs).get('data-src', '')
            src = src or data_src

            if src:
                self.result.append(f'<img src="{src}">')

        elif tag == 'a':
            href = dict(attrs).get('href', '')
            self.result.append(f'<a href="{href}">')
            self.tag_stack.append('a')

        elif tag == 'br':
            self.result.append('<br>')

    def handle_endtag(self, tag):
        tag = tag.lower()

        if self.skip_depth > 0:
            if tag in self.REMOVE_TAGS:
                self.skip_depth -= 1
            return

        if tag in self.ALLOWED_TAGS and self.tag_stack and self.tag_stack[-1] == tag:
            self.result.append(f'</{tag}>')
            self.tag_stack.pop()

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.result.append(data)

    def handle_entityref(self, name):
        if self.skip_depth == 0:
            c = chr(name2codepoint[name])
            self.result.append(c)

    def handle_charref(self, name):
        if self.skip_depth == 0:
            c = chr(int(name))
            self.result.append(c)

    def get_result(self) -> str:
        """获取清理后的HTML"""
        return ''.join(self.result)


class ReadabilityExtractor:
    """Readability算法实现"""

    # 内容质量评分权重
    CLASS_WEIGHTS = {
        'article': 25,
        'main': 25,
        'content': 25,
        'post': 20,
        'entry': 20,
        'hentry': 15,
        'story': 15,
        'post-content': 30,
        'article-content': 30,
        'entry-content': 30,
        'post-body': 25,
        'article-body': 25,
    }

    # 负面权重
    NEGATIVE_CLASSES = [
        'comment', 'comments', 'meta', 'footer', 'footnote',
        'sidebar', 'widget', 'ad', 'ads', 'advertisement',
        'social', 'share', 'related', 'outbrain', 'tab',
    ]

    # 标签权重
    TAG_WEIGHTS = {
        'article': 20,
        'section': 5,
        'div': -5,
    }

    def __init__(self):
        pass

    def calculate_content_score(self, element) -> float:
        """计算元素内容得分"""
        score = 0

        # 基于class评分
        class_name = element.get('class', [])
        if isinstance(class_name, str):
            class_name = class_name.split()

        for cls in class_name:
            cls_lower = cls.lower()
            if cls_lower in self.CLASS_WEIGHTS:
                score += self.CLASS_WEIGHTS[cls_lower]

            for neg in self.NEGATIVE_CLASSES:
                if neg in cls_lower:
                    score -= 25

        # 基于标签评分
        tag = element.name.lower() if hasattr(element, 'name') else ''
        if tag in self.TAG_WEIGHTS:
            score += self.TAG_WEIGHTS[tag]

        # 基于段落数量评分
        paragraphs = element.find_all('p') if hasattr(element, 'find_all') else []
        score += min(len(paragraphs) * 3, 15)

        # 基于文本长度评分
        text = element.get_text() if hasattr(element, 'get_text') else ''
        text_length = len(text.strip())

        if text_length > 100:
            score += min(text_length / 100, 10)

        return score

    def extract_content(self, html: str) -> Tuple[str, str]:
        """
        提取主要内容

        Args:
            html: HTML内容

        Returns:
            (content_html, content_text)
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
        except ImportError:
            # 如果没有BeautifulSoup，使用正则提取
            return self._extract_with_regex(html)

        # 移除噪音元素
        for selector in HTMLCleaner.NOISE_SELECTORS:
            for element in soup.select(selector):
                element.decompose()

        # 查找主要内容容器
        candidates = []

        # 方法1: 查找文章标签
        for tag in ['article', 'main', '[class*="article"]', '[class*="content"]']:
            try:
                elements = soup.select(tag)
                for elem in elements:
                    score = self.calculate_content_score(elem)
                    if score > 0:
                        candidates.append((score, elem))
            except:
                pass

        # 方法2: 查找包含多个段落的div
        for div in soup.find_all('div'):
            paragraphs = div.find_all('p')
            if len(paragraphs) >= 3:
                score = self.calculate_content_score(div)
                if score > 0:
                    candidates.append((score, div))

        # 选择得分最高的
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0][1]

            # 提取内容
            content_html = self._extract_article_content(best)
        else:
            # 降级方案：提取body
            body = soup.find('body')
            if body:
                content_html = str(body)
            else:
                content_html = html

        # 清理HTML
        cleaner = HTMLCleaner()
        cleaner.feed(content_html)
        content_html = cleaner.get_result()

        # 转换为纯文本
        content_text = self._html_to_text(content_html)

        return content_html, content_text

    def _extract_article_content(self, element) -> str:
        """提取文章内容"""
        # 克隆元素，避免修改原始HTML
        try:
            content = element.__copy__()
        except:
            content = element

        # 移除脚本和样式
        for tag in content.find_all(['script', 'style', 'noscript']) if hasattr(content, 'find_all') else []:
            tag.decompose()

        return str(content)

    def _html_to_text(self, html: str) -> str:
        """HTML转纯文本"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # 移除所有标签，保留文本
            text = soup.get_text(separator='\n', strip=True)

            # 规范化空白字符
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)

            return text.strip()

        except ImportError:
            # 降级方案：使用正则
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s{2,}', ' ', text)
            return text.strip()

    def _extract_with_regex(self, html: str) -> Tuple[str, str]:
        """使用正则表达式提取内容（降级方案）"""
        # 提取正文区域
        patterns = [
            r'<div[^>]*id=["\']?["\']?content["\']?["\']?[^>]*>(.*?)</div>',
            r'<div[^>]*class=["\']?["\']?(?:article_content|post_content|entry-content)[^>]*>(.*?)</div>',
            r'<article[^>]*>(.*?)</article>',
        ]

        content_html = html
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                content_html = match.group(1)
                break

        # 清理HTML
        cleaner = HTMLCleaner()
        cleaner.feed(content_html)
        content_html = cleaner.get_result()

        # 转换为纯文本
        content_text = re.sub(r'<[^>]+>', ' ', content_html)
        content_text = re.sub(r'\s{2,}', ' ', content_text)

        return content_html, content_text.strip()


class ArticleParser:
    """文章解析器"""

    def __init__(self, config: Config):
        """
        初始化解析器

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.readability = ReadabilityExtractor()

        # 编译常用正则
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """编译常用正则表达式"""
        # 标题提取
        self.title_pattern = re.compile(
            r'<h1[^>]*>(.*?)</h1>',
            re.DOTALL | re.IGNORECASE
        )

        # 作者提取
        self.author_patterns = [
            re.compile(r'class=["\']?author["\']?[^>]*>(.*?)</[^>]+>', re.DOTALL | re.IGNORECASE),
            re.compile(r'class=["\']?name["\']?[^>]*>(.*?)</[^>]+>', re.DOTALL | re.IGNORECASE),
            re.compile(r'data-author=["\'](.*?)["\']', re.IGNORECASE),
        ]

        # 时间提取
        self.time_patterns = [
            re.compile(r'class=["\']?time["\']?[^>]*>(\d{4}-\d{2}-\d{2})', re.IGNORECASE),
            re.compile(r'date=["\']?(\d{4}-\d{2}-\d{2})', re.IGNORECASE),
            re.compile(r'(\d{4}年\d{1,2}月\d{1,2}日)', re.IGNORECASE),
        ]

        # 图片URL提取
        self.img_pattern = re.compile(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
            re.IGNORECASE
        )

        # 视频URL提取
        self.video_pattern = re.compile(
            r'<video[^>]+src=["\']([^"\']+)["\']',
            re.IGNORECASE
        )

        # 音频URL提取
        self.audio_pattern = re.compile(
            r'<audio[^>]+src=["\']([^"\']+)["\']',
            re.IGNORECASE
        )

    def parse_article(self, downloaded: DownloadedArticle) -> ParsedArticle:
        """
        解析文章

        Args:
            downloaded: 下载结果

        Returns:
            解析后的文章对象
        """
        result = ParsedArticle()
        article = downloaded.article

        # 读取HTML内容
        html_path = downloaded.html_path
        if not html_path or not Path(html_path).exists():
            self.logger.error(f"HTML文件不存在: {html_path}")
            return result

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # 提取基本信息
        result.title = self._extract_title(html) or article.title
        result.author = self._extract_author(html) or article.author
        result.publish_time = self._extract_time(html) or article.publish_date
        result.publish_date = article.publish_date
        result.original_url = article.content_url
        result.digest = article.digest

        # 使用Readability提取正文
        content_html, content_text = self.readability.extract_content(html)
        result.content_html = content_html
        result.content_text = content_text
        result.word_count = len(content_text)

        # 提取资源URL
        result.images = self._extract_images(content_html)
        result.videos = self._extract_videos(content_html)
        result.audios = self._extract_audios(content_html)

        # 构建资源映射
        for resource in downloaded.resources:
            result.resource_map[resource.original_url] = resource.local_path

        # 替换HTML中的图片路径为本地路径
        result.content_html = self._replace_resource_paths(result)

        # 保存到manifest
        manifest = downloaded.manifest.copy()
        manifest['parsed'] = result.to_dict()
        manifest['parse_time'] = datetime.now().isoformat()

        manifest_path = Path(html_path).parent / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        self.logger.info(f"文章解析完成: {result.title[:30]}... "
                        f"字数: {result.word_count}, 图片: {len(result.images)}")

        return result

    def _extract_title(self, html: str) -> str:
        """提取标题"""
        # 尝试从title标签提取
        title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            # 移除微信公众号名称后缀
            title = re.sub(r'[-_]\s*微信公众平台$', '', title)
            title = re.sub(r'\s*-\s*微信.*$', '', title)
            return title

        # 尝试从h1标签提取
        h1_match = self.title_pattern.search(html)
        if h1_match:
            return self._clean_text(h1_match.group(1))

        return ""

    def _extract_author(self, html: str) -> str:
        """提取作者"""
        for pattern in self.author_patterns:
            match = pattern.search(html)
            if match:
                author = self._clean_text(match.group(1))
                if author:
                    return author

        return ""

    def _extract_time(self, html: str) -> str:
        """提取发布时间"""
        for pattern in self.time_patterns:
            match = pattern.search(html)
            if match:
                time_str = match.group(1)
                # 转换为标准格式
                time_str = time_str.replace('年', '-').replace('月', '-').replace('日', '')
                return time_str

        return ""

    def _extract_images(self, html: str) -> List[str]:
        """提取图片URL"""
        images = []

        # 从HTML提取
        for match in self.img_pattern.finditer(html):
            url = match.group(1)
            if url and not url.startswith('data:'):
                images.append(url)

        # 去重
        return list(dict.fromkeys(images))

    def _extract_videos(self, html: str) -> List[str]:
        """提取视频URL"""
        videos = []

        for match in self.video_pattern.finditer(html):
            url = match.group(1)
            if url:
                videos.append(url)

        return list(dict.fromkeys(videos))

    def _extract_audios(self, html: str) -> List[str]:
        """提取音频URL"""
        audios = []

        for match in self.audio_pattern.finditer(html):
            url = match.group(1)
            if url:
                audios.append(url)

        return list(dict.fromkeys(audios))

    def _replace_resource_paths(self, result: ParsedArticle) -> str:
        """替换HTML中的资源路径为本地路径"""
        content_html = result.content_html

        # 替换图片路径
        for original_url, local_path in result.resource_map.items():
            if original_url in content_html:
                content_html = content_html.replace(
                    original_url,
                    f"images/{Path(local_path).name}"
                )

        return content_html

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)

        # 解码HTML实体
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # 规范化空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def parse_articles(self, downloaded_list: List[DownloadedArticle]) -> List[ParsedArticle]:
        """
        批量解析文章

        Args:
            downloaded_list: 下载结果列表

        Returns:
            解析结果列表
        """
        results = []

        for downloaded in downloaded_list:
            if downloaded.success:
                parsed = self.parse_article(downloaded)
                results.append(parsed)

        return results
