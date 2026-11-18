FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY bot ./bot

# Ma'lumotlar bazasi /app/data ichida saqlanadi — hostingda shu papkaga doimiy disk (volume) ulanadi
RUN mkdir -p /app/data
# Mini App veb-serveri
EXPOSE 8080
CMD ["python", "-m", "bot"]
