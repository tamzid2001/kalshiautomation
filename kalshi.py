import uuid
import time
import kalshi_python
from kalshi_python.models import *
from pprint import pprint
import numpy as np
from collections import deque
import os
import csv
import pandas as pd
from scipy import stats
# import telegram  # Commented out

config = kalshi_python.Configuration()
# Using production environment
# config.host = 'https://demo-api.kalshi.co/trade-api/v2'

# Create an API configuration passing your credentials.
kalshi_api = kalshi_python.ApiInstance(
    email='email',
    password='password',
    configuration=config,
)

# Telegram Bot setup
# bot = telegram.Bot(token='YOUR_TELEGRAM_BOT_TOKEN')
# chat_id = 'YOUR_CHAT_ID'

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
        self.movement_type = None

# def send_telegram_message(message):
#     bot.send_message(chat_id=chat_id, text=message)

def get_active_markets():
    active_markets = []
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

def get_file_path(market_data):
    folder_name = market_data.event_ticker
    file_name = f"{market_data.event_title}_{market_data.market_subtitle}.csv"
    os.makedirs(folder_name, exist_ok=True)
    return os.path.join(folder_name, file_name)

def update_csv(market_data, yes_price, no_price, fractal, total_avg, margin_of_error, std_dev, sma9_avg, sma9_3, pattern):
    file_path = get_file_path(market_data)
    headers = ['yes_price', 'no_price', 'fractal', 'total_avg', 'margin_of_error', 'std_dev', 'sma9_avg', 'sma9_3', 'pattern']
    
    if not os.path.exists(file_path):
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    with open(file_path, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([yes_price, no_price, fractal, total_avg, margin_of_error, std_dev, sma9_avg, sma9_3, pattern])

def calculate_fractal(prices):
    if len(prices) < 5:
        return "N/A"
    if prices[-3] < prices[-5] < prices[-4] > prices[-2] > prices[-1]:
        return "high"
    elif prices[-3] > prices[-5] > prices[-4] < prices[-2] < prices[-1]:
        return "low"
    return "none"

def monitor_market_price(market_data):
    print(f"Starting to monitor market: {market_data.event_title} - {market_data.market_subtitle}")
    crossing_points = []
    
    while True:
        market_response = kalshi_api.get_market(market_data.market_ticker)
        current_yes_price = market_response.market.yes_ask
        current_no_price = market_response.market.no_ask
        current_time = market_response.market.close_time

        if current_time != market_data.last_update_time:
            market_data.prices.append(current_yes_price)
            market_data.last_update_time = current_time
            print(f"New price for {market_data.event_title} - {market_data.market_subtitle}: {current_yes_price} at {current_time}")

            if len(market_data.prices) == 9:
                sma9 = calculate_sma9(market_data.prices)
                market_data.sma_values.appendleft(sma9)
                print(f"Calculated new SMA9 for {market_data.event_title} - {market_data.market_subtitle}: {sma9}")

                new_movement_type = detect_pattern(list(market_data.sma_values))
                if new_movement_type and new_movement_type != market_data.movement_type:
                    market_data.movement_type = new_movement_type
                    print(f"New pattern detected for {market_data.event_title} - {market_data.market_subtitle}: {market_data.movement_type} movement")
                    # send_telegram_message(f"New pattern detected for {market_data.event_title} - {market_data.market_subtitle}: {market_data.movement_type} movement")
                    print("Actionable Decision Point: Consider opening a position based on the new pattern.")

                if market_data.movement_type:
                    sma9_3 = list(market_data.sma_values)[2] if len(market_data.sma_values) >= 3 else None
                    if sma9_3:
                        if (market_data.movement_type == "up" and current_yes_price > sma9_3) or \
                           (market_data.movement_type == "down" and current_yes_price < sma9_3):
                            crossing_points.append(current_yes_price)
                            if len(crossing_points) >= 2:
                                avg = np.mean(crossing_points)
                                std = np.std(crossing_points)
                                margin_of_error = stats.t.ppf(0.975, len(crossing_points)-1) * (std / np.sqrt(len(crossing_points)))
                                lower_ci = avg - margin_of_error
                                upper_ci = avg + margin_of_error
                                
                                if lower_ci <= current_yes_price <= upper_ci:
                                    print(f"Alert: {market_data.event_title} - {market_data.market_subtitle} has crossed SMA9_3 ({sma9_3}) in the {market_data.movement_type} direction.")
                                    print(f"Current price: {current_yes_price}")
                                    print(f"95% Confidence Interval: [{lower_ci}, {upper_ci}]")
                                    # send_telegram_message(f"Alert: {market_data.event_title} - {market_data.market_subtitle} has crossed SMA9_3 ({sma9_3}) in the {market_data.movement_type} direction. Current price: {current_yes_price}")
                                    print("Actionable Decision Point: Consider closing or adjusting your position.")
                        else:
                            crossing_points = []

            fractal = calculate_fractal(list(market_data.prices))
            total_avg = np.mean(market_data.prices)
            std_dev = np.std(market_data.prices)
            margin_of_error = stats.t.ppf(0.975, len(market_data.prices)-1) * (std_dev / np.sqrt(len(market_data.prices)))
            sma9_avg = np.mean(market_data.sma_values) if market_data.sma_values else None
            sma9_3 = list(market_data.sma_values)[2] if len(market_data.sma_values) >= 3 else None

            update_csv(market_data, current_yes_price, current_no_price, fractal, total_avg, margin_of_error, std_dev, sma9_avg, sma9_3, market_data.movement_type)

        else:
            print(f"No new data for {market_data.event_title} - {market_data.market_subtitle}. Last price: {current_yes_price}")

        if market_response.market.status != "active":
            print(f"Market {market_data.event_title} - {market_data.market_subtitle} is no longer active. Removing CSV file.")
            os.remove(get_file_path(market_data))
            return False

        return True

def main():
    print("Starting Kalshi Market Analysis")
    while True:
        active_markets = get_active_markets()
        popular_markets = [market for market in active_markets if is_popular(market)]
        
        print(f"Total active markets: {len(active_markets)}")
        print(f"Popular markets: {len(popular_markets)}")
        
        for market_data in popular_markets:
            if not monitor_market_price(market_data):
                popular_markets.remove(market_data)
        
        print("Finished monitoring all markets. Waiting for 60 seconds before next cycle.")
        time.sleep(60)

if __name__ == "__main__":
    main()
