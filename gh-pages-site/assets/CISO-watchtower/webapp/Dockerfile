# Stage 1: Build Tailwind CSS
FROM node:20-alpine AS tailwind
WORKDIR /build
COPY static/css/input.css ./static/css/input.css
COPY static/js/ ./static/js/
COPY templates/ ./templates/
COPY tailwind.config.js ./
RUN npm install tailwindcss @tailwindcss/cli
RUN npx @tailwindcss/cli -i ./static/css/input.css -o ./static/css/output.css --minify

# Stage 2: Flask App
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

COPY app.py .
COPY templates/ templates/
COPY static/ static/

COPY --from=tailwind /build/static/css/output.css ./static/css/output.css

RUN useradd -u 10001 -m appuser
USER appuser

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "app:app"]
