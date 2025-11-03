FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory early so build steps can reference it
WORKDIR /app

# Install ffmpeg and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xz-utils \
    ca-certificates \
    ffmpeg

# Build GPAC and Bento4 on Debian base
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    git \
    g++ \
    make \
    cmake \
    zlib1g-dev \
    coreutils; \
    \
    # Build and install GPAC
    git clone --depth=1 https://github.com/gpac/gpac.git ./build/gpac; \
    cd ./build/gpac; \
    ./configure; \
    make -j"$(nproc)"; \
    make install; \
    MP4BOX_PATH="$(command -v MP4Box)"; \
    if [ -n "$MP4BOX_PATH" ]; then ln -sf "$MP4BOX_PATH" "$(dirname "$MP4BOX_PATH")/mp4box"; fi; \
    cd /app; \
    \
    # Build and install Bento4
    git clone --depth=1 https://github.com/axiomatic-systems/Bento4.git ./build/Bento4; \
    mkdir -p ./build/Bento4/cmakebuild; \
    cd ./build/Bento4/cmakebuild; \
    cmake -DCMAKE_BUILD_TYPE=Release ..; \
    make -j"$(nproc)"; \
    make install; \
    cd /app; \
    \
    # Clean up
    rm -rf ./build; \
    apt-get purge -y git g++ make cmake zlib1g-dev coreutils; \
    apt-get autoremove -y; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code into the container
COPY . .

# Run the bot
CMD ["python", "main.py"]
