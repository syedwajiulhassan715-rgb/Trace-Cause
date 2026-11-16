FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tracecause ./tracecause
ENV TRACECAUSE_DB=/data/spans.db
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "tracecause.app:default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
