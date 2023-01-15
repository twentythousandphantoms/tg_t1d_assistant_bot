import telebot
import sqlite3
import datetime
import logging

from config import TOKEN

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# connect to telegram bot using API key
bot = telebot.TeleBot(TOKEN)


def mg_dl_to_mmol_l(mg_dl):
    return round(mg_dl / 18.0182, 2)


@bot.message_handler(content_types=['text'])
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_input = message.text
    if user_input.isnumeric():
        user_input = float(user_input)
        if user_input > 35:
            mg_dl = user_input
            mmol_l = round(mg_dl / 18, 2)
        elif user_input <= 35:
            mmol_l = user_input
            mg_dl = round(mmol_l * 18, 2)
        conn = sqlite3.connect('user_inputs.db')
        c = conn.cursor()
        c.execute("INSERT INTO user_inputs (timestamp, user_id, mg_dl,mmol_l) VALUES (?,?,?,?)",
                  (datetime.datetime.now(), user_id, mg_dl, mmol_l))
        conn.commit()
        c.close()
        conn.close()
        bot.send_message(chat_id,
                         f'Your input of {user_input} has been saved, which is {mg_dl} mg/dl or {mmol_l} mmol/L')
        send_last_week_a1c(user_id, chat_id)
    elif user_input == "history last day":
        send_last_day_entries(user_id, chat_id)
    else:
        bot.send_message(chat_id, "Invalid input. Please enter a number or 'history last day'")


def send_last_day_entries(user_id, chat_id):
    conn = sqlite3.connect('user_inputs.db')
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, user_id, mg_dl, mmol_l FROM user_inputs "
        "WHERE user_id = ? and timestamp >= date('now', '-1 day') ORDER BY timestamp DESC",
        (user_id,))
    rows = c.fetchall()
    if len(rows) == 0:
        bot.send_message(chat_id, 'No entries for the last day')
    else:
        entries = []
        for row in rows:
            timestamp = datetime.datetime.fromisoformat(row[0]).strftime("%d.%m %H:%M")
            entry = f'{timestamp} - {row[2]} mg/dl or {row[3]} mmol/L'
            entries.append(entry)
        bot.send_message(chat_id, '\n'.join(reversed(entries)))
    c.close()
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
