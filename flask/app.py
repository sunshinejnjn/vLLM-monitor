from flask import Flask, render_template, request, jsonify
import requests
from concurrent.futures import ThreadPoolExecutor
import time

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/proxy', methods=['GET'])
def proxy_get():
    url = request.args.get('url')
    if not url:
        return "Missing URL config", 400
    try:
        response = requests.get(url, timeout=5)
        return response.text, response.status_code
    except Exception as e:
        return str(e), 500

@app.route('/api/proxy_post', methods=['POST'])
def proxy_post():
    url = request.args.get('url')
    if not url:
        return "Missing URL config", 400
    try:
        payload = request.json
        response = requests.post(url, json=payload, timeout=120)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return str(e), 500

@app.route('/api/benchmark', methods=['POST'])
def benchmark():
    url = request.args.get('url')
    if not url:
        return "Missing URL config", 400
    try:
        concurrency = int(request.args.get('concurrency', 1))
    except ValueError:
        concurrency = 1

    payload = request.json
    results = []
    errors = []
    
    start_t = time.time()
    
    def worker():
        try:
            req_start = time.time()
            res = requests.post(url, json=payload, timeout=120)
            req_end = time.time()
            if res.status_code == 200:
                data = res.json()
                usage = data.get("usage", {})
                gen_tokens = usage.get("completion_tokens", 0) or usage.get("total_tokens", 0) or 0
                results.append({
                    "gen_tokens": gen_tokens,
                    "duration": req_end - req_start
                })
            else:
                errors.append(f"HTTP {res.status_code}")
        except Exception as e:
            errors.append(str(e))

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        for f in futures:
            f.result()
            
    end_t = time.time()
    elapsed = end_t - start_t
    
    return jsonify({
        "results": results,
        "errors": errors,
        "elapsed": elapsed
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
