import requests
import time
import os

# API endpoint URLs
API_URL_EXECUTE = os.getenv("API_URL_EXECUTE", "http://localhost:8000/trade/execute") 
API_URL_TSL = os.getenv("API_URL_TSL", "http://localhost:8000/trade/update-tsl") 

def run_scheduler():
    print("--- Scheduler started. Looking for trading opportunities... ---")
    while True:
        try:
            # 1. Main call to analyze and execute trades
            print(f"\n[{time.strftime('%H:%M:%S')}] Requesting analysis and execution at: {API_URL_EXECUTE}")
            response = requests.get(API_URL_EXECUTE, timeout=30)
            response.raise_for_status() # Raise an error for 4xx/5xx codes
            result = response.json()
            
            if 'data' in result and 'decision' in result['data']:
                print(f"Decision: {result['data']['decision']}")
            if 'status' in result:
                print(f"Execution status: {result['status']}")

        except requests.exceptions.RequestException as e:
            print(f"Error calling execution API: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during execution: {e}")

        # Short pause for the system to process the order before checking TSL
        time.sleep(5)

        try:
            # 2. Call to update the Trailing Stop-Loss
            print(f"[{time.strftime('%H:%M:%S')}] Checking Trailing Stop-Loss at: {API_URL_TSL}")
            tsl_response = requests.get(API_URL_TSL, timeout=15)
            tsl_response.raise_for_status()
            tsl_result = tsl_response.json()
            print(f"TSL status: {tsl_result.get('status', 'unknown')}")

        except requests.exceptions.RequestException as e:
            print(f"Error calling TSL API: {e}")
        except Exception as e:
            print(f"An unexpected error occurred in TSL: {e}")

        # Wait for the rest of the cycle (total ~60 seconds)
        time.sleep(55) 

if __name__ == "__main__":
    run_scheduler()