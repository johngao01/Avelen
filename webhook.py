import asyncio
import json
import time
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


def catch_errors(func):
    def wrapper(*args, **kwargs):
        acquired = False
        try:
            while True:
                acquired = BUSY_LOCK.acquire(blocking=False)
                if acquired:
                    r = asyncio.run(func(*args, **kwargs))
                    return r
                else:
                    print("等待4秒后处理请求")
                    time.sleep(4)
        except Exception as e:
            traceback.print_exc()
            detailed_error_info = traceback.format_exc()
            print(detailed_error_info)
            return jsonify({'error': str(e)}), 500
        finally:
            if acquired and BUSY_LOCK.locked():
                BUSY_LOCK.release()

    return wrapper


@app.route('/main', methods=['POST'], endpoint='main')
@catch_errors
async def main():
    data = request.get_data(as_text=True)  # Get the request data as a string
    data = json.loads(data)
    print(data['username'], data['url'], data['create_time'])
    files = data.get('files')
    if type(files) is dict:
        response_message = await send.send_single(data)
    elif type(files) is list:
        response_message = await send.send_multiple(data)
    else:
        return
    if response_message:
        result = {
            'messages': response_message
        }
        return jsonify(result)


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


if __name__ == "__main__":
    app.run(host='0.0.0.0')
