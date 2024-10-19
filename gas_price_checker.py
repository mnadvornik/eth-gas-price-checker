import os
import time
import requests
import logging
import asyncio
from telegram import Bot
from telegram.error import TelegramError


# Configure logging to output to the Docker console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Read environment variables for Telegram bot and chat details
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'default_token')
chat_id = os.getenv('TELEGRAM_CHAT_ID', 'default_chat_id')

# Read the state file path from environment variables (default to /data/notified_state.txt)
state_file_path = os.getenv('STATE_FILE_PATH', '/data/notified_state.txt')

# Read the Etherscan API key from environment variables
etherscan_api_key = os.getenv('ETHERSCAN_API_KEY', 'default_api_key')

# API URL
api_url = f'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey={etherscan_api_key}'

#Threshold
try:
    gas_fee_threshold = float(os.getenv('GAS_FEE_THRESHOLD', '100'))
except ValueError:
    logging.warning(f"Invalid GAS_FEE_THRESHOLD value")
    gas_fee_threshold = 100.0

#Interval in seconds to check for update
try:
    check_interval = int(os.getenv('CHECK_INTERVAL', '300'))
except ValueError:
    logging.warning(f"Invalid CHECK_INTERVAL value")
    check_interval = 300

# Function to send a Telegram message
async def send_telegram_message(message):
    bot = Bot(token=telegram_bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        logging.info(f'Telegram notification sent: {message}')
    except TelegramError as e:
        logging.error(f'Failed to send Telegram message: {str(e)}')

# Function to read the current state from a file, create it with False if it doesn't exist
def read_state():
    if not os.path.exists(state_file_path):
        # If the state file doesn't exist, create it with the initial value of False
        with open(state_file_path, 'w') as file:
            file.write('False')
        logging.info(f"State file not found. Created {state_file_path} with default value 'False'.")
        return False
    
    # If the file exists, read the state from the file
    with open(state_file_path, 'r') as file:
        state = file.read().strip() == 'True'
        logging.info(f"State file content: {state}")
        return state


# Function to write the current state to a file
def write_state(state):
    with open(state_file_path, 'w') as file:
        file.write(str(state))

# Function to check the gas price and send a notification if needed
async def check_gas_price_and_notify():
    logging.info(f"Checking if gas fee is below {gas_fee_threshold}...")
    
    # Read the current state (True means notification has been sent, False means it hasn't)
    notified_state = read_state()

    try:
        # Make the API request
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception if the request was unsuccessful
        
        # Parse the JSON response
        data = response.json()
        
        if data['status'] == '1':  # Ensure the API request was successful
            propose_gas_price = float(data['result']['ProposeGasPrice'])
            
            # Check if the ProposeGasPrice falls below notified_state and hasn't already triggered an alert
            if propose_gas_price < gas_fee_threshold and not notified_state:
                message = f'ETH Average Gas Fee ist unterhalb vom Grenzwert {gas_fee_threshold}: {propose_gas_price}'
                await send_telegram_message(message)
                write_state(True)  # Mark that the alert has been sent by writing to the file
            # Check if the ProposeGasPrice rises above notified_state, reset the alert state
            elif propose_gas_price >= gas_fee_threshold and notified_state:
                write_state(False)  # Reset the state for future alerts
                logging.info(f'ProposeGasPrice is {propose_gas_price}, resetting alert state.')
            else:
                logging.info(f'ProposeGasPrice is {propose_gas_price}, no action taken.')
        else:
            # Send a Telegram message if the API response is not OK
            await send_telegram_message(f'API request failed with message: {data["message"]}')
    except requests.RequestException as e:
        # Send a Telegram message if there's an exception (e.g., network failure)
        await send_telegram_message(f'API request failed with exception: {str(e)}')

# Main loop to check the gas price every 5 minutes
async def main_loop():
    while True:
        await check_gas_price_and_notify()
        await asyncio.sleep(check_interval)  # Wait before checking again

# Run the main loop
if __name__ == "__main__":
    asyncio.run(main_loop())
