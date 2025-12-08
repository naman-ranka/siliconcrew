# SiliconCrew: Autonomous Hardware Design Agent

**SiliconCrew** is an agentic AI framework that automates the digital hardware design loop. It orchestrates three specialized AI agents to transform natural language specifications into functionally verified, physically realizable silicon designs.

## 🤖 The Architecture

The system uses a cyclic **LangGraph** state machine to iterate, debug, and self-correct:

1.  **The Architect (RTL Coder)**: Writes SystemVerilog based on specs and linter feedback.
2.  **The Auditor (Verifier)**: Writes testbenches, runs simulations (Icarus Verilog), and analyzes waveforms.
3.  **The Builder (PPA Analyst)**: Runs synthesis (OpenROAD) to generate GDSII layouts and analyze Power, Performance, and Area (PPA).

---

## 🚀 Getting Started

You can run SiliconCrew in two ways. **Option 1 (Dev Container)** is recommended for the easiest setup.

### Option 1: VS Code Dev Container (Recommended)
*Best for: Users who want a "one-click" setup without installing tools manually.*

1.  Install **Docker Desktop** and **VS Code**.
2.  Install the **Dev Containers** extension in VS Code.
3.  Open this folder in VS Code.
4.  Click **"Reopen in Container"** when prompted.
    *   *This automatically installs Python, Icarus Verilog, and all dependencies.*
5.  Open the terminal in VS Code and run:
    ```bash
    streamlit run app.py
    ```

### Option 2: Local Setup (Power Users)
*Best for: Users who prefer running tools natively on their OS.*

1.  **Install Prerequisites**:
    *   **Python 3.10+**
    *   **Icarus Verilog**:
        *   *Windows*: [Download Installer](https://bleyer.org/icarus/) (Check "Add to PATH").
        *   *Linux*: `sudo apt-get install iverilog`
        *   *Mac*: `brew install icarus-verilog`
    *   **Docker** (Optional, only required for Synthesis/Layout).

2.  **Setup Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Run**:
    ```bash
    streamlit run app.py
    ```

---

## 🔑 Configuration

Create a `.env` file in the root directory with your Google Gemini API Key:
```env
GOOGLE_API_KEY=your_api_key_here
```

---

## 🛠️ Usage

Once the app is running at `http://localhost:8501`:

1.  **Chat**: Describe your design (e.g., "Design a 4-bit counter with reset").
2.  **Code Tab**: Watch the agent write Verilog in real-time.
3.  **Waveform Tab**: View simulation results (VCD) to verify functionality.
4.  **Layout Tab**: (Requires Docker) View the final GDSII layout after synthesis.

---

## 📂 Project Structure

*   `src/agents`: Logic for the Architect, Verifier, and Builder.
*   `src/tools`: Python wrappers for Icarus, OpenROAD, and File I/O.
*   `src/graph`: LangGraph state machine definitions.
*   `workspace/`: Sandbox where agents write code and tools dump logs.
*   `.devcontainer/`: Configuration for the VS Code Dev Container.

---

**License**: MIT