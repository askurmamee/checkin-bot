FROM python:3.12-slim
RUN useradd --create-home appuser
WORKDIR /home/appuser/app
USER appuser
COPY --chown=appuser:appuser requirements.txt ./
RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser . .
RUN mkdir -p /home/appuser/app/data
ENV CHECKIN_DB=/home/appuser/app/data/checkin.db
CMD ["python3", "bot.py"]
