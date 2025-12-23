FROM python:3.14-slim

LABEL maintainer="PythonID Bot"
LABEL description="Telegram bot for group profile monitoring"

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy all project files
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Install dependencies
RUN uv sync --frozen

# Create non-root user and set ownership
RUN useradd -m -u 1000 bot && chown -R bot:bot /app

# Switch to non-root user
USER bot

# Run the bot
CMD ["uv", "run", "pythonid-bot"]
