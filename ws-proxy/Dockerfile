FROM python:3.10-slim
WORKDIR /app
RUN pip install websockets
COPY proxy.py .
CMD ["python", "proxy.py"]
