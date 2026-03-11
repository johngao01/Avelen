import asyncio
import traceback
import sys
import threading

from flask import Flask, request, jsonify

import send

# 设置标准输出的编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)
app.config['DEFAULT_CHARSET'] = 'utf-8'
BUSY_LOCK = threading.Lock()


@app.route('/main', methods=['POST'], endpoint='main')
def main():
    acquired = BUSY_LOCK.acquire(blocking=False)
    if not acquired:
        return jsonify({'error': 'server busy'}), 429
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'invalid json payload'}), 400
        print(data.get('username'), data.get('url'), data.get('create_time'))
        files = data.get('files')
        if isinstance(files, dict):
            response_message = asyncio.run(send.send_single(data))
        elif isinstance(files, list):
            response_message = asyncio.run(send.send_multiple(data))
        else:
            return jsonify({'error': 'invalid files field'}), 400
        if response_message:
            return jsonify({'messages': response_message})
        return jsonify({'messages': []})
    except Exception as e:
        traceback.print_exc()
        detailed_error_info = traceback.format_exc()
        print(detailed_error_info)
        return jsonify({'error': str(e)}), 500
    finally:
        BUSY_LOCK.release()


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


if __name__ == "__main__":
    app.run(host='0.0.0.0')
