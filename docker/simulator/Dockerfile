FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir "paho-mqtt>=2.1,<3.0" "httpx>=0.27,<1.0"

COPY simulator /app/simulator
COPY scenarios /app/scenarios

CMD ["python", "simulator/multi_sensor_simulator.py", "--api-base", "http://backend:8000", "--transport", "mqtt", "--mqtt-host", "mqtt"]
