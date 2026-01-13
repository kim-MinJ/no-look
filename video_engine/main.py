"""
Video Engine - Virtual Camera Output Service
"""
from flask import Flask
from flask_socketio import SocketIO
import cv2
import numpy as np

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/health')
def health():
    return {'status': 'ok'}

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
