FROM python:3.12-slim

WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
WORKDIR /app/backend
CMD python -m app.db.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8001
