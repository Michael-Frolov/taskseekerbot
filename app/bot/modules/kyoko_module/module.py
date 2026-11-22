from .._base_module import BaseModule

from pathlib import Path

class KyokoModule(BaseModule):
    def __init__(self, bot):
        super().__init__(bot)
        self.words = ["Kyoko", "Кёко", "Кеко"]
    
    def check_triggers(self, message):
        command = self.get_command(message)
        if self.check_command(command, ["/kyoko"]):
            return True, command
        
        for word in self.words:
            if word.lower() in message.get("text", "").lower() or word.lower() in message.get("caption", "").lower():
                return True, command
        
        return False, command
    
    async def run(self, message, command, timeout):
        caught_word = None
        text = message.get("text") or message.get("caption") or ""

        if len(text):
            for word in self.words:
                position = text.lower().find(word.lower())

                if position != -1:
                    caught_word = text[position:position + len(word)]
                    break
        
        file_id = await self.bot.telegram_connect.send_animation(
            message["chat"]["id"],
            Path(__file__).parent / self.settings["kyoko_module"]["file_path"],
            file_id=self.settings["kyoko_module"]["file_id"],
            message_thread_id=message.get("message_thread_id"),
            reply_to_id=message["message_id"],
            quote=caught_word
        )
        if file_id != self.settings["kyoko_module"]["file_id"]:
            self.settings["kyoko_module"]["file_id"] = file_id
            await self.save_settings()
    
    async def close(self):
        return