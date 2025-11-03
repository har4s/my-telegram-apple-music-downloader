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
    libicu76 \
    && rm -rf /var/lib/apt/lists/*

# Download and install pre-built binaries
RUN set -eux; \
    # Install GPAC (MP4Box) from official release
    wget -O /tmp/gpac.deb "https://download.tsi.telecom-paristech.fr/gpac/release/2.4/gpac_2.4-rev0-g5d70253a-master_amd64.deb"; \
    dpkg -i /tmp/gpac.deb || apt-get install -f -y; \
    ln -sf /usr/bin/MP4Box /usr/local/bin/mp4box; \
    \
    # Install Bento4 (mp4decrypt and other tools)
    wget -O /tmp/bento4.zip "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"; \
    unzip /tmp/bento4.zip -d /tmp/bento4; \
    find /tmp/bento4 -name "mp4decrypt" -type f -exec install -m 755 {} /usr/local/bin/mp4decrypt \;; \
    \
    # Install N_m3u8DL-RE
    wget -O /tmp/N_m3u8DL-RE.tar.gz "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_v0.5.1-beta_linux-x64_20251029.tar.gz"; \
    tar -xzf /tmp/N_m3u8DL-RE.tar.gz -C /tmp; \
    find /tmp -name "N_m3u8DL-RE" -type f -exec install -m 755 {} /usr/local/bin/N_m3u8DL-RE \;; \
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
