FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Optional: run as non-root user
RUN useradd -m app && chown -R app:app /app
USER app

CMD ["python3", "bot.py"]
