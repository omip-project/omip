FROM python:3.12-slim
WORKDIR /project
RUN pip install --no-cache-dir "paho-mqtt>=2.1,<3.0"
COPY simulator ./simulator
COPY scenarios ./scenarios
CMD ["python", "simulator/multi_sensor_simulator.py", "--api-base", "http://backend:8000", "--transport", "mqtt", "--mqtt-host", "mosquitto", "--scenario", "scenarios/multi_sensor_nominal.json"]
