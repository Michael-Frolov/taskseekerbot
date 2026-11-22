from .._base_module import BaseModule

import time

class PingModule(BaseModule):
    def __init__(self, bot):
        super().__init__(bot)
        self.responses = {
            "bot": "online",
            "бот": "онлайн",
            "ping": "pong",
            "пинг": "понг",
            "king": "kong",
            "кинг": "конг"
        }

    def _get_uppers(self, string: str) -> bool | set[int]:
        if string.isupper():
            return True
        
        list_of_uppers = set()
        for i, c in enumerate(string):
            if c.isupper():
                list_of_uppers.add(i)
        return list_of_uppers
    
    def _set_uppers(self, string: str, uppers: bool | set[int]) -> str:
        if uppers is True:
            return string.upper()
        
        return "".join(
            c.upper() if i in uppers else c
            for i, c in enumerate(string)
        )

    def check_triggers(self, message):
        command = self.get_command(message)
        if self.check_command(command, ["/online", "/ping"]):
            return True, command
        
        if str(message.get("text", "")).strip().lower() in self.responses:
            return True, command
                
        return False, command
    
    async def run(self, message, command, timeout):
        
        text_to_send = "✅ Bot online."
        text = str(message.get("text", "")).strip()
        max_response_time = 30
        
        if text.lower() in self.responses:
            text_to_send = self._set_uppers(self.responses[text.lower()], self._get_uppers(text))
    
        if not time.time() > message["date"] + max_response_time:
            result = await self.bot.telegram_connect.reply_to_message(message, text_to_send, is_reply=False)
            return result
    
    async def close(self):
        return