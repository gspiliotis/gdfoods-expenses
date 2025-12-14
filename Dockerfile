# Use official Python runtime as base image
FROM python:3.12-slim

# Set working directory in container
WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY fetch_expenses.py .
COPY vat_numbers.txt .

# Create directory for credentials and config files
RUN mkdir -p /app/config

# Make script executable
RUN chmod +x fetch_expenses.py

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command (can be overridden)
ENTRYPOINT ["python", "fetch_expenses.py"]
CMD ["--help"]
