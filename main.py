import socket
import threading
import json
from datetime import datetime

HOST = "127.0.0.1"
PORT = 9000

clients = {}       # { "A": conn, "B": conn }
lock = threading.Lock()


def log(msg):
    print(f"[SERVER {datetime.now().strftime('%H:%M:%S')}] {msg}")


def handle_client(conn, addr):
    # First message must be identity: {"identity": "A"} or {"identity": "B"}
    try:
        raw = conn.recv(1024).decode()
        data = json.loads(raw)
        identity = data.get("identity", "").upper()

        if identity not in ("A", "B"):
            conn.send(json.dumps({"error": "Send identity A or B first"}).encode())
            conn.close()
            return

        with lock:
            if identity in clients:
                conn.send(json.dumps({"error": f"{identity} already connected"}).encode())
                conn.close()
                return
            clients[identity] = conn

        log(f"Person {identity} connected from {addr}")
        conn.send(json.dumps({"status": f"Connected as Person {identity}"}).encode())

        # Wait until both are connected
        while len(clients) < 2:
            pass

        conn.send(json.dumps({"status": "Both users connected. Start chatting!"}).encode())

        # Message relay loop
        while True:
            raw = conn.recv(4096)
            if not raw:
                break

            data = json.loads(raw.decode())
            msg = data.get("message", "")
            target = "B" if identity == "A" else "A"

            payload = json.dumps({
                "from": identity,
                "message": msg,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })

            with lock:
                if target in clients:
                    clients[target].send(payload.encode())
                    log(f"{identity} → {target}: {msg}")

    except (ConnectionResetError, json.JSONDecodeError):
        pass
    finally:
        with lock:
            to_remove = [k for k, v in clients.items() if v == conn]
            for k in to_remove:
                del clients[k]
                log(f"Person {k} disconnected")
        conn.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(2)
    log(f"Server listening on {HOST}:{PORT} — waiting for 2 clients...")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    main()