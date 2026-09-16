FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --upgrade pip wheel setuptools

COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

RUN pip uninstall -y pip setuptools wheel 2>/dev/null || true

COPY news_processor.py .
COPY image_utils.py .

RUN useradd -u 10001 -m appuser
USER appuser

CMD ["python", "news_processor.py"]
