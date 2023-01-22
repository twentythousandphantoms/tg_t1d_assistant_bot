from tg_t1d_assistant_bot.main import insert_data, mg_dl_to_mmol_l, handle_last_a1c
import datetime
import pytest


def test_handle_last_a1c(mocker):
    # Test data
    user_id = 1
    chat_id = 12345
    glucose_levels = [100, 120, 90, 110, 130, 80, 140]
    timestamp = datetime.datetime.now() - datetime.timedelta(days=1)
    expected_a1c = 5.46

    # Insert test data into the database
    for level in glucose_levels:
        insert_data(user_id=user_id, mg_dl=level, mmol_l=mg_dl_to_mmol_l(level), timestamp=timestamp)
        timestamp += datetime.timedelta(hours=1)

    # Mock the send_message function to check the message sent
    mock_bot = mocker.patch('tg_t1d_assistant_bot.main.bot')

    # Call the handle_last_week_a1c function
    handle_last_a1c(user_id, chat_id)

    # Assert that the bot sent the message with the correct A1C
    message = f'Your calculated A1C for the last 60 days is {expected_a1c}% \n'
    message += "Please note that it is not a real A1C. " \
               "Please consider taking a real " \
               "[A1C blood test](https://www.healthline.com/health/type-2-diabetes/a1c-test)."
    mock_bot.send_message.assert_called_with(chat_id, message)
