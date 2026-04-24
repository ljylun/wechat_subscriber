#!/usr/bin/env python3
"""
微信公众号订阅系统主程序
Main Entry Point for WeChat Public Account Subscriber
"""

import os
import sys
import time
import signal
import logging
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json

from .config import Config, WeChatAccount
from .monitor import WeChatMonitor, Article
from .downloader import ArticleDownloader
from .parser import ArticleParser, ParsedArticle
from .notifier import NotificationService, setup_logger
from .storage import ArticleStorage
from .logger import setup_logger


class WeChatSubscriber:
    """微信公众号订阅系统主类"""

    def __init__(self, config: Config):
        """
        初始化订阅系统

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = setup_logger(config)
        self.running = False
        self.pause_event = threading.Event()
        self.pause_event.set()

        # 初始化组件
        self.monitor = WeChatMonitor(config)
        self.downloader = ArticleDownloader(config)
        self.parser = ArticleParser(config)
        self.notifier = NotificationService(config)
        self.storage = ArticleStorage(config)

        # 设置信号处理
        self._setup_signal_handlers()

        self.logger.info("微信公众号订阅系统初始化完成")

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """处理终止信号"""
        self.logger.info(f"收到信号 {signum}，准备停止...")
        self.stop()

    def start(self) -> None:
        """启动订阅系统"""
        if self.running:
            self.logger.warning("系统已在运行中")
            return

        self.running = True
        self.pause_event.set()
        self.logger.info("微信公众号订阅系统已启动")

        try:
            while self.running:
                self.pause_event.wait()  # 等待恢复信号

                if not self.running:
                    break

                self._run_cycle()

                if self.running:
                    self.logger.debug(f"等待 {self.config.poll_interval} 秒后进行下一次轮询...")
                    self._wait_with_pause(self.config.poll_interval)

        except Exception as e:
            self.logger.error(f"系统运行异常: {e}", exc_info=True)

        finally:
            self.logger.info("微信公众号订阅系统已停止")

    def stop(self) -> None:
        """停止订阅系统"""
        self.logger.info("正在停止系统...")
        self.running = False
        self.pause_event.set()  # 确保循环退出

    def pause(self) -> None:
        """暂停订阅系统"""
        if self.running:
            self.logger.info("系统已暂停")
            self.pause_event.clear()

    def resume(self) -> None:
        """恢复订阅系统"""
        if self.running:
            self.logger.info("系统已恢复")
            self.pause_event.set()

    def _wait_with_pause(self, seconds: int) -> None:
        """带暂停检查的等待"""
        interval = 1  # 每秒检查一次
        waited = 0

        while waited < seconds and self.running:
            self.pause_event.wait(timeout=interval)
            if not self.pause_event.is_set():
                # 处于暂停状态，等待恢复
                self.pause_event.wait()  # 阻塞直到被set
            waited += interval

    def _run_cycle(self) -> None:
        """运行一次监控周期"""
        cycle_start = time.time()

        try:
            self.logger.info("开始检查公众号更新...")

            # 1. 检查所有公众号的新文章
            new_articles = self.monitor.check_all_accounts()

            if not new_articles:
                self.logger.info("本次检查未发现新文章")
                return

            # 2. 处理新文章
            total_new = sum(len(articles) for articles in new_articles.values())
            self.logger.info(f"发现 {total_new} 篇新文章")

            all_parsed = []

            for biz, articles in new_articles.items():
                for article in articles:
                    try:
                        # 检查重复
                        if self.storage.is_duplicate(article):
                            self.logger.debug(f"文章已存在，跳过: {article.title}")
                            continue

                        # 添加到存储
                        self.storage.add_article(article)

                        # 下载文章
                        self.logger.info(f"下载文章: {article.title[:30]}...")
                        downloaded = self.downloader.download_article(article)

                        if not downloaded.success:
                            self.storage.update_article(
                                biz, article.article_id,
                                status='failed',
                                error_message=downloaded.error
                            )
                            continue

                        # 解析文章
                        self.logger.info(f"解析文章: {article.title[:30]}...")
                        parsed = self.parser.parse_article(downloaded)

                        if parsed.title:
                            # 更新存储状态
                            local_path = str(Path(downloaded.html_path).parent)
                            self.storage.update_article(
                                biz, article.article_id,
                                status='parsed',
                                local_path=local_path
                            )

                            all_parsed.append(parsed)

                            # 发送通知
                            self.notifier.send_wechat_notification(parsed)

                    except Exception as e:
                        self.logger.error(f"处理文章失败: {article.title[:30]}... 错误: {e}")
                        self.storage.update_article(
                            biz, article.article_id,
                            status='failed',
                            error_message=str(e)
                        )

            # 3. 批量发送通知
            if all_parsed:
                self.logger.info(f"成功处理 {len(all_parsed)} 篇文章")

            # 4. 记录统计
            duration = time.time() - cycle_start
            self.logger.info(f"本次周期完成，耗时: {duration:.2f}秒")

        except Exception as e:
            self.logger.error(f"执行周期失败: {e}", exc_info=True)

    def process_single_article(self, biz: str, article_id: str) -> Optional[ParsedArticle]:
        """
        处理单篇文章

        Args:
            biz: 公众号标识
            article_id: 文章ID

        Returns:
            解析后的文章或None
        """
        # 查找文章记录
        record = self.storage.get_article(biz, article_id)
        if not record:
            self.logger.error(f"文章记录不存在: {biz}/{article_id}")
            return None

        # 查找HTML文件
        local_path = Path(record.local_path)
        html_path = local_path / 'index.html'

        if not html_path.exists():
            self.logger.error(f"HTML文件不存在: {html_path}")
            return None

        # 重新解析
        from .downloader import DownloadedArticle, ResourceInfo
        from .monitor import Article

        # 构建下载结果
        manifest_path = local_path / 'manifest.json'
        manifest = {}
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

        downloaded = DownloadedArticle(
            article=Article(
                article_id=article_id,
                biz=biz,
                title=record.title,
                content_url=record.content_url,
            ),
            html_path=str(html_path),
            manifest=manifest,
            success=True,
        )

        return self.parser.parse_article(downloaded)

    def get_status(self) -> Dict:
        """
        获取系统状态

        Returns:
            状态信息字典
        """
        stats = self.storage.get_statistics()

        return {
            'running': self.running,
            'paused': not self.pause_event.is_set() if self.running else None,
            'poll_interval': self.config.poll_interval,
            'accounts_count': len(self.config.accounts),
            'statistics': stats,
        }

    def force_check(self) -> Dict[str, List[Article]]:
        """
        强制检查所有公众号

        Returns:
            新文章字典
        """
        return self.monitor.check_all_accounts()


class SubscriberManager:
    """订阅系统管理器（用于多实例控制）"""

    PID_FILE = '/var/run/wechat_subscriber.pid'

    @classmethod
    def write_pid(cls, pid: int = None) -> None:
        """写入PID文件"""
        if pid is None:
            pid = os.getpid()

        pid_path = Path(cls.PID_FILE)
        pid_path.parent.mkdir(parents=True, exist_ok=True)

        with open(pid_path, 'w') as f:
            f.write(str(pid))

    @classmethod
    def read_pid(cls) -> Optional[int]:
        """读取PID文件"""
        pid_path = Path(cls.PID_FILE)

        if not pid_path.exists():
            return None

        try:
            with open(pid_path, 'r') as f:
                return int(f.read().strip())
        except:
            return None

    @classmethod
    def is_running(cls) -> bool:
        """检查是否正在运行"""
        pid = cls.read_pid()

        if pid is None:
            return False

        try:
            # 检查进程是否存在
            os.kill(pid, 0)
            return True
        except OSError:
            # 进程不存在，删除PID文件
            cls.cleanup()
            return False

    @classmethod
    def cleanup(cls) -> None:
        """清理PID文件"""
        pid_path = Path(cls.PID_FILE)
        if pid_path.exists():
            pid_path.unlink()

    @classmethod
    def start_daemon(cls, config_path: str) -> bool:
        """启动守护进程"""
        if cls.is_running():
            print("系统已在运行中")
            return False

        pid = os.fork()
        if pid != 0:
            # 父进程
            return True

        # 子进程
        try:
            # 启动新会话
            os.setsid()

            # 加载配置
            config = Config.from_yaml(config_path)

            # 创建订阅系统
            subscriber = WeChatSubscriber(config)

            # 写入PID
            cls.write_pid()

            # 启动
            subscriber.start()

        except Exception as e:
            print(f"启动失败: {e}")
            sys.exit(1)

        return True

    @classmethod
    def stop_daemon(cls) -> bool:
        """停止守护进程"""
        pid = cls.read_pid()

        if pid is None:
            print("系统未运行")
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            print(f"已发送停止信号到进程 {pid}")
            return True
        except OSError as e:
            print(f"停止失败: {e}")
            cls.cleanup()
            return False

    @classmethod
    def get_status(cls) -> Dict:
        """获取守护进程状态"""
        pid = cls.read_pid()
        running = cls.is_running() if pid else False

        status = {
            'running': running,
            'pid': pid,
        }

        if running:
            try:
                # 获取进程信息
                import psutil
                process = psutil.Process(pid)
                status['uptime'] = (datetime.now() - datetime.fromtimestamp(
                    process.create_time()
                )).total_seconds()
                status['cpu_percent'] = process.cpu_percent()
                status['memory_mb'] = process.memory_info().rss / 1024 / 1024
            except ImportError:
                pass

        return status


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description='微信公众号文章自动订阅系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--config', '-c',
        default='/etc/wechat_subscriber/config.yaml',
        help='配置文件路径 (默认: /etc/wechat_subscriber/config.yaml)'
    )

    parser.add_argument(
        'command',
        choices=['start', 'stop', 'status', 'run', 'check'],
        help='命令: start(启动守护进程), stop(停止), status(状态), run(前台运行), check(单次检查)'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='后台运行模式'
    )

    args = parser.parse_args()

    # 检查配置文件
    if not Path(args.config).exists():
        print(f"配置文件不存在: {args.config}")
        sys.exit(1)

    # 加载配置
    try:
        config = Config.from_yaml(args.config)
        errors = config.validate()
        if errors:
            print("配置验证失败:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
    except Exception as e:
        print(f"加载配置失败: {e}")
        sys.exit(1)

    # 执行命令
    if args.command == 'start':
        if SubscriberManager.start_daemon(args.config):
            if args.daemon:
                print("系统已在后台启动")
            else:
                print("启动中...")
        else:
            sys.exit(1)

    elif args.command == 'stop':
        SubscriberManager.stop_daemon()

    elif args.command == 'status':
        status = SubscriberManager.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

    elif args.command == 'run':
        subscriber = WeChatSubscriber(config)
        subscriber.start()

    elif args.command == 'check':
        monitor = WeChatMonitor(config)
        results = monitor.check_all_accounts()

        total = sum(len(articles) for articles in results.values())
        print(f"发现 {total} 篇新文章")

        for biz, articles in results.items():
            print(f"\n{biz}:")
            for article in articles:
                print(f"  - {article.title}")


if __name__ == '__main__':
    main()
