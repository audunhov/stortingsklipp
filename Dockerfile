FROM python:3.14-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY web.py stortingklipp.py ./

EXPOSE 8000
CMD ["python3", "web.py", "--host", "0.0.0.0", "--port", "8000"]
