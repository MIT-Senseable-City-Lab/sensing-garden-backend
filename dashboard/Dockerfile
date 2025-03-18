FROM python:3.9-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY dashboard/pyproject.toml /app/dashboard/

# Install dependencies
RUN pip install --upgrade pip && \
    pip install flask==2.2.5 boto3 python-dotenv

# Copy application code
COPY dashboard /app/dashboard/

# Set environment variables
ENV PYTHONPATH=/app/dashboard
ENV PORT=5052

# Expose the port
EXPOSE 5052

# Run the application
CMD cd dashboard && python -c "import os; from app import app; app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5052)))"
