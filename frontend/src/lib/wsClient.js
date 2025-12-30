/**
 * WebSocket client for real-time communication
 */

const WS_URL = 'ws://127.0.0.1:8000/ws/control';

export const ConnectionState = {
    CONNECTED: 'CONNECTED',
    CONNECTING: 'CONNECTING',
    DISCONNECTED: 'DISCONNECTED'
};

class WSClient {
    constructor() {
        this.ws = null;
        this.state = ConnectionState.DISCONNECTED;
        this.onStateChange = null;
        this.onMessage = null;
        this.reconnectTimeout = null;
    }

    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
        }

        this.setState(ConnectionState.CONNECTING);

        try {
            this.ws = new WebSocket(WS_URL);

            this.ws.onopen = () => {
                this.setState(ConnectionState.CONNECTED);
            };

            this.ws.onclose = () => {
                this.setState(ConnectionState.DISCONNECTED);
                this.ws = null;
            };

            this.ws.onerror = () => {
                this.setState(ConnectionState.DISCONNECTED);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (this.onMessage) {
                        this.onMessage(data);
                    }
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.setState(ConnectionState.DISCONNECTED);
        }
    }

    disconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.setState(ConnectionState.DISCONNECTED);
    }

    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
            return true;
        }
        return false;
    }

    sendSwitch(target, fadeMs = 500) {
        return this.send({
            type: 'switch',
            target,
            fade_ms: fadeMs
        });
    }

    setState(state) {
        this.state = state;
        if (this.onStateChange) {
            this.onStateChange(state);
        }
    }

    getState() {
        return this.state;
    }
}

// Singleton instance
export const wsClient = new WSClient();

// Helper function for switch command
export function sendSwitchCommand(target, fadeMs = 500) {
    return wsClient.sendSwitch(target, fadeMs);
}
