# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Node.js for frontend build
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build frontend
COPY frontend/ /tmp/frontend/
WORKDIR /tmp/frontend
RUN npm install && npm run build

# Copy project files and frontend build
WORKDIR /app
COPY backend/ /app/
RUN cp -r /tmp/frontend/dist /app/frontend_dist

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=bingo.settings

# Expose port
EXPOSE 8000

# Copy superuser creation script
COPY backend/create_prod_superuser.py /app/create_prod_superuser.py

# Copy startup script that runs both Django app and Telegram bot
COPY start-app.sh /start-app.sh
RUN chmod +x /start-app.sh

# Create entrypoint script
RUN echo '#!/bin/bash\nset -e\necho "Running migrations..."\npython manage.py migrate --noinput\necho "Creating superuser if needed..."\npython create_prod_superuser.py || echo "Superuser creation skipped"\necho "Collecting static files (including frontend assets)..."\npython manage.py collectstatic --noinput || true\necho "Verifying frontend files..."\nls -la /app/frontend_dist/ || echo "Frontend dist not found"\nls -la /app/frontend_dist/assets/ 2>/dev/null || echo "Frontend assets not found"\necho "Starting server..."\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Start script runs both Django app and Telegram bot
CMD ["bash", "/start-app.sh"]
