<!-- classy+'s vision, brought to life. -->
# GEMINI.md — SIDELAB Project Context

## Project Overview

**SIDELAB** (Advanced Universal Diagnostic & Responsive Expert Yield) is a sophisticated Clinical Intelligence Platform architected for Primary Healthcare (Puskesmas) in Indonesia. It serves as a Clinical Decision Support System (CDSS) providing structured clinical guidance, ICD-10 coding, and pharmacological recommendations.

- **Primary Technologies:** Python 3.14+, Rich (Terminal UI), Ollama (Local LLM), DeepSeek (Cloud LLM), Requests, Dotenv.
- **Target Environment:** Windows-based clinical terminals with varying hardware capabilities (8GB-16GB RAM).

### Architecture

1.  **Orchestrator (`medgemma_chat.py`):** The main entry point. Handles the terminal-based chat loop, RAG logic, and clinical protocol formatting.
2.  **LLM Module (`sidelab/llm/`):**
    -   Multi-backend router supporting DeepSeek (default), Local Ollama, NVIDIA NIM, Google Gemini (Vertex), and others.
    -   Implements an OpenAI-compatible client for most cloud providers.
3.  **ICD Module (`sidelab/icd/`):**
    -   Manages an Indonesian-localized ICD-10 database (`data/icd10_indonesia.json`).
    -   Provides search, retrieval, and REPL functionality for medical coding.
4.  **Notification Module (`sidelab/notify/`):**
    -   Optional Telegram integration for sending clinical summaries.
5.  **RAG Engine:**
    -   Advanced clinical retrieval using TF-IDF and clinical entity recognition.
    -   Injects data from Indonesian SKDI (144 diseases), PPK IDI, and local pharmacy stock data.
    -   Features "Red Flag" detection for high-risk clinical scenarios.

---

## Building and Running

### Setup
The project uses a local virtual environment and batch scripts for lifecycle management.

- **Installation:** Run `install.bat`. This sets up the `.venv`, installs dependencies from `requirements.txt`, and checks for Ollama.
- **Diagnostics:** Run `diagnose-sidelab.bat` to generate a system health report in the `diagnostics/` folder.

### Running the Application
- **Standard Launch:** Run `SIDELAB.bat` (or `run.bat` for direct venv execution).
- **Environment Configuration:** Managed via `.env`. Key variables:
    - `DEEPSEEK_API_KEY`: Required for Cloud mode.
    - `SIDELAB_DEFAULT_BACKEND`: Sets default inference engine.
    - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: For notification features.

### Testing
- **Test Runner:** `pytest`
- **Commands:** Run `pytest` from the root directory to execute the test suite in `tests/`.

---

## Development Conventions

- **Clinical Integrity:** The system follows strict protocols (SKDI, FORNAS 2023, PPK IDI). Changes to clinical logic or output formatting must adhere to the 8-section "SIDELAB Protocol" defined in `medgemma_chat.py`.
- **Typing:** Uses `from __future__ import annotations` and type hints (e.g., `str | None`).
- **Formatting:** Terminal output is strictly managed via the `rich` library with a "Platinum & Onyx" monochromatic aesthetic.
- **Indonesian Localization:** Indonesia is the primary language (70% Indonesian, 30% English for technical/clinical terms).
- **Safety First:** Red flag detection is prioritized. Always verify that new features do not bypass the safety guardrails in `_detect_red_flags`.
