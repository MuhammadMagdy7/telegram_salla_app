# Massive Option Monitor Bot

A professional Telegram bot that monitors stock & options contracts using the Massive API and automatically sends visual status updates to a Telegram group.

## Features

- **Market Data**: Real-time integration with Massive API.
- **Commands**: 
  - `/monitor <symbol>,<strike>,<type>,<expiration>`
  - `/list`
  - `/remove <id>`
- **Visual Updates**: Generates images with price, P/L, and trend indicators.
- **Monitoring**: Continuous background monitoring of selected contracts.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Copy `.env.example` to `.env` and fill in your details:
   ```env
   TELEGRAM_BOT_TOKEN=your_token
   MASSIVE_API_KEY=your_key
   ```

3. **Run**:
   ```bash
   python main.py
   ```

## Architecture

- `main.py`: Entry point.
- `src/bot_handlers.py`: Telegram interaction logic.
- `src/monitor.py`: Background loop for checking prices.
- `src/image_gen.py`: Image generation using Pillow.
- `src/api_client.py`: API wrapper for Massive.
- `src/database.py`: SQLite storage for persistent monitoring.
