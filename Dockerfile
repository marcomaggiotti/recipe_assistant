FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY topping_service ./topping_service
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Which app this image runs: "pizza-service" (default, app/main.py) or
# "topping-service" (topping_service/main.py) - see docker-entrypoint.sh. Both apps
# expose GET /health on port 8000, so this healthcheck works regardless of SERVICE.
ENV SERVICE=pizza-service

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
