## taskseeker Telegram Bot

This repository contains my pet project, a small bot for Telegram messenger. This project was developed for local, temporary use and was never intended as a showcase or for public use, therefore <b><u>the code does not contain any comments</u></b>. Nevertheless, I decided to publish the source code on GitHub.

### Known Issues:

- Telethon works unstably and may cause occasional unhandled exceptions, so I do not recommend using it (leave `enable_telethon` to `false` in [settings.json](app/bot/settings.example.json)).
- The bot was never designed to handle a huge number of concurrent requests at once. Despite having asynchronous code, the bot processes all incoming requests simultaneously, so it may fail to process messages under a massive spike in requests due to a timeout parameter that limits the maximum processing time for a single message.