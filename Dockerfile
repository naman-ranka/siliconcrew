FROM python:3.12-slim

# Install EDA tools, Docker CLI, and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    iverilog \
    yosys \
    ca-certificates \
    curl \
    git \
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

# ---- Native EDA toolchains for hosted SIM_ENGINE=native (Cloud Run, no DooD) ----
# iverilog + yosys are already installed above, and cocotb comes via pip
# (requirements.txt). These add what the three light engines (xls/sby/cocotb)
# need to run as NATIVE subprocesses instead of Docker:
#   * build-essential — C compiler/make for cocotb's Icarus VPI build
#   * z3              — SMT solver SymbiYosys needs (yosys/yosys-smtbmc present)
#   * SymbiYosys (sby)— the `sby` CLI (installed from source; uses yosys-smtbmc)
#   * Google XLS      — interpreter_main / ir_converter_main / opt_main /
#                       codegen_main / benchmark_main / xlscc on PATH
# Harmless locally (default SIM_ENGINE=docker). For a leaner/faster LOCAL image:
#   docker build --build-arg INSTALL_NATIVE_TOOLCHAINS=0 ...
ARG INSTALL_NATIVE_TOOLCHAINS=1
# Point at a valid Google XLS Linux release tarball for native XLS (the layout
# changes across releases; verify the binaries land on PATH after extract).
ARG XLS_RELEASE_URL=https://github.com/google/xls/releases/latest/download/xls-linux-x64.tar.gz
RUN if [ "$INSTALL_NATIVE_TOOLCHAINS" = "1" ]; then set -eux; \
      apt-get update && apt-get install -y --no-install-recommends \
        build-essential z3 libffi-dev make && \
      git clone --depth 1 https://github.com/YosysHQ/sby.git /tmp/sby && \
        make -C /tmp/sby install && rm -rf /tmp/sby && \
      mkdir -p /opt/xls && \
        ( curl -fsSL "$XLS_RELEASE_URL" | tar -xz -C /opt/xls \
          || echo "WARN: XLS download failed; set --build-arg XLS_RELEASE_URL for native XLS" ) && \
      rm -rf /var/lib/apt/lists/*; \
    fi
ENV PATH="/opt/xls:${PATH}"

# Python backend
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Frontend
COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm install
WORKDIR /app

COPY . .

ENV RTL_WORKSPACE=/workspace

EXPOSE 3000 8000 8080

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
