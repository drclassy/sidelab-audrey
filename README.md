<!-- classy+'s vision, brought to life. -->
# SideLab — Clinical Intelligence Platform

[![Build Status](https://img.shields.io/github/actions/workflow/status/classyplus/sidelab/ci.yml?branch=main)](https://github.com/classyplus/sidelab/actions)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**SideLab** is an advanced Clinical Decision Support System (CDSS) providing structured clinical guidance, ICD-10 coding, and pharmacological recommendations. Architected for Primary Healthcare (Puskesmas) in Indonesia.

## Architecture
- **Orchestrator:** Terminal-based RAG logic and clinical protocol formatting.
- **LLM Module:** Multi-backend router (DeepSeek, Local Ollama, NVIDIA NIM, Google Gemini).
- **ICD Module:** Indonesian-localized ICD-10 database integration.
- **RAG Engine:** TF-IDF based clinical entity recognition and Red Flag detection.

## Prerequisites
- Python 3.12+ (3.14+ recommended)
- 8GB RAM Minimum (16GB recommended for Local Ollama mode)

## Installation & Usage
Please refer to `README-INSTALL.md` for detailed setup instructions.

## Documentation
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

## License
MIT License. See [LICENSE](LICENSE) for details.
