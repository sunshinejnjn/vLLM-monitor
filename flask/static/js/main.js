document.addEventListener("DOMContentLoaded", () => {
    const hostInput = document.getElementById("host");
    const connectBtn = document.getElementById("btn-connect");
    const refreshSelect = document.getElementById("refresh-rate");
    const benchmarkBtn = document.getElementById("btn-benchmark");
    const metricsBtn = document.getElementById("btn-open-metrics");
    const statusText = document.getElementById("status-bar");
    const dashboard = document.getElementById("dashboard");
    const modelNameText = document.getElementById("model-name");
    const benchmarkResultText = document.getElementById("benchmark-result");
    const concurrencySelect = document.getElementById("concurrency");

    // Elements for metrics
    const gpuCacheVal = document.getElementById("val-gpu-cache");
    const cpuCacheVal = document.getElementById("val-cpu-cache");
    const reqRunVal = document.getElementById("val-req-run");
    const reqSwapVal = document.getElementById("val-req-swap");
    const reqWaitVal = document.getElementById("val-req-wait");
    const promptThruVal = document.getElementById("val-prompt-thru");
    const genThruVal = document.getElementById("val-gen-thru");

    // Charts
    let chartReq, chartPrompt, chartGen;

    // State
    let isMonitoring = false;
    let metricsUrl = "";
    let updateIntervalMs = 5000;
    let intervalId = null;
    let currentModelName = "Unknown";

    let lastPromptTokens = -1;
    let lastGenTokens = -1;
    let lastTime = Date.now();

    // Chart.js common options
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.borderColor = "rgba(255,255,255,0.1)";

    function initCharts() {
        const createChart = (ctxId, title, datasets) => {
            return new Chart(document.getElementById(ctxId), {
                type: 'line',
                data: { labels: [], datasets: datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: {
                        title: { display: true, text: title, color: '#f1f5f9' },
                        legend: { position: 'top', align: 'start', labels: { boxWidth: 10, font: { size: 10 } } }
                    },
                    scales: {
                        x: { display: true },
                        y: { beginAtZero: true, display: true }
                    },
                    elements: { point: { radius: 0 }, line: { borderWidth: 2 } },
                    interaction: { mode: 'index', intersect: false }
                }
            });
        };

        chartReq = createChart("chart-req", "Requests", [
            { label: "Running", data: [], borderColor: "#3b82f6" },
            { label: "Waiting", data: [], borderColor: "#f59e0b" },
            { label: "Swapped", data: [], borderColor: "#ef4444" }
        ]);

        chartPrompt = createChart("chart-prompt", "Prompt Throughput (tok/s)", [
            { label: "Prompt", data: [], borderColor: "#8b5cf6" }
        ]);

        chartGen = createChart("chart-gen", "Generation Throughput (tok/s)", [
            { label: "Gen", data: [], borderColor: "#10b981" }
        ]);
    }

    function clearCharts() {
        if (!chartReq) return;
        [chartReq, chartPrompt, chartGen].forEach(chart => {
            chart.data.labels = [];
            chart.data.datasets.forEach(ds => ds.data = []);
            chart.update();
        });
    }

    // Load from local storage
    const savedHost = localStorage.getItem("vllm_host");
    if (savedHost) {
        hostInput.value = savedHost;
    } else {
        hostInput.value = "127.0.0.1:8000";
    }

    const savedRefresh = localStorage.getItem("vllm_refresh_rate");
    if (savedRefresh) {
        refreshSelect.value = savedRefresh;
        updateIntervalMs = parseInt(savedRefresh) * 1000;
    }

    initCharts();

    connectBtn.addEventListener("click", () => {
        if (!isMonitoring) {
            let hostStr = hostInput.value.trim();
            if (!hostStr) {
                statusText.innerText = "Status: Please enter a valid host:port";
                statusText.style.color = "var(--danger-color)";
                return;
            }
            if (!hostStr.startsWith("http://") && !hostStr.startsWith("https://")) {
                hostStr = "http://" + hostStr;
            }
            if (!hostStr.endsWith("/metrics")) {
                metricsUrl = hostStr.replace(/\/$/, "") + "/metrics";
            } else {
                metricsUrl = hostStr;
            }

            localStorage.setItem("vllm_host", hostInput.value.trim());

            isMonitoring = true;
            connectBtn.innerText = "Disconnect";
            hostInput.disabled = true;
            dashboard.classList.remove("is-dimmed");
            modelNameText.innerText = "Model: Unknown";
            currentModelName = "Unknown";
            benchmarkBtn.disabled = false;
            concurrencySelect.disabled = false;
            metricsBtn.disabled = false;
            benchmarkResultText.innerText = "Benchmark TPS: N/A";

            lastPromptTokens = -1;
            lastGenTokens = -1;
            lastTime = Date.now();

            updateIntervalMs = parseInt(refreshSelect.value) * 1000;

            clearCharts();
            statusText.innerText = "Status: Connecting...";
            statusText.style.color = "var(--text-color)";

            monitorLoop();
            intervalId = setInterval(monitorLoop, updateIntervalMs);
        } else {
            isMonitoring = false;
            clearInterval(intervalId);
            connectBtn.innerText = "Connect";
            hostInput.disabled = false;
            dashboard.classList.add("is-dimmed");
            statusText.innerText = "Status: Disconnected";
            statusText.style.color = "#94a3b8";
            modelNameText.innerText = "Model: Unknown";
            benchmarkBtn.disabled = true;
            concurrencySelect.disabled = true;
            metricsBtn.disabled = true;
        }
    });

    refreshSelect.addEventListener("change", () => {
        localStorage.setItem("vllm_refresh_rate", refreshSelect.value);
        if (isMonitoring) {
            clearInterval(intervalId);
            updateIntervalMs = parseInt(refreshSelect.value) * 1000;
            intervalId = setInterval(monitorLoop, updateIntervalMs);
        }
    });

    metricsBtn.addEventListener("click", () => {
        if (metricsUrl) {
            window.open(metricsUrl, '_blank');
        }
    });

    benchmarkBtn.addEventListener("click", () => {
        if (!isMonitoring || currentModelName === "Unknown") {
            benchmarkResultText.innerText = "Please wait for model detection...";
            benchmarkResultText.style.color = "var(--danger-color)";
            return;
        }
        benchmarkBtn.disabled = true;
        concurrencySelect.disabled = true;
        benchmarkBtn.innerText = "Running...";
        benchmarkResultText.innerText = "Benchmark TPS: Running...";
        benchmarkResultText.style.color = "var(--primary-color)";
 
        let baseUrl = metricsUrl;
        if (baseUrl.endsWith("/metrics")) {
            baseUrl = baseUrl.substring(0, baseUrl.length - 8);
        }
        if (!baseUrl.endsWith("/v1")) {
            baseUrl += "/v1";
        }
        const completionsUrl = baseUrl + "/completions";
 
        const payload = {
            model: currentModelName,
            prompt: "Write a detailed and immersive story about a time traveler who accidentally alters the course of history. Please ensure the story is approximately 500 tokens (or words) long.",
            max_tokens: 600,
            temperature: 0.7
        };
 
        const concurrency = parseInt(concurrencySelect.value) || 1;
        const benchmarkUrl = `/api/benchmark?url=${encodeURIComponent(completionsUrl)}&concurrency=${concurrency}`;

        fetch(benchmarkUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                const elapsed = data.elapsed;
                const successfulRuns = data.results || [];
                const errors = data.errors || [];
 
                if (successfulRuns.length > 0) {
                    const totalTokens = successfulRuns.reduce((sum, run) => sum + run.gen_tokens, 0);
                    const systemTps = totalTokens / elapsed;
                    const avgReqTps = successfulRuns.reduce((sum, run) => sum + (run.duration > 0 ? run.gen_tokens / run.duration : 0), 0) / successfulRuns.length;
                    
                    let resultMsg = `System TPS: ${systemTps.toFixed(2)} tok/s (Avg Req: ${avgReqTps.toFixed(2)} tok/s) [${successfulRuns.length}/${concurrency} OK]`;
                    if (successfulRuns.length < concurrency) {
                        resultMsg += ` (Errors: ${errors.length})`;
                        benchmarkResultText.style.color = "var(--warning-color)";
                    } else {
                        benchmarkResultText.style.color = "var(--success-color)";
                    }
                    benchmarkResultText.innerText = resultMsg;
                } else {
                    const errSummary = errors[0] || "Unknown error";
                    benchmarkResultText.innerText = `Benchmark Failed: ${errSummary}`;
                    benchmarkResultText.style.color = "var(--danger-color)";
                }
            })
            .catch(err => {
                benchmarkResultText.innerText = `Benchmark Error: ${err.message}`;
                benchmarkResultText.style.color = "var(--danger-color)";
            })
            .finally(() => {
                if (isMonitoring) {
                    benchmarkBtn.disabled = false;
                    concurrencySelect.disabled = false;
                    benchmarkBtn.innerText = "Run Benchmark";
                }
            });
    });

    async function monitorLoop() {
        try {
            const res = await fetch(`/api/proxy?url=${encodeURIComponent(metricsUrl)}`);
            if (res.ok) {
                const text = await res.text();
                const data = parseMetrics(text);
                updateDashboard(data);
            } else {
                statusText.innerText = `Status: HTTP Error ${res.status} (${metricsUrl})`;
                statusText.style.color = "var(--danger-color)";
            }
        } catch (e) {
            statusText.innerText = `Status: Request Error - ${e.message.substring(0, 50)}`;
            statusText.style.color = "var(--danger-color)";
        }
    }

    function parseMetrics(text) {
        const metrics = {};
        let modelName = "Unknown";

        const lines = text.split(/\r?\n/);
        for (let line of lines) {
            line = line.trim();
            if (!line || line.startsWith('#')) continue;

            if (line.includes('model_name="')) {
                const match = line.match(/model_name="([^"]+)"/);
                if (match) modelName = match[1];
            }

            const parts = line.split(' ');
            if (parts.length >= 2) {
                const namePart = parts[0];
                const valPart = parts[parts.length - 1];

                const cleanName = namePart.split('{')[0];
                const val = parseFloat(valPart);
                if (!isNaN(val)) {
                    if (!metrics[cleanName]) metrics[cleanName] = [];
                    metrics[cleanName].push(val);
                }
            }
        }
        return { metrics, modelName };
    }

    function updateDashboard({ metrics, modelName }) {
        statusText.innerText = "Status: Connected & Updating";
        statusText.style.color = "var(--success-color)";

        if (modelName !== "Unknown") {
            currentModelName = modelName;
            modelNameText.innerText = `Model: ${currentModelName}`;
        }

        const getSum = (key) => metrics[key] ? metrics[key].reduce((a, b) => a + b, 0) : 0;
        const getAvg = (key) => metrics[key] ? getSum(key) / metrics[key].length : 0;

        const findMetric = (suffix, agg = 'sum') => {
            const key = Object.keys(metrics).find(k => k.includes(suffix));
            if (!key) return -1;
            return agg === 'avg' ? getAvg(key) : getSum(key);
        };

        // GPU Cache
        let gpuCache = findMetric('gpu_cache_usage_perc', 'avg');
        if (gpuCache < 0) gpuCache = findMetric('kv_cache_usage_perc', 'avg');
        if (gpuCache >= 0) {
            gpuCacheVal.innerText = (gpuCache * 100).toFixed(1) + '%';
            if (gpuCache > 0.9) gpuCacheVal.style.color = "var(--danger-color)";
            else if (gpuCache > 0.7) gpuCacheVal.style.color = "var(--warning-color)";
            else gpuCacheVal.style.color = "var(--text-color)";
        } else {
            gpuCacheVal.innerText = "N/A";
            gpuCacheVal.style.color = "var(--text-color)";
        }

        // CPU Cache
        let cpuCache = findMetric('cpu_cache_usage_perc', 'avg');
        if (cpuCache >= 0) {
            cpuCacheVal.innerText = (cpuCache * 100).toFixed(1) + '%';
            cpuCacheVal.style.color = "var(--text-color)";
        } else {
            cpuCacheVal.innerText = "N/A";
            cpuCacheVal.style.color = "var(--text-color)";
        }

        // Requests
        let reqRun = Math.max(0, parseInt(findMetric('num_requests_running')));
        let reqSwap = Math.max(0, parseInt(findMetric('num_requests_swapped')));
        let reqWait = Math.max(0, parseInt(findMetric('num_requests_waiting')));

        reqRunVal.innerText = isNaN(reqRun) || reqRun < 0 ? 0 : reqRun;
        reqSwapVal.innerText = isNaN(reqSwap) || reqSwap < 0 ? 0 : reqSwap;
        reqWaitVal.innerText = isNaN(reqWait) || reqWait < 0 ? 0 : reqWait;

        // Throughput
        const now = Date.now();
        const dt = (now - lastTime) / 1000;

        let promptTokens = findMetric('prompt_tokens_total');
        let genTokens = findMetric('generation_tokens_total');

        let promptRate = 0.0;
        let genRate = 0.0;

        if (lastPromptTokens !== -1 && dt > 0) {
            promptRate = Math.max(0.0, (promptTokens - lastPromptTokens) / dt);
            genRate = Math.max(0.0, (genTokens - lastGenTokens) / dt);

            promptThruVal.innerText = promptRate.toFixed(1);
            genThruVal.innerText = genRate.toFixed(1);
        }

        lastPromptTokens = promptTokens;
        lastGenTokens = genTokens;
        lastTime = now;

        // Charts
        const timeStr = new Date().toLocaleTimeString();

        // Helper to update chart
        const pushChartData = (chart, label, datasetsData) => {
            chart.data.labels.push(label);
            datasetsData.forEach((d, i) => {
                chart.data.datasets[i].data.push(d);
            });
            if (chart.data.labels.length > 60) {
                chart.data.labels.shift();
                chart.data.datasets.forEach(ds => ds.data.shift());
            }
            chart.update();
        };

        pushChartData(chartReq, timeStr, [reqRunVal.innerText, reqWaitVal.innerText, reqSwapVal.innerText]);
        pushChartData(chartPrompt, timeStr, [promptRate]);
        pushChartData(chartGen, timeStr, [genRate]);
    }

    // Auto-connect if there's a valid host
    if (hostInput.value.trim()) {
        connectBtn.click();
    }
});
