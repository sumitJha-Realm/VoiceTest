# Voice server for Hugging Face Spaces (Docker SDK) / Render / Fly.io.
# HF Spaces expects the app on port 7860.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860
EXPOSE 7860

CMD ["python", "main.py"]
