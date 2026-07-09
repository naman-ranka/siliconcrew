FROM python:3.12-slim

# Install EDA tools, Docker CLI, and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    iverilog \
    verilator \
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
#   * Google XLS      — DSLX/IR toolchain binaries (interpreter_main,
#                       ir_converter_main, opt_main, codegen_main) on PATH
# Harmless locally (default SIM_ENGINE=docker). For a leaner/faster LOCAL image:
#   docker build --build-arg INSTALL_NATIVE_TOOLCHAINS=0 ...
ARG INSTALL_NATIVE_TOOLCHAINS=1
# Keep this pinned: hosted native mode depends on these binaries being present
# in the backend image. If download/extract/verification fails, fail the build.
ARG XLS_VERSION=v0.0.0-10092-g25df2916b
ARG XLS_SHA256=
ENV PATH="/opt/xls:/opt/xls/xls/tools:/opt/xls/xls/dslx:/opt/xls/xls/dslx/ir_convert:${PATH}"
RUN if [ "$INSTALL_NATIVE_TOOLCHAINS" = "1" ]; then set -eux; \
      apt-get update && apt-get install -y --no-install-recommends \
        build-essential z3 libffi-dev make tar && \
      git clone --depth 1 https://github.com/YosysHQ/sby.git /tmp/sby && \
        make -C /tmp/sby install && rm -rf /tmp/sby && \
      mkdir -p /opt/xls && \
      curl -fL "https://github.com/google/xls/releases/download/${XLS_VERSION}/xls-${XLS_VERSION}-linux-x64.tar.gz" \
        -o /tmp/xls.tar.gz && \
      if [ -n "$XLS_SHA256" ]; then echo "$XLS_SHA256  /tmp/xls.tar.gz" | sha256sum -c -; fi && \
      tar -xzf /tmp/xls.tar.gz -C /opt/xls --strip-components=1 && \
      rm /tmp/xls.tar.gz && \
      command -v interpreter_main && \
      command -v ir_converter_main && \
      command -v opt_main && \
      command -v codegen_main && \
      printf '%s\n' 'fn main() -> u32 { u32:42 }' > /tmp/xls_smoke.x && \
      interpreter_main /tmp/xls_smoke.x >/dev/null && \
      ir_converter_main --top=main /tmp/xls_smoke.x > /tmp/xls_smoke.ir && \
      opt_main /tmp/xls_smoke.ir > /tmp/xls_smoke.opt.ir && \
      codegen_main --generator=combinational /tmp/xls_smoke.opt.ir > /tmp/xls_smoke.v && \
      grep -q "module" /tmp/xls_smoke.v && \
      rm -f /tmp/xls_smoke.x /tmp/xls_smoke.ir /tmp/xls_smoke.opt.ir /tmp/xls_smoke.v && \
      rm -rf /var/lib/apt/lists/*; \
    fi

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
