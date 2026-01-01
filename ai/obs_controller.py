from obswebsocket import obsws, requests

class OBSController:
    def __init__(self, host="localhost", port=4455, password="CDeP1CouhTyM5F1T"):
        self.ws = obsws(host, port, password)
        self.connected = False

    def connect(self):
        if not self.connected:
            self.ws.connect()
            self.connected = True

    def disconnect(self):
        if self.connected:
            self.ws.disconnect()
            self.connected = False

    def set_scene(self, scene_name: str):
        self.connect()
        self.ws.call(
            requests.SetCurrentProgramScene(sceneName=scene_name)
        )
