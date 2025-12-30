from obswebsocket import obsws, requests
import threading
import time

class OBSClient:
    def __init__(self, host='localhost', port=4455, password=''):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.connected = False
        
        # Start connection in background
        self.connect_thread = threading.Thread(target=self._connect_loop, daemon=True)
        self.connect_thread.start()

    def _connect_loop(self):
        while True:
            try:
                if not self.connected:
                    self.ws = obsws(self.host, self.port, self.password)
                    self.ws.connect()
                    self.connected = True
                    print(f"[OBS] Connected to {self.host}:{self.port}")
            except Exception as e:
                self.connected = False
                # print(f"[OBS] Connection failed: {e}")
            
            time.sleep(5)

    def set_scene(self, scene_name):
        if not self.connected:
            return
        try:
            self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            print(f"[OBS] Switched to scene: {scene_name}")
        except Exception as e:
            print(f"[OBS] Error setting scene: {e}")
            self.connected = False

    def disconnect(self):
        if self.ws and self.connected:
            self.ws.disconnect()
