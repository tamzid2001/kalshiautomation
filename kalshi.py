"""
Kalshi Market Monitoring Script

This script monitors Kalshi prediction markets, analyzes price movements,
and executes trades based on specific patterns and confidence intervals.

Author: Tamzid Ullah
Website: https://tamzidullah.com
Email: tamzid257@gmail.com
GitHub: https://github.com/tamzid2001

Version: 1.0.0
Last Updated: 2024-08-03

License: MIT License

Copyright (c) 2024 Tamzid Ullah

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Description:
This script connects to the Kalshi API to monitor prediction markets.
It calculates Simple Moving Averages (SMA), detects price patterns,
and makes trading decisions based on confidence intervals. The script
also logs market data and sends notifications via Telegram.

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
from scipy import stats

config = kalshi_python.Configuration()
config.host = 'https://trading-api.kalshi.com/trade-api/v2'
kalshi_api = kalshi_python.ApiInstance(email='', password='', configuration=config)

AUTO_TRADING_ENABLED, MAX_CONTRACTS, ACTIVE_MARKETS, VOLUME = True, 10, [], 1000
TOKEN, chat_id = "", '@kalshinotifications'

class MarketData:
    def __init__(self, event_ticker, market_ticker, event_title, market_subtitle, volume):
        self.event_ticker = event_ticker
        self.market_ticker = market_ticker
        self.event_title = event_title
        self.market_subtitle = market_subtitle
        self.volume = volume
        self.prices = deque(maxlen=9)
        self.sma_values = deque(maxlen=5)
        self.last_price = None
        self.movement_type = None
        self.signal_data = {
            'up': {'sma9_3': None, 'crossed': False, 'price_updates_after_cross': 0},
            'down': {'sma9_3': None, 'crossed': False, 'price_updates_after_cross': 0}
        }
        self.trade_direction = None
        self.crossed_prices = []
        self.last_yes_ask = None
        self.last_yes_bid = None
        self.last_no_ask = None
        self.last_no_bid = None
        self.last_total_avg = None
        self.last_margin_of_error_95 = None
        self.last_margin_of_error_9999 = None
        self.last_std_dev = None
        self.last_sma9_avg = None
        self.last_sma9_3 = None
        self.last_pattern = None
        self.last_trade_sent = None
        self.last_csv_values = None
        self.current_order = None
        self.current_order_uuid = None
        self.order_price = None

    def print_attributes(self):
        for attr, value in self.__dict__.items():
            print(f"{attr}: {value}")

def create_order(market_ticker, side, count):
    try:
        order_uuid = str(uuid.uuid4())
        order = kalshi_api.create_order(CreateOrderRequest(
            ticker=market_ticker,
            action="buy",
            type="market",
            count=count,
            side=side,
            client_order_id=order_uuid
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
            market_data.current_order = None
            market_data.current_order_uuid = None
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
                    # Check if this market already exists in ACTIVE_MARKETS
                    existing_market = next((m for m in ACTIVE_MARKETS if m.market_ticker == market.ticker), None)
                    
                    if existing_market:
                        # Update existing market data
                        existing_market.volume = market.volume
                        current_active_markets.append(existing_market)
                        print(f"Updated existing market: {existing_market.event_title} - {existing_market.market_subtitle}")
                    else:
                        # Create new MarketData object for new market
                        new_market = MarketData(event.event_ticker, market.ticker, event.title, market.subtitle, market.volume)
                        current_active_markets.append(new_market)
                        print(f"Added new market: {new_market.event_title} - {new_market.market_subtitle}")
        
        # Update ACTIVE_MARKETS with the current list
        ACTIVE_MARKETS = current_active_markets
        
        print(f"Total active markets: {len(ACTIVE_MARKETS)}")
        return ACTIVE_MARKETS
    except ApiException as e:
        print(f"Error fetching active markets: {e}")
        return []

def is_popular(market):
    return market.volume > VOLUME

def calculate_sma9(prices):
    return np.mean(prices)

def detect_pattern(sma_values):
    if len(sma_values) < 5:
        return None
    
    sma9_1 = sma_values[1]
    sma9_2 = sma_values[2]
    sma9_3 = sma_values[3]
    sma9_4 = sma_values[4]
    sma9_5 = sma_values[0]
    
    # Detect down pattern
    if sma9_2 > sma9_1 and sma9_2 > sma9_3 and sma9_1 < sma9_3 and sma9_4 < sma9_3 and sma9_5 < sma9_1:
        return "down"
    
    # Detect up pattern (vice versa of down pattern)
    if sma9_2 < sma9_1 and sma9_2 < sma9_3 and sma9_1 > sma9_3 and sma9_4 > sma9_3 and sma9_5 > sma9_1:
        return "up"
    
    # If neither pattern is detected
    return None

def get_file_path(market_data):
    KALSHI_MARKET_DATA_DIR = "KALSHI_MARKET_DATA"
    os.makedirs(KALSHI_MARKET_DATA_DIR, exist_ok=True)
    folder_name = re.sub(r'[<>:"/\\|?*]', '_', market_data.event_ticker)[:255]
    folder_path = os.path.join(KALSHI_MARKET_DATA_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    file_name = re.sub(r'[<>:"/\\|?*]', '_', f"{market_data.event_title}_{market_data.market_subtitle}.csv")[:255]
    return os.path.join(folder_path, file_name)

def update_csv(market_data, timestamp, yes_ask, yes_bid, no_ask, no_bid, sma9_avg, sma9_3, pattern, trade_sent):
    signal_crossed = 'up' if market_data.signal_data['up']['crossed'] else ('down' if market_data.signal_data['down']['crossed'] else 'none')
    new_values = [
        timestamp, yes_ask, yes_bid, no_ask, no_bid, total_avg, 
        margin_of_error_95 or 0, margin_of_error_9999 or 0, std_dev or 0, 
        sma9_avg or 0, sma9_3 or 0, pattern or 'none', trade_sent, 
        signal_crossed, market_data.trade_direction or 'none'
    ]
    if market_data.last_csv_values is None or new_values[2] != market_data.last_csv_values[2]:  # Check if yes_bid has changed
        with open(get_file_path(market_data), 'a', newline='') as f:
            csv.writer(f).writerow(new_values)
        market_data.last_csv_values = new_values
        market_data.last_yes_ask, market_data.last_yes_bid = yes_ask, yes_bid
        market_data.last_no_ask, market_data.last_no_bid = no_ask, no_bid
        market_data.last_total_avg = total_avg
        market_data.last_margin_of_error_95 = margin_of_error_95
        market_data.last_margin_of_error_9999 = margin_of_error_9999
        market_data.last_std_dev, market_data.last_sma9_avg = std_dev, sma9_avg
        market_data.last_sma9_3, market_data.last_pattern = sma9_3, pattern
        market_data.last_trade_sent = trade_sent
        market_data.last_trade_direction = market_data.trade_direction
        print(f"Updated CSV for {market_data.event_title} - {market_data.market_subtitle}: New yes_bid = {yes_bid}")
    else:
        print(f"No changes in yes_bid for {market_data.event_title} - {market_data.market_subtitle}")

def check_confidence_interval(prices, current_price):
    if len(prices) < 2:
        return False
    mean, std_dev = np.mean(prices), np.std(prices)
    t_value_95 = stats.t.ppf(0.975, len(prices) - 1)
    margin_of_error = t_value_95 * (std_dev / np.sqrt(len(prices)))
    return mean - margin_of_error <= current_price <= mean + margin_of_error

def reset_market_data(market_data):
    market_data.signal_data = {'up': {'sma9_3': None, 'crossed': False, 'price_updates_after_cross': 0}, 
                               'down': {'sma9_3': None, 'crossed': False, 'price_updates_after_cross': 0}}
    market_data.trade_direction = None
    market_data.crossed_prices = []
    market_data.current_order = None
    market_data.current_order_uuid = None
    market_data.order_price = None

def monitor_market_price(market_data, market_number, total_markets):
    print(f"Monitoring market {market_number}/{total_markets}: {market_data.event_title} - {market_data.market_subtitle}")
    try:
        market_response = kalshi_api.get_market(market_data.market_ticker)
        current_yes_ask, current_yes_bid = market_response.market.yes_ask, market_response.market.yes_bid
        current_no_ask, current_no_bid = market_response.market.no_ask, market_response.market.no_bid
        current_time = datetime.datetime.now().isoformat()

        print(f"DEBUG: Current market data: yes_ask={current_yes_ask}, yes_bid={current_yes_bid}, no_ask={current_no_ask}, no_bid={current_no_bid}")

        if current_yes_bid != market_data.last_yes_bid:
            print(f"DEBUG: Price change detected: new yes_bid={current_yes_bid}, old yes_bid={market_data.last_yes_bid}")
            if market_data.last_price is not None:
                send_telegram_message(f"Price Update: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nNew Yes Bid: {current_yes_bid}\nPrevious Yes Bid: {market_data.last_price}\nReason: Price change detected")
            
            market_data.prices.append(current_yes_bid)
            market_data.last_price = current_yes_bid

            sma9_avg = sma9_3 = None
            pattern = None

            if len(market_data.prices) >= 9:
                print("DEBUG: Calculating SMA9 and detecting patterns")
                sma9 = calculate_sma9(list(market_data.prices)[-9:])
                
                if len(market_data.sma_values) == 5:
                    market_data.sma_values.pop()
                market_data.sma_values.appendleft(sma9)
                
                sma9_avg = np.mean(market_data.sma_values)

                if len(market_data.sma_values) == 5:
                    new_movement_type = detect_pattern(list(market_data.sma_values))
                    print(f"DEBUG: New movement type detected: {new_movement_type}")
                    
                    if new_movement_type and new_movement_type != market_data.movement_type:
                        market_data.movement_type = new_movement_type
                        pattern = new_movement_type
                        sma9_3 = list(market_data.sma_values)[2]
                        
                        # Update signal data
                        market_data.signal_data[new_movement_type]['sma9_3'] = sma9_3
                        market_data.signal_data[new_movement_type]['crossed'] = False
                        market_data.signal_data[new_movement_type]['price_updates_after_cross'] = 0
                        
                        send_telegram_message(f"New Pattern: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nYes Bid: {current_yes_bid}\nPattern: {market_data.movement_type} movement\nAction: Consider opening a position based on the new pattern")

                print(f"DEBUG: Checking for signal cross: movement_type={market_data.movement_type}, current_yes_bid={current_yes_bid}, signal_data={market_data.signal_data}")
                
                # Check for signal crossing
                for direction in ['up', 'down']:
                    if market_data.signal_data[direction]['sma9_3'] is not None:
                        if (direction == 'up' and current_yes_bid > market_data.signal_data[direction]['sma9_3']) or \
                           (direction == 'down' and current_yes_bid < market_data.signal_data[direction]['sma9_3']):
                            if not market_data.signal_data[direction]['crossed']:
                                market_data.signal_data[direction]['crossed'] = True
                                market_data.signal_data[direction]['price_updates_after_cross'] = 0
                                market_data.crossed_prices = []  # Reset crossed_prices when a new signal is crossed
                                print(f"DEBUG: Signal crossed for {direction} direction")
                                send_telegram_message(f"Alert: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nYes Bid: {current_yes_bid}\nDirection: {direction}\nAction: Signal crossed, monitoring for trade opportunity")
                            else:
                                market_data.signal_data[direction]['price_updates_after_cross'] += 1
                                # Update crossed_prices array
                                if direction == 'up' and (not market_data.crossed_prices or current_yes_bid > market_data.crossed_prices[-1]):
                                    market_data.crossed_prices.append(current_yes_bid)
                                elif direction == 'down' and (not market_data.crossed_prices or current_yes_bid < market_data.crossed_prices[-1]):
                                    market_data.crossed_prices.append(current_yes_bid)

                # Check for trade opportunity
                if market_data.signal_data['up']['crossed'] != market_data.signal_data['down']['crossed']:
                    crossed_direction = 'up' if market_data.signal_data['up']['crossed'] else 'down'
                    uncrossed_direction = 'down' if crossed_direction == 'up' else 'up'
                    
                    if market_data.signal_data[crossed_direction]['sma9_3'] is not None and \
                       market_data.signal_data[uncrossed_direction]['sma9_3'] is not None and \
                       market_data.signal_data[crossed_direction]['price_updates_after_cross'] >= 2:
                        
                        signal_difference = abs(market_data.signal_data['up']['sma9_3'] - market_data.signal_data['down']['sma9_3'])
                        current_spread = current_yes_ask - current_no_bid
                        
                        if signal_difference > current_spread:
                            market_data.trade_direction = 'yes' if crossed_direction == 'up' else 'no'
                            order, order_uuid = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                            print(f"DEBUG: Trade opportunity detected. Direction: {market_data.trade_direction}")

                # Check for exit condition
                if market_data.current_order and market_data.order_price:
                    exit_price = current_yes_bid if market_data.trade_direction == 'yes' else current_no_bid
                    if (market_data.trade_direction == 'yes' and exit_price < market_data.order_price) or \
                       (market_data.trade_direction == 'no' and exit_price > market_data.order_price):
                        print(f"DEBUG: Exit condition met. Cancelling order with UUID: {market_data.current_order_uuid}")
                        cancel_order(market_data)
                        reset_market_data(market_data)
            
            # Determine if a trade was sent in this cycle
            trade_sent = market_data.current_order is not None and market_data.current_order_uuid is not None
    
            update_csv(market_data, current_time, current_yes_ask, current_yes_bid, current_no_ask, current_no_bid, sma9_avg, sma9_3, pattern, trade_sent)
        else:
            print(f"DEBUG: No change in yes_bid for {market_data.event_title} - {market_data.market_subtitle}")
    except ApiException as e:
        print(f"DEBUG: Error monitoring market {market_data.market_ticker}: {e}")
    except Exception as e:
        print(f"DEBUG: Unexpected error in monitor_market_price: {e}")

def main():
    print("Starting Kalshi market monitoring script...")

    while True:
        try:
            get_active_markets()  # This will update the global ACTIVE_MARKETS list
            popular_markets = [market for market in ACTIVE_MARKETS if is_popular(market)]
            print(f"Found {len(popular_markets)} popular markets to monitor.")
            
            for i, market in enumerate(popular_markets, 1):
                monitor_market_price(market, i, len(popular_markets))
            
            print("Finished monitoring cycle. Waiting for 1 minute(s) before next cycle...")
            time.sleep(60)
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            print("Waiting for 1 minute(s) before retrying...")
            time.sleep(60)

if __name__ == "__main__":
    main()
