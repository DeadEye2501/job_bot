import asyncio
from pyrogram import idle
from bot import JobBot
from config import get_logger

logger = get_logger(__name__)


async def main():
    bot = JobBot()
    
    try:
        await bot.start()
        logger.info("Bot started. Press Ctrl+C to stop")
        await idle()
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
