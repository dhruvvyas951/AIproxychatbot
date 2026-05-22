import socket
import threading
import json

HOST = "127.0.0.1"
PORT = 9000
IDENTITY = "B"

def receive_messages(sock):
    while True:
        try:
            raw = sock.recv(4096)
            if not raw:
                print("\n[Disconnected from server]")
                break
            data = json.loads(raw.decode())

            if "status" in data:
                print(f"\n[{data['status']}]")
            elif "error" in data:
                print(f"\n[ERROR: {data['error']}]")
            elif "message" in data:
                print(f"\n  [Person A @ {data['timestamp']}]: {data['message']}")
                print("You: ", end="", flush=True)
        except Exception:
            break


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # Send identity
    sock.send(json.dumps({"identity": IDENTITY}).encode())

    # Start receiving in background
    t = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
    t.start()

    print("=== Person B's Chat Window ===")
    print("Type a message and press Enter to send.\n")

    while True:
        try:
            msg = input("You: ")
            if msg.strip():
                sock.send(json.dumps({"message": msg}).encode())
        except (KeyboardInterrupt, EOFError):
            print("\n[Exiting]")
            break

    sock.close()


if __name__ == "__main__":
    main()