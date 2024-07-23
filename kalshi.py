import uuid
import time
import kalshi_python
from kalshi_python.models import *
from pprint import pprint
import numpy as np
from collections import deque

config = kalshi_python.Configuration()
# Using production environment
# config.host = 'https://demo-api.kalshi.co/trade-api/v2'

# Create an API configuration passing your credentials.
kalshi_api = kalshi_python.ApiInstance(
    email='EMAIL',
    password='PASSWORD',
    configuration=config,
)

class MarketData:
    def __init__(self, event_ticker, market_ticker):
        self.event_ticker = event_ticker
        self.market_ticker = market_ticker
        self.prices = deque(maxlen=9)
        self.sma_values = deque(maxlen=5)
        self.last_update_time = None
        self.movement_type = None

def get_active_markets():
    active_markets = []
    events_response = kalshi_api.get_events(status="open")
    print(f"Fetched {len(events_response.events)} open events.")
    for event in events_response.events:
        print(f"Processing event: {event.event_ticker}")
        event_data = kalshi_api.get_event(event.event_ticker)
        for market in event_data.markets:
            if market.status == "active":
                active_markets.append(market)
                print(f"  Added active market: {market.ticker}")
    print(f"Total active markets found: {len(active_markets)}")
    return active_markets

def is_popular(market):
    VOLUME_THRESHOLD = 1000  # Example: consider markets with volume > 1000 as popular
    is_pop = market.volume > VOLUME_THRESHOLD
    print(f"Market {market.ticker}: Volume = {market.volume}, Popular = {is_pop}")
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

def monitor_market_price(market_data):
    print(f"Starting to monitor market: {market_data.market_ticker}")
    while True:
        market_response = kalshi_api.get_market(market_data.market_ticker)
        current_price = market_response.market.last_price
        current_time = market_response.market.close_time  # Using close_time as a proxy for last update time

        if current_time != market_data.last_update_time:
            market_data.prices.append(current_price)
            market_data.last_update_time = current_time
            print(f"New price for {market_data.market_ticker}: {current_price} at {current_time}")

            if len(market_data.prices) == 9:
                sma9 = calculate_sma9(market_data.prices)
                market_data.sma_values.appendleft(sma9)
                print(f"Calculated new SMA9 for {market_data.market_ticker}: {sma9}")

                new_movement_type = detect_pattern(list(market_data.sma_values))
                if new_movement_type and new_movement_type != market_data.movement_type:
                    market_data.movement_type = new_movement_type
                    print(f"New pattern detected for {market_data.market_ticker}: {market_data.movement_type} movement")
                    print("Actionable Decision Point: Consider opening a position based on the new pattern.")

                if market_data.movement_type:
                    sma9_3 = list(market_data.sma_values)[2] if len(market_data.sma_values) >= 3 else None
                    if sma9_3:
                        if (market_data.movement_type == "up" and current_price > sma9_3) or \
                           (market_data.movement_type == "down" and current_price < sma9_3):
                            print(f"Alert: {market_data.market_ticker} has crossed SMA9_3 ({sma9_3}) in the {market_data.movement_type} direction.")
                            print(f"Current price: {current_price}")
                            print("Actionable Decision Point: Consider closing or adjusting your position.")
                            return  # Exit the function after alert

        else:
            print(f"No new data for {market_data.market_ticker}. Last price: {current_price}")

        print(f"Waiting for 60 seconds before next check on {market_data.market_ticker}")
        time.sleep(60)  # Wait for 1 minute before checking again

def main():
    print("Starting Kalshi Market Analysis")
    active_markets = get_active_markets()
    popular_markets = [market for market in active_markets if is_popular(market)]
    
    print(f"Total active markets: {len(active_markets)}")
    print(f"Popular markets: {len(popular_markets)}")
    
    market_data_array = [MarketData(market.event_ticker, market.ticker) for market in popular_markets]
    
    print("Starting to monitor popular markets")
    for market_data in market_data_array:
        print(f"Monitoring market: {market_data.market_ticker}")
        monitor_market_price(market_data)

if __name__ == "__main__":
    main()
