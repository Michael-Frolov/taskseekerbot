if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    from .bot import BotRunner
    import asyncio
    asyncio.run(BotRunner.run(os.getenv("token")))
