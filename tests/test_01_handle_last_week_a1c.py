import main
import datetime
import pytest


def handle_last_a1c(mocker):
    # Test data
    user_id = 1
    chat_id = 12345
    glucose_levels = [100, 120, 90, 110, 130, 80, 140]
    timestamp = datetime.datetime.now() - datetime.timedelta(days=1)
    expected_a1c = 7.8

    # Insert test data into the database
    for level in glucose_levels:
        main.insert_data(user_id=user_id, mg_dl=level, mmol_l=main.mg_dl_to_mmol_l(level), timestamp=timestamp)
        timestamp += datetime.timedelta(hours=1)

    # Mock the send_message function to check the message sent
    mock_bot = mocker.patch('main.bot')

    # Call the handle_last_week_a1c function
    main.handle_last_week_a1c(user_id, chat_id)

    # Assert that the bot sent the message with the correct A1C
    mock_bot.send_message.assert_called_with(chat_id, f'Your A1C for the last week is {expected_a1c}%')
