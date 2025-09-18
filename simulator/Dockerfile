FROM python:3.11-slim
WORKDIR /simulator
COPY replay.py .
RUN pip install --no-cache-dir requests
CMD ["python", "replay.py", "--rate", "5"]
