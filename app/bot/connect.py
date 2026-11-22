from .logger import logging
log = logging.getLogger(__name__)

import aiohttp
from pathlib import Path
import json
import base64

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.types import User
from telethon.tl.functions.users import GetFullUserRequest

class TelegramAPIError(Exception):
    def __init__(
        self,
        status: int,
        description: str
    ):
        self.status = status
        self.description = description

        super().__init__(
            f"Telegram API error {status}: {description}"
        )

class TelegramConnect:
    
    def __init__(self, token: str, session: aiohttp.ClientSession):
        self.token = token
        self.session = session
    
    async def _check_response(self, response):
        if response.status < 400:
            return

        try:
            data = await response.json()
            description = data.get(
                "description",
                "Unknown Telegram API error"
            )
        except Exception:
            description = await response.text()

        raise TelegramAPIError(
            response.status,
            description
        )
    
    async def get_update(
        self,
        offset: int = 0,
        timeout: int = 30,
        client_timeout: int = 60
    ):
        
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        while True:
            data = {
                "timeout": timeout,
                "offset": offset,
            }

            async with self.session.get(
                url,
                json=data,
                timeout=aiohttp.ClientTimeout(total=client_timeout)
            ) as response:
                
                await self._check_response(response)
                data = await response.json()

            for event in data["result"]:
                offset = event["update_id"] + 1
                yield event
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        message_thread_id: int | None = None,
        reply_to_id: int | None = None,
        quote: str | None = None,
        parse_mode: str | None = None
    ):
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        data = {
            "chat_id": chat_id,
            "text": text,
        }

        if message_thread_id is not None:
            data["message_thread_id"] = message_thread_id
        
        if reply_to_id is not None:
            data["reply_parameters"] = {"message_id": reply_to_id}
            
            if quote is not None:
                data["reply_parameters"]["quote"] = quote
        
        if parse_mode is not None:
            data["parse_mode"] = parse_mode

        async with self.session.post(url, json=data) as response:
            await self._check_response(response)
            data = await response.json()

        if data["ok"]:
            return data["result"]
    
    async def get_file(
        self,
        file_id: str | None
    ) -> str | None:
        
        url = f"https://api.telegram.org/bot{self.token}/getFile"
        
        if file_id is None:
            return None
        
        data = {
            "file_id": file_id
        }
        
        async with self.session.post(url, json=data) as response:
            await self._check_response(response)
            data = await response.json()
        
        if data["ok"]:
            return data["result"]

    async def get_profile_photo(
        self,
        chat_id: int
    ) -> str | None:
        
        url = f"https://api.telegram.org/bot{self.token}/getChat"

        data = {
            "chat_id": chat_id
        }

        async with self.session.post(url, json=data) as response:
            await self._check_response(response)
            data = await response.json()

        if not data["ok"]:
            return None

        chat = data["result"]
        chat_type = chat["type"]

        if chat_type == "private":
            url = f"https://api.telegram.org/bot{self.token}/getUserProfilePhotos"

            data = {
                "user_id": chat_id,
                "limit": 1
            }

            async with self.session.post(url, json=data) as response:
                await self._check_response(response)
                data = await response.json()

            if not data["ok"]:
                return None

            result = data["result"]

            if result["total_count"] == 0:
                return None

            return result["photos"][0][-1]["file_id"]

        photo = chat.get("photo")

        if photo is None:
            return None

        return photo["big_file_id"]
    
    async def _send_media(
        self,
        chat_id: int,
        file_path: str | Path | None,
        file_id: str | None,
        method: str,
        media_field: str,
        message_thread_id: int | None = None,
        reply_to_id: int | None = None,
        quote: str | None = None
    ) -> dict | None:

        if file_path is None and file_id is None:
            return None

        url = f"https://api.telegram.org/bot{self.token}/{method}"

        if file_id is not None:
            found_file = await self.get_file(file_id)

            if found_file is not None:
                data = {
                    "chat_id": chat_id,
                    media_field: found_file["file_id"],
                }

                if message_thread_id is not None:
                    data["message_thread_id"] = message_thread_id

                if reply_to_id is not None:
                    reply_parameters = {
                        "message_id": reply_to_id
                    }

                    if quote is not None:
                        reply_parameters["quote"] = quote

                    data["reply_parameters"] = reply_parameters

                async with self.session.post(url, json=data) as response:
                    await self._check_response(response)
                    data = await response.json()

                return data["result"]

        file_path = Path(file_path)

        with file_path.open("rb") as file:
            form = aiohttp.FormData()

            form.add_field(
                "chat_id",
                str(chat_id)
            )

            form.add_field(
                media_field,
                file,
                filename=file_path.name,
                content_type="application/octet-stream"
            )

            if message_thread_id is not None:
                form.add_field(
                    "message_thread_id",
                    str(message_thread_id)
                )

            if reply_to_id is not None:
                reply_parameters = {
                    "message_id": reply_to_id
                }

                if quote is not None:
                    reply_parameters["quote"] = quote

                form.add_field(
                    "reply_parameters",
                    json.dumps(reply_parameters)
                )

            async with self.session.post(url, data=form) as response:
                await self._check_response(response)
                data = await response.json()

        return data["result"]

    async def send_photo(
        self,
        chat_id: int,
        image_path: str | Path | None = None,
        file_id: str | None = None,
        message_thread_id: int | None = None,
        reply_to_id: int | None = None,
        quote: str | None = None
    ) -> str | None:

        result = await self._send_media(
            chat_id=chat_id,
            file_path=image_path,
            file_id=file_id,
            method="sendPhoto",
            media_field="photo",
            message_thread_id=message_thread_id,
            reply_to_id=reply_to_id,
            quote=quote
        )

        if result is None:
            return None

        return result["photo"][-1]["file_id"]

    async def send_animation(
        self,
        chat_id: int,
        animation_path: str | Path | None = None,
        file_id: str | None = None,
        message_thread_id: int | None = None,
        reply_to_id: int | None = None,
        quote: str | None = None
    ) -> str | None:

        result = await self._send_media(
            chat_id=chat_id,
            file_path=animation_path,
            file_id=file_id,
            method="sendAnimation",
            media_field="animation",
            message_thread_id=message_thread_id,
            reply_to_id=reply_to_id,
            quote=quote
        )

        if result is None:
            return None

        return result["animation"]["file_id"]

    async def download_file_bytes(self, file_id: str | None) -> bytes | None:
        file = await self.get_file(file_id)

        if file is None:
            return None

        file_path = file.get("file_path")

        if file_path is None:
            return None

        url = (
            f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        )

        async with self.session.get(url) as response:
            await self._check_response(response)
            return await response.read()

    async def download_file_base64(self, file_id):
        file = await self.get_file(file_id)

        if not file:
            return None

        file_path = file["file_path"]

        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        async with self.session.get(url) as response:
            await self._check_response(response)
            data = await response.read()

        encoded = base64.b64encode(data).decode()

        return f"data:image/jpeg;base64,{encoded}"

    async def download_file(
        self,
        file_id: str | None,
        output_path: Path
    ) -> Path | None:

        file = await self.get_file(file_id)

        if file is None:
            return None

        file_path = file.get("file_path")

        if file_path is None:
            return None

        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        async with self.session.get(url) as response:
            await self._check_response(response)

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            output_path.write_bytes(
                await response.read()
            )

        return output_path

    async def get_chat_administrators(
        self,
        chat_id: int
    ) -> list[dict]:

        url = f"https://api.telegram.org/bot{self.token}/getChatAdministrators"

        data = {
            "chat_id": chat_id
        }

        async with self.session.post(url, json=data) as response:
            await self._check_response(response)
            data = await response.json()

        if not data["ok"]:
            return None

        return data["result"]

    async def reply_to_message(
        self,
        message: dict,
        text: str,
        is_reply: bool = True,
        parse_mode: str | None = None,
    ):
        
        chat_id = message["chat"]["id"]
        
        message_thread_id = message.get("message_thread_id")
        
        message_id = None
        if is_reply:
            message_id = message["message_id"]
        
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            message_thread_id=message_thread_id,
            reply_to_id=message_id,
            parse_mode=parse_mode
        )

class TelethonConnect:

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        token: str,
        session: str | Path = "telethon"
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.token = token

        self.client = TelegramClient(
            Path(__file__).resolve().parent / session,
            api_id,
            api_hash
        )
    
    async def start(self):
        await self.client.start(bot_token=self.token)

    async def disconnect(self):
        await self.client.disconnect()
    
    async def get_message(self, chat_id: int, message_id: int) -> Message | None:
        return await self.client.get_messages(chat_id, ids=message_id)
    
    async def get_user(self, username: str) -> User | None:
        try:
            user = await self.client.get_entity(username)
        
        except Exception:
            return None

        if isinstance(user, User):
            return user
    
    async def get_profile_photo(self, user):
        if user.photo:
            return await self.client.download_profile_photo(
                user,
                file=bytes
            )

        result = await self.client(
            GetFullUserRequest(user)
        )

        if result.full_user.fallback_photo:
            return await self.client.download_file(
                result.full_user.fallback_photo
            )

    def file_to_base64(self, file: bytes):
        encoded = base64.b64encode(file).decode()
        return f"data:image/jpeg;base64,{encoded}"