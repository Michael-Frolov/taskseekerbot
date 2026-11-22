from .logger import logging
log = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.ERROR)
from .connect import TelegramAPIError, TelegramConnect, TelethonConnect
from .modules import *

import os
from pathlib import Path
import json
import asyncio
import time
import aiohttp
from pprint import pformat

class Bot:
    def __init__(self, connect: TelegramConnect, telethon: TelethonConnect | None = None):
        
        self.telegram_connect: TelegramConnect = connect
        self.telethon_connect: TelethonConnect = telethon
        
        self.running = None
        self.restart_event = asyncio.Event()
        
        self.path = Path(__file__).resolve().parent
        self.settings_path = self.path / "settings.json"
        
        with open(self.settings_path, "r") as file:
            self.settings = json.load(file)
        
        log.info("Importing modules...")
        self.modules: dict[BaseModule] = {
            "PingModule": PingModule(self),
            "AccessManagerModule": AccessManagerModule(self),
            "WaitModule": WaitModule(self),
            "KyokoModule": KyokoModule(self),
            "ArticleModule": ArticleModule(self),
            "QuoteModule": QuoteModule(self)
        }
        
        self.message_tasks = set()
    
    async def start_telethon(self):
        if self.telethon_connect is not None:
            await self.telethon_connect.start()
    
    async def save_settings(self):
        def _save_settings():
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(
                    self.settings,
                    file,
                    indent=2,
                    ensure_ascii=False
                )
        await asyncio.to_thread(_save_settings)
    
    def check_global_access(self, message: dict) -> bool:
        access_settings = self.settings["access"]
        
        chat_id = message["chat"]["id"]
        
        if "sender_chat" in message:
            from_id = message["sender_chat"].get("id")
            is_bot = False
        
        elif "from" in message:
            from_id = message["from"]["id"]
            is_bot = message["from"].get("is_bot", False)

        else:
            from_id = None
            is_bot = False
        
        if from_id is None:
            return False
        
        if from_id in self.settings["dev_ids"]:
            return True
        
        if access_settings["devs_only"]:
            return False
        
        has_access = False
        
        if chat_id > 0:
            if access_settings["categories"]["users"]:
                has_access = True
        
        else:
            if str(chat_id).startswith("-100"):
                if access_settings["categories"]["supergroups"]:
                    has_access = True
            
            else:
                if access_settings["categories"]["groups"]:
                    has_access = True
        
        if is_bot:
            if not access_settings["allow_bots"]:
                has_access = False
        
        exceptions_pos = set(access_settings["exceptions_pos"])
        exceptions_neg = set(access_settings["exceptions_neg"])
        
        if chat_id in exceptions_pos:
            has_access = True
        
        if chat_id in exceptions_neg:
            has_access = False
        
        if from_id in exceptions_pos:
            has_access = True
        
        if from_id in exceptions_neg:
            has_access = False
        
        return has_access
    
    async def process_message(self, message: dict):
        try:
            async with asyncio.timeout(self.settings["messages"]["timeout"]) as timeout:
                for module in self.modules.values():
                    result = await module.process_message(message, timeout)
                    if result:
                        break
        
        except TimeoutError:
            log.error(
                f"Message processing timed out ({timeout}s).\n"
                f"MESSAGE: {pformat(message)}"
            )
        
        except Exception:
            log.exception(
                f"Message processing failed.\n"
                f"MESSAGE: {pformat(message)}"
            )
    
    async def listen_events(self):
        max_event_lifespan = self.settings["messages"]["max_lifespan"]
        messages_skipped = 0
        
        while self.running:
            try:
                async for event in self.telegram_connect.get_update():
                    
                    message = None
                    
                    if "message" in event:
                        message = event["message"]
                    
                    if message is None:
                        continue
                        
                    if max_event_lifespan is not None and message["date"] < time.time() - max_event_lifespan:
                        messages_skipped += 1
                        continue
                    
                    if messages_skipped:
                        log.warning(
                            f"Messages skipped by max_event_lifespan ({messages_skipped})."
                        )
                    
                    messages_skipped = 0
                    
                    if self.check_global_access(message):
                        task = asyncio.create_task(self.process_message(message))

                        self.message_tasks.add(task)
                        task.add_done_callback(self.message_tasks.discard)
            
            except TimeoutError:
                log.warning("TimeoutError.")

    async def close(self):
        self.running = False
        
        for task in self.message_tasks:
            task.cancel()
        
        if self.message_tasks:
            await asyncio.gather(
                *self.message_tasks,
                return_exceptions=True
            )
        
        for module in self.modules.values():
            await module.close()

        if self.telethon_connect is not None:
            await self.telethon_connect.disconnect()

class BotRunner:
    async def run(
        token: str,
        timeout_session: int = 120,
        timeout_reconnect: int = 20
    ):
        log.info("Bot runner started.")
        
        while True:
            bot = None
            
            try:
                log.info("Starting bot session...")
                
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(
                        total=timeout_session,
                        connect=15,
                        sock_connect=15,
                        sock_read=None
                    )
                ) as session:
                    
                    telegram_connect=TelegramConnect(token, session=session)
                    
                    log.info("Creating bot...")
                    bot = Bot(connect=telegram_connect)
                    
                    if bot.settings["enable_telethon"]:
                        
                        log.info("Starting telethon...")
                        
                        bot.telethon_connect = TelethonConnect(
                            int(os.getenv("api_id")),
                            os.getenv("api_hash"),
                            token
                        )
                        
                        await bot.start_telethon()
                    
                    bot.running = True
                    log.info("Bot started.")
                    
                    listener_task = asyncio.create_task(
                        bot.listen_events()
                    )
                    restart_task = asyncio.create_task(
                        bot.restart_event.wait()
                    )

                    done, pending = await asyncio.wait(
                        {listener_task, restart_task},
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()

                    await asyncio.gather(
                        *pending,
                        return_exceptions=True
                    )

                    if listener_task in done:
                        await listener_task

                    if bot.restart_event.is_set():
                        log.warning(
                            "Restart requested due to connection error."
                        )
            
            except TelegramAPIError as exc:
                if exc.status == 502:
                    log.warning(
                        f"Telegram API error: {exc}. "
                        f"Retrying in {timeout_reconnect}s."
                    )
                    await asyncio.sleep(timeout_reconnect)
                    continue

                log.exception(f"Telegram API error: {exc}.")
            
            except aiohttp.ClientError:
                log.error(f"aiohttp.ClientError.")
            
            except Exception as exc:
                log.exception(f"{exc}")
            
            if bot is not None:
                try:
                    await bot.close()
                    log.info("Bot closed.")
                except Exception:
                    log.exception("Bot closing failed.")
            
            log.info(f"Restarting in {timeout_reconnect}s.")
            
            await asyncio.sleep(timeout_reconnect)