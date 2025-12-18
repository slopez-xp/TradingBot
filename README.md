# Binance Futures Trading Bot

This is a configurable and automated trading bot for Binance Futures. It uses a strategy-based approach to execute trades based on market data and technical indicators. The bot is containerized with Docker for easy setup and deployment.

## Features

- **Automated Trading**: Executes trades 24/7 based on a selected strategy.
- **Strategy-Based**: Comes with "aggressive" (RSI-based) and "conservative" (Bollinger Bands based) strategies.
- **Configurable**: Easily configurable through environment variables.
- **Live Monitoring**: A terminal-based UI to monitor the bot's status and trade history in real-time.
- **Position Reversal**: The bot can automatically reverse positions (from long to short and vice versa).
- **Trailing Stop-Loss**: Includes a trailing stop-loss feature to protect profits.
- **Dockerized**: All services (API, scheduler, monitor, database) are containerized for portability and ease of use.

## Tech Stack

- **Backend**: Python, FastAPI
- **Database**: PostgreSQL
- **Data Analysis**: Pandas, Pandas-TA
- **Exchange**: Binance Futures (Testnet)
- **Containerization**: Docker, Docker Compose
- **UI**: Rich (for the terminal monitor)

## Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/slopez-xp/TradingBot
    cd TradingBot
    ```

2.  **Configure Environment Variables:**
    Create a `.env` file by copying the example file:
    ```bash
    cp .env.example .env
    ```
    Now, edit the `.env` file and fill in your Binance API credentials:
    ```env
    # --- Binance API Credentials ---
    BINANCE_API_KEY=YOUR_API_KEY
    BINANCE_SECRET_KEY=YOUR_SECRET_KEY
    ```
    You can also customize other trading parameters in this file (see Configuration section below).

## Usage

The application is split into multiple services that are managed by Docker Compose.

### 1. Start the Core Services

In a terminal, run the following command to start the API, the scheduler, and the database in the background:
```bash
sudo docker-compose up -d --build api db scheduler
```

### 2. Run the Monitor

In a separate terminal, run the monitor to see the bot's activity in real-time:
```bash
sudo docker-compose run --rm --service-ports monitor
```
The monitor will display the current strategy status and the trade history.

### 3. Stop the Services

To stop all running services, use:
```bash
sudo docker-compose down
```

## Configuration

All configuration is done via the `.env` file. Here are the key parameters:

| Variable                  | Description                                                                                                   | Default          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------- |
| `BINANCE_API_KEY`         | Your Binance API key.                                                                                         | (empty)          |
| `BINANCE_SECRET_KEY`      | Your Binance API secret key.                                                                                    | (empty)          |
| `POSTGRES_USER`           | Username for the PostgreSQL database.                                                                         | `user`           |
| `POSTGRES_PASSWORD`       | Password for the PostgreSQL database.                                                                         | `password`       |
| `POSTGRES_DB`             | Name of the PostgreSQL database.                                                                              | `trading_bot_db` |
| `TRADE_SYMBOL`            | The market symbol to trade (e.g., `BTCUSDT`, `ETHUSDT`).                                                        | `BTCUSDT`        |
| `TRADE_INTERVAL`          | The time interval for market data analysis (e.g., `15m`, `1h`, `4h`).                                             | `4h`             |
| `TRADE_SL_PERCENTAGE`     | The stop-loss percentage for trades (e.g., `0.02` for 2%).                                                      | `0.02`           |
| `TRADING_STRATEGY`        | The trading strategy to use. Can be `"conservative"` or `"aggressive"`.                                         | `"conservative"` |
| `TRADE_QUANTITY`          | (Conservative Strategy) The fixed amount to trade.                                                            | `0.001`          |
| `TRADE_RISK_PERCENTAGE`   | (Aggressive Strategy) The percentage of your balance to risk per trade (e.g., `1.0` for 1%).                    | `1.0`            |
| `TRADE_MAX_HOLDING_HOURS` | (Aggressive Strategy) The maximum number of hours to hold a position before closing it.                         | `24`             |

After changing any of these variables, you will need to restart the services with `sudo docker-compose up -d --build` for the changes to take effect.
