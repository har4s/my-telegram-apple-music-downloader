# My Telegram Apple Music Downloader

A Telegram bot that downloads Apple Music content using Celery for task processing.

## Prerequisites

- Docker and Docker Compose installed
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram User ID (you can get it from [@userinfobot](https://t.me/userinfobot))
- Apple Music subscription
- Cookies file from your Apple Music browser session

## Setup

### 1. Environment Variables

Create a copy of the example environment file:

```bash
cp deployment/example.env deployment/.env
```

Edit the `.env` file and set the following required environment variables:

- `TELEGRAM_TOKEN`: Your Telegram bot token obtained from BotFather
- `TELEGRAM_ADMIN_ID`: Your Telegram user ID (or comma-separated list of IDs for multiple admins)

Example:
```
TELEGRAM_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ
TELEGRAM_ADMIN_ID=123456789,987654321
```

### 2. Apple Music Cookies

The bot requires a cookies.txt file in Netscape HTTP Cookie File format from your Apple Music logged-in session (requires an active subscription).

To obtain this file:
- **Firefox**: Use the [Export Cookies](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/) extension
- **Chromium-based Browsers** (Chrome, Edge, etc.): Use the [Open Cookies.txt](https://chrome.google.com/webstore/detail/open-cookiestxt/gdocmgbfkjnnpapoeobnolbbkoibbcif) extension

Place the cookies.txt file at:
```
deployment/_data/cookies.txt
```

For more details on cookie extraction, refer to [gamdl documentation](https://github.com/glomatico/gamdl).

## Deployment

Start the application using Docker Compose:

```bash
cd deployment
docker-compose up -d
```

This will start:
- Redis service for message queuing
- Celery worker for processing download tasks
- Telegram bot service

## Usage

1. Start a chat with your bot on Telegram
2. Send an Apple Music link to the bot
3. The bot will download the content and send it back to you

## Stopping the Application

```bash
cd deployment
docker-compose down
```
