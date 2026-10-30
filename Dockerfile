FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock \
    && pip check \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app

COPY app ./app
COPY migrations ./migrations
COPY tests ./tests
COPY config.py run.py tags.json achievements.json ./
COPY docker-entrypoint.sh ./
RUN mkdir -p /app/instance /app/app/static/achievements_icons \
    && chown -R app:app /app/instance \
    && chmod +x /app/docker-entrypoint.sh

USER app
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/login', timeout=3).close()"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "run.py"]
