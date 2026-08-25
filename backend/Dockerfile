FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
CMD exec uvicorn app.lexproof.main:app --host 0.0.0.0 --port ${PORT}