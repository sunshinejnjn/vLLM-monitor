import customtkinter as ctk
import requests
import threading
import time
import json
import os
import re
import collections
import datetime
import webbrowser
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class VLLMMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("vLLM Real-time Monitor")
        self.geometry("720x950")
        
        # History
        self.history = collections.defaultdict(lambda: collections.deque(maxlen=3600))
        self.history_times = collections.deque(maxlen=3600)
        self.start_time = time.time()

        # Config variables
        self.is_monitoring = False
        self.metrics_url = ""
        self.update_interval = 3.0  # seconds
        self.config_file = "vllm_config.json"
        
        self.current_model_name = "Unknown"

        # UI Setup
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top connection frame
        self.conn_frame = ctk.CTkFrame(self)
        self.conn_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        self.conn_frame.grid_columnconfigure(1, weight=1)

        self.lbl_host = ctk.CTkLabel(self.conn_frame, text="vLLM Host:Port")
        self.lbl_host.grid(row=0, column=0, padx=10, pady=10)

        self.entry_host = ctk.CTkComboBox(self.conn_frame, values=["127.0.0.1:8000"])
        self.entry_host.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.btn_connect = ctk.CTkButton(self.conn_frame, text="Connect", command=self.toggle_connection, width=180)
        self.btn_connect.grid(row=0, column=2, padx=10, pady=10)

        self.lbl_refresh = ctk.CTkLabel(self.conn_frame, text="Refresh Rate:")
        self.lbl_refresh.grid(row=1, column=0, padx=10, pady=10)

        self.refresh_model_frame = ctk.CTkFrame(self.conn_frame, fg_color="transparent")
        self.refresh_model_frame.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.refresh_model_frame.grid_columnconfigure(1, weight=1)

        self.combo_refresh = ctk.CTkComboBox(self.refresh_model_frame, values=["1 sec", "2 sec", "3 sec", "5 sec", "10 sec"], command=self.change_refresh_rate)
        self.combo_refresh.set("3 sec")
        self.combo_refresh.grid(row=0, column=0, sticky="w")

        self.lbl_model = ctk.CTkLabel(self.refresh_model_frame, text="Model: Unknown", font=("Arial", 12, "bold"), text_color="#1f538d")
        self.lbl_model.grid(row=0, column=1, padx=(20, 10), sticky="e")

        self.btn_open_metrics = ctk.CTkButton(self.conn_frame, text="Open Metrics in Browser", command=self.open_metrics_browser, state="disabled", width=180)
        self.btn_open_metrics.grid(row=1, column=2, padx=10, pady=10)

        self.btn_benchmark = ctk.CTkButton(self.conn_frame, text="Run Benchmark", command=self.run_benchmark, state="disabled")
        self.btn_benchmark.grid(row=2, column=0, padx=10, pady=10)

        # Sub-frame to hold concurrency selector and benchmark result on the same row
        self.bench_sub_frame = ctk.CTkFrame(self.conn_frame, fg_color="transparent")
        self.bench_sub_frame.grid(row=2, column=1, columnspan=2, padx=10, pady=10, sticky="ew")
        self.bench_sub_frame.grid_columnconfigure(1, weight=1)

        self.combo_concurrency = ctk.CTkComboBox(self.bench_sub_frame, values=["1", "2", "4", "8", "16", "32", "64"], width=60)
        self.combo_concurrency.set("1")
        self.combo_concurrency.grid(row=0, column=0, sticky="w")

        self.lbl_benchmark_result = ctk.CTkLabel(self.bench_sub_frame, text="Benchmark TPS: N/A", text_color="gray")
        self.lbl_benchmark_result.grid(row=0, column=1, padx=10, sticky="w")

        # Dashboard frame
        self.dash_frame = ctk.CTkScrollableFrame(self)
        self.dash_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.dash_frame.grid_columnconfigure(1, weight=1)

        # Metrics widgets
        self.lbl_status = ctk.CTkLabel(self.dash_frame, text="Status: Disconnected", text_color="gray")
        self.lbl_status.grid(row=0, column=0, columnspan=3, pady=10)

        # Row builder helper
        self.current_row = 1
        self.lbl_gpu_cache_val = self.add_value_row("GPU KV Cache Usage:")
        self.lbl_cpu_cache_val = self.add_value_row("CPU KV Cache Usage:")
        
        self.val_req_running = self.add_value_row("Requests Running:")
        self.val_req_swapped = self.add_value_row("Requests Swapped:")
        self.val_req_waiting = self.add_value_row("Requests Waiting:")
        
        self.val_throughput = self.add_value_row("Prompt Throughput (tok/s):")
        self.val_gen_throughput = self.add_value_row("Generation Throughput (tok/s):")

        # State for throughput diff
        self.last_prompt_tokens = -1
        self.last_gen_tokens = -1
        self.last_time = time.time()
        
        self.setup_plots()

    def setup_plots(self):
        # The main plots go in column 1 which naturally expands.
        def create_plot(row, rowspan):
            fig = Figure(figsize=(5.5, 2), dpi=100)
            fig.patch.set_facecolor('#2b2b2b')
            ax = fig.add_subplot(111)
            ax.set_facecolor('#2b2b2b')
            ax.tick_params(colors='white', labelsize=8)
            ax.xaxis.label.set_color('white')
            ax.yaxis.label.set_color('white')
            for spine in ax.spines.values():
                spine.set_edgecolor('white')
            fig.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.3)
            
            canvas = FigureCanvasTkAgg(fig, master=self.dash_frame)
            canvas.get_tk_widget().grid(row=row, column=1, rowspan=rowspan, padx=10, pady=5, sticky="nsew")
            return fig, ax, canvas

        self.fig_req, self.ax_req, self.canvas_req = create_plot(1, 3)
        self.fig_prompt, self.ax_prompt, self.canvas_prompt = create_plot(4, 2)
        self.fig_gen, self.ax_gen, self.canvas_gen = create_plot(6, 2)

    def update_plots(self):
        if not self.history_times:
            return
            
        t = list(self.history_times)
        
        self.ax_req.clear()
        self.ax_req.set_title("Requests", color='white', fontsize=10)
        if self.history["req_run"]:
            self.ax_req.plot(t, list(self.history["req_run"]), label="Running")
        if self.history["req_wait"]:
            self.ax_req.plot(t, list(self.history["req_wait"]), label="Waiting")
        if self.history["req_swap"]:
            self.ax_req.plot(t, list(self.history["req_swap"]), label="Swapped")
        self.ax_req.legend(loc="upper left", fontsize='x-small')
        self.ax_req.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        
        self.ax_prompt.clear()
        self.ax_prompt.set_title("Prompt Throughput (tok/s)", color='white', fontsize=10)
        if self.history["prompt_rate"]:
            self.ax_prompt.plot(t, list(self.history["prompt_rate"]), label="Prompt")
        self.ax_prompt.legend(loc="upper left", fontsize='x-small')
        self.ax_prompt.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        
        self.ax_gen.clear()
        self.ax_gen.set_title("Generation Throughput (tok/s)", color='white', fontsize=10)
        if self.history["gen_rate"]:
            self.ax_gen.plot(t, list(self.history["gen_rate"]), label="Gen", color="#2ca02c")
        self.ax_gen.legend(loc="upper left", fontsize='x-small')
        self.ax_gen.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

        for ax in [self.ax_req, self.ax_prompt, self.ax_gen]:
            ax.set_ylim(bottom=0)
            ax.tick_params(axis='x', rotation=25)
            if t and t[-1] - t[0] > datetime.timedelta(hours=1):
                ax.set_xlim(left=t[-1] - datetime.timedelta(hours=1), right=t[-1])
            
        self.canvas_req.draw()
        self.canvas_prompt.draw()
        self.canvas_gen.draw()

    def add_value_row(self, label_text):
        frame = ctk.CTkFrame(self.dash_frame, fg_color="transparent")
        frame.grid(row=self.current_row, column=0, padx=10, pady=10, sticky="nw")
        
        lbl = ctk.CTkLabel(frame, text=label_text, font=("Arial", 14, "bold"))
        lbl.grid(row=0, column=0, sticky="w")
        
        val_lbl = ctk.CTkLabel(frame, text="0", font=("Arial", 16))
        val_lbl.grid(row=1, column=0, pady=(5, 0), sticky="w")
        
        self.current_row += 1
        return val_lbl

    def change_refresh_rate(self, choice):
        try:
            self.update_interval = float(choice.split()[0])
        except ValueError:
            pass

    def load_config(self):
        default_host = "127.0.0.1:8000"
        self.hosts_history = [default_host]
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    hosts = config.get("hosts", [])
                    last_host = config.get("last_host", "")
                    
                    if not hosts and last_host:
                        hosts = [last_host]
                        
                    if hosts:
                        seen = set()
                        self.hosts_history = [x for x in hosts if not (x in seen or seen.add(x))][:5]
                    
                    if not self.hosts_history:
                        self.hosts_history = [default_host]
            except Exception as e:
                print(f"Error loading config: {e}")
                self.hosts_history = [default_host]
        
        self.entry_host.configure(values=self.hosts_history)
        self.entry_host.set(self.hosts_history[0])
        self.after(50, self.toggle_connection)

    def save_config(self, host_str):
        try:
            if host_str in self.hosts_history:
                self.hosts_history.remove(host_str)
            self.hosts_history.insert(0, host_str)
            self.hosts_history = self.hosts_history[:5]
            
            self.entry_host.configure(values=self.hosts_history)
            self.entry_host.set(host_str)
            
            with open(self.config_file, "w") as f:
                json.dump({"hosts": self.hosts_history, "last_host": host_str}, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def toggle_connection(self):
        if not self.is_monitoring:
            host_str = self.entry_host.get().strip()
            if not host_str:
                self.lbl_status.configure(text="Please enter a valid host:port", text_color="red")
                return

            if not host_str.startswith("http://") and not host_str.startswith("https://"):
                host_str = "http://" + host_str
            
            if not host_str.endswith("/metrics"):
                self.metrics_url = host_str.rstrip("/") + "/metrics"
            else:
                self.metrics_url = host_str

            self.save_config(self.entry_host.get().strip())

            self.btn_connect.configure(text="Disconnect")
            self.entry_host.configure(state="disabled")
            self.is_monitoring = True
            self.lbl_model.configure(text="Model: Unknown")
            self.current_model_name = "Unknown"
            self.btn_benchmark.configure(state="normal", text="Run Benchmark")
            self.lbl_benchmark_result.configure(text="Benchmark TPS: N/A", text_color="gray")
            self.btn_open_metrics.configure(state="normal")
            
            # Reset counters
            self.history.clear()
            self.history_times.clear()
            self.start_time = time.time()
            self.last_prompt_tokens = -1
            self.last_gen_tokens = -1
            self.last_time = time.time()
            self.update_plots()
            
            # Start monitoring thread
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
        else:
            self.is_monitoring = False
            self.btn_connect.configure(text="Connect")
            self.entry_host.configure(state="normal")
            self.lbl_status.configure(text="Status: Disconnected", text_color="gray")
            self.lbl_model.configure(text="Model: Unknown")
            self.current_model_name = "Unknown"
            self.btn_benchmark.configure(state="disabled", text="Run Benchmark")
            self.btn_open_metrics.configure(state="disabled")

    def parse_metrics(self, text):
        # A simple regex-based Prometheus parser for the metrics we care about
        metrics = {}
        model_name = "Unknown"
        for line in text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if 'model_name="' in line:
                match = re.search(r'model_name="([^"]+)"', line)
                if match:
                    model_name = match.group(1)

            # Match name and value
            parts = line.split(' ')
            if len(parts) >= 2:
                name_part = parts[0]
                val_part = parts[-1]
                
                # Extract clean name
                clean_name = name_part.split('{')[0]
                try:
                    val = float(val_part)
                    if clean_name in metrics:
                        metrics[clean_name].append(val)
                    else:
                        metrics[clean_name] = [val]
                except ValueError:
                    pass
        return metrics, model_name

    def monitor_loop(self):
        while self.is_monitoring:
            try:
                response = requests.get(self.metrics_url, timeout=2)
                if response.status_code == 200:
                    metrics, model_name = self.parse_metrics(response.text)
                    if model_name != "Unknown":
                        self.current_model_name = model_name
                    self.update_dashboard(metrics, model_name)
                else:
                    self.lbl_status.configure(text=f"Status: HTTP Error {response.status_code} ({self.metrics_url})", text_color="red")
            except Exception as e:
                err_msg = str(e)
                if len(err_msg) > 50:
                    err_msg = err_msg[:50] + "..."
                self.lbl_status.configure(text=f"Status: Request Error - {err_msg}", text_color="red")
            
            time.sleep(self.update_interval)

    def update_dashboard(self, metrics, model_name="Unknown"):
        # We need to schedule GUI updates in the main thread
        def gui_update():
            if not self.is_monitoring:
                return
            
            self.lbl_status.configure(text="Status: Connected & Updating", text_color="green")
            self.lbl_model.configure(text=f"Model: {model_name}")
            
            # Helper to safely get sum
            def get_sum(key):
                vals = metrics.get(key, [0.0])
                return sum(vals)

            # Helper to safely get avg
            def get_avg(key):
                vals = metrics.get(key, [0.0])
                return sum(vals) / len(vals) if vals else 0.0

            # Find matching keys since metrics name could have prefixes based on prometheus config.
            # But usually it is directly `vllm:gpu_cache_usage_perc` (or `vllm_gpu_cache_usage_perc`)
            def find_metric(suffix, agg="sum"):
                for k in metrics.keys():
                    if suffix in k:
                        return get_avg(k) if agg == "avg" else get_sum(k)
                return -1

            # GPU Cache
            gpu_cache = find_metric('gpu_cache_usage_perc', 'avg')
            if gpu_cache < 0:
                gpu_cache = find_metric('kv_cache_usage_perc', 'avg') # Fallback if GPU cache is named this

            if gpu_cache >= 0:
                self.lbl_gpu_cache_val.configure(text=f"{gpu_cache*100:.1f}%")
                if gpu_cache > 0.9:
                    self.lbl_gpu_cache_val.configure(text_color="red")
                elif gpu_cache > 0.7:
                    self.lbl_gpu_cache_val.configure(text_color="orange")
                else:
                    self.lbl_gpu_cache_val.configure(text_color=["black", "white"])
            else:
                self.lbl_gpu_cache_val.configure(text="N/A", text_color=["black", "white"])

            # CPU Cache
            cpu_cache = find_metric('cpu_cache_usage_perc', 'avg')
            if cpu_cache >= 0:
                self.lbl_cpu_cache_val.configure(text=f"{cpu_cache*100:.1f}%")
            else:
                self.lbl_cpu_cache_val.configure(text="N/A")

            # Requests
            req_run = int(find_metric('num_requests_running'))
            req_swap = int(find_metric('num_requests_swapped'))
            req_wait = int(find_metric('num_requests_waiting'))
            if req_run < 0: req_run = 0
            if req_swap < 0: req_swap = 0
            if req_wait < 0: req_wait = 0
            self.val_req_running.configure(text=str(req_run))
            self.val_req_swapped.configure(text=str(req_swap))
            self.val_req_waiting.configure(text=str(req_wait))

            # Throughput
            cur_time = time.time()
            dt = cur_time - self.last_time
            
            prompt_tokens = find_metric('prompt_tokens_total')
            gen_tokens = find_metric('generation_tokens_total')
            
            prompt_rate = 0.0
            gen_rate = 0.0
            
            if self.last_prompt_tokens != -1 and dt > 0:
                prompt_rate = max(0.0, (prompt_tokens - self.last_prompt_tokens) / dt)
                gen_rate = max(0.0, (gen_tokens - self.last_gen_tokens) / dt)
                
                self.val_throughput.configure(text=f"{prompt_rate:.1f}")
                self.val_gen_throughput.configure(text=f"{gen_rate:.1f}")
                    
            self.last_prompt_tokens = prompt_tokens
            self.last_gen_tokens = gen_tokens
            self.last_time = cur_time
            
            # Update history and plot
            self.history_times.append(datetime.datetime.now())
            
            if gpu_cache >= 0:
                self.history["gpu_cache"].append(gpu_cache * 100)
            else:
                self.history["gpu_cache"].append(float('nan'))
                
            if cpu_cache >= 0:
                self.history["cpu_cache"].append(cpu_cache * 100)
            else:
                self.history["cpu_cache"].append(float('nan'))
                
            self.history["req_run"].append(req_run)
            self.history["req_wait"].append(req_wait)
            self.history["req_swap"].append(req_swap)
            self.history["prompt_rate"].append(prompt_rate)
            self.history["gen_rate"].append(gen_rate)
            
            self.update_plots()

        self.after(0, gui_update)

    def run_benchmark(self):
        if not self.is_monitoring or self.current_model_name == "Unknown":
            self.lbl_benchmark_result.configure(text="Please wait for model detection...", text_color="red")
            return
            
        self.btn_benchmark.configure(state="disabled", text="Running...")
        self.lbl_benchmark_result.configure(text="Benchmark TPS: Running...", text_color="#1f538d")
        threading.Thread(target=self._benchmark_worker, daemon=True).start()

    def _benchmark_worker(self):
        try:
            base_url = self.metrics_url[:-8] if self.metrics_url.endswith("/metrics") else self.metrics_url
            if not base_url.endswith("/v1"):
                base_url += "/v1"
                
            completions_url = base_url + "/completions"
            
            try:
                concurrency = int(self.combo_concurrency.get())
            except Exception:
                concurrency = 1
            
            payload = {
                "model": self.current_model_name,
                "prompt": "Write a detailed and immersive story about a time traveler who accidentally alters the course of history. Please ensure the story is approximately 500 tokens (or words) long.",
                "max_tokens": 600,
                "temperature": 0.7
            }
            
            results = []
            errors = []
            threads = []
            
            start_t = time.time()
            
            def worker():
                try:
                    req_start = time.time()
                    res = requests.post(completions_url, json=payload, timeout=120)
                    req_end = time.time()
                    if res.status_code == 200:
                        data = res.json()
                        usage = data.get("usage", {})
                        gen_tokens = usage.get("completion_tokens", 0)
                        results.append((gen_tokens, req_end - req_start))
                    else:
                        errors.append(f"HTTP {res.status_code}")
                except Exception as e:
                    errors.append(str(e))
            
            for _ in range(concurrency):
                t = threading.Thread(target=worker)
                threads.append(t)
                t.start()
                
            for t in threads:
                t.join()
                
            end_t = time.time()
            elapsed = end_t - start_t
            
            if results:
                total_tokens = sum(r[0] for r in results)
                system_tps = total_tokens / elapsed if elapsed > 0 else 0
                avg_req_tps = sum(r[0]/r[1] for r in results if r[1] > 0) / len(results)
                
                result_msg = f"System TPS: {system_tps:.2f} tok/s (Avg Req: {avg_req_tps:.2f} tok/s) [{len(results)}/{concurrency} OK]"
                color = "green"
                if len(results) < concurrency:
                    result_msg += f" (Errors: {len(errors)})"
                    color = "orange"
            else:
                err_summary = errors[0] if errors else "Unknown error"
                if len(err_summary) > 40:
                    err_summary = err_summary[:40] + "..."
                result_msg = f"Benchmark Failed: {err_summary}"
                color = "red"
        except Exception as e:
            err_msg = str(e)
            if len(err_msg) > 30: err_msg = err_msg[:30] + "..."
            result_msg = f"Benchmark Error: {err_msg}"
            color = "red"
            
        def update_ui():
            self.lbl_benchmark_result.configure(text=result_msg, text_color=color)
            if self.is_monitoring:
                self.btn_benchmark.configure(state="normal", text="Run Benchmark")
                
        self.after(0, update_ui)

    def open_metrics_browser(self):
        if self.is_monitoring and self.metrics_url:
            webbrowser.open(self.metrics_url)

if __name__ == "__main__":
    app = VLLMMonitorApp()
    app.mainloop()
