FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory early so build steps can reference it
WORKDIR /app

# Install ffmpeg and dependencies for downloading binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Download and install pre-built binaries
RUN set -eux; \
    # Install GPAC (MP4Box) from nightly builds
    wget -O /tmp/gpac.zip "https://download.tsi.telecom-paristech.fr/gpac/nightly_builds/linux64/gpac_nightly_linux64.zip"; \
    unzip /tmp/gpac.zip -d /tmp/gpac; \
    find /tmp/gpac -name "MP4Box" -type f -exec install -m 755 {} /usr/local/bin/MP4Box \;; \
    ln -sf /usr/local/bin/MP4Box /usr/local/bin/mp4box; \
    \
    # Install Bento4 (mp4decrypt and other tools)
    wget -O /tmp/bento4.zip "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"; \
    unzip /tmp/bento4.zip -d /tmp/bento4; \
    find /tmp/bento4 -name "mp4decrypt" -type f -exec install -m 755 {} /usr/local/bin/mp4decrypt \;; \
    \
    # Install N_m3u8DL-RE
    wget -O /tmp/N_m3u8DL-RE.zip "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_Beta_linux-x64_20240828.zip"; \
    unzip /tmp/N_m3u8DL-RE.zip -d /tmp/N_m3u8DL-RE; \
    find /tmp/N_m3u8DL-RE -name "N_m3u8DL-RE" -type f -exec install -m 755 {} /usr/local/bin/N_m3u8DL-RE \;; \
    \
    # Clean up
    rm -rf /tmp/*

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code into the container
COPY . .

# Run the bot
CMD ["python", "main.py"]
