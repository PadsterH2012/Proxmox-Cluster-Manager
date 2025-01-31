FROM python:3.9-slim
RUN apt-get update && apt-get install -y libpq-dev gcc && \
    pip install flask flask-sqlalchemy flask-session flask-wtf psycopg2-binary proxmoxer requests apscheduler paramiko python-json-logger pytest && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /tmp/flask_session && \
    chmod 777 /tmp/flask_session
COPY . /app/
WORKDIR /app
ENV PYTHONPATH=/app
EXPOSE 5000
CMD ["python", "app.py"]
