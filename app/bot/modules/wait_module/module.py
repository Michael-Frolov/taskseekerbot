from .._base_module import BaseModule

import asyncio

class WaitModule(BaseModule):
    def check_triggers(self, message):
        command = self.get_command(message)
        if self.check_command(command, "/wait"):
            return True, command
        return False, command
    
    async def run(self, message, command, timeout):
        if self.check_command(command, "/wait"):
            sleep = 0
            error_message = None
            if len(command) > 1:
                try:
                    sleep = float(command[1])
                except ValueError:
                    error_message = "❌ Invalid number entered. Use \"/wait 1.0\"."
            
            if sleep > self.settings["wait_module"]["max_time"]:
                error_message = f"❌ Cannot set a wait time of more than {self.settings["wait_module"]["max_time"]}s."
            
            if error_message:
                result = await self.bot.telegram_connect.reply_to_message(
                    message,
                    error_message
                )
            
            else:
                timeout.reschedule(
                    asyncio.get_running_loop().time() + sleep
                )
                
                await asyncio.sleep(sleep)
                
                result = await self.bot.telegram_connect.reply_to_message(
                    message,
                    f"✅ {sleep}s passed."
                )
        
        return result
    
    async def close(self):
        return