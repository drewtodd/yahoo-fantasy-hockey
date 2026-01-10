FROM python:3.12-slim

WORKDIR /app

# System deps (add more only if you need them later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project
COPY . .

# Default entrypoint (your contract)
ENTRYPOINT ["python", "create_bodies_table.py"]