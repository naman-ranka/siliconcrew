# 🛠️ SiliconCrew Setup Guide

This guide covers the system requirements and installation steps to get the **SiliconCrew** autonomous hardware design agent running on your machine.

## 📋 Prerequisites

To run the full flow (Design -> Verify -> Synthesize), you need the following tools installed:

1.  **Python 3.10+** (The brain of the agent)
2.  **Icarus Verilog** (For simulation and linting)
3.  **Docker Desktop** (For OpenROAD synthesis flow)
4.  **Git** (For version control)

---

## 📥 Installation Steps

### 1. Clone the Repository
```bash
git clone https://github.com/naman-ranka/HardwareCoDesign.git
cd HardwareCoDesign
```

### 2. Python Environment
It is recommended to use a virtual environment.

**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Note: If `requirements.txt` is missing, install manually: `pip install langchain langchain-google-genai langgraph langgraph-checkpoint-sqlite streamlit watchdog python-dotenv`)*

### 3. Install Icarus Verilog (Simulation)

**Windows:**
1.  Download the installer from [bleyer.org/icarus](https://bleyer.org/icarus/).
2.  Run the installer.
3.  **Important:** Check the box "Add executable to PATH" during installation.
4.  Verify by running `iverilog -v` in a new terminal.

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install iverilog
```

**MacOS:**
```bash
brew install icarus-verilog
```

### 4. Setup Docker (Synthesis)

The agent uses the **OpenROAD Flow Scripts (ORFS)** docker image to perform synthesis, placement, and routing.

1.  Install **Docker Desktop** for your OS.
2.  Start Docker Desktop and ensure it is running.
3.  Pull the required image (Warning: This image is large, ~5GB):
    ```bash
    docker pull openroad/orfs
    ```
4.  Verify Docker is working:
    ```bash
    docker run --rm hello-world
    ```

---

## 🔑 Configuration

1.  Create a `.env` file in the root directory.
2.  Add your Google Gemini API Key:
    ```env
    GOOGLE_API_KEY=your_api_key_here
    ```

---

## 🚀 Running the Project

### Interactive Dashboard (Recommended)
The easiest way to use the agent is via the Streamlit dashboard.

```bash
streamlit run app.py
```
This will open a web interface at `http://localhost:8501`.

### Headless Mode (CLI)
To run the verification script directly without UI:

```bash
python tests/verify_architect.py
```

### 🧪 Running Individual Tool Tests

### 🧪 Running Individual Tool Tests

You can verify specific components of the system using the provided test scripts in the `tests/` directory.

**1. Infrastructure & Tools**
*   `python tests/verify_docker.py`: Checks if Docker is running and the OpenROAD image is accessible.
*   `python tests/verify_iverilog.py`: Checks if Icarus Verilog is installed and working.
*   `python tests/verify_linter.py`: Tests the Verilog syntax checker.
*   `python tests/verify_simulation.py`: Tests the compilation and simulation flow.
*   `python tests/verify_synthesis.py`: Tests the OpenROAD synthesis execution (requires Docker).
*   `python tests/verify_ppa.py`: Tests the PPA report parser (regex logic).
*   `python tests/test_waveform.py`: Tests the VCD waveform parser.

**2. Individual Agents**
*   `python tests/verify_rtl_coder.py`: Tests the **RTL Coder** (LLM) ability to write Verilog.
*   `python tests/verify_verifier.py`: Tests the **Verifier** (LLM) ability to write testbenches.
*   `python tests/verify_ppa_analyst.py`: Tests the **PPA Analyst** (LLM) ability to interpret metrics.

**3. System Integration**
*   `python tests/verify_architect.py`: Tests the **Architect** (Autonomous Agent) in headless mode.
*   `python tests/verify_cycle.py`: Tests the LangGraph state machine routing logic.
*   `python tests/verify_full_flow.py`: Runs the complete pipeline from RTL to GDSII.

---

## 🐛 Troubleshooting

*   **`iverilog` not found:** Ensure the path to `iverilog.exe` is in your System PATH environment variable.
*   **Docker permission denied:** On Linux, ensure your user is in the `docker` group (`sudo usermod -aG docker $USER`).
*   **Synthesis fails immediately:** Check if Docker is running. The agent attempts to mount the `workspace/` directory to Docker. Ensure File Sharing is enabled in Docker settings if using Windows.
