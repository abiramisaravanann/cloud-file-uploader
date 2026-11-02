FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source only — never copy .env or credential JSON files
COPY app.py .

ENV FLASK_APP=app.py
# PORT defaults to 8080 for Cloud Run; override with --env PORT=xxxx locally
ENV PORT=8080

EXPOSE 8080

# Use Gunicorn for production (Cloud Run)
# Credentials come from the attached Cloud Run service account at runtime
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "120", "--workers", "2", "app:app"]
