FROM python:3.12-slim

RUN apt-get update \
	&& apt-get install -y --no-install-recommends tesseract-ocr \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-adk.txt constraints.txt ./
# constraints.txt is the set the PayPal tests ran against. The second step is
# --no-deps on purpose. See the comments in requirements-adk.txt and constraints.txt.
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt \
	&& pip install --no-cache-dir --no-deps -r requirements-adk.txt -c constraints.txt \
	&& python -c "import google.adk, mcp, vertexai.generative_models; print('imports ok')"

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 lexproof
USER lexproof

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
CMD exec uvicorn app.lexproof.main:app --host 0.0.0.0 --port ${PORT}