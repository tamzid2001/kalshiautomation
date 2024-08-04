import uuid
import time
import datetime
import kalshi_python
import numpy as np
import os
import csv
import pandas as pd
import re
import requests
from kalshi_python.rest import ApiException
from kalshi_python.models import *
from collections import deque
from scipy import stats

config = kalshi_python.Configuration()
config.host = 'https://trading-api.kalshi.com/trade-api/v2'
kalshi_api = kalshi_python.ApiInstance(email='', password='', configuration=config)

AUTO_TRADING_ENABLED, MAX_CONTRACTS, ACTIVE_MARKETS = True, 10, []
TOKEN, chat_id = "", '@kalshinotifications'

class MarketData:
    def __init__(self, event_ticker, market_ticker, event_title, market_subtitle, volume):
        self.event_ticker, self.market_ticker, self.event_title, self.market_subtitle, self.volume = event_ticker, market_ticker, event_title, market_subtitle, volume
        self.prices, self.sma_values = deque(maxlen=9), deque(maxlen=5)
        self.last_price = self.movement_type = self.up_signal = self.down_signal = self.signal_crossed = self.trade_direction = None
        self.crossed_prices = []
        self.last_yes_ask = self.last_yes_bid = self.last_no_ask = self.last_no_bid = None
        self.last_total_avg = self.last_margin_of_error = self.last_std_dev = self.last_sma9_avg = self.last_sma9_3 = None
        self.last_pattern = self.last_trade_sent = self.last_signal_crossed = self.last_trade_direction = None
        self.last_csv_values = None

    def print_attributes(self):
        for attr, value in self.__dict__.items():
            print(f"{attr}: {value}")

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
    return market.volume > 100000

def calculate_sma9(prices):
    return np.mean(prices)

def detect_pattern(sma_values):
    if len(sma_values) < 5:
        return None
    if sma_values[1] < sma_values[0] < sma_values[4] and sma_values[1] < sma_values[2] < sma_values[3]:
        return "up"
    elif sma_values[1] > sma_values[0] > sma_values[4] and sma_values[1] > sma_values[2] > sma_values[3]:
        return "down"
    return None

def get_file_path(market_data):
    folder_name = re.sub(r'[<>:"/\\|?*]', '_', market_data.event_ticker)[:255]
    file_name = re.sub(r'[<>:"/\\|?*]', '_', f"{market_data.event_title}_{market_data.market_subtitle}.csv")[:255]
    os.makedirs(folder_name, exist_ok=True)
    return os.path.join(folder_name, file_name)

def reset_csv(market_data):
    with open(get_file_path(market_data), 'w', newline='') as f:
        csv.writer(f).writerow(['timestamp', 'yes_ask', 'yes_bid', 'no_ask', 'no_bid', 'total_avg', 'margin_of_error', 'std_dev', 'sma9_avg', 'sma9_3', 'pattern', 'trade_sent', 'signal_crossed', 'trade_direction'])

def update_csv(market_data, timestamp, yes_ask, yes_bid, no_ask, no_bid, total_avg, margin_of_error_95, margin_of_error_9999, std_dev, sma9_avg, sma9_3, pattern, trade_sent):
    new_values = [timestamp, yes_ask, yes_bid, no_ask, no_bid, total_avg, margin_of_error_95 or 0, margin_of_error_9999 or 0, std_dev or 0, sma9_avg or 0, sma9_3 or 0, pattern or 'none', trade_sent, market_data.signal_crossed or 'none', market_data.trade_direction or 'none']
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
        market_data.last_signal_crossed = market_data.signal_crossed
        market_data.last_trade_direction = market_data.trade_direction
        print(f"Updated CSV for {market_data.event_title} - {market_data.market_subtitle}: New yes_bid = {yes_bid}")
    else:
        print(f"No changes in yes_bid for {market_data.event_title} - {market_data.market_subtitle}")

def create_order(market_ticker, side, count):
    try:
        return kalshi_api.create_order(CreateOrderRequest(ticker=market_ticker, action="buy", type="market", count=count, side=side)).order
    except ApiException as e:
        print(f"Error creating order: {e}")
        return None

def check_confidence_interval(prices, current_price):
    if len(prices) < 2:
        return False
    mean, std_dev = np.mean(prices), np.std(prices)
    t_value_95 = stats.t.ppf(0.975, len(prices) - 1)
    margin_of_error = t_value_95 * (std_dev / np.sqrt(len(prices)))
    return mean - margin_of_error <= current_price <= mean + margin_of_error

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
                sma9 = calculate_sma9(market_data.prices)
                market_data.sma_values.appendleft(sma9)
                sma9_avg = np.mean(market_data.sma_values)
                if len(market_data.sma_values) >= 3:
                    sma9_3 = list(market_data.sma_values)[2]
                new_movement_type = detect_pattern(list(market_data.sma_values))
                print(f"DEBUG: New movement type detected: {new_movement_type}")
                if new_movement_type and new_movement_type != market_data.movement_type:
                    market_data.movement_type = new_movement_type
                    pattern = new_movement_type
                    send_telegram_message(f"New Pattern: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nYes Bid: {current_yes_bid}\nPattern: {market_data.movement_type} movement\nAction: Consider opening a position based on the new pattern")

                if market_data.movement_type and sma9_3:
                    market_data.up_signal = sma9_3 if market_data.movement_type == "up" else market_data.up_signal
                    market_data.down_signal = sma9_3 if market_data.movement_type == "down" else market_data.down_signal

                print(f"DEBUG: Checking for signal cross: movement_type={market_data.movement_type}, current_yes_bid={current_yes_bid}, sma9_3={sma9_3}, signal_crossed={market_data.signal_crossed}")
                if (market_data.movement_type == "up" and current_yes_bid > sma9_3 and market_data.signal_crossed != "up") or \
                   (market_data.movement_type == "down" and current_yes_bid < sma9_3 and market_data.signal_crossed != "down"):
                    market_data.signal_crossed = market_data.movement_type
                    market_data.crossed_prices = [current_yes_bid]
                    market_data.trade_direction = "yes" if market_data.movement_type == "up" else "no"
                    print(f"DEBUG: Signal crossed: direction={market_data.signal_crossed}, trade_direction={market_data.trade_direction}")
                    send_telegram_message(f"Alert: {market_data.event_title} - {market_data.market_subtitle}\nVolume: {market_data.volume}\nYes Bid: {current_yes_bid}\nSMA9_3: {sma9_3}\nDirection: {market_data.movement_type}\nAction: Signal crossed, monitoring for trade opportunity")

                elif market_data.signal_crossed:
                    print(f"DEBUG: Monitoring crossed signal: signal_crossed={market_data.signal_crossed}, current_yes_bid={current_yes_bid}, last_crossed_price={market_data.crossed_prices[-1]}")
                    if (market_data.signal_crossed == "up" and current_yes_bid < market_data.crossed_prices[-1]) or \
                       (market_data.signal_crossed == "down" and current_yes_bid > market_data.crossed_prices[-1]):
                        market_data.crossed_prices.append(current_yes_bid)
                        print(f"DEBUG: Price reversal detected. Checking confidence interval.")
                        
                        # Calculate confidence intervals only if we have enough data points
                        if len(market_data.crossed_prices) > 1:
                            prices_array = np.array(market_data.crossed_prices)
                            n = len(prices_array)
                            mean = np.mean(prices_array)
                            std_dev = np.std(prices_array, ddof=1)  # Using n-1 for sample standard deviation
                            
                            # Standard Error of the Mean (SEM)
                            sem = std_dev / np.sqrt(n)
                            
                            # 95% Confidence Interval
                            ci_95 = stats.t.interval(confidence=0.95, df=n-1, loc=mean, scale=sem)
                            margin_of_error_95 = (ci_95[1] - ci_95[0]) / 2
                            
                            # 99.99% Confidence Interval
                            ci_9999 = stats.t.interval(confidence=0.9999, df=n-1, loc=mean, scale=sem)
                            margin_of_error_9999 = (ci_9999[1] - ci_9999[0]) / 2
                            
                            print(f"DEBUG: 95% Confidence Interval: {ci_95}")
                            print(f"DEBUG: 99.99% Confidence Interval: {ci_9999}")
                            print(f"DEBUG: 95% Margin of Error: {margin_of_error_95}")
                            print(f"DEBUG: 99.99% Margin of Error: {margin_of_error_9999}")

                            if ci_95[0] <= current_yes_bid <= ci_95[1] and AUTO_TRADING_ENABLED:
                                print("DEBUG: Price within 95% confidence interval. Creating order.")
                                order = create_order(market_data.market_ticker, market_data.trade_direction, MAX_CONTRACTS)
                                if order:
                                    send_telegram_message(f"Trade Executed: {market_data.event_title} - {market_data.market_subtitle}\nDirection: {'Buy' if market_data.trade_direction == 'yes' else 'Sell'} {market_data.trade_direction.capitalize()}\nPrice: {current_yes_bid}\nContracts: {MAX_CONTRACTS}\n95% CI: {ci_95}\n99.99% CI: {ci_9999}")
                        else:
                            print("DEBUG: Not enough data points for confidence interval calculation.")
                    elif ((market_data.signal_crossed == "up" and current_yes_bid < sma9_3) or (market_data.signal_crossed == "down" and current_yes_bid > sma9_3)):
                        print("DEBUG: Signal reset condition met.")
                        market_data.signal_crossed = market_data.crossed_prices = market_data.trade_direction = None
                        send_telegram_message(f"Signal Reset: {market_data.event_title} - {market_data.market_subtitle}\nYes Bid: {current_yes_bid}\nSMA9_3: {sma9_3}\nReason: Price returned to SMA9_3")

            # Calculate overall statistics
            total_avg = np.mean(market_data.prices)
            std_dev = np.std(market_data.prices, ddof=1) if len(market_data.prices) > 1 else 0
            n = len(market_data.prices)
            
            margin_of_error_95 = margin_of_error_9999 = 0
            if n > 1:
                sem = std_dev / np.sqrt(n)
                
                # 95% Confidence Interval
                ci_95 = stats.t.interval(0.95, df=n-1, loc=total_avg, scale=sem)
                margin_of_error_95 = (ci_95[1] - ci_95[0]) / 2
                
                # 99.99% Confidence Interval
                ci_9999 = stats.t.interval(0.9999, df=n-1, loc=total_avg, scale=sem)
                margin_of_error_9999 = (ci_9999[1] - ci_9999[0]) / 2
            
            update_csv(market_data, current_time, current_yes_ask, current_yes_bid, current_no_ask, current_no_bid, 
                       total_avg, margin_of_error_95, margin_of_error_9999, std_dev, sma9_avg, sma9_3, pattern, 
                       bool(market_data.trade_direction))
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
            
            # Reset or create CSV files only for popular markets
            for market in popular_markets:
                file_path = get_file_path(market)
                if os.path.exists(file_path):
                    print(f"Existing CSV file found for {market.event_title} - {market.market_subtitle}. Resetting...")
                    reset_csv(market)
                else:
                    print(f"Creating new CSV file for {market.event_title} - {market.market_subtitle}")
                    reset_csv(market)

                print("\nMarket data:")
                market.print_attributes()
                print()  # Add a blank line for readability

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
