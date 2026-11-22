from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...bot import Bot

from abc import ABC, abstractmethod
from pathlib import Path
import asyncio
import aiohttp
import time
import inspect
import json
import shlex
from pprint import pformat


class BaseModule(ABC):
    def __init__(self, bot: "Bot"):
        self.bot = bot
        
        self.settings_path =  Path(inspect.getfile(type(self))).resolve().parent / "settings.json"
        with open(self.settings_path, "r", encoding="utf-8") as file:
            self.settings = json.load(file)
        
        from ...logger import logging
        self.log = logging.getLogger(type(self).__module__)
        
        self.msg_timestamps = {}
    
    
    async def save_settings(self):
        def _save_settings():
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(self.settings, file, indent=2, ensure_ascii=False)
        await asyncio.to_thread(_save_settings)
    
    
    def check_module_access(self, message: dict) -> tuple[bool, bool]:
        """return tuple[bool, bool]: has_access, notification"""
        
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
            return False, False
        
        if not access_settings["enabled"]:
            return False, False
        
        if from_id in self.bot.settings["dev_ids"]:
            return True, True
        
        has_access, notif = False, False
        
        if chat_id > 0:
            if access_settings["categories"]["users"]:
                has_access, notif = True, True
                
        else:
            if str(chat_id).startswith("-100"):
                if access_settings["categories"]["supergroups"]:
                    has_access, notif = True, True
                    
            else:
                if access_settings["categories"]["groups"]:
                    has_access, notif = True, True
        
        if is_bot:
            if not access_settings["allow_bots"]:
                has_access, notif = False, False
        
        exceptions_pos = set(access_settings["exceptions_pos"])
        exceptions_neg = set(access_settings["exceptions_neg"])
        
        if chat_id in exceptions_pos:
            has_access, notif = True, True
            
        if chat_id in exceptions_neg:
            has_access, notif = False, True
        
        if from_id in exceptions_pos:
            has_access, notif = True, True
            
        if from_id in exceptions_neg:
            has_access, notif = False, True
        
        if access_settings["devs_only"]:
            has_access = False
        
        if not access_settings["noaccess_notif"]:
            notif = False
        
        return has_access, notif
    
    
    def check_limit_rate(self, message: dict) -> tuple[bool, bool]:
        """return tuple[bool, bool]: limit_not_reached, notification"""
        
        if self.settings["access"]["limit"] is None:
            return True, False
        
        if "sender_chat" in message:
            from_id = message["sender_chat"]["id"]
        elif "from" in message:
            from_id = message["from"]["id"]
        else:
            from_id = None
        
        if from_id is None:
            return False, False
        
        rate = self.settings["access"]["limit"]["rate"]
        span = self.settings["access"]["limit"]["span"]
        current_time = time.time()
        
        for stored_id in list(self.msg_timestamps):
            self.msg_timestamps[stored_id] = [
                timestamp
                for timestamp in self.msg_timestamps[stored_id]
                if timestamp >= current_time - span
            ]
            if not self.msg_timestamps[stored_id]:
                self.msg_timestamps.pop(stored_id)
        
        if from_id in self.msg_timestamps:
            self.msg_timestamps[from_id].append(current_time)
        else:
            self.msg_timestamps[from_id] = [current_time]
        
        if from_id in self.bot.settings["dev_ids"]:
            return True, False
        
        if len(self.msg_timestamps[from_id]) <= rate:
            return True, False
        
        if len(self.msg_timestamps[from_id]) <= rate + 3:
            return False, True
        
        return False, False
    
    
    def get_command(self, message: dict) -> list[str] | None:
        text = str(message.get("text", "")) or str(message.get("caption", ""))
        if not text.startswith("/"):
            return
        return shlex.split(text.strip())
    
    
    def check_command(self, command: list[str] | None, keys: str | list[str]) -> bool:
        if isinstance(keys, str):
            keys = [keys]
        if command and len(command):
            if command[0].lower() in keys:
                return True
        return False
    
    
    @abstractmethod
    def check_triggers(self, message: dict) -> tuple[bool | None, list[str] | None]:
        """return tuple[bool, list[str]]: triggered, command"""
        return None, None
    
    
    @abstractmethod
    async def run(self, message: dict, command: list[str] | None, timeout: int | None):
        return
    
    @abstractmethod
    async def close(self):
        return
    
    
    async def process_message(self, message: dict, timeout: asyncio.Timeout):
        try:
            triggered, command = self.check_triggers(message)
            
            if triggered:
                has_access, no_access_notif = self.check_module_access(message)
                
                if has_access:
                    limit_not_reached, limit_reached_notif = self.check_limit_rate(message)
                        
                    if limit_not_reached:
                        await self.run(message, command, timeout)
                        
                        self.log.info(
                            f"[chat: {message["chat"]["id"]}] "
                            f"{type(self).__name__} executed."
                        )
                    
                    elif limit_reached_notif:
                        await self.bot.telegram_connect.reply_to_message(
                            message,
                            "❌ Too many requests."
                        )
                
                elif no_access_notif:
                    await self.bot.telegram_connect.reply_to_message(
                        message,
                        "❌ You have no access to this module."
                    )
                
                return True
        
        except aiohttp.ClientConnectorError:
            self.log.exception(
                f"[chat: {message["chat"]["id"]}] "
                f"{type(self).__name__} failed. "
                f"aiohttp client connection error.\n"
                f"MESSAGE: {pformat(message)}"
            )
            self.bot.restart_event.set()
        
        except Exception:
            self.log.exception(
                f"[chat: {message["chat"]["id"]}] "
                f"{type(self).__name__} failed.\n"
                f"MESSAGE: {pformat(message)}"
            )