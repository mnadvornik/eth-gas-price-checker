import os
import time
import requests
import logging
import asyncio
import signal
from telegram import Bot
from telegram.error import TelegramError

# Map the logging level string from the environment variable to a logging constant
def get_logging_level():
    log_level = os.getenv('LOGGING_LEVEL', 'INFO').upper()  # Default to INFO if not set
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return log_levels.get(log_level, logging.INFO)  # Default to INFO if invalid value

# Configure logging with a level from the environment variable
logging.basicConfig(level=get_logging_level(), format='%(asctime)s - %(levelname)s - %(message)s')


# Read environment variables for Telegram bot and chat details
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'default_token')
chat_id = os.getenv('TELEGRAM_CHAT_ID', 'default_chat_id')

# Read the Etherscan API key from environment variables
etherscan_api_key = os.getenv('ETHERSCAN_API_KEY', 'default_api_key')

# API URL
api_url = f'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey={etherscan_api_key}'

# Threshold
try:
    gas_fee_lower_threshold = float(os.getenv('GAS_FEE_LOWER_THRESHOLD', '30'))
except ValueError:
    logging.warning(f"Invalid gas_fee_lower_threshold value")
    gas_fee_lower_threshold = 30.0
try:
    gas_fee_upper_threshold = float(os.getenv('GAS_FEE_UPPER_THRESHOLD', '50'))
except ValueError:
    logging.warning(f"Invalid gas_fee_upper_threshold value")
    gas_fee_upper_threshold = 50.0

# Interval in seconds to check for update
try:
    check_interval = int(os.getenv('CHECK_INTERVAL', '300'))
except ValueError:
    logging.warning(f"Invalid CHECK_INTERVAL value")
    check_interval = 300

# Track whether the program should stop (for graceful shutdown)
shutdown_flag = False

# Tracking Variables
last_message_id_in_range = None
last_price = -1

# Send a Telegram message
async def send_telegram_message(message):
    bot = Bot(token=telegram_bot_token)
    try:
        msg = await bot.send_message(chat_id=chat_id, text=message)
        logging.info(f'Telegram notification sent: {message} (ID: {msg.message_id})')
        return msg.message_id  # Return the message ID
    except TelegramError as e:
        logging.error(f'Failed to send Telegram message: {str(e)}')
        return None

# Edit an existing Telegram message
async def edit_telegram_message(message_id, new_message):
    bot = Bot(token=telegram_bot_token)
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=new_message)
        logging.info(f"Edited message ID: {message_id} with new content: {new_message}")
    except TelegramError as e:
        logging.error(f'Failed to edit Telegram message: {str(e)}')

# Delete the a Telegram message
async def delete_telegram_message(message_id):
    bot = Bot(token=telegram_bot_token)
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logging.info(f"Deleted message ID: {message_id}")
        except TelegramError as e:
            logging.error(f'Failed to delete Telegram message: {str(e)}')

# Check the gas price and send a notification if needed
async def check_gas_price_and_notify():
    logging.debug(f"Checking if gas fee is below {gas_fee_lower_threshold}...")

    global last_message_id_in_range
    global last_price

    try:
        # Make the API request
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception if the request was unsuccessful
        
        # Parse the JSON response
        data = response.json()
        
        # More detailed error handling for API response
        if data.get('status') == '1' and 'result' in data and 'ProposeGasPrice' in data['result']:
            propose_gas_price = float(data['result']['ProposeGasPrice'])
            logging.info(f'ProposeGasPrice: {propose_gas_price}, last_price: {last_price}, last_message_id_in_range: {last_message_id_in_range}')
            
            # Check if the ProposeGasPrice falls below gas_fee_lower_threshold and hasn't already triggered an alert
            if propose_gas_price < gas_fee_lower_threshold:
                message = f'ETH Gas Fee: {propose_gas_price} - https://etherscan.io/gastracker'
                if last_message_id_in_range is None:
                    last_message_id_in_range = await send_telegram_message(message)
                elif last_message_id_in_range is not None and last_price != propose_gas_price:
                    await edit_telegram_message(last_message_id_in_range, message)
            # Check if the ProposeGasPrice rises above gas_fee_upper_threshold and delete message
            elif propose_gas_price > gas_fee_upper_threshold and last_message_id_in_range is not None:
                await delete_telegram_message(last_message_id_in_range)
                last_message_id_in_range = None
                logging.debug(f'ProposeGasPrice is above upper threshold, deleted message')
            else:
                logging.debug(f'No action taken')
        else:
                logging.error(f'API request returned invalid data or status: {data}')
        last_price = propose_gas_price
    except requests.RequestException as e:
        logging.error(f'API request failed with exception: {str(e)}')

# Exponential backoff retry mechanism
async def retry_with_backoff(task, retries=2, delay=5):
    for attempt in range(1, retries + 1):
        try:
            await task()
            break
        except Exception as e:
            if attempt < retries:
                logging.error(f"Attempt {attempt} failed: {e}. Retrying in {delay} seconds...")
                await asyncio.sleep(delay * attempt)
            else:
                logging.error(f"All {retries} attempts failed: {e}")

# Main loop to check the gas price
async def main_loop():
    global shutdown_flag

    logging.info(f'Started')
    logging.info(f'ENV: gas_fee_lower_threshold: {gas_fee_lower_threshold}')
    logging.info(f'ENV: gas_fee_upper_threshold: {gas_fee_upper_threshold}')
    logging.info(f'ENV:check_interval: {check_interval}')

    while not shutdown_flag:
        await retry_with_backoff(check_gas_price_and_notify)
        await asyncio.sleep(check_interval)  # Wait before checking again

# Graceful shutdown handler
def handle_shutdown(signum, frame):
    global shutdown_flag
    logging.info(f"Received shutdown signal ({signum}). Shutting down gracefully...")
    shutdown_flag = True

# Register the shutdown signal handlers (for SIGINT and SIGTERM)
signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# Run the main loop
if __name__ == "__main__":
    asyncio.run(main_loop())
