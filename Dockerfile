FROM python:3.11-slim-bookworm

# Install runtime dependencies for network ping and upsc binary utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    nut-client \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install dependencies first to optimize layers caching
COPY pyproject.toml . 
RUN pip install --no-cache-dir .

# Copy structural codebase blocks inside
COPY src/ src/
RUN pip install --no-cache-dir .

# Create the standard persistent config target dir mapping point
RUN mkdir -p /config

ENV PYTHONUNBUFFERED=1

CMD ["wolnut", "--config", "/config/config.yaml"]
