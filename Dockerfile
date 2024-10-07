# Use the official Ubuntu base image
FROM ubuntu:latest

# Set environment variables to avoid interactive prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Update the package list and install Python, FFmpeg, and other necessary packages
RUN apt-get update && \
    apt-get install -y python3 python3-pip ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create and set the working directory
WORKDIR /app

# Copy requirements file if you have one (optional)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code into the container
COPY . .

# Set the default command to run your bot
CMD ["python3", "main.py"]