import datetime
import logging

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import TOKEN
from database import insert_data, select_all_data, select_history_data

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# connect to telegram bot using API key
bot = telebot.TeleBot(TOKEN)

# button labels and callback data
buttons = {
    'entry_glucose_level': {'label': '🩸', 'callback_data': 'entry_glucose_level'},
    'request_history': {'label': 'history', 'callback_data': 'request_history'}
}

history_options = {
    '1 day': {'label': '1 day', 'callback_data': '1 day'},
    '2 days': {'label': '2 days', 'callback_data': '2 days'},
    'week': {'label': 'week', 'callback_data': 'week'},
    'month': {'label': 'month', 'callback_data': 'month'},
    'all': {'label': 'all', 'callback_data': 'all'}
}

# convert dictionaries to InlineKeyboardButton objects
keyboard = [
    [InlineKeyboardButton(buttons[key]['label'], callback_data=buttons[key]['callback_data']) for key in buttons]]
history_keyboard = [
    [InlineKeyboardButton(history_options[key]['label'], callback_data=history_options[key]['callback_data']) for key in
     history_options]]


def mg_dl_to_mmol_l(mg_dl):
    return round(mg_dl / 18.0182, 2)


def handle_start_command(chat_id):
    bot.send_message(chat_id, "Welcome! I am your T1D assistant bot. How can I help you today?")


def handle_help_command(chat_id):
    help_text = "Here are the available commands:\n"
    help_text += "/start - start the bot\n"
    help_text += "/help - display this help message\n"
    help_text += "/glucose - input a glucose level (mg/dL)\n"
    help_text += "/a1c - calculate your estimated A1C based on the last 7 days of glucose levels\n"
    help_text += "or choose an option from below:\n"
    bot.send_message(chat_id=chat_id, text=help_text, reply_markup=InlineKeyboardMarkup(keyboard))


def handle_invalid_input(chat_id):
    """
        This function is used to handle invalid input from the user.
        It takes the update and context as inputs, and sends a message to the user
        indicating that their input is invalid.
    """
    invalid_message = "Invalid input. Please enter a number (glucose level) or choose an option"
    bot.send_message(chat_id, invalid_message, reply_markup=InlineKeyboardMarkup(keyboard))


def insert_glucose_level(user_id: int, glucose_level: str):
    mg_dl = float(glucose_level)
    mmol_l = mg_dl / 18
    logger.info(f'User {user_id} sent {mg_dl} mg/dl ({mmol_l} mmol/L)')
    insert_data(user_id, mg_dl, round(mmol_l, 2))


def send_history_data(user_id: int, chat_id: int, time_period='month'):
    """
        It is used to send the data of the user's glucose level entries for the specified time period.
        This function takes user_id, time_period and bot as the input parameter.

        The function first creates a connection to the sqlite3 database and retrieves the data from the 'user_inputs'
        table based on the user_id and time_period passed as the parameter. It then loops through the data,
        formats the timestamp and message, then sends the message to the user via the bot. Finally, it closes the
        connection to the database.
    """
    logger.info(f'Chat ID: {chat_id}: User {user_id} requested a history data for period: {time_period}')
    if time_period == "1 day":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=1), datetime.datetime.now())
    elif time_period == "2 days":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=2), datetime.datetime.now())
    elif time_period == "week":
        date_range = (datetime.datetime.now() - datetime.timedelta(weeks=1), datetime.datetime.now())
    elif time_period == "month":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=30), datetime.datetime.now())
    elif time_period.isnumeric():
        date_range = (datetime.datetime.now() - datetime.timedelta(days=int(time_period)), datetime.datetime.now())
    elif time_period == "all":
        rows = select_all_data(user_id)
    else:
        message = "Invalid time period"
        bot.send_message(chat_id, message)
        logger.info(f'Sent: {message}')
        return
    if time_period != "all":
        rows = select_history_data(user_id, date_range[0], date_range[1])

    if len(rows) == 0:
        message = "No entries for the {}".format(time_period)
        bot.send_message(chat_id, message)
        logger.info(f'Sent: {message}')
        return
    message = "Entries for the last {}:\n".format(time_period)
    for row in rows:
        try:
            timestamp = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S.%f')
        except:
            timestamp = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        timestamp = timestamp.strftime("%d.%m %H:%M")
        mg_dl = row[2]
        mmol_l = row[3]
        message += "{} - {} mg/dl ({} mmol/l)\n".format(timestamp, mg_dl, round(mmol_l, 2))
    bot.send_message(chat_id, message)
    logger.info(f'Sent: {message}')


def a1c_calculation(mg_dl):
    # A1C = (average glucose (mg/dL) + 46.7) / 28.7
    a1c = (mg_dl + 46.7) / 28.7
    a1c = round(a1c, 2)
    return a1c


def get_ag(user_id: int, time_period):
    if time_period.isnumeric():
        date_from = (datetime.datetime.now() - datetime.timedelta(days=time_period)).strftime("%Y-%m-%d")
        date_to = datetime.datetime.now().strftime("%Y-%m-%d")
        data = select_history_data(user_id, date_from, date_to)
    else:
        data = select_all_data(user_id)

    if len(data) == 0:
        return None
    total_mg_dl = 0
    total_days = 0
    for row in data:
        total_mg_dl += row[2]
        total_days += 1
    ag = total_mg_dl / total_days
    return ag


def send_ag(user_id: int, chat_id: int, time_period='60'):
    ag = get_ag(user_id, time_period)
    if ag is None:
        message = f'No entries for the last {time_period} days'
        bot.send_message(chat_id, message)
        return
    else:
        message = f'Your calculated average glucose for the last {time_period} days is {ag} \n'
        bot.send_message(chat_id, message)
    return


def handle_last_a1c(user_id: int, chat_id: int, time_period=60):
    ag = get_ag(user_id, time_period=time_period)
    a1c = (ag + 46.7) / 28.7
    message = "Your calculated A1C for the last {} days is {}% \n".format(round(a1c, 2), time_period)
    message += "Please note that it is not a real A1C. " \
               "Please consider taking a real " \
               "[A1C blood test](https://www.healthline.com/health/type-2-diabetes/a1c-test)."
    bot.send_message(chat_id, message)
    return


# callback query handler
@bot.callback_query_handler(func=lambda call: call.data in buttons)
def process_callback_main(call):
    if call.data == "entry_glucose_level":
        bot.send_message(call.message.chat.id, "Please enter your glucose level")
    elif call.data == "request_history":
        bot.send_message(call.message.chat.id, "Please choose a history option",
                         reply_markup=InlineKeyboardMarkup(history_keyboard))


@bot.callback_query_handler(func=lambda call: call.data in history_options)
def process_callback_history(call):
    send_history_data(call.from_user.id, call.message.chat.id, call.data)


@bot.message_handler(content_types=['text'])
def handle_message(message):
    user_input = message.text
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_input.isnumeric():
        insert_glucose_level(user_id, user_input)
        send_ag(chat_id, user_id)
    elif user_input == "/start":
        handle_start_command(chat_id)
    elif user_input == "/help":
        handle_help_command(chat_id)
    elif user_input == "/a1c":
        handle_last_a1c(chat_id, user_id)
    else:
        handle_invalid_input(chat_id)


if __name__ == "__main__":
    bot.polling()
