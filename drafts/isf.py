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
        self.default_isf = 18 * 4
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
        self.logger.info(f"Fetched {len(self.entries)} entries and {len(self.treatments)} treatments")
        self.logger.info(f"Entries: {self.entries if len(self.entries) < 10 else self.entries[:10]}")
        self.logger.info(f"Treatments: {self.treatments if len(self.treatments) < 10 else self.treatments[:10]}")
        return False if not self.entries else True

    def analyze_data(self):
        """Calculate average ISF from correction periods."""
        correction_periods = [
            self._compute_isf(treatment)
            for treatment in self.treatments
            if treatment.get('eventType') == 'Correction Bolus' and not self._is_near_meal(treatment)
        ]
        # Remove None values
        correction_periods = [x for x in correction_periods if x is not None]

        average_isf = sum(correction_periods) / len(correction_periods) if correction_periods else None
        return average_isf

    def _parse_date(self, date_str):
        """Parse ISO formatted date string into datetime object."""
        return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)

    def _compute_isf(self, treatment):
        """Compute ISF (Insulin Sensitivity Factor) for a given treatment.
        ISF is the amount of glucose points that 1 unit of insulin will reduce.
        ISF = (start_glucose - end_glucose) / insulin

        """
        start_time = self._parse_date(treatment.get('created_at'))
        end_time = start_time + timedelta(hours=4)

        start_glucose = next((e['sgv'] for e in self.entries if self._parse_date(e.get('dateString')) == start_time), None)
        # If there is no entry for the start time, use the first entry after the start time
        if not start_glucose:
            start_glucose = next((e['sgv'] for e in self.entries if self._parse_date(e.get('dateString')) > start_time), None)
        end_glucose = next((e['sgv'] for e in self.entries if self._parse_date(e.get('dateString')) == end_time), None)
        # If there is no entry for the end time, use the first entry before the end time
        if not end_glucose:
            # entries sorted by dateString
            sorted_entries = sorted(self.entries, key=lambda x: x.get('dateString', ''), reverse=True)
            end_glucose = next((e['sgv'] for e in sorted_entries if self._parse_date(e.get('dateString')) < end_time), None)

        if start_glucose and end_glucose and treatment.get('insulin', 0) not in [0, None]:
            return (start_glucose - end_glucose) / treatment.get('insulin')
        return None

    def _is_near_meal(self, treatment):
        """Check if the treatment is near a meal."""
        treatment_time = self._parse_date(treatment.get('created_at'))
        # Check if there is a meal bolus within 4 hours of the treatment
        return any(
            t.get('eventType') == 'Meal Bolus' and abs(
                (self._parse_date(t.get('created_at')) - treatment_time).total_seconds()) < 4 * 3600
            for t in self.treatments
        )

    def predict_glucose(self, hours_ahead=1):
        current_glucose = self.entries[-1]['sgv'] if self.entries else None
        if not current_glucose:
            self.logger.warning("Insufficient data for prediction.")
            return None

        # Получаем ISF (или значение по умолчанию, если ISF = None)
        isf = self.analyze_data() or self.default_isf

        future_glucose = current_glucose

        # Итеративно вычисляем уровень глюкозы для каждого часа вперед
        for hour in range(1, hours_ahead + 1):
            future_iob = self.total_IOB_for_period(datetime.utcnow() + timedelta(hours=hour), self.calculate_dia())
            glucose_change_due_to_insulin = future_iob * isf
            future_glucose -= glucose_change_due_to_insulin  # вычитаем, так как инсулин снижает уровень глюкозы

        return future_glucose

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
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    TOKEN = None
    PERIOD = '1 month'
    COUNT = 100000
    analyzer = NightscoutAnalyzer("https://twentythousandphantoms.my.nightscoutpro.com", TOKEN)
    start_time, end_time = get_start_end_time(PERIOD)
    analyzer.fetch_data(start_time=start_time, end_time=end_time, count=COUNT)
    isf = analyzer.analyze_data()
    logger.info(f"Calculated ISF: {isf}")

    current_human_readable_time = (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M")
    logger.info("Current time: " + current_human_readable_time)
    logger.info(f"Current glucose level: {analyzer.entries[-1]['sgv']} mg/dl, ({round(analyzer.entries[-1]['sgv'] / 18, 1)} mmol/l)")
    logger.info(f"Total IOB for the last {analyzer.calculate_dia()} hours: {round(analyzer.total_IOB_for_period(datetime.utcnow(), analyzer.calculate_dia()), 2)}")
    logger.info("")

    # timezone: Istanbul
    for hours in [1, 2, 3, 4]:
        predicted_glucose = analyzer.predict_glucose(hours_ahead=hours)

        # logger.info(f"Prediction at : {round(predicted_glucose)} mg/dl, ({round(predicted_glucose / 18, 1)} mmol/l)")
        # timezone: Istanbul
        predicted_human_readable_time = (datetime.utcnow() + timedelta(hours=3 + hours)).strftime("%H:%M")
        logger.info(f"Prediction at {predicted_human_readable_time}: {round(predicted_glucose)} mg/dl, ({round(predicted_glucose / 18, 1)} mmol/l)")
        logger.info("")

    logger.info("Done.")
