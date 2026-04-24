#!/usr/bin/env python3
"""
微信公众号监控模块
WeChat Public Account Monitoring Module
"""

import re
import time
import random
import hashlib
import json
import logging
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config, WeChatAccount


@dataclass
class Article:
    """文章数据结构"""
    article_id: str  # 唯一标识 (sn)
    biz: str  # 公众号标识
    title: str
    author: str = ""
    digest: str = ""
    cover_url: str = ""
    content_url: str = ""
    source_url: str = ""
    publish_time: int = 0  # Unix时间戳
    publish_date: str = ""  # YYYY-MM-DD格式
    seq: int = 0  # 序号

    @property
    def hash_id(self) -> str:
        """生成文章唯一哈希"""
        return hashlib.md5(f"{self.biz}:{self.article_id}".encode()).hexdigest()

    @classmethod
    def from_json(cls, data: Dict, biz: str) -> Optional['Article']:
        """从JSON数据创建Article对象"""
        try:
            # 尝试多种可能的字段名
            aid = data.get('id') or data.get('aid') or data.get('sn') or ""

            # 解析时间戳
            pub_time = data.get('pub_time') or data.get('publish_time') or 0
            if isinstance(pub_time, str):
                try:
                    pub_time = int(pub_time)
                except:
                    pub_time = 0

            # 格式化日期
            if pub_time:
                publish_date = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d")
            else:
                publish_date = datetime.now().strftime("%Y-%m-%d")

            return cls(
                article_id=str(aid),
                biz=biz,
                title=data.get('title', '').strip(),
                author=data.get('author', '').strip(),
                digest=data.get('digest', '').strip(),
                cover_url=data.get('cover', '') or data.get('cover_url', ''),
                content_url=data.get('link', '') or data.get('content_url', ''),
                source_url=data.get('source_url', ''),
                publish_time=pub_time,
                publish_date=publish_date,
                seq=data.get('seq', 0) or 0,
            )
        except Exception as e:
            logging.error(f"解析文章数据失败: {e}, data={data}")
            return None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'article_id': self.article_id,
            'biz': self.biz,
            'title': self.title,
            'author': self.author,
            'digest': self.digest,
            'cover_url': self.cover_url,
            'content_url': self.content_url,
            'source_url': self.source_url,
            'publish_time': self.publish_time,
            'publish_date': self.publish_date,
            'seq': self.seq,
        }


class WeChatMonitor:
    """微信公众号监控器"""

    # 微信文章列表API
    LIST_API_TEMPLATE = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&begin={offset}&count={count}&fakeid={biz}&type=9&token={token}&lang=zh_CN&f=json&ajax=1"

    def __init__(self, config: Config):
        """
        初始化监控器

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()
        self.last_articles: Dict[str, List[Article]] = {}  # 缓存上次抓取的文章列表
        self.failure_count: Dict[str, int] = {}  # 失败计数

    def _create_session(self) -> requests.Session:
        """创建HTTP会话"""
        session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # 默认请求头
        session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })

        return session

    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(self.config.user_agents)

    def _get_random_delay(self) -> float:
        """获取随机延迟时间"""
        return random.uniform(
            self.config.min_request_delay,
            self.config.max_request_delay
        )

    def _get_proxy(self) -> Optional[Dict]:
        """获取代理"""
        if not self.config.proxy.enabled or not self.config.proxy.api_url:
            return None

        try:
            response = requests.get(self.config.proxy.api_url, timeout=10)
            if response.status_code == 200:
                proxy_data = response.json()
                return {
                    'http': proxy_data.get('http'),
                    'https': proxy_data.get('https'),
                }
        except Exception as e:
            self.logger.warning(f"获取代理失败: {e}")

        return None

    def _request_with_retry(
        self,
        url: str,
        account: WeChatAccount,
        **kwargs
    ) -> Optional[requests.Response]:
        """
        带重试的请求

        Args:
            url: 请求URL
            account: 公众号配置
            **kwargs: 其他请求参数

        Returns:
            Response对象或None
        """
        headers = kwargs.pop('headers', {})
        headers['User-Agent'] = self._get_random_user_agent()
        kwargs['headers'] = headers

        proxy = self._get_proxy()
        if proxy:
            kwargs['proxies'] = proxy

        attempt = 0
        delay = self.config.base_retry_delay

        while attempt < self.config.max_retries:
            try:
                response = self.session.get(url, timeout=30, **kwargs)

                # 检查是否被拦截
                if self._is_blocked(response):
                    self.logger.warning(f"检测到反爬拦截: {account.biz}")
                    attempt += 1
                    if attempt < self.config.max_retries:
                        time.sleep(delay)
                        delay = min(delay * 2, self.config.max_retry_delay)
                        continue

                return response

            except requests.RequestException as e:
                self.logger.error(f"请求失败 (尝试 {attempt + 1}/{self.config.max_retries}): {e}")
                attempt += 1
                if attempt < self.config.max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, self.config.max_retry_delay)

        return None

    def _is_blocked(self, response: requests.Response) -> bool:
        """检测是否被反爬拦截"""
        if response.status_code != 200:
            return True

        content = response.text.lower()

        # 检测常见的拦截特征
        block_patterns = [
            '验证页面',
            '请输入验证码',
            '系统繁忙',
            '操作太频繁',
            '调用频率超限',
        ]

        for pattern in block_patterns:
            if pattern in content:
                return True

        return False

    def _handle_js_redirect(self, url: str, account: WeChatAccount) -> Optional[str]:
        """
        处理微信JS重定向

        Args:
            url: 原始URL
            account: 公众号配置

        Returns:
            真实URL或None
        """
        try:
            headers = {'User-Agent': self._get_random_user_agent()}
            response = self.session.head(url, headers=headers, timeout=10, allow_redirects=False)

            if response.status_code in [301, 302]:
                return response.headers.get('Location', url)

            return url

        except Exception as e:
            self.logger.error(f"处理JS重定向失败: {e}")
            return url

    def fetch_article_list(
        self,
        account: WeChatAccount,
        token: str = "",
        count: int = 10,
        offset: int = 0
    ) -> List[Article]:
        """
        获取公众号文章列表

        Args:
            account: 公众号配置
            token: 访问令牌
            count: 每次获取数量
            offset: 偏移量

        Returns:
            文章列表
        """
        # 如果没有token，使用备用方法
        if not token:
            return self._fetch_article_list_alternative(account)

        url = self.LIST_API_TEMPLATE.format(
            offset=offset,
            count=count,
            biz=account.biz
        )

        params = {
            'token': token,
        }

        response = self._request_with_retry(url, account, params=params)

        if not response:
            self.logger.error(f"获取文章列表失败: {account.biz}")
            return []

        try:
            data = response.json()

            if data.get('app_msg_list'):
                articles = []
                for item in data['app_msg_list']:
                    article = Article.from_json(item, account.biz)
                    if article:
                        articles.append(article)

                return articles

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {account.biz}")

        return []

    def _fetch_article_list_alternative(self, account: WeChatAccount) -> List[Article]:
        """
        备用方法：通过搜索页面获取文章列表

        Args:
            account: 公众号配置

        Returns:
            文章列表
        """
        # 使用历史消息页面
        url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={account.biz}&scene=124&devicetype=android-23&version=2700043c&lang=zh_CN&nettype=WIFI&abtest_cookie=AAACAA%3D%3D&pass_ticket=5jM1L4R8x0p9q2r6v8n3m0k5s7t9u1w4e6=&wx_header=1"

        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        proxy = self._get_proxy()

        try:
            response = self.session.get(
                url,
                headers=headers,
                proxies=proxy,
                timeout=30
            )

            if response.status_code != 200:
                self.logger.error(f"页面请求失败: {response.status_code}")
                return []

            # 提取文章列表
            return self._parse_article_list_from_html(response.text, account)

        except Exception as e:
            self.logger.error(f"备用方法获取文章列表失败: {e}")
            return []

    def _parse_article_list_from_html(self, html: str, account: WeChatAccount) -> List[Article]:
        """
        从HTML中解析文章列表

        Args:
            html: HTML内容
            account: 公众号配置

        Returns:
            文章列表
        """
        articles = []

        # 尝试从script标签中提取JSON数据
        patterns = [
            r'var appmsgList\s*=\s*(\[.*?\]);',
            r'"app_msg_list"\s*:\s*(\[.*?\])',
            r'appmsg_content\s*=\s*\'([^\']+)\'',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    # 尝试解析为JSON
                    data = json.loads(match)
                    if isinstance(data, list):
                        for item in data:
                            article = Article.from_json(item, account.biz)
                            if article:
                                articles.append(article)
                        if articles:
                            return articles
                except json.JSONDecodeError:
                    continue

        # 尝试从URL提取
        url_pattern = r'href="(https?://mp\.weixin\.qq\.com/s/[^"]+)"[^>]*>\s*([^<]+)'
        urls = re.findall(url_pattern, html)

        for url, title in urls:
            # 提取文章ID
            aid_match = re.search(r'/s/([a-zA-Z0-9_-]+)', url)
            if aid_match:
                article = Article(
                    article_id=aid_match.group(1),
                    biz=account.biz,
                    title=title.strip(),
                    content_url=url,
                )
                articles.append(article)

        return articles

    def get_new_articles(
        self,
        account: WeChatAccount,
        token: str = ""
    ) -> List[Article]:
        """
        获取新增文章

        Args:
            account: 公众号配置
            token: 访问令牌

        Returns:
            新增文章列表
        """
        # 获取当前文章列表
        current_articles = []

        # 尝试分页获取
        offset = 0
        while True:
            batch = self.fetch_article_list(
                account,
                token=token,
                count=10,
                offset=offset
            )

            if not batch:
                break

            current_articles.extend(batch)
            offset += 10

            # 限制最大数量
            if len(current_articles) >= 50:
                break

            # 添加延迟
            time.sleep(self._get_random_delay())

        if not current_articles:
            self.logger.warning(f"未获取到文章: {account.biz}")
            return []

        # 与上次结果对比
        last_articles = self.last_articles.get(account.biz, [])

        if not last_articles:
            # 首次运行，返回所有文章（假设都是新的）
            self.logger.info(f"首次运行，返回全部 {len(current_articles)} 篇文章")
            self.last_articles[account.biz] = current_articles
            return current_articles

        # 构建已存在文章的哈希集合
        existing_hashes = {a.hash_id for a in last_articles}

        # 找出新增文章
        new_articles = [
            a for a in current_articles
            if a.hash_id not in existing_hashes
        ]

        # 更新缓存
        self.last_articles[account.biz] = current_articles

        if new_articles:
            self.logger.info(f"发现 {len(new_articles)} 篇新文章: {account.biz}")
            # 重置失败计数
            self.failure_count[account.biz] = 0
        else:
            self.logger.debug(f"未发现新文章: {account.biz}")

        return new_articles

    def check_all_accounts(self, tokens: Dict[str, str] = None) -> Dict[str, List[Article]]:
        """
        检查所有配置的公众号

        Args:
            tokens: 公众号token映射

        Returns:
            每个公众号的新增文章字典
        """
        results = {}

        for account in self.config.accounts:
            try:
                token = tokens.get(account.biz, "") if tokens else ""
                new_articles = self.get_new_articles(account, token)

                if new_articles:
                    results[account.biz] = new_articles

            except Exception as e:
                self.logger.error(f"检查公众号失败 {account.biz}: {e}")

                # 增加失败计数
                self.failure_count[account.biz] = self.failure_count.get(account.biz, 0) + 1

                # 连续3次失败触发告警
                if self.failure_count[account.biz] >= 3:
                    self.logger.critical(
                        f"公众号 {account.biz} 连续 {self.failure_count[account.biz]} 次失败，触发告警"
                    )

            # 每次请求后添加随机延迟
            time.sleep(self._get_random_delay())

        return results

    def get_account_info(self, biz: str) -> Optional[Dict]:
        """
        获取公众号信息

        Args:
            biz: 公众号biz标识

        Returns:
            公众号信息字典
        """
        url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}"

        headers = {'User-Agent': self._get_random_user_agent()}

        try:
            response = self.session.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                # 提取公众号名称
                name_match = re.search(r'"nick_name"\s*:\s*"([^"]+)"', response.text)
                if name_match:
                    return {'nick_name': name_match.group(1)}

        except Exception as e:
            self.logger.error(f"获取公众号信息失败: {e}")

        return None
