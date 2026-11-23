FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY core/ core/
COPY sites_backend.py ./

ENV STORIDEX_RUNS_DIR=/data/runs
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 180 sites_backend:application"]
