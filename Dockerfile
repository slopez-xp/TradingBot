# Use a lightweight Python image
FROM python:3.12-slim

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Create a non-root user and group for running the application
RUN addgroup --system app && adduser --system --ingroup app app

# Create and set permissions for a Numba cache directory
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
RUN mkdir -p $NUMBA_CACHE_DIR && chown -R app:app $NUMBA_CACHE_DIR

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
# These should run as root, before switching to 'app' user
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code and set ownership
COPY --chown=app:app . .

# Switch to the non-root user
USER app

# Expose the port the app runs on
EXPOSE 8000

# Define the command to start Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
