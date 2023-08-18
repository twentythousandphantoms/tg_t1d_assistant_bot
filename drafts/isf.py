import requests
import logging
import sys
from datetime import datetime, timedelta, timezone
import re
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error


class NightscoutAnalyzer:
    def __init__(self, url, token=None):
        self.url = url
        self.token = token
        self.entries = []
        self.treatments = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _fetch_from_endpoint(self, endpoint, params={}):
        """Utility function to fetch data from Nightscout API endpoint."""
        try:
            response = requests.get(f"{self.url}/api/v1/{endpoint}.json", headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from {endpoint}: {e}")
            return []

    def fetch_data(self, start_time=None, end_time=None, count=1000):
        params = {"count": count, "start": start_time, "end": end_time}
        self.entries = sorted(self._fetch_from_endpoint('entries', params), key=lambda x: x.get('date', ''))
        self.treatments = self._fetch_from_endpoint('treatments')

    def analyze_data(self):
        """Calculate average ISF from correction periods."""
        correction_periods = [
            self._compute_isf(treatment)
            for treatment in self.treatments
            if treatment.get('eventType') == 'Insulin' and not self._is_near_meal(treatment)
        ]
        # Remove None values
        correction_periods = [x for x in correction_periods if x is not None]

        average_isf = sum(correction_periods) / len(correction_periods) if correction_periods else None
        self.logger.info(f"Average ISF: {average_isf}")
        return average_isf

    def _compute_isf(self, treatment):
        """Compute ISF for a given treatment."""
        start_time = treatment.get('timestamp')
        end_time = start_time + 4 * 3600

        start_glucose = next((e['sgv'] for e in self.entries if e.get('timestamp') == start_time), None)
        end_glucose = next((e['sgv'] for e in self.entries if e.get('timestamp') == end_time), None)

        if start_glucose and end_glucose and treatment.get('insulin', 0) != 0:
            return (start_glucose - end_glucose) / treatment.get('insulin')
        return None

    def _is_near_meal(self, treatment):
        """Check if the treatment is near a meal."""
        return any(
            t.get('eventType') == 'Meal Bolus' and abs(t.get('timestamp', 0) - treatment.get('timestamp', 0)) < 4 * 3600
            for t in self.treatments
        )

    def predict_glucose(self, hours_ahead=1):
        """Predict glucose level using RandomForestRegressor."""
        timestamps = [entry.get('date', 0) for entry in self.entries if entry.get('date')]
        glucose_values = [entry.get('sgv', 0) for entry in self.entries if entry.get('sgv')]

        # Ensure equal lengths
        min_length = min(len(timestamps), len(glucose_values))
        timestamps = timestamps[:min_length]
        glucose_values = glucose_values[:min_length]

        if not timestamps:
            self.logger.warning("Insufficient data for prediction.")
            return None

        X = np.array(timestamps).reshape(-1, 1)
        y = glucose_values

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = RandomForestRegressor(n_estimators=100).fit(X_train, y_train)
        future_timestamp = timestamps[-1] + hours_ahead * 3600
        return model.predict([[future_timestamp]])[0]

    def total_IOB_for_period(self, target_time, DIA_hours):
        # Make target_time offset-aware
        target_time = target_time.replace(tzinfo=timezone.utc)
        insulin_entries = self._fetch_insulin_entries_for_period(target_time, DIA_hours)
        return sum(self._compute_IOB(entry, target_time, DIA_hours) for entry in insulin_entries)

    def _fetch_insulin_entries_for_period(self, end_time, duration_hours):
        start_time = end_time - timedelta(hours=duration_hours)
        return [entry for entry in self.treatments if entry.get('insulin') and start_time <= datetime.fromisoformat(
            entry['created_at'].replace('Z', '+00:00')) <= end_time]

    @staticmethod
    def _compute_IOB(entry, target_time, DIA_hours):
        time_since_injection = (target_time - datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))).total_seconds() / 3600
        return entry['insulin'] * (1 - (time_since_injection / DIA_hours)) if time_since_injection <= DIA_hours else 0

    @staticmethod
    def calculate_dia():
        return 4  # Placeholder value

def get_start_end_time(period=None):
    def get_period_days(period):
        """Convert period string into days."""
        period_conversion = {
            'day': 1,
            'week': 7,
            'month': 30
        }

        def replace_with_conversion(match):
            number = match.group(1)
            unit = match.group(2).rstrip('s')
            return f"{number} * {period_conversion.get(unit, 1)}"

        period_in_days = eval(re.sub(r'(\d+)\s+([a-z]+)', replace_with_conversion, period.lower()))
        return period_in_days

    period_days = period and get_period_days(period) or 999
    end_time = datetime.utcnow().isoformat() + "Z"
    start_time = (datetime.utcnow() - timedelta(days=period_days)).isoformat() + "Z"
    return start_time, end_time


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    TOKEN = None
    PERIOD = '1 month'
    analyzer = NightscoutAnalyzer("https://twentythousandphantoms.my.nightscoutpro.com", TOKEN)
    start_time, end_time = get_start_end_time(PERIOD)
    analyzer.fetch_data(start_time=start_time, end_time=end_time, count=1000)
    analyzer.analyze_data()

    logger.info(f"Current glucose level: {analyzer.entries[-1]['sgv']}")
    for hours in [1, 2, 3, 4]:
        predicted_glucose = analyzer.predict_glucose(hours_ahead=hours)
        logger.info(f"Prediction for {hours} hour(s) in mg/dl: {round(predicted_glucose)}")
        logger.info(f"Prediction for {hours} hour(s) in mmol/l: {round(predicted_glucose / 18, 1)}")

    logger.info(f"Total IOB for the last {analyzer.calculate_dia()}: {analyzer.total_IOB_for_period(datetime.utcnow(), analyzer.calculate_dia())}")

    logger.info("Done.")
