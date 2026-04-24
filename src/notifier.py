#!/usr/bin/env python3
"""
通知与日志模块
Notification and Logging Module
"""

import re
import smtplib
import json
import logging
import logging.handlers
from typing import List, Dict, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import Config
from .parser import ParsedArticle
from .monitor import Article


@dataclass
class NotificationMessage:
    """通知消息"""
    title: str
    summary: str
    author: str
    publish_time: str
    original_url: str
    local_path: str
    word_count: int
    image_count: int


class NotificationService:
    """通知服务"""

    def __init__(self, config: Config):
        """
        初始化通知服务

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    def _build_message(self, article: ParsedArticle) -> NotificationMessage:
        """构建通知消息"""
        return NotificationMessage(
            title=article.title,
            summary=article.summary,
            author=article.author,
            publish_time=article.publish_time or article.publish_date,
            original_url=article.original_url,
            local_path=article.local_path,
            word_count=article.word_count,
            image_count=len(article.images),
        )

    def _format_wechat_message(self, msg: NotificationMessage) -> Dict:
        """格式化企业微信消息"""
        content = f"""📢 新文章发布提醒

**标题**: {msg.title}
**作者**: {msg.author}
**时间**: {msg.publish_time}
**字数**: {msg.word_count}
**图片**: {msg.image_count}张

**摘要**:
{msg.summary}

🔗 原文链接: {msg.original_url}
📁 本地路径: {msg.local_path}"""

        return {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }

    def _format_email_message(self, msg: NotificationMessage) -> Dict:
        """格式化邮件消息"""
        html = f"""
        <html>
        <body>
        <h2>📢 新文章发布提醒</h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">标题</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{msg.title}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">作者</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{msg.author}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">时间</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{msg.publish_time}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">字数</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{msg.word_count}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">图片</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{msg.image_count}张</td>
            </tr>
        </table>
        <h3>摘要</h3>
        <p>{msg.summary}</p>
        <p>🔗 原文链接: <a href="{msg.original_url}">{msg.original_url}</a></p>
        <p>📁 本地路径: {msg.local_path}</p>
        </body>
        </html>
        """
        return {
            "subject": f"【新文章】{msg.title}",
            "html": html,
            "text": f"{msg.title}\n\n{msg.summary}\n\n链接: {msg.original_url}",
        }

    def send_wechat_notification(self, article: ParsedArticle) -> bool:
        """
        发送企业微信通知

        Args:
            article: 解析后的文章

        Returns:
            是否发送成功
        """
        if not self.config.notification.enabled:
            self.logger.debug("通知未启用")
            return False

        webhook_url = self.config.notification.webhook_url
        if not webhook_url:
            self.logger.warning("企业微信Webhook URL未配置")
            return False

        try:
            msg = self._build_message(article)
            payload = self._format_wechat_message(msg)

            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    self.logger.info(f"企业微信通知发送成功: {article.title[:30]}")
                    return True
                else:
                    self.logger.error(f"企业微信通知发送失败: {result.get('errmsg')}")
            else:
                self.logger.error(f"企业微信通知HTTP错误: {response.status_code}")

        except Exception as e:
            self.logger.error(f"发送企业微信通知异常: {e}")

        return False

    def send_email_notification(
        self,
        article: ParsedArticle,
        to_addr: str,
        from_addr: str = "",
        smtp_server: str = "",
        smtp_port: int = 587,
        username: str = "",
        password: str = ""
    ) -> bool:
        """
        发送邮件通知

        Args:
            article: 解析后的文章
            to_addr: 收件人地址
            from_addr: 发件人地址
            smtp_server: SMTP服务器
            smtp_port: SMTP端口
            username: 用户名
            password: 密码

        Returns:
            是否发送成功
        """
        if not all([from_addr, smtp_server, username, password]):
            self.logger.warning("邮件配置不完整")
            return False

        try:
            msg = self._build_message(article)
            email_content = self._format_email_message(msg)

            # 创建邮件
            message = MIMEMultipart('alternative')
            message['Subject'] = email_content['subject']
            message['From'] = from_addr
            message['To'] = to_addr

            # 添加纯文本和HTML版本
            message.attach(MIMEText(email_content['text'], 'plain', 'utf-8'))
            message.attach(MIMEText(email_content['html'], 'html', 'utf-8'))

            # 发送邮件
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(message)

            self.logger.info(f"邮件通知发送成功: {article.title[:30]}")
            return True

        except Exception as e:
            self.logger.error(f"发送邮件通知异常: {e}")
            return False

    def send_notifications(self, articles: List[ParsedArticle]) -> Dict[str, int]:
        """
        批量发送通知

        Args:
            articles: 文章列表

        Returns:
            发送结果统计
        """
        results = {
            'total': len(articles),
            'wechat_success': 0,
            'wechat_failed': 0,
            'email_success': 0,
            'email_failed': 0,
        }

        for article in articles:
            if self.send_wechat_notification(article):
                results['wechat_success'] += 1
            else:
                results['wechat_failed'] += 1

        return results


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, config: Config):
        """
        初始化日志记录器

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger('wechat_subscriber')
        self._setup_logger()

    def _setup_logger(self) -> None:
        """设置日志记录器"""
        # 清除现有处理器
        self.logger.handlers.clear()

        # 设置日志级别
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        self.logger.setLevel(level)

        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 文件处理器（带轮转）
        if self.config.log_file:
            try:
                log_path = Path(self.config.log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)

                file_handler = logging.handlers.TimedRotatingFileHandler(
                    self.config.log_file,
                    when='midnight',
                    interval=1,
                    backupCount=self.config.log_retention_days,
                    encoding='utf-8'
                )
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.warning(f"无法创建日志文件: {e}")

    def log_structured(
        self,
        level: str,
        biz: str,
        article_id: str,
        message: str,
        duration: float = 0,
        error: str = None,
        extra: Dict = None
    ) -> None:
        """
        记录结构化日志

        Args:
            level: 日志级别
            biz: 公众号标识
            article_id: 文章ID
            message: 日志消息
            duration: 耗时（秒）
            error: 错误信息
            extra: 额外数据
        """
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'biz': biz,
            'article_id': article_id,
            'message': message,
        }

        if duration > 0:
            log_data['duration'] = round(duration, 3)

        if error:
            log_data['error'] = error

        if extra:
            log_data.update(extra)

        log_message = json.dumps(log_data, ensure_ascii=False)

        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(log_level, log_message)

    def info(self, biz: str, article_id: str, message: str, **kwargs) -> None:
        """记录INFO级别日志"""
        self.log_structured('INFO', biz, article_id, message, **kwargs)

    def warning(self, biz: str, article_id: str, message: str, **kwargs) -> None:
        """记录WARNING级别日志"""
        self.log_structured('WARNING', biz, article_id, message, **kwargs)

    def error(self, biz: str, article_id: str, message: str, **kwargs) -> None:
        """记录ERROR级别日志"""
        self.log_structured('ERROR', biz, article_id, message, **kwargs)

    def critical(self, biz: str, article_id: str, message: str, **kwargs) -> None:
        """记录CRITICAL级别日志"""
        self.log_structured('CRITICAL', biz, article_id, message, **kwargs)


def setup_logger(config: Config) -> StructuredLogger:
    """
    设置日志记录器

    Args:
        config: 配置对象

    Returns:
        StructuredLogger实例
    """
    return StructuredLogger(config)
