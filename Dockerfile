FROM python:3.11-slim

# Install Java 17 + git
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set Java env vars so J.A.R.V.I.S can find it
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:8080", "app:app"]
