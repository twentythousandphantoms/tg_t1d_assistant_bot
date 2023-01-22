import datetime
import logging

import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import TOKEN

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# connect to telegram bot using API key
bot = telebot.TeleBot(TOKEN)


def mg_dl_to_mmol_l(mg_dl):
    return round(mg_dl / 18.0182, 2)


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
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_input = message.text
    if user_input.isnumeric():
        user_input = float(user_input)
        if user_input > 35:
            mg_dl = user_input
            mmol_l = round(mg_dl / 18, 1)
        elif user_input <= 35:
            mmol_l = user_input
            mg_dl = round(mmol_l * 18, 0)
        conn = sqlite3.connect('user_inputs.db')
        c = conn.cursor()
        c.execute("INSERT INTO user_inputs (timestamp, user_id, mg_dl,mmol_l) VALUES (?,?,?,?)",
                  (datetime.datetime.now(), user_id, mg_dl, mmol_l))
        conn.commit()
        c.close()
        conn.close()
        bot.send_message(chat_id,
                         f'Your input of {user_input} has been saved, which is {mg_dl} mg/dl or {mmol_l} mmol/L')
        logger.info(f'User {user_id} sent {mg_dl} mg/dl ({mmol_l} mmol/L)')
        send_last_week_a1c(user_id, chat_id)
        # send message with inline keyboard
        bot.send_message(chat_id, "Please choose an option", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        bot.send_message(chat_id, "Invalid input. Please enter a number (glucose level) or choose an option",
                         reply_markup=InlineKeyboardMarkup(keyboard))


def send_history_data(user_id: int, chat_id: int, time_period: str):
    """
        It is used to send the data of the user's glucose level entries for the specified time period.
        This function takes user_id, time_period and bot as the input parameter.

        The function first creates a connection to the sqlite3 database and retrieves the data from the 'user_inputs'
        table based on the user_id and time_period passed as the parameter. It then loops through the data,
        formats the timestamp and message, then sends the message to the user via the bot. Finally, it closes the
        connection to the database.
    """
    conn = sqlite3.connect('user_inputs.db')
    c = conn.cursor()
    logger.info(f'Chat ID: {chat_id}: User {user_id} requested a history data for period: {time_period}')
    if time_period == "1 day":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=1), datetime.datetime.now())
    elif time_period == "2 days":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=2), datetime.datetime.now())
    elif time_period == "week":
        date_range = (datetime.datetime.now() - datetime.timedelta(weeks=1), datetime.datetime.now())
    elif time_period == "month":
        date_range = (datetime.datetime.now() - datetime.timedelta(days=30), datetime.datetime.now())
    elif time_period == "all":
        c.execute("SELECT * FROM user_inputs WHERE user_id=? ORDER BY timestamp DESC", (user_id,))
    else:
        message = "Invalid time period"
        bot.send_message(chat_id, message)
        logger.info(f'Sent: {message}')
        return
    if time_period != "all":
        c.execute("SELECT * FROM user_inputs WHERE user_id=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC",
                  (user_id, date_range[0], date_range[1]))
    rows = c.fetchall()
    if len(rows) == 0:
        message = "No entries for the {}".format(time_period)
        bot.send_message(chat_id, message)
        logger.info(f'Sent: {message}')
        return
    message = "Entries for the {}:\n".format(time_period)
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
    conn.close()


def a1c_calculation(mg_dl):
    # A1C = (average glucose (mg/dL) + 46.7) / 28.7
    a1c = (mg_dl + 46.7) / 28.7
    a1c = round(a1c, 2)
    return a1c


def send_last_week_a1c(user_id, chat_id):
    # connect to sqlite3 database
    conn = sqlite3.connect('user_inputs.db')
    c = conn.cursor()
    # get current time
    current_time = datetime.datetime.now()
    # get time 7 days ago
    last_week_time = current_time - datetime.timedelta(days=7)
    # convert to string
    last_week_time = last_week_time.strftime("%Y-%m-%d %H:%M:%S")

    # select mg/dl entries from user_inputs table for specific user id and for the last 7 days
    c.execute("SELECT mg_dl FROM user_inputs WHERE user_id = ? AND timestamp > ? ORDER BY timestamp DESC",
              (user_id, last_week_time))
    entries = c.fetchall()
    # calculate the average of mg/dl entries
    total_mg_dl = 0
    for entry in entries:
        total_mg_dl += entry[0]
    if len(entries) > 0:
        avg_mg_dl = total_mg_dl / len(entries)
        a1c = a1c_calculation(avg_mg_dl)
        bot.send_message(chat_id, f'The average A1C for the last 7 days is {a1c}')
    else:
        bot.send_message(chat_id, 'No entries found for the last 7 days')
    # close cursor and connection
    c.close()
    conn.close()


bot.polling()
