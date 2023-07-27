import asyncio
import json
import os
import traceback

from flask import Flask, request, jsonify

import send

app = Flask(__name__)
script_directory = os.path.dirname(os.path.abspath(__file__))


def catch_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return asyncio.run(func(*args, **kwargs))
        except Exception as e:
            traceback.print_exc()
            detailed_error_info = traceback.format_exc()
            print(detailed_error_info)
            return jsonify({'error': str(e)}), 500

    return wrapper


@app.route('/send-album', methods=['POST'], endpoint='send_album')
@catch_errors
async def send_long_weibo():
    data = request.get_data(as_text=True)  # Get the request data as a string
    data = json.loads(data)
    print(data['weibo_link'], data['text_raw'].replace('\n', '\t'))
    result = {
        'messages': await send.send_medias(data)
    }
    return jsonify(result)


@app.route('/photo-or-video', methods=['POST'], endpoint='send_pv')
@catch_errors
async def send_pv():
    data = request.get_data(as_text=True)  # Get the request data as a string
    data = json.loads(data)
    print(data['weibo_link'], data['text_raw'].replace('\n', '\t'))
    result = {
        'messages': await send.send_video_or_photo(data)
    }
    return jsonify(result)


@app.route('/send_message', methods=['POST'], endpoint='send_message')
@catch_errors
async def send_message():
    data = request.get_data(as_text=True)
    data = json.loads(data)
    print(data['weibo_link'], data['text_raw'].replace('\n', '\t'))
    response_message = await send.message_send(data)
    result = {
        'messages': [response_message]
    }
    return jsonify(result)


@app.route('/send_document', methods=['POST'], endpoint='send_document')
@catch_errors
async def send_document():
    data = request.get_data(as_text=True)
    data = json.loads(data)
    print(data['weibo_link'], data['text_raw'].replace('\n', '\t'))
    response_message = await send.send_document(data)
    result = {
        'messages': [response_message]
    }
    return jsonify(result)


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


if __name__ == "__main__":
    app.run(host='0.0.0.0')
