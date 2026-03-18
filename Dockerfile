FROM python:3.12-slim

# Install EDA tools, Docker CLI, and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    iverilog \
    yosys \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI (for DooD — talks to host daemon via socket)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python backend
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Frontend
WORKDIR /app/frontend
RUN npm install
WORKDIR /app

ENV RTL_WORKSPACE=/workspace
ENV WORKSPACE_VOLUME=sc-workspace

EXPOSE 3000 8000

# Start both backend and frontend
CMD bash -c "uvicorn api:app --host 0.0.0.0 --port 8000 & cd frontend && npm run dev -- -p 3000 & wait"
