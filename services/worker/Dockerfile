FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# CPU-only PyTorch keeps the image small; swap the index URL for a CUDA build if you have a GPU host.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY services/common /app/services/common
COPY services/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt ./services/common
COPY services/worker /app/services/worker
WORKDIR /app/services/worker
RUN useradd -m app && chown -R app /app
USER app
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]
