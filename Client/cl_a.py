import socket
import threading
import json

HOST = "127.0.0.1"
PORT = 9000
IDENTITY = "A"

ai_mode = False


def receive_messages(sock):
    while True:
        try:
            raw = sock.recv(4096)
            if not raw:
                print("\n[Disconnected from server]")
                break
            data = json.loads(raw.decode())

            if "typing" in data:
                if data["typing"]:
                    print(f"\n  [Person B is typing...]", flush=True)
                else:
                    # clear typing indicator line
                    print(f"\r{' ' * 30}\r", end="", flush=True)

            elif "status" in data:
                print(f"\n[{data['status']}]")

            elif "error" in data:
                print(f"\n[ERROR: {data['error']}]")

            elif "message" in data:
                ai_tag = " [AI handled]" if data.get("ai_handled") else ""
                print(f"\n  [Person B @ {data['timestamp']}]: {data['message']}{ai_tag}")
                print("You: ", end="", flush=True)

        except Exception:
            break


def main():
    global ai_mode

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.send(json.dumps({"identity": IDENTITY}).encode())

    t = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
    t.start()

    print("=== Person A's Chat Window ===")
    print("Commands: /ai on | /ai off | /exit\n")

    while True:
        try:
            msg = input("You: ")

            if msg.strip() == "/ai on":
                ai_mode = True
                sock.send(json.dumps({"ai_switch": True}).encode())
                continue
            elif msg.strip() == "/ai off":
                ai_mode = False
                sock.send(json.dumps({"ai_switch": False}).encode())
                continue
            elif msg.strip() == "/exit":
                break
            elif msg.strip() and not ai_mode:
                sock.send(json.dumps({"message": msg}).encode())

        except (KeyboardInterrupt, EOFError):
            print("\n[Exiting]")
            break

    sock.close()


if __name__ == "__main__":
    main()