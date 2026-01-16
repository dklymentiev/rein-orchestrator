FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (will be mounted as volume in production)
COPY . .

# Set umask so files are world-writable (for www-data to delete)
CMD ["sh", "-c", "umask 000 && python rein.py --daemon --daemon-interval 5 --max-workflows 3 --ws-port 8765"]
