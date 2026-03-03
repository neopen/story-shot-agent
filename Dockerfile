    # Use a slim Python base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable stdout/stderr to be unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system deps required to build some Python packages (if any)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential libffi-dev libssl-dev git curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker cache
COPY requirements.txt ./

# Install Python dependencies
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . /app

# Expose default application port
EXPOSE 8000

# Recommended environment variables (can be overridden at runtime)
ENV API__HOST=0.0.0.0
ENV API__PORT=8000

# Entrypoint uses the repo's entrypoint script which execs to the app process
ENTRYPOINT ["python", "-m", "scripts.entrypoint"]
# Default behavior: start the service
CMD ["start"]

