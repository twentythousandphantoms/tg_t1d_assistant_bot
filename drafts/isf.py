import requests
import logging
import sys
from datetime import datetime, timedelta
import re

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

    def fetch_data(self, start_time=None, end_time=None, count=1000):
        params = {"count": count}

        if start_time:
            params['start'] = start_time
        if end_time:
            params['end'] = end_time

        try:
            entries_response = requests.get(f"{self.url}/api/v1/entries.json", headers=self.headers, params=params)

            self.logger.debug(f"URL: {entries_response.url}")
            # Trip the response to 1000 characters
            self.logger.debug(f"Response: {entries_response.text[:1000] + '...' if len(entries_response.text) > 1000 else entries_response.text}")

            if entries_response.status_code == 200:
                self.entries = entries_response.json()
                self.logger.info(f"Successfully fetched CGM data. Number of entries: {len(self.entries)}")

                # Show only 15 last entries sorted by date
                self.entries.sort(key=lambda x: x['date'], reverse=True)
                self.logger.debug(f"Last 15 entries: ")
                for entry in self.entries[-15:]:
                    self.logger.debug(f"Entry: {entry}")

            else:
                self.logger.error(
                    f"Error fetching CGM data. Status code: {entries_response.status_code}. "
                    f"URL: {entries_response.url}. "
                    f"Response: {entries_response.text}")

            treatments_response = requests.get(f"{self.url}/api/v1/treatments.json", headers=self.headers)
            if treatments_response.status_code == 200:
                self.treatments = treatments_response.json()
                self.logger.info(f"Successfully fetched treatments data. Number of treatments: {len(self.treatments)}")
                for treatment in self.treatments:
                    self.logger.debug(f"Treatment: {treatment}")
            else:
                self.logger.error(
                    f"Error fetching treatments data. Status code: {treatments_response.status_code}. Response: {treatments_response.text}")

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")

    def analyze_data(self):
        correction_periods = []

        for treatment in self.treatments:
            if treatment.get('eventType') == 'Insulin' and not any(
                    t.get('eventType') == 'Meal Bolus' for t in self.treatments if
                    abs(t.get('timestamp', 0) - treatment.get('timestamp', 0)) < 4 * 3600):

                start_time = treatment.get('timestamp')
                end_time = start_time + 4 * 3600

                start_glucose = next((e['glucose'] for e in self.entries if e.get('timestamp') == start_time), None)
                end_glucose = next((e['glucose'] for e in self.entries if e.get('timestamp') == end_time), None)

                if start_glucose and end_glucose and treatment.get('insulin'):
                    isf = (start_glucose - end_glucose) / treatment['insulin']
                    correction_periods.append(isf)
                    self.logger.info(f"Found correction period. ISF: {isf}")
                else:
                    missing_data = []
                    if not start_glucose:
                        missing_data.append("start glucose")
                    if not end_glucose:
                        missing_data.append("end glucose")
                    self.logger.warning(f"Missing data for correction period: {', '.join(missing_data)}.")

        if not correction_periods:
            self.logger.warning("No correction periods found for ISF calculation.")

        average_isf = sum(correction_periods) / len(correction_periods) if correction_periods else None
        self.logger.info(f"Average ISF: {average_isf}")
        return average_isf

    def calculate_dia(self):
        # Этот метод требует сложного анализа, и в этом примере мы просто возвращаем стандартное значение (например, 4 часа для быстродействующего инсулина)
        return 4  # in hours

    def predict_glucose(self, hours_ahead=1):
        from sklearn.model_selection import train_test_split
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import mean_squared_error
        import numpy as np


        # 1. Подготовка данных
        self.logger.debug("Preparing data for prediction...")
        timestamps = [entry['date'] for entry in self.entries if 'date' in entry]
        glucose_values = [entry['sgv'] for entry in self.entries if 'sgv' in entry]

        # Преобразование данных для обучения модели
        X = np.array(timestamps).reshape(-1, 1)
        y = glucose_values

        # 2. Разделение данных на обучающую и тестовую выборки
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # 3. Обучение модели
        model = LinearRegression().fit(X_train, y_train)

        # 4. Тестирование модели
        y_pred = model.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)

        # 5. Прогнозирование уровня глюкозы
        self.logger.debug("Predicting glucose level for the future...")
        current_timestamp = timestamps[-1]
        future_timestamp = current_timestamp + hours_ahead * 3600
        future_glucose = model.predict([[future_timestamp]])

        return future_glucose[0]

    def fetch_insulin_entries_for_period(self, end_time, duration_hours):

        # Фильтруем записи, чтобы оставить только те, которые касаются инъекций инсулина
        # check if entry keys include 'insulin'
        # insulin_entries = [entry for entry in self.treatments if entry. == 'insulin']
        insulin_entries = [entry for entry in self.treatments if 'insulin' in entry]

        # Определяем начальное время для извлечения записей
        start_time = end_time - timedelta(hours=duration_hours)

        # Оставляем только записи, которые находятся в заданном временном диапазоне
        relevant_entries = [entry for entry in insulin_entries if
                            start_time <= datetime.fromisoformat(entry['created_at'].rstrip('Z')) <= end_time]

        return relevant_entries

    def calculate_IOB(self, insulin_dose, time_since_injection, DIA):
        """
        Calculate Insulin On Board (IOB) based on a simple linear model.

        :param insulin_dose: The total amount of insulin injected.
        :param time_since_injection: The time since the insulin was injected (in hours).
        :param DIA: Duration of Insulin Activity (in hours).
        :return: Estimated IOB.
        """
        if time_since_injection > DIA:
            return 0
        else:
            return insulin_dose * (1 - (time_since_injection / DIA))

    def total_IOB_for_period(self, target_time, DIA_hours):
        # Извлекаем все записи инъекции за период DIA до целевого времени
        insulin_entries = self.fetch_insulin_entries_for_period(target_time, DIA_hours)

        total_iob = 0

        for entry in insulin_entries:
            time_since_injection = (target_time - datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
                                    ).total_seconds() / 3600
            # Предполагаем, что у нас есть функция calculate_IOB, которая вычисляет IOB на основе времени с момента инъекции и количества инсулина
            iob = self.calculate_IOB(entry['insulin'], time_since_injection, DIA_hours)
            total_iob += iob

        return total_iob

def get_start_end_time(period=None):

    def convert_period(period):
        if not period:
            return None
        period = period.lower()
        period = re.sub(r'(\d+)\s+months?', r'\1 * 30', period)
        period = re.sub(r'(\d+)\s+weeks?', r'\1 * 7', period)
        period = re.sub(r'(\d+)\s+days?', r'\1', period)
        return eval(period)

    period_days = convert_period(period) or 999
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

