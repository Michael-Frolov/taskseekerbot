from .._base_module import BaseModule

class NewModule(BaseModule):
    def __init__(self, bot):
        super().__init__(bot)
    
    def check_triggers(self, message):
        return None, None
    
    async def run(self, message, command):
        return
    
    async def close(self):
        return