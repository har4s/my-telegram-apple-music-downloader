FROM python:latest

# Set environment variables to avoid interactive prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    ca-certificates

# Define environment variable for architecture
# This will dynamically fetch architecture: amd64 (x86_64) or arm64
ARG ARCH=$(uname -m)

# Switch case for different architectures
RUN if [ "$ARCH" = "x86_64" ]; then \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -O /tmp/ffmpeg.tar.xz; \
    elif [ "$ARCH" = "aarch64" ]; then \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz -O /tmp/ffmpeg.tar.xz; \
    else \
    echo "Unsupported architecture: $ARCH" && exit 1; \
    fi

# Extract and install ffmpeg
RUN tar -xf /tmp/ffmpeg.tar.xz -C /tmp && \
    mv /tmp/ffmpeg-*/ffmpeg /usr/local/bin/ && \
    mv /tmp/ffmpeg-*/ffprobe /usr/local/bin/ && \
    rm -rf /tmp/ffmpeg*

# Create and set the working directory
WORKDIR /app

# Copy requirements file if you have one (optional)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code into the container
COPY . .

# Set the default command to run your bot
CMD ["python", "main.py"]