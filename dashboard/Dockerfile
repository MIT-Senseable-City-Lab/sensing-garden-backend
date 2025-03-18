FROM python:3.9-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY . .

# Create common directory and copy schema files
RUN mkdir -p /common
COPY ../common/db-schema.json /common/
COPY ../common/api-schema.json /common/

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

EXPOSE 5052
CMD ["gunicorn", "--bind", "0.0.0.0:5052", "--timeout", "120", "app:app"]
