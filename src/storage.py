#!/usr/bin/env python3
"""
存储与去重模块
Storage and Deduplication Module
"""

import sqlite3
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

from .config import Config
from .monitor import Article


@dataclass
class ArticleRecord:
    """文章记录"""
    id: int = 0
    biz: str = ""
    article_id: str = ""
    sn: str = ""  # 唯一标识
    title: str = ""
    author: str = ""
    publish_time: int = 0
    publish_date: str = ""
    content_url: str = ""
    local_path: str = ""
    status: str = "pending"  # pending, downloaded, parsed, failed
    created_at: str = ""
    updated_at: str = ""
    error_message: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class ArticleStorage:
    """文章存储管理"""

    # 建表SQL
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        biz TEXT NOT NULL,
        article_id TEXT NOT NULL,
        sn TEXT UNIQUE NOT NULL,
        title TEXT,
        author TEXT,
        publish_time INTEGER DEFAULT 0,
        publish_date TEXT,
        content_url TEXT,
        local_path TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error_message TEXT,
        UNIQUE(biz, article_id)
    );

    CREATE INDEX IF NOT EXISTS idx_articles_biz ON articles(biz);
    CREATE INDEX IF NOT EXISTS idx_articles_sn ON articles(sn);
    CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
    CREATE INDEX IF NOT EXISTS idx_articles_publish_time ON articles(publish_time);
    """

    # 历史记录表
    CREATE_HISTORY_SQL = """
    CREATE TABLE IF NOT EXISTS article_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (article_id) REFERENCES articles(id)
    );

    CREATE INDEX IF NOT EXISTS idx_history_article_id ON article_history(article_id);
    CREATE INDEX IF NOT EXISTS idx_history_created_at ON article_history(created_at);
    """

    def __init__(self, config: Config):
        """
        初始化存储

        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.db_path = config.db_path
        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库"""
        # 确保目录存在
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # 创建连接
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建表
        cursor.executescript(self.CREATE_TABLE_SQL)
        cursor.executescript(self.CREATE_HISTORY_SQL)

        conn.commit()
        conn.close()

        self.logger.info(f"数据库初始化完成: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_record(self, row: sqlite3.Row) -> ArticleRecord:
        """行转换为记录"""
        return ArticleRecord(
            id=row['id'],
            biz=row['biz'],
            article_id=row['article_id'],
            sn=row['sn'],
            title=row['title'],
            author=row['author'],
            publish_time=row['publish_time'],
            publish_date=row['publish_date'],
            content_url=row['content_url'],
            local_path=row['local_path'],
            status=row['status'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            error_message=row['error_message'],
        )

    def add_article(self, article: Article) -> bool:
        """
        添加文章记录

        Args:
            article: 文章对象

        Returns:
            是否添加成功
        """
        now = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO articles (
                    biz, article_id, sn, title, author, publish_time,
                    publish_date, content_url, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (
                article.biz,
                article.article_id,
                article.hash_id,
                article.title,
                article.author,
                article.publish_time,
                article.publish_date,
                article.content_url,
                now,
                now,
            ))

            conn.commit()

            if cursor.rowcount > 0:
                self.logger.debug(f"文章记录添加成功: {article.hash_id}")
                return True
            else:
                self.logger.debug(f"文章记录已存在: {article.hash_id}")
                return False

        except sqlite3.Error as e:
            self.logger.error(f"添加文章记录失败: {e}")
            return False

        finally:
            conn.close()

    def is_duplicate(self, article: Article) -> bool:
        """
        检查文章是否重复

        Args:
            article: 文章对象

        Returns:
            是否重复
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE biz = ? AND article_id = ?
            """, (article.biz, article.article_id))

            count = cursor.fetchone()[0]
            return count > 0

        except sqlite3.Error as e:
            self.logger.error(f"检查重复失败: {e}")
            return False

        finally:
            conn.close()

    def get_article(self, biz: str, article_id: str) -> Optional[ArticleRecord]:
        """
        获取文章记录

        Args:
            biz: 公众号标识
            article_id: 文章ID

        Returns:
            文章记录或None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM articles
                WHERE biz = ? AND article_id = ?
            """, (biz, article_id))

            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)

            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取文章记录失败: {e}")
            return None

        finally:
            conn.close()

    def update_article(
        self,
        biz: str,
        article_id: str,
        status: str = None,
        local_path: str = None,
        error_message: str = None
    ) -> bool:
        """
        更新文章记录

        Args:
            biz: 公众号标识
            article_id: 文章ID
            status: 状态
            local_path: 本地路径
            error_message: 错误信息

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        updates = ["updated_at = ?"]
        values = [now]

        if status:
            updates.append("status = ?")
            values.append(status)

        if local_path:
            updates.append("local_path = ?")
            values.append(local_path)

        if error_message:
            updates.append("error_message = ?")
            values.append(error_message)

        values.extend([biz, article_id])

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(f"""
                UPDATE articles
                SET {', '.join(updates)}
                WHERE biz = ? AND article_id = ?
            """, values)

            conn.commit()
            return cursor.rowcount > 0

        except sqlite3.Error as e:
            self.logger.error(f"更新文章记录失败: {e}")
            return False

        finally:
            conn.close()

    def get_pending_articles(self, limit: int = 100) -> List[ArticleRecord]:
        """
        获取待处理文章

        Args:
            limit: 数量限制

        Returns:
            文章记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM articles
                WHERE status IN ('pending', 'failed')
                ORDER BY publish_time DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

        except sqlite3.Error as e:
            self.logger.error(f"获取待处理文章失败: {e}")
            return []

        finally:
            conn.close()

    def get_articles_by_biz(self, biz: str, limit: int = 100) -> List[ArticleRecord]:
        """
        获取指定公众号的文章

        Args:
            biz: 公众号标识
            limit: 数量限制

        Returns:
            文章记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM articles
                WHERE biz = ?
                ORDER BY publish_time DESC
                LIMIT ?
            """, (biz, limit))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

        except sqlite3.Error as e:
            self.logger.error(f"获取公众号文章失败: {e}")
            return []

        finally:
            conn.close()

    def add_history(
        self,
        article_id: int,
        action: str,
        details: Dict = None
    ) -> bool:
        """
        添加历史记录

        Args:
            article_id: 文章ID
            action: 操作类型
            details: 详情

        Returns:
            是否添加成功
        """
        now = datetime.now().isoformat()
        details_json = json.dumps(details, ensure_ascii=False) if details else None

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO article_history (article_id, action, details, created_at)
                VALUES (?, ?, ?, ?)
            """, (article_id, action, details_json, now))

            conn.commit()
            return True

        except sqlite3.Error as e:
            self.logger.error(f"添加历史记录失败: {e}")
            return False

        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        stats = {}

        try:
            # 总数
            cursor.execute("SELECT COUNT(*) FROM articles")
            stats['total'] = cursor.fetchone()[0]

            # 按状态统计
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM articles
                GROUP BY status
            """)
            stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

            # 按公众号统计
            cursor.execute("""
                SELECT biz, COUNT(*) as count
                FROM articles
                GROUP BY biz
            """)
            stats['by_biz'] = {row['biz']: row['count'] for row in cursor.fetchall()}

            # 今日新增
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE publish_date = ?
            """, (today,))
            stats['today_new'] = cursor.fetchone()[0]

            return stats

        except sqlite3.Error as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {}

        finally:
            conn.close()

    def cleanup_old_records(self, days: int = 30) -> int:
        """
        清理旧记录

        Args:
            days: 保留天数

        Returns:
            清理记录数
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 删除历史记录
            cursor.execute("""
                DELETE FROM article_history
                WHERE created_at < ?
            """, (cutoff_date,))

            deleted_history = cursor.rowcount

            # 删除已完成的旧文章记录
            cursor.execute("""
                DELETE FROM articles
                WHERE status IN ('downloaded', 'parsed')
                AND updated_at < ?
            """, (cutoff_date,))

            deleted_articles = cursor.rowcount

            conn.commit()

            total_deleted = deleted_history + deleted_articles
            self.logger.info(f"清理旧记录: {total_deleted}条")
            return total_deleted

        except sqlite3.Error as e:
            self.logger.error(f"清理旧记录失败: {e}")
            return 0

        finally:
            conn.close()

    def close(self) -> None:
        """关闭连接（用于清理）"""
        # SQLite连接会自动关闭，这里主要是为了接口一致性
        pass
