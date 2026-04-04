from flask import Flask, render_template, request, jsonify
import requests

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
