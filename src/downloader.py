#!/usr/bin/env python3
"""
文章下载与存储模块
Article Download and Storage Module
"""

import os
import re
import json
import time
import random
import hashlib
import logging
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urlparse, unquote
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config
from .monitor import Article


@dataclass
class ResourceInfo:
    """资源信息"""
    original_url: str
    local_path: str
    resource_type: str  # image, video, audio, other
    file_size: int = 0
    mime_type: str = ""


@dataclass
class DownloadedArticle:
    """下载完成的文章"""
    article: Article
    html_path: str
    manifest: Dict
    resources: List[ResourceInfo] = field(default_factory=list)
    success: bool = False
    error: str = ""


class ArticleDownloader:
    """文章下载器"""

    # 资源URL模式
    IMAGE_PATTERNS = [
        r'src=["\']([^"\']*\.(?:jpg|jpeg|png|gif|webp|bmp)[^"\']*)["\']',
        r'data-src=["\']([^"\']*\.(?:jpg|jpeg|png|gif|webp|bmp)[^"\']*)["\']',
        r'background-image:\s*url\(["\']?([^"\'()]+)["\']?\)',
    ]

    VIDEO_PATTERNS = [
        r'<video[^>]+src=["\']([^"\']+)["\']',
        r'<source[^>]+src=["\']([^"\']+)["\']',
        r'"video_url"\s*:\s*"([^"]+)"',
    ]

    AUDIO_PATTERNS = [
        r'<audio[^>]+src=["\']([^"\']+)["\']',
        r'"voice_url"\s*:\s*"([^"]+)"',
    ]

    def __init__(self, config: Config):
        """
        初始化下载器

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()
        self.downloaded_resources: Set[str] = set()  # 记录已下载的资源URL

    def _create_session(self) -> requests.Session:
        """创建HTTP会话"""
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
        })

        return session

    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(self.config.user_agents)

    def _get_random_delay(self) -> float:
        """获取随机延迟时间"""
        return random.uniform(0.5, 2.0)

    def _get_file_extension(self, url: str) -> str:
        """从URL获取文件扩展名"""
        parsed = urlparse(url)
        path = unquote(parsed.path)

        # 尝试从路径获取
        ext = os.path.splitext(path)[1].lower()
        if ext and ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.mp4', '.mp3', '.wav']:
            return ext

        # 尝试从查询参数获取
        query_ext = parsed.query.get('ext', '')
        if query_ext:
            return f".{query_ext}"

        # 默认扩展名
        content_type = self._get_content_type(url)
        mime_to_ext = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'video/mp4': '.mp4',
            'audio/mpeg': '.mp3',
            'audio/wav': '.wav',
        }

        return mime_to_ext.get(content_type, '.bin')

    def _get_content_type(self, url: str) -> str:
        """获取资源MIME类型"""
        try:
            head_response = self.session.head(
                url,
                headers={'User-Agent': self._get_random_user_agent()},
                timeout=10,
                allow_redirects=True
            )
            return head_response.headers.get('Content-Type', '').split(';')[0].strip()
        except:
            return ''

    def _generate_resource_filename(self, url: str, resource_type: str) -> str:
        """生成资源文件名"""
        # 使用URL的哈希作为文件名，避免特殊字符问题
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        ext = self._get_file_extension(url)
        return f"{resource_type}_{url_hash}{ext}"

    def _ensure_directory(self, path: Path) -> None:
        """确保目录存在"""
        path.mkdir(parents=True, exist_ok=True)

    def _download_file(
        self,
        url: str,
        save_path: Path,
        resource_type: str = "other"
    ) -> Tuple[bool, str]:
        """
        下载文件

        Args:
            url: 资源URL
            save_path: 保存路径
            resource_type: 资源类型

        Returns:
            (成功标志, 错误信息)
        """
        if not url or url in self.downloaded_resources:
            return False, "URL为空或已下载"

        try:
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Referer': 'https://mp.weixin.qq.com/',
            }

            response = self.session.get(url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()

            # 检查文件大小
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > 100 * 1024 * 1024:  # 100MB限制
                return False, "文件过大"

            # 保存文件
            self._ensure_directory(save_path.parent)

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.downloaded_resources.add(url)
            return True, ""

        except Exception as e:
            self.logger.error(f"下载失败 {url}: {e}")
            return False, str(e)

    def _convert_to_jpg(self, image_path: Path) -> bool:
        """
        将WebP等格式转换为JPG

        Args:
            image_path: 图片路径

        Returns:
            转换是否成功
        """
        if image_path.suffix.lower() != '.webp':
            return True

        try:
            from PIL import Image

            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            new_path = image_path.with_suffix('.jpg')
            img.save(new_path, 'JPEG', quality=85)

            # 删除原文件
            image_path.unlink()
            return True

        except ImportError:
            self.logger.warning("Pillow未安装，无法转换图片格式")
            return True
        except Exception as e:
            self.logger.error(f"图片转换失败: {e}")
            return False

    def extract_resources(self, html: str) -> Dict[str, List[str]]:
        """
        从HTML中提取资源URL

        Args:
            html: HTML内容

        Returns:
            分类的资源URL字典
        """
        resources = {
            'images': [],
            'videos': [],
            'audios': [],
        }

        # 提取图片
        for pattern in self.IMAGE_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            resources['images'].extend(matches)

        # 提取视频
        for pattern in self.VIDEO_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            resources['videos'].extend(matches)

        # 提取音频
        for pattern in self.AUDIO_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            resources['audios'].extend(matches)

        # 去重
        for key in resources:
            resources[key] = list(set(resources[key]))

        return resources

    def download_article(self, article: Article) -> DownloadedArticle:
        """
        下载文章

        Args:
            article: 文章对象

        Returns:
            下载结果
        """
        start_time = time.time()
        result = DownloadedArticle(
            article=article,
            html_path="",
            manifest={},
            success=False,
        )

        # 生成存储路径
        storage_path = self.config.get_storage_path(
            article.biz,
            article.article_id,
            article.publish_date
        )

        try:
            self._ensure_directory(storage_path)

            # 下载文章页面
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml',
            }

            response = self.session.get(
                article.content_url,
                headers=headers,
                timeout=60
            )
            response.encoding = 'utf-8'
            html = response.text

            # 保存HTML
            html_path = storage_path / 'index.html'
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)

            result.html_path = str(html_path)

            # 提取并下载资源
            resources = self.extract_resources(html)

            # 下载图片
            images_dir = storage_path / 'images'
            self._ensure_directory(images_dir)

            for img_url in resources['images']:
                if not img_url or img_url.startswith('data:'):
                    continue

                filename = self._generate_resource_filename(img_url, 'img')
                img_path = images_dir / filename

                success, error = self._download_file(img_url, img_path, 'image')
                if success:
                    resource_info = ResourceInfo(
                        original_url=img_url,
                        local_path=str(img_path.relative_to(storage_path)),
                        resource_type='image',
                        file_size=img_path.stat().st_size if img_path.exists() else 0,
                    )
                    result.resources.append(resource_info)

                    # 转换WebP为JPG
                    if img_path.suffix.lower() == '.webp':
                        self._convert_to_jpg(img_path)
                        # 更新路径
                        resource_info.local_path = str(img_path.with_suffix('.jpg').relative_to(storage_path))
                else:
                    self.logger.warning(f"图片下载失败: {img_url}, 错误: {error}")

            # 下载视频
            videos_dir = storage_path / 'videos'
            self._ensure_directory(videos_dir)

            for video_url in resources['videos']:
                if not video_url:
                    continue

                filename = self._generate_resource_filename(video_url, 'video')
                video_path = videos_dir / filename

                success, error = self._download_file(video_url, video_path, 'video')
                if success:
                    resource_info = ResourceInfo(
                        original_url=video_url,
                        local_path=str(video_path.relative_to(storage_path)),
                        resource_type='video',
                        file_size=video_path.stat().st_size if video_path.exists() else 0,
                    )
                    result.resources.append(resource_info)

            # 下载音频
            audios_dir = storage_path / 'audios'
            self._ensure_directory(audios_dir)

            for audio_url in resources['audios']:
                if not audio_url:
                    continue

                filename = self._generate_resource_filename(audio_url, 'audio')
                audio_path = audios_dir / filename

                success, error = self._download_file(audio_url, audio_path, 'audio')
                if success:
                    resource_info = ResourceInfo(
                        original_url=audio_url,
                        local_path=str(audio_path.relative_to(storage_path)),
                        resource_type='audio',
                        file_size=audio_path.stat().st_size if audio_path.exists() else 0,
                    )
                    result.resources.append(resource_info)

            # 生成manifest
            result.manifest = {
                'title': article.title,
                'author': article.author,
                'publish_time': article.publish_time,
                'publish_date': article.publish_date,
                'original_url': article.content_url,
                'article_id': article.article_id,
                'biz': article.biz,
                'digest': article.digest,
                'cover_url': article.cover_url,
                'resources': [
                    {
                        'type': r.resource_type,
                        'original_url': r.original_url,
                        'local_path': r.local_path,
                        'file_size': r.file_size,
                    }
                    for r in result.resources
                ],
                'download_time': datetime.now().isoformat(),
                'download_duration': time.time() - start_time,
            }

            manifest_path = storage_path / 'manifest.json'
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(result.manifest, f, ensure_ascii=False, indent=2)

            result.success = True
            self.logger.info(
                f"文章下载完成: {article.title[:30]}... "
                f"资源: {len(result.resources)}个, 耗时: {time.time() - start_time:.2f}秒"
            )

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"下载文章失败: {article.title[:30]}... 错误: {e}")

        return result

    def download_articles(self, articles: List[Article]) -> List[DownloadedArticle]:
        """
        批量下载文章

        Args:
            articles: 文章列表

        Returns:
            下载结果列表
        """
        results = []

        for article in articles:
            result = self.download_article(article)
            results.append(result)

            # 下载完成后添加延迟，避免请求过快
            time.sleep(self._get_random_delay())

        return results

    def is_duplicate(self, article: Article) -> bool:
        """
        检查文章是否已下载（通过去重表）

        Args:
            article: 文章对象

        Returns:
            是否重复
        """
        if not self.config.enable_dedup:
            return False

        # 检查本地文件是否存在
        storage_path = self.config.get_storage_path(
            article.biz,
            article.article_id,
            article.publish_date
        )

        if storage_path.exists():
            manifest_path = storage_path / 'manifest.json'
            if manifest_path.exists():
                return True

        return False

    def mark_downloaded(self, article: Article) -> None:
        """
        标记文章已下载

        Args:
            article: 文章对象
        """
        storage_path = self.config.get_storage_path(
            article.biz,
            article.article_id,
            article.publish_date
        )

        if storage_path.exists():
            manifest_path = storage_path / 'manifest.json'
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    manifest['downloaded'] = True
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    self.logger.error(f"更新manifest失败: {e}")
