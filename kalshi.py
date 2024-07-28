import uuid
import time
import datetime
import kalshi_python
from kalshi_python.rest import ApiException
from kalshi_python.models import *
from pprint import pprint
import numpy as np
from collections import deque
import os
import csv
import pandas as pd
from scipy import stats
import re
import requests

config = kalshi_python.Configuration()
# Using production environment
config.host = 'https://trading-api.kalshi.com/trade-api/v2'

# Create an API configuration passing your credentials.
kalshi_api = kalshi_python.ApiInstance(
    email='email',
    password='password',
    configuration=config,
)

AUTO_TRADING_ENABLED = True  # Set this to True to enable auto-trading
MAX_CONTRACTS = 10  # Maximum number of contracts to trade

# Telegram Bot setup
TOKEN = ""
chat_id = '@'

class MarketData:
    def __init__(self, event_ticker, market_ticker, event_title, market_subtitle, volume):
        self.event_ticker = event_ticker
        self.market_ticker = market_ticker
        self.event_title = event_title
        self.market_subtitle = market_subtitle
        self.volume = volume
        self.prices = deque(maxlen=9)
        self.sma_values = deque(maxlen=5)
        self.last_update_time = None
        self.last_price = None
        self.movement_type = None
        self.up_signal = None
        self.down_signal = None
        self.signal_crossed = None
        self.crossed_prices = []
        self.trade_direction = None

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": text
    }
    response = requests.get(url, params=params)
    return response.json()

def get_active_markets():
    active_markets = []
    try:
        events_response = kalshi_api.get_events(status="open")
        print(f"Fetched {len(events_response.events)} open events.")
        for event in events_response.events:
            print(f"Processing event: {event.title}")
            event_data = kalshi_api.get_event(event.event_ticker)
            for market in event_data.markets:
                if market.status == "active":
                    active_markets.append(MarketData(event.event_ticker, market.ticker, event.title, market.subtitle, market.volume))
                    print(f"  Added active market: {market.subtitle}")
        print(f"Total active markets found: {len(active_markets)}")
    except ApiException as e:
        print(f"Error fetching active markets: {e}")
    return active_markets

def is_popular(market):
    VOLUME_THRESHOLD = 100000  # Example: consider markets with volume > 1000 as popular
    is_pop = market.volume > VOLUME_THRESHOLD
    print(f"Market {market.market_subtitle}: Volume = {market.volume}, Popular = {is_pop}")
    return is_pop

def calculate_sma9(prices):
    return np.mean(prices)

def detect_pattern(sma_values):
    if len(sma_values) < 5:
        return None
    if (sma_values[1] < sma_values[0] and sma_values[1] < sma_values[2] and
        sma_values[0] > sma_values[2] and sma_values[3] > sma_values[2] and
        sma_values[4] > sma_values[0]):
        return "up"
    elif (sma_values[1] > sma_values[0] and sma_values[1] > sma_values[2] and
          sma_values[0] < sma_values[2] and sma_values[3] < sma_values[2] and
          sma_values[4] < sma_values[0]):
        return "down"
    return None

def sanitize_filename(filename):
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename[:255]

def get_file_path(market_data):
    folder_name = sanitize_filename(market_data.event_ticker)
    file_name = sanitize_filename(f"{market_data.event_title}_{market_data.market_subtitle}.csv")
    os.makedirs(folder_name, exist_ok=True)
    return os.path.join(folder_name, file_name)

def reset_csv(market_data):
    file_path = get_file_path(market_data)
    headers = ['timestamp', 'yes_ask', 'yes_bid', 'no_ask', 'no_bid', 'total_avg', 'margin_of_error', 'std_dev', 'sma9_avg', 'sma9_3', 'pattern', 'trade_sent', 'signal_crossed', 'trade_direction']
    
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

def update_csv(market_data, timestamp, yes_ask, yes_bid, no_ask, no_bid, total_avg, margin_of_error, std_dev, sma9_avg, sma9_3, pattern, trade_sent):
    file_path = get_file_path(market_data)
    
    with open(file_path, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            yes_ask or 0,
            yes_bid or 0,
            no_ask or 0,
            no_bid or 0,
            total_avg or 0,
            margin_of_error or 0,
            std_dev or 0,
            sma9_avg or 0,
            sma9_3 or 0,
            pattern or 'none',
            trade_sent or False,
            market_data.signal_crossed or 'none',
            market_data.trade_direction or 'none'
        ])

def create_order(market_ticker, side, count):
    try:
        order_request = CreateOrderRequest(
            ticker=market_ticker,
            action="buy",
            type="market",
            count=count,
            side=side,
        )
        
        response = kalshi_api.create_order(order_request)
        print(f"Order created: {response.order}")
        return response.order
    except ApiException as e:
        print(f"Error creating order: {e}")
        return None

def close_order(order_id):
    try:
        response = kalshi_api.cancel_order(order_id)
        print(f"Order closed: {response}")
        return response
    except ApiException as e:
        print(f"Error closing order: {e}")
        return None

def check_confidence_interval(prices, current_price):
    if len(prices) < 2:
        return False
    mean = np.mean(prices)
    std_dev = np.std(prices)
    degrees_of_freedom = len(prices) - 1
    t_value_95 = stats.t.ppf(0.975, degrees_of_freedom)
    t_value_99 = stats.t.ppf(0.995, degrees_of_freedom)
    margin_of_error_95 = t_value_95 * (std_dev / np.sqrt(len(prices)))
    margin_of_error_99 = t_value_99 * (std_dev / np.sqrt(len(prices)))
    lower_bound_95 = mean - margin_of_error_95
    upper_bound_95 = mean + margin_of_error_95
    lower_bound_99 = mean - margin_of_error_99
    upper_bound_99 = mean + margin_of_error_99
    return lower_bound_95 <= current_price <= upper_bound_99

def monitor_market_price(market_data, market_number, total_markets):
    print(f"Monitoring market {market_number}/{total_markets}: {market_data.event_title} - {market_data.market_subtitle}")
    reset_csv(market_data)  # Reset CSV file at the start of monitoring
    
    try:
        market_response = kalshi_api.get_market(market_data.market_ticker)
        current_yes_ask = market_response.market.yes_ask
        current_yes_bid = market_response.market.yes_bid
        current_no_ask = market_response.market.no_ask
        current_no_bid = market_response.market.no_bid
        current_time = datetime.datetime.now().isoformat()

        if current_time != market_data.last_update_time:
            if market_data.last_price is not None and current_yes_bid != market_data.last_price:
                message = f"Price Update: {market_data.event_title} - {market_data.market_subtitle}\n"
                message += f"Volume: {market_data.volume}\n"
                message += f"New Yes Bid: {current_yes_bid}\n"
                message += f"Previous Yes Bid: {market_data.last_price}\n"
                message += f"Reason: Price change detected"
                send_telegram_message(message)

            market_data.prices.append(current_yes_bid)
            market_data.last_update_time = current_time
            market_data.last_price = current_yes_bid
            print(f"New price for {market_data.event_title} - {market_data.market_subtitle}: {current_yes_bid} at {current_time}")

            if len(market_data.prices) == 9:
                sma9 = calculate_sma9(market_data.prices)
                market_data.sma_values.appendleft(sma9)
                print(f"Calculated new SMA9 for {market_data.event_title} - {market_data.market_subtitle}: {sma9}")

                new_movement_type = detect_pattern(list(market_data.sma_values))
                if new_movement_type and new_movement_type != market_data.movement_type:
                    market_data.movement_type = new_movement_type
                    message = f"New Pattern: {market_data.event_title} - {market_data.market_subtitle}\n"
                    message += f"Volume: {market_data.volume}\n"
                    message += f"Yes Bid: {current_yes_bid}\n"
                    message += f"Pattern: {market_data.movement_type} movement\n"
                    message += f"Action: Consider opening a position based on the new pattern"
                    send_telegram_message(message)

                if market_data.movement_type:
                    sma9_3 = list(market_data.sma_values)[2] if len(market_data.sma_values) >= 3 else None
                    if sma9_3:
                        if market_data.movement_type == "up":
                            market_data.up_signal = sma9_3
                        elif market_data.movement_type == "down":
                            market_data.down_signal = sma9_3

                        if (market_data.movement_type == "up" and current_yes_bid > sma9_3 and market_data.signal_crossed != "up") or \
                           (market_data.movement_type == "down" and current_yes_bid < sma9_3 and market_data.signal_crossed != "down"):
                            market_data.signal_crossed = market_data.movement_type
                            market_data.crossed_prices = [current_yes_bid]
                            market_data.trade_direction = "yes" if market_data.movement_type == "up" else "no"
                            message = f"Alert: {market_data.event_title} - {market_data.market_subtitle}\n"
                            message += f"Volume: {market_data.volume}\n"
                            message += f"Yes Bid: {current_yes_bid}\n"
                            message += f"SMA9_3: {sma9_3}\n"
                            message += f"Direction: {market_data.movement_type}\n"
                            message += f"Action: Signal crossed, monitoring for trade opportunity"
                            send_telegram_message(message)
                        elif market_data.signal_crossed:
                            if (market_data.signal_crossed == "up" and current_yes_bid < market_data.crossed_prices[-1]) or \
                               (market_data.signal_crossed == "down" and current_yes_bid > market_data.crossed_prices[-1]):
                                market_data.crossed_prices.append(current_yes_bid)
                                if check_confidence_interval(market_data.crossed_prices, current_yes_bid) and AUTO_TRADING_ENABLED:
                                    order = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                                    if order:
                                        message = f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\n"
                                        message += f"Direction: {'Buy' if market_data.trade_direction == 'yes' else 'Sell'} {market_data.trade_direction.capitalize()}\n"
                                        message += f"Price: {current_yes_bid}\n"
                                        message += f"Contracts: {MAX_CONTRACTS}"
                                        send_telegram_message(message)
                            elif ((market_data.signal_crossed == "up" and current_yes_bid < sma9_3) or 
                                  (market_data.signal_crossed == "down" and current_yes_bid > sma9_3)):
                                market_data.signal_crossed = None
                                market_data.crossed_prices = []
                                market_data.trade_direction = None
                                message = f"Signal Reset: {market_data.event_title} - {market_data.market_subtitle}\n"
                                message += f"Yes Bid: {current_yes_bid}\n"
                                message += f"SMA9_3: {sma9_3}\n"
                                message += f"Reason: Price returned to SMA9_3"
                                send_telegram_message(message)

            total_avg = np.mean(market_data.prices)
            std_dev = np.std(market_data.prices)
            margin_of_error = stats.t.ppf(0.975, len(market_data.prices)-1) * (std_dev / np.sqrt(len(market_data.prices)))
            sma9_avg = np.mean(market_data.sma_values) if market_data.sma_values else None
            sma9_3 = list(market_data.sma_values)[2] if len(market_data.sma_values) >= 3 else None

            update_csv(market_data, current_time, current_yes_ask, current_yes_bid, current_no_ask, current_no_bid, total_avg, margin_of_error, std_dev, sma9_avg, sma9_3, market_data.movement_type, bool(market_data.trade_direction))

        else:
          print(f"No new data for {market_data.event_title} - {market_data.market_subtitle}")

    except ApiException as e:
        print(f"Error monitoring market {market_data.market_ticker}: {e}")

def main():
    print("Starting Kalshi market monitoring script...")
    
    while True:
        try:
            active_markets = get_active_markets()
            popular_markets = [market for market in active_markets if is_popular(market)]
            
            print(f"Found {len(popular_markets)} popular markets to monitor.")
            
            for i, market in enumerate(popular_markets, 1):
                monitor_market_price(market, i, len(popular_markets))
            
            print("Finished monitoring cycle. Waiting for 5 minutes before next cycle...")
            time.sleep(300)  # Wait for 5 minutes before the next cycle
        
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            print("Waiting for 5 minutes before retrying...")
            time.sleep(300)

if __name__ == "__main__":
    main()
