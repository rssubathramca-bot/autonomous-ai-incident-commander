FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 simulation
COPY simulation/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY simulation /app/simulation
RUN chown -R simulation:simulation /app

USER simulation
EXPOSE 8088 8090 8091 8092