import datetime
from unittest.mock import MagicMock

import main


def test_handle_last_week_a1c(monkeypatch):
    # Use a mock bot object to simulate sending a message
    bot = MagicMock()
    monkeypatch.setattr('main.bot', bot)

    # Set up test data
    user_id = 1
    chat_id = 12345
    test_data = [(datetime.datetime.now(), user_id, 150, 8.3),
                 (datetime.datetime.now() - datetime.timedelta(days=1), user_id, 120, 6.7),
                 (datetime.datetime.now() - datetime.timedelta(days=2), user_id, 100, 5.6),
                 (datetime.datetime.now() - datetime.timedelta(days=7), user_id, 80, 4.4),
                 (datetime.datetime.now() - datetime.timedelta(days=8), user_id, 90, 5.0)]
    # Use a mock select_history_data function that returns the test data
    monkeypatch.setattr('main.select_history_data', lambda user_id, date_from, date_to: test_data)

    # Call the function to test
    main.handle_last_week_a1c(chat_id, user_id)

    # Assert that the bot.send_message function was called with the correct arguments
    bot.send_message.assert_called_with(chat_id, 'Your average glucose level for the last 7 days is 110 mg/dL (6.1 mmol/L)')
