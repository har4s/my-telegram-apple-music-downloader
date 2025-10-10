FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install ffmpeg and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xz-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install static ffmpeg
RUN wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -O /tmp/ffmpeg.tar.xz && \
    tar -xf /tmp/ffmpeg.tar.xz -C /tmp && \
    mv /tmp/ffmpeg-*/ffmpeg /usr/local/bin/ && \
    mv /tmp/ffmpeg-*/ffprobe /usr/local/bin/ && \
    rm -rf /tmp/ffmpeg*

# Set working directory
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code into the container
COPY . .

# Run the bot
CMD ["python", "main.py"]
