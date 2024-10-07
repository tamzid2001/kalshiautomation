"""
Kalshi Market Monitoring Script

This script monitors Kalshi prediction markets, analyzes price movements,
and executes trades based on specific patterns and confidence intervals.

Author: Tamzid Ullah
Website: https://tamzidullah.com
Email: tamzid257@gmail.com
GitHub: https://github.com/tamzid2001

Version: 1.1.0
Last Updated: 2024-08-03

License: MIT License

Description:
This script connects to the Kalshi API to monitor prediction markets.
It calculates RSI and Bollinger Bands, detects trading signals,
and makes trading decisions based on these advanced indicators.
The script also logs market data and sends notifications via Telegram.

Usage:
Ensure all required libraries are installed and API credentials are set.
Run the script to start monitoring Kalshi markets and execute trades
based on the defined strategies.

Note: This script involves financial trading. Use at your own risk and
always understand the implications of automated trading systems.
"""

import uuid
import time
import datetime
import kalshi_python
import numpy as np
import os
import csv
import re
import requests
from kalshi_python.rest import ApiException
from kalshi_python.models import *
from collections import deque

config = kalshi_python.Configuration()
config.host = 'https://trading-api.kalshi.com/trade-api/v2'
kalshi_api = kalshi_python.ApiInstance(email='', password='', configuration=config)

AUTO_TRADING_ENABLED, MAX_CONTRACTS, ACTIVE_MARKETS, VOLUME = True, 10, [], 100000
TOKEN, chat_id = "", '@kalshinotifications'

class MarketData:
    def __init__(self, event_ticker, market_ticker, event_title, market_subtitle, volume):
        self.event_ticker, self.market_ticker = event_ticker, market_ticker
        self.event_title, self.market_subtitle, self.volume = event_title, market_subtitle, volume
        self.prices = deque(maxlen=100)
        self.last_price, self.movement_type = None, None
        self.trade_direction = None
        self.last_csv_values = None
        self.current_order, self.current_order_uuid, self.order_price = None, None, None
        self.rsi_values = deque(maxlen=100)
        self.bollinger_band_values = deque(maxlen=100)

def create_order(market_ticker, side, count):
    try:
        order_uuid = str(uuid.uuid4())
        order = kalshi_api.create_order(CreateOrderRequest(
            ticker=market_ticker, action="buy", type="market", count=count, side=side, client_order_id=order_uuid
        )).order
        print(f"Created order: {order} with UUID: {order_uuid}")
        return order, order_uuid
    except ApiException as e:
        print(f"Error creating order: {e}")
        return None, None

def cancel_order(market_data):
    if market_data.current_order and market_data.current_order_uuid:
        try:
            kalshi_api.cancel_order(market_data.current_order.order_id)
            print(f"Cancelled order for {market_data.event_title} - {market_data.market_subtitle} with UUID: {market_data.current_order_uuid}")
            market_data.current_order, market_data.current_order_uuid = None, None
        except ApiException as e:
            print(f"Error cancelling order: {e}")

def send_telegram_message(text):
    return requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={"chat_id": chat_id, "text": text}).json()

def get_active_markets():
    global ACTIVE_MARKETS
    print("Fetching active markets...")
    try:
        events_response = kalshi_api.get_events(status="open")
        current_active_markets = []
        for event in events_response.events:
            for market in kalshi_api.get_event(event.event_ticker).markets:
                if market.status == "active":
                    existing_market = next((m for m in ACTIVE_MARKETS if m.market_ticker == market.ticker), None)
                    if existing_market:
                        existing_market.volume = market.volume
                        current_active_markets.append(existing_market)
                        print(f"Updated existing market: {existing_market.event_title} - {existing_market.market_subtitle}")
                    else:
                        new_market = MarketData(event.event_ticker, market.ticker, event.title, market.subtitle, market.volume)
                        current_active_markets.append(new_market)
                        print(f"Added new market: {new_market.event_title} - {new_market.market_subtitle}")
        ACTIVE_MARKETS = current_active_markets
        print(f"Total active markets: {len(ACTIVE_MARKETS)}")
        return ACTIVE_MARKETS
    except ApiException as e:
        print(f"Error fetching active markets: {e}")
        return []

def is_popular(market):
    return market.volume > VOLUME

def calculate_rsi(prices, period=14):
    prices = list(prices)
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices[-(period + 1):])
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    if down == 0:
        return 100
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(prices, period=20, num_std_dev=2):
    prices = list(prices)
    if len(prices) < period:
        return None, None, None
    prices = prices[-period:]
    sma = np.mean(prices)
    std_dev = np.std(prices)
    upper_band = sma + (std_dev * num_std_dev)
    lower_band = sma - (std_dev * num_std_dev)
    return upper_band, sma, lower_band

def get_file_path(market_data):
    KALSHI_MARKET_DATA_DIR = "KALSHI_MARKET_DATA"
    os.makedirs(KALSHI_MARKET_DATA_DIR, exist_ok=True)
    folder_name = re.sub(r'[<>:"/\\|?*]', '_', market_data.event_ticker)[:255]
    folder_path = os.path.join(KALSHI_MARKET_DATA_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    file_name = re.sub(r'[<>:"/\\|?*]', '_', f"{market_data.event_title}_{market_data.market_subtitle}.csv")[:255]
    return os.path.join(folder_path, file_name)

def update_csv(market_data, timestamp, last_price, rsi, upper_band, middle_band, lower_band, trade_sent):
    new_values = [
        timestamp, last_price, rsi or 0, upper_band or 0, middle_band or 0, lower_band or 0,
        trade_sent, market_data.trade_direction or 'none'
    ]
    header = [
        'Timestamp', 'Last Price', 'RSI', 'Upper Band', 'Middle Band', 'Lower Band',
        'Trade Sent', 'Trade Direction'
    ]
    file_path = get_file_path(market_data)
    file_exists = os.path.isfile(file_path)
    if market_data.last_csv_values is None or new_values[1] != market_data.last_csv_values[1]:
        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(header)
            writer.writerow(new_values)
        market_data.last_csv_values = new_values
        print(f"Updated CSV for {market_data.event_title} - {market_data.market_subtitle}: New last_price = {last_price}")
    else:
        print(f"No changes in last_price for {market_data.event_title} - {market_data.market_subtitle}")

def reset_market_data(market_data):
    market_data.trade_direction = None
    market_data.current_order, market_data.current_order_uuid, market_data.order_price = None, None, None

def monitor_market_price(market_data, market_number, total_markets):
    print(f"Monitoring market {market_number}/{total_markets}: {market_data.event_title} - {market_data.market_subtitle}")
    try:
        market_response = kalshi_api.get_market(market_data.market_ticker)
        current_last_price = market_response.market.last_price
        current_time = datetime.datetime.now().isoformat()

        print(f"DEBUG: Current market data: last_price={current_last_price}")

        if current_last_price != market_data.last_price:
            print(f"DEBUG: Price change detected: new last_price={current_last_price}, old last_price={market_data.last_price}")
            market_data.prices.append(current_last_price)
            market_data.last_price = current_last_price

            prices_list = list(market_data.prices)

            # Calculate RSI
            rsi = calculate_rsi(prices_list)
            market_data.rsi_values.append(rsi)

            # Calculate Bollinger Bands
            upper_band, middle_band, lower_band = calculate_bollinger_bands(prices_list)
            market_data.bollinger_band_values.append((upper_band, middle_band, lower_band))

            trade_sent = False

            # Trading logic based on RSI
            if rsi is not None and not market_data.current_order:
                if rsi < 30:
                    # Oversold condition, consider buying 'yes' side
                    print(f"RSI indicates oversold condition: RSI={rsi}")
                    if AUTO_TRADING_ENABLED:
                        market_data.trade_direction = 'yes'
                        market_data.order_price = current_last_price
                        order, order_uuid = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                        market_data.current_order = order
                        market_data.current_order_uuid = order_uuid
                        send_telegram_message(f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nAction: Buy YES side based on RSI oversold condition\nRSI: {rsi}")
                        trade_sent = True
                elif rsi > 70:
                    # Overbought condition, consider buying 'no' side
                    print(f"RSI indicates overbought condition: RSI={rsi}")
                    if AUTO_TRADING_ENABLED:
                        market_data.trade_direction = 'no'
                        market_data.order_price = current_last_price
                        order, order_uuid = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                        market_data.current_order = order
                        market_data.current_order_uuid = order_uuid
                        send_telegram_message(f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nAction: Buy NO side based on RSI overbought condition\nRSI: {rsi}")
                        trade_sent = True

            # Trading logic based on Bollinger Bands
            if upper_band is not None and lower_band is not None and not market_data.current_order:
                if current_last_price < lower_band:
                    # Price below lower Bollinger Band, consider buying 'yes' side
                    print(f"Price below lower Bollinger Band: Price={current_last_price}, Lower Band={lower_band}")
                    if AUTO_TRADING_ENABLED:
                        market_data.trade_direction = 'yes'
                        market_data.order_price = current_last_price
                        order, order_uuid = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                        market_data.current_order = order
                        market_data.current_order_uuid = order_uuid
                        send_telegram_message(f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nAction: Buy YES side based on Bollinger Bands\nPrice: {current_last_price}, Lower Band: {lower_band}")
                        trade_sent = True
                elif current_last_price > upper_band:
                    # Price above upper Bollinger Band, consider buying 'no' side
                    print(f"Price above upper Bollinger Band: Price={current_last_price}, Upper Band={upper_band}")
                    if AUTO_TRADING_ENABLED:
                        market_data.trade_direction = 'no'
                        market_data.order_price = current_last_price
                        order, order_uuid = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                        market_data.current_order = order
                        market_data.current_order_uuid = order_uuid
                        send_telegram_message(f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nAction: Buy NO side based on Bollinger Bands\nPrice: {current_last_price}, Upper Band: {upper_band}")
                        trade_sent = True

            # Exit logic
            if market_data.current_order and market_data.order_price:
                # Example exit condition: Close position if RSI returns to neutral range
                if 40 < rsi < 60:
                    print(f"RSI back to neutral range: RSI={rsi}. Closing position.")
                    cancel_order(market_data)
                    reset_market_data(market_data)
                # Example exit condition: Close position if price re-enters Bollinger Bands
                elif lower_band < current_last_price < upper_band:
                    print(f"Price re-entered Bollinger Bands. Closing position.")
                    cancel_order(market_data)
                    reset_market_data(market_data)

            update_csv(
                market_data, current_time, current_last_price, rsi,
                upper_band, middle_band, lower_band, trade_sent
            )
        else:
            print(f"DEBUG: No change in last_price for {market_data.event_title} - {market_data.market_subtitle}")
    except ApiException as e:
        print(f"DEBUG: Error monitoring market {market_data.market_ticker}: {e}")
    except Exception as e:
        print(f"DEBUG: Unexpected error in monitor_market_price: {e}")

def main():
    print("Starting Kalshi market monitoring script...")
    while True:
        try:
            get_active_markets()
            popular_markets = [market for market in ACTIVE_MARKETS if is_popular(market)]
            print(f"Found {len(popular_markets)} popular markets to monitor.")

            for i, market in enumerate(popular_markets, 1):
                monitor_market_price(market, i, len(popular_markets))

            print("Finished monitoring cycle. Waiting for 1 minute before next cycle...")
            time.sleep(60)
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            print("Waiting for 1 minute before retrying...")
            time.sleep(60)

if __name__ == "__main__":
    main()
