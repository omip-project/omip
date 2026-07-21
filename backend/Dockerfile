FROM python:3.12-slim
WORKDIR /project
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app ./backend/app
COPY simulator ./simulator
COPY scenarios ./scenarios
ENV PYTHONPATH=/project/backend
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
