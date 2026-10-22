FROM python:3.12-slim

# Pinned so builds are repeatable.
RUN pip install --no-cache-dir uv==0.7.14

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ app/
COPY bike_models/ bike_models/

# Run as an unprivileged user. /data is where the database lives (a volume).
RUN useradd --system --uid 1000 --no-create-home torque \
    && mkdir /data && chown torque /data
USER torque

ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
