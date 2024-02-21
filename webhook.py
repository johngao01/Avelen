import asyncio
import json
import time
import traceback
import sys

from flask import Flask, request, jsonify

import send

# 设置标准输出的编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)
app.config['DEFAULT_CHARSET'] = 'utf-8'
BUSY = False


def catch_errors(func):
    def wrapper(*args, **kwargs):
        try:
            global BUSY
            while True:
                if not BUSY:
                    BUSY = True
                    r = asyncio.run(func(*args, **kwargs))
                    BUSY = False
                    return r
                else:
                    print("等待4秒后处理请求")
                    time.sleep(4)
        except Exception as e:
            BUSY = False
            traceback.print_exc()
            detailed_error_info = traceback.format_exc()
            print(detailed_error_info)
            return jsonify({'error': str(e)}), 500

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


@app.route('/backup', methods=['GET'], endpoint='backup')
@catch_errors
async def backup():
    await send.backup()
    return "backup done"


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


if __name__ == "__main__":
    app.run(host='0.0.0.0')
