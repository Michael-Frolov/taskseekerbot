from .._base_module import BaseModule
from ...logger import logging
log = logging.getLogger(__name__)

from pathlib import Path
import sqlite3
from datetime import datetime
import random
from html import escape
import re

class ArticleModule(BaseModule):
    def __init__(self, bot):
        super().__init__(bot)
        
        self.article_commands = ["/article"]
        
        self.article_pings = [
            "статья",
            "article",
            "моя статья",
            "my article"
        ]
        self.article_re = (
            r"(?i)(?:" +
            "|".join(map(re.escape, self.article_pings)) +
            ")"
        )
        
        self.articles_commands = ["/articles"]
        
        self.articles_pings = [
            "статьи",
            "articles",
            "мои статьи",
            "my articles"
        ]
        self.articles_re = (
            r"(?i)(" +
            "|".join(map(re.escape, self.articles_pings)) +
            r")(?: (@\w+))?(?: (-?\d+))?"
        )
        
        self.article_page_length = self.settings["article_module"]["article_page_length"]
        
        self.articles = {}
        
        self.database_path = (Path(__file__).parent / self.settings["article_module"]["database_path"])
        
        with open(Path(__file__).parent / self.settings["article_module"]["articles_path"], "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                article, description = line.split(maxsplit=1)
                article = article.rstrip(".")

                self.articles[article] = description
        
        log.info("Initializing database...")
        with sqlite3.connect(self.database_path, timeout=30) as connection:
            
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys = ON")

            connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    last_use_date TEXT,
                    last_article TEXT
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS user_articles (
                    user_id INTEGER NOT NULL,
                    article TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,

                    PRIMARY KEY (user_id, article),

                    FOREIGN KEY (user_id)
                        REFERENCES users (user_id)
                        ON DELETE CASCADE
                )
            """)

    def _get_user_data(
        self,
        message: dict
    ):
        if "sender_chat" in message:
            sender_chat = message["sender_chat"]

            user_id = sender_chat.get("id")

            if sender_chat.get("username"):
                return user_id, f"@{sender_chat['username']}"

            if sender_chat.get("title"):
                return user_id, sender_chat["title"]

            username = " ".join(filter(None, (
                sender_chat.get("first_name"),
                sender_chat.get("last_name")
            ))) or None

            return user_id, username

        if "from" in message:
            user = message["from"]

            user_id = user["id"]

            if user.get("username"):
                return user_id, f"@{user['username']}"

            username = " ".join(filter(None, (
                user.get("first_name"),
                user.get("last_name")
            ))) or None

            return user_id, username

        return None, None
    
    def _get_or_set_article(
        self,
        user_id: int,
        date: str
    ) -> tuple[bool, str | None]:

        connection = sqlite3.connect(
            self.database_path,
            timeout=30
        )

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute("""
                SELECT last_article
                FROM users
                WHERE user_id = ?
                    AND last_use_date = ?
            """, (
                user_id,
                date
            ))

            row = cursor.fetchone()
            
            if row is not None:
                connection.commit()

                return True, row[0]
            
            article = None
            
            if random.random() >= self.settings["article_module"]["clean_chance"]:
                article = random.choice(list(self.articles))
            
            connection.execute("""
                INSERT INTO users (
                    user_id,
                    last_use_date,
                    last_article
                )
                VALUES (?, ?, ?)

                ON CONFLICT(user_id)
                DO UPDATE SET
                    last_use_date = excluded.last_use_date,
                    last_article = excluded.last_article
            """, (
                user_id,
                date,
                article
            ))
            
            if article is not None:

                connection.execute("""
                    INSERT INTO user_articles (
                        user_id,
                        article,
                        count
                    )
                    VALUES (?, ?, 1)

                    ON CONFLICT(user_id, article)
                    DO UPDATE SET
                        count = count + 1
                """, (
                    user_id,
                    article
                ))

            connection.commit()

            return False, article

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()
    
    def _get_msg_text(
        self,
        username: str | None,
        article_number: str | None,
        article_full: str | None,
        repeat: bool = False,
        private_chat: bool = False
    ) -> str:
        
        if private_chat:
            
            if article_number is None:
                
                if repeat:
                    
                    return f"✅ На тебя сегодня не было заведено никакой статьи УК РБ."
                
                return f"✅ Твоему везению нет предела! Сегодня на тебя не было заведено никакой статьи УК РБ." 

            if repeat:
                
                return f"🤷‍♂ Сегодня ты уже был приговорен к статье {article_number} УК РБ. {article_full}."
            
            return f"🤷‍♂ Сегодня ты приговариваешься к статье {article_number} УК РБ. {article_full}."
        
        if article_number is None:
            
            if repeat:
                
                return f"✅ На тебя сегодня не было заведено никакой статьи УК РБ, {username if username else "пользователь"}."
            
            return f"✅ Твоему везению нет предела! Сегодня на тебя не было заведено никакой статьи УК РБ, {username if username else "пользователь"}."
        
        if repeat:
            
            return f"🤷‍♂ Сегодня {username if username else "пользователь"} уже был приговорен к статье {article_number} УК РБ. {article_full}."
        
        return f"🤷‍♂ Сегодня {username if username else "пользователь"} приговаривается к статье {article_number} УК РБ. {article_full}."
    
    def _get_articles_command_params(self, command, message_text):
        page = 1
        username = None

        if self.check_command(command, self.articles_commands):
            command_text = " ".join(command)

            match = re.fullmatch(
                rf"(?i){re.escape(command[0])}(?: (@\w+))?(?: (-?\d+))?",
                command_text
            )

            if not match:
                return False, f"{command[0]} ('@{self.bot.settings["bot"]["domain"]}', '1', '2', '3')"

            username = match.group(1)

            if match.group(2):
                page = int(match.group(2))

                if page <= 0:
                    return False, f"{command[0]} ('@{self.bot.settings["bot"]["domain"]}', '1', '2', '3')"

            return True, (username, page)

        match = re.fullmatch(self.articles_re, message_text)

        try:
            username = match.group(2) if match and match.group(2) else None
            page = int(match.group(3)) if match and match.group(3) else page

            if page <= 0:
                raise ValueError

        except ValueError:
            return False, f"{match.group(1)} ('@{self.bot.settings["bot"]["domain"]}', '1', '2', '3')"

        return True, (username, page)
    
    def _get_user_articles(self, user_id: int) -> list[tuple[str, int]]:

        connection = sqlite3.connect(
            self.database_path,
            timeout=30
        )

        try:
            cursor = connection.execute("""
                SELECT article, count
                FROM user_articles
                WHERE user_id = ?
            """, (
                user_id,
            ))

            articles = cursor.fetchall()

            return sorted(
                articles,
                key=lambda item: (
                    -item[1],
                    tuple(
                        int(part)
                        for part in item[0].split(".")
                    )
                )
            )

        finally:
            connection.close()
    
    def _get_msg_text_list(
        self,
        username: str | None,
        articles: list | None,
        page: int = 1,
        private: bool = False
    ) -> str:
            
        if not articles:
            
            if private:
        
                return f"📋 У тебя пока нет ни одной статьи УК РБ."
    
            return f"📋 У {username if username else "пользователя"} пока нет ни одной статьи УК РБ."
        
        articles_count_user = len(articles)
        articles_count_total = len(self.articles)

        pages = []
        current_page = []
        current_length = 0

        for article_number, count in articles:
            article_length = len(
                f"{article_number} УК РБ. "
                f"{escape(self.articles[article_number])}."
            )

            if (
                current_page and
                current_length + article_length > self.article_page_length
            ):
                pages.append(current_page)
                current_page = []
                current_length = 0

            current_page.append((article_number, count))
            current_length += article_length

        if current_page:
            pages.append(current_page)

        pages_count = len(pages)

        page = max(1, min(page, pages_count))
        articles = pages[page - 1]
        
        articles_text = "\n".join(
            f"{article_number} УК РБ. "
            f"{escape(self.articles[article_number])}."
            + (f" ({count})" if count >= 2 else "")
            for article_number, count in articles
        )
        
        page_text = (
            f"\nСтраница {page} из {pages_count}"
            if pages_count > 1
            else ""
        )
        
        if private:
            
            return (
                f"📋 Твои статьи УК РБ "
                f"({articles_count_user}/{articles_count_total}):\n"
                f"<blockquote expandable>{articles_text}</blockquote>"
                f"{page_text}"
            )
        
        return (
            f"📋 Статьи УК РБ {username if username else "пользователя"} "
            f"({articles_count_user}/{articles_count_total}):\n"
            f"<blockquote expandable>{articles_text}</blockquote>"
            f"{page_text}"
        )

    def check_triggers(self, message):
        command = self.get_command(message)
        if (
            self.check_command(command, self.article_commands) or
            self.check_command(command, self.articles_commands)
        ):
            return True, command
        
        message_text = (
            message.get("text") or
            message.get("caption") or
            ""
        ).strip()
        
        if (
            re.fullmatch(self.article_re, message_text) or
            re.fullmatch(self.articles_re, message_text)
        ):
            return True, command
                
        return False, command
    
    async def run(self, message, command, timeout):
        
        user_id, username = self._get_user_data(message)
        
        if not user_id:
            return await self.bot.telegram_connect.reply_to_message(
                message,
                "Этот модуль требует наличия ID отправителя. ID не обнаружен."
            )
        
        message_text = (
            message.get("text") or
            message.get("caption") or
            ""
        ).strip()
        
        today = datetime.fromtimestamp(message["date"]).date().isoformat()
        
        if (
            self.check_command(command, self.article_commands) or 
            re.fullmatch(self.article_re, message_text)
        ):
            used_today, article_number = self._get_or_set_article(user_id, today)

            article_full = None
            if article_number is not None:
                article_full = self.articles[article_number]

            private = message["chat"]["type"] == "private"

            msg_text = self._get_msg_text(
                username,
                article_number,
                article_full,
                used_today,
                private
            )

            return await self.bot.telegram_connect.reply_to_message(
                message,
                msg_text,
                is_reply=False
            )
        
        if (
            self.check_command(command, self.articles_commands) or
            re.fullmatch(self.articles_re, message_text)
        ):
            no_error, result = self._get_articles_command_params(command, message_text)
                        
            if not no_error:
                return await self.bot.telegram_connect.reply_to_message(message, result)
            
            custom_username, page = result
            
            if custom_username is not None:
                
                if self.bot.telethon_connect is None:
                    
                    return await self.bot.telegram_connect.reply_to_message(
                        message,
                        "Поиск пользователей по домену сейчас недоступен."
                    )
                
                user = await self.bot.telethon_connect.get_user(custom_username)
                
                if user is None:
                    return await self.bot.telegram_connect.reply_to_message(
                        message,
                        f"Пользователь с указанным доменом не найден."
                    )
                
                user_id = user.id
                username = custom_username
            
            articles = self._get_user_articles(user_id)
            
            private = (
                message["chat"]["type"] == "private" and
                custom_username is None
            )

            msg_text = self._get_msg_text_list(
                username,
                articles,
                page,
                private
            )

            return await self.bot.telegram_connect.reply_to_message(
                message,
                msg_text,
                is_reply=False,
                parse_mode="HTML"
            )
    
    async def close(self):
        return