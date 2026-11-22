from .._base_module import BaseModule
from ...logger import logging
log = logging.getLogger(__name__)

import asyncio
from pathlib import Path
from html import escape
import secrets
import random
import re
from playwright.async_api import async_playwright
import shutil
import os
from faster_whisper import WhisperModel
from io import BytesIO

class QuoteModule(BaseModule):
    def __init__(self, bot):
        super().__init__(bot)
        
        self.ping_words = ["/", "q", "й"]
        
        self.stt_model = None
        
        os.environ["HF_HUB_CACHE"] = self.settings["quote_module"]["stt_model"]["hf_hub_cache_path"]
        
        self.stt_model_task = asyncio.create_task(
            self._init_stt_model()
        )
        
        output_path = (
            Path(__file__).parent /
            self.settings["quote_module"]["path"]["output"]
        )

        output_path.mkdir(parents=True, exist_ok=True)
        
        log.info("Initializing templates...")
        self.templates = [
            path.read_text(encoding="utf-8")
            for path in (
                Path(__file__).parent /
                self.settings["quote_module"]["path"]["templates"]
            ).iterdir()
            if path.is_file()
            and path.suffix.lower() in [".html", ".php"]
            and not path.stem.endswith("DISABLED")
        ]
        
        self.stock_backgrounds = [
            path
            for path in (
                Path(__file__).parent /
                self.settings["quote_module"]["path"]["stock_background_images"]
            ).iterdir()
            if path.is_file()
        ]
        
        self.stock_pfps = [
            path
            for path in (
                Path(__file__).parent /
                self.settings["quote_module"]["path"]["stock_profile_images"]
            ).iterdir()
            if path.is_file()
        ]
        
        self.playwright = None
        self.browser = None
        
        log.info("Initializing browser...")
        self.browser_task = asyncio.create_task(self._init_browser())

    def _is_model_cached(self, model_name: str) -> bool:
        cache_dir = Path(os.environ["HF_HUB_CACHE"])
        model_suffix = f"--faster-whisper-{model_name}"

        return any(
            path.is_dir() and path.name.endswith(model_suffix)
            for path in cache_dir.glob("models--*")
        )

    async def _init_stt_model(self, timeout_task: int = 60):
        self.stt_model = None
        model_name = self.settings["quote_module"]["stt_model"]["model"]
        
        log.info(f"Initializing speech-to-text model '{model_name}'...")
        
        if not self._is_model_cached(model_name):
            log.info(
                f"Model '{model_name}' not found in cache. Downloading without timeout..."
            )
            timeout_task = None
            
        try:
            task = asyncio.to_thread(
                WhisperModel,
                model_name,
                device="cpu",
                compute_type="int8"
            )

            if timeout_task is None:
                self.stt_model = await task
            
            else:
                self.stt_model = await asyncio.wait_for(
                    task,
                    timeout=timeout_task
                )
            
            text = f"Speech-to-text model '{model_name}' loaded."
            
            log.info(text)
            return text

        except asyncio.TimeoutError:
            self.stt_model = None
            text = f"Speech-to-text model '{model_name}' initialization failed: Timed out after 60 seconds."
            
            log.error(text)
            return text

        except Exception as exc:
            self.stt_model = None
            text = f"Speech-to-text model '{model_name}' initialization failed."
            
            log.exception(text)
            return f"{text} ({exc})"

    async def _init_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
    
    def _get_reply_text(self, message):
        if "quote" in message:
            return message["quote"].get("text").strip()
        
        if "reply_to_message" in message:
            return message["reply_to_message"].get("text") or message["reply_to_message"].get("caption")
    
    def _get_reply_voice(self, message):
        if "reply_to_message" in message:
            return message["reply_to_message"].get("voice")
    
    def _transcribe(self, audio):
        segments, info = self.stt_model.transcribe(audio)
        return "".join(segment.text for segment in segments)
    
    async def _transcribe_voice(self, file_id):
        await self.stt_model_task
        
        file = await self.bot.telegram_connect.download_file_bytes(file_id)

        if file is None:
            return None

        audio = BytesIO(file)
        audio.name = "voice_message.ogg"

        return await asyncio.to_thread(
            self._transcribe,
            audio
        )

    def _get_user_data(self, user):
        first_name = user.get("first_name")
        last_name = user.get("last_name")

        name = " ".join(filter(None, (first_name, last_name)))

        return (
            user["id"],
            name or None,
            user.get("username")
        )

    def _get_origin_profile_data(self, origin, chat_id=None, message_id=None):
        match origin["type"]:

            case "user":
                user_id, name, username = self._get_user_data(origin["sender_user"])

                return (
                    user_id,
                    name,
                    username,
                    chat_id,
                    message_id
                )

            case "hidden_user":
                return (
                    None,
                    origin["sender_user_name"],
                    None,
                    chat_id,
                    message_id
                )

            case "chat":
                chat = origin["sender_chat"]
                name = chat.get("title") or origin.get("author_signature")

                return (
                    chat["id"],
                    name,
                    chat.get("username"),
                    chat_id,
                    message_id
                )

            case "channel":
                chat = origin["chat"]
                name = chat.get("title") or origin.get("author_signature")

                return (
                    chat["id"],
                    name,
                    chat.get("username"),
                    chat_id,
                    message_id
                )

        return None, None, None, chat_id, message_id
    
    def _get_reply_photo(self, message):
        reply = message.get("reply_to_message")

        if reply:
            photo = reply.get("photo")

            if photo:
                return photo[-1]["file_id"]

        external_reply = message.get("external_reply")

        if external_reply:
            external_message = external_reply.get("message")

            if external_message:
                photo = external_message.get("photo")

                if photo:
                    return photo[-1]["file_id"]

        return None

    def _get_reply_data(self, message) -> tuple[int | None, str | None, str | None, int | None, int | None]:
        """return tuple[int, str, str, int, int]: user_id, name, username, reply_chat_id, reply_message_id"""
        
        reply = message.get("reply_to_message")

        if reply:
            chat_id = message["chat"]["id"]
            message_id = reply["message_id"]

            if "forward_origin" in reply:
                return self._get_origin_profile_data(
                    reply["forward_origin"],
                    chat_id,
                    message_id
                )

            if "sender_chat" in reply:
                chat = reply["sender_chat"]

                return (
                    chat["id"],
                    chat.get("title"),
                    chat.get("username"),
                    chat_id,
                    message_id
                )

            if "from" in reply:
                user_id, name, username = self._get_user_data(reply["from"])

                return (
                    user_id,
                    name,
                    username,
                    chat_id,
                    message_id
                )

        external_reply = message.get("external_reply")

        if external_reply:
            chat = external_reply.get("chat")

            return self._get_origin_profile_data(
                external_reply["origin"],
                chat["id"] if chat else None,
                external_reply.get("message_id")
            )

        return None, None, None, None, None
    
    async def _get_pfp_path(self, user_id, username, chat_id, message_id) -> str:
        
        if user_id is not None:
            if pfp := await self.bot.telegram_connect.get_profile_photo(user_id):
                return await self.bot.telegram_connect.download_file_base64(pfp)
        
        if self.bot.telethon_connect is None:
            return
        
        if username:
            user = await self.bot.telethon_connect.get_user(username)
            if pfp:= await self.bot.telethon_connect.get_profile_photo(user):
                return self.bot.telethon_connect.file_to_base64(pfp)
        
        message = await self.bot.telethon_connect.get_message(chat_id, message_id)
        
        if message is None:
            return
        
        sender = await message.get_sender()
        
        if sender is None:
            return
        
        if pfp:= await self.bot.telethon_connect.get_profile_photo(sender):
            return self.bot.telethon_connect.file_to_base64(pfp)
            
    def generate_quote(
        self,
        template,
        path: str,
        text: str | None = None,
        name: str | None = None,
        username: str | None = None,
        pfp: Path | None = None,
        image: Path | None = None,
        background_size: str = "cover"
    ):
        
        html = template
        
        text = re.sub(r"\n+", "\n", text)
        
        if len(text) > 1000:
            text = text[:997] + "..."
        
        html = html.replace("{{TEXT}}", escape(text or ""))
        html = html.replace("{{NAME}}", escape(name or ""))
        html = html.replace("{{USERNAME}}", escape(f"@{username}" if username else ""))
        
        pfp_uri = (
            pfp.resolve().as_uri()
            if isinstance(pfp, Path)
            else pfp or ""
        )

        image_uri = (
            image.resolve().as_uri()
            if isinstance(image, Path)
            else image or ""
        )

        html = html.replace("{{PROFILE_IMAGE}}", pfp_uri)
        html = html.replace("{{BACKGROUND}}", image_uri)
        html = html.replace("{{BACKGROUND_SIZE}}", background_size)
        
        path.write_text(html, encoding="utf-8")
    
    async def render_html(
        self,
        html_path: Path,
        output_path: Path
    ):
        await self.browser_task

        page = await self.browser.new_page(
            device_scale_factor=2
        )

        try:
            await page.goto(
                html_path.resolve().as_uri(),
                wait_until="networkidle"
            )

            quote = page.locator(".quote")

            await quote.screenshot(
                path=output_path,
                type="png"
            )

        finally:
            await page.close()
    
    def check_triggers(self, message):
        
        command = self.get_command(message)
        if self.check_command(command, [
            "/quote",
            "/q",
            "/reloadsttmodel",
            "/setsttmodel"
        ]):
            return True, command
        
        message_text = message.get("text") or message.get("caption") or ""
        
        if message_text.lower() in [
            word.lower()
            for word
            in self.ping_words
        ]:
            return True, command
        
        return False, command
    
    async def run(self, message, command, timeout):
        
        if self.check_command(command, "/reloadsttmodel"):
            
            if "from" in message and message["from"]["id"] in self.bot.settings["dev_ids"]:
                
                timeout.reschedule(None)
                
                await self.bot.telegram_connect.reply_to_message(
                    message,
                    f"Reloading speech-to-text model '{self.settings["quote_module"]["stt_model"]["model"]}'..."
                )
                
                self.stt_model_task = asyncio.create_task(
                    self._init_stt_model()
                )
                
                result = await self.stt_model_task
                
                return await self.bot.telegram_connect.reply_to_message(
                    message,
                    result
                )
            
            return await self.bot.telegram_connect.reply_to_message(message, "❌ You have no access to this command.")
        
        if self.check_command(command, "/setsttmodel"):
            
            if "from" in message and message["from"]["id"] in self.bot.settings["dev_ids"]:
                
                if len(command) > 1:
                    
                    timeout.reschedule(None)
                    
                    self.settings["quote_module"]["stt_model"]["model"] = command[1]
                    await self.save_settings()
                    
                    await self.bot.telegram_connect.reply_to_message(
                        message,
                        f"Initializing speech-to-text model '{command[1]}'..."
                    )
                    
                    self.stt_model_task = asyncio.create_task(
                        self._init_stt_model()
                    )
                    
                    result = await self.stt_model_task
                    
                    return await self.bot.telegram_connect.reply_to_message(
                        message,
                        result
                    )
                
                return await self.bot.telegram_connect.reply_to_message(message, f"{command[0]} {("('{Model}')")}") 
            
            return await self.bot.telegram_connect.reply_to_message(message, "❌ You have no access to this command.")
        
        text = self._get_reply_text(message)
        
        msg_from_dev = False
        
        if "from" in message and message["from"]["id"] in self.bot.settings["dev_ids"]:
            msg_from_dev = True
        
        if not text:
            
            if voice := self._get_reply_voice(message):
                
                if self.stt_model is None:
                    return await self.bot.telegram_connect.reply_to_message(
                        message,
                        f"Speech-to-text convertion is currently unavailable."
                    )
                
                duration = self.settings["quote_module"]["stt_model"]["max_voice_message_duration"]
                
                if voice["duration"] > duration and not msg_from_dev:
                    
                    return await self.bot.telegram_connect.reply_to_message(
                        message,
                        f"You cannot quote voice messages longer than {duration}s."
                    )

                await self.bot.telegram_connect.reply_to_message(
                    message,
                    "Transcribing voice..."
                )
                
                transcribing_timeout = self.settings["quote_module"]["stt_model"]["transcribing_timeout"]
                
                if transcribing_timeout is not None:
                    timeout.reschedule(
                        asyncio.get_running_loop().time() + transcribing_timeout
                    )
                
                text = await self._transcribe_voice(voice["file_id"])
        
        if not text:
            
            if "reply_to_message" not in message and "external_reply" not in message:
                if not self.check_command(command, ["/quote", "/q"]):
                    return
            
            return await self.bot.telegram_connect.reply_to_message(
                message,
                "Text not found. Reply to a message with a text or select a specific quote."
            )
        
        user_id, name, username, reply_chat_id, reply_message_id = self._get_reply_data(message)
        
        if user_id is None and username is not None:
            if self.bot.telethon_connect is not None:
                if user := await self.bot.telethon_connect.get_user(username):
                    user_id = user.id
        
        pfp = await self._get_pfp_path(user_id, username, reply_chat_id, reply_message_id)
        
        if not pfp:
            pfp = random.choice(self.stock_pfps) if self.stock_pfps else None
        
        image = self._get_reply_photo(message)
        
        if "photo" in message:
            image = message["photo"][-1]["file_id"]
        
        background_size = "cover"
        
        if image:
            image = await self.bot.telegram_connect.download_file_base64(image)
            background_size = "100% 100%"
        else:
            image = random.choice(self.stock_backgrounds) if self.stock_backgrounds else None
        
        token = secrets.token_hex(16)
        
        folder = (
            Path(__file__).parent /
            self.settings["quote_module"]["path"]["output"] /
            token
        )
        
        await asyncio.to_thread(
            folder.mkdir,
            parents=True,
            exist_ok=True
        )
        
        template = random.choice(self.templates)
        
        html_output_path = folder / f".html"
        
        await asyncio.to_thread(
            self.generate_quote,
            template,
            html_output_path,
            text,
            name,
            username,
            pfp,
            image,
            background_size
        )
        
        quote_image_output_path = folder / f".png"
        
        await self.render_html(
            html_output_path,
            quote_image_output_path
        )
        
        result = await self.bot.telegram_connect.send_photo(
            message["chat"]["id"],
            quote_image_output_path,
            message_thread_id=message.get("message_thread_id")
        )
        
        await asyncio.to_thread(shutil.rmtree, folder)
        
        return result

    async def close(self):
        if not self.browser_task.done():
            self.browser_task.cancel()

            try:
                await self.browser_task
            except asyncio.CancelledError:
                pass

        if self.browser is not None:
            await self.browser.close()

        if self.playwright is not None:
            await self.playwright.stop()
        
        self.stt_model = None