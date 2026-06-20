# vLLM Real-time Monitor

A suite of tools to monitor vLLM instance metrics in real-time. This repository includes both a desktop GUI version and a standalone web-based Flask version.

---

## 🖥️ GUI Version (Desktop)

A lightweight Python desktop application for direct monitoring.

### Features
- **Real-time Metrics:** Tracks GPU/CPU KV cache usage and request states (running, waiting, swapped).
- **Throughput Visualization:** Live plots for Prompt and Generation tokens per second.
- **Customizable Refresh:** Set your own monitoring interval (default: 3s).
- **Persistent Settings & History:** Automatically stores and suggests up to the **5 most recent connected hosts** in a dropdown box.
- **Concurrency Benchmarking:** Built-in tool to run parallel performance tests under various concurrency levels (`1`, `2`, `4`, `8`, `16`, `32`, `64`), reporting overall **System TPS** and **Average Request TPS**.

### Requirements & Quick Start
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Requires `customtkinter`, `requests`, and `matplotlib`)*
2. Run the application:
   ```bash
   python vllm_monitor.py
   ```

---

## 🌐 Flask Web Version (Dashboard)

A standalone Flask-based web dashboard accessible via any browser.

### Features
- **Web Interface:** Access your vLLM metrics from any device in your network.
- **Persistent Settings:** Uses browser `localStorage` to save your config (no database required).
- **Interactive Charts:** Powered by `Chart.js` for smooth visualization.
- **Proxy Support:** Includes a Flask proxy to bypass CORS issues for remote telemetry.
- **Concurrent Benchmark Tool:** Integrated TPS test supporting multi-request parallel benchmarking.

### Requirements & Quick Start
1. Install dependencies:
   ```bash
   pip install Flask requests
   ```
2. Run the server:
   ```bash
   cd flask
   python app.py
   ```
3. Navigate to `http://localhost:5000` in your browser.

---

## 📝 License
This project is licensed under the [BSD 3-Clause License](LICENSE.md).
