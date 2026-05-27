import socket
import threading
import json
import os
import time
import random
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

HOST = "0.0.0.0"
PORT = 9000

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

clients = {}
ai_mode = {
    "A": False,
    "B": False
}
chat_history = {
    "A": [],
    "B": []
}

lock = threading.Lock()
both_connected = threading.Event()


def log(msg):
    print(f"[SERVER {datetime.now().strftime('%H:%M:%S')}] {msg}")


def send_typing_indicator(target_conn, identity, is_typing):
    """Send typing indicator to the other person."""
    try:
        target_conn.send(json.dumps({
            "typing": is_typing,
            "from": identity
        }).encode())
    except Exception:
        pass


def get_ai_reply(identity, incoming_message):
    with lock:
        history = list(chat_history[identity][-20:])

    if history:
        examples = "\n".join([f"- {h['message']}" for h in history])
        style_context = f"Here are some of {identity}'s past messages to learn their style:\n{examples}"
    else:
        style_context = f"You are person {identity}. Reply naturally and casually."

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are acting as Person {identity} in a private chat. "
                        f"Reply ONLY as them — match their tone, vocabulary, and message length exactly. "
                        f"Never reveal you are an AI. Keep replies short and natural like a real chat. "
                        f"{style_context}"
                    )
                },
                {
                    "role": "user",
                    "content": incoming_message
                }
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        log(f"Groq API error: {e}")
        return "yeah, makes sense"


def ai_reply_with_delay(identity, target, incoming_message, sender_conn, target_conn, timestamp):
    """
    Runs in a separate thread:
    1. Sends typing indicator to sender
    2. Waits random delay (simulates human typing)
    3. Gets AI reply
    4. Stops typing indicator
    5. Sends reply
    """
    # Step 1 — show typing indicator to sender
    send_typing_indicator(sender_conn, target, is_typing=True)
    log(f"[{target} is typing...]")

    # Step 2 — random delay based on message length (feels natural)
    base_delay = random.uniform(1.5, 3.5)
    length_delay = min(len(incoming_message) * 0.05, 2.0)  # longer msg = slightly longer reply time
    total_delay = base_delay + length_delay
    log(f"AI delay: {total_delay:.1f}s")
    time.sleep(total_delay)

    # Step 3 — get AI reply
    ai_reply = get_ai_reply(target, incoming_message)

    # Step 4 — stop typing indicator
    send_typing_indicator(sender_conn, target, is_typing=False)

    # Step 5 — send reply to sender as if target wrote it
    try:
        sender_conn.send(json.dumps({
            "from": target,
            "message": ai_reply,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }).encode())
        log(f"Groq as {target} → {identity}: {ai_reply}")
    except Exception as e:
        log(f"Failed to send AI reply: {e}")

    # Also notify target silently so they can monitor
    try:
        target_conn.send(json.dumps({
            "from": identity,
            "message": incoming_message,
            "timestamp": timestamp,
            "ai_handled": True
        }).encode())
    except Exception:
        pass


def handle_client(conn, addr):
    identity = None
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
            if len(clients) == 2:
                both_connected.set()

        log(f"Person {identity} connected from {addr}")
        conn.send(json.dumps({"status": f"Connected as Person {identity}"}).encode())

        both_connected.wait()
        conn.send(json.dumps({"status": "Both users connected. Start chatting!"}).encode())

        target = "B" if identity == "A" else "A"

        while True:
            raw = conn.recv(4096)
            if not raw:
                break

            try:
                data = json.loads(raw.decode())
            except json.JSONDecodeError:
                continue

            # ── AI switch command ──
            if "ai_switch" in data:
                with lock:
                    target_ai = ai_mode[target]
                    want_on = data["ai_switch"]

                if want_on and target_ai:
                    conn.send(json.dumps({
                        "error": "Can't enable AI mode — other person is already in AI mode"
                    }).encode())
                    log(f"Person {identity} tried AI mode but {target} is already AI")
                    continue

                with lock:
                    ai_mode[identity] = want_on

                state = "ON" if want_on else "OFF"
                conn.send(json.dumps({"status": f"AI mode {state}"}).encode())
                log(f"Person {identity} AI mode → {state}")
                continue

            msg = data.get("message", "")
            if not msg:
                continue

            # Save to history
            with lock:
                chat_history[identity].append({
                    "role": "sender",
                    "message": msg,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })

            timestamp = datetime.now().strftime("%H:%M:%S")

            with lock:
                target_conn = clients.get(target)
                target_ai = ai_mode[target]

            if not target_conn:
                conn.send(json.dumps({"error": "Other user disconnected"}).encode())
                continue

            if target_ai:
                # Fire AI reply in background thread so server doesn't block
                t = threading.Thread(
                    target=ai_reply_with_delay,
                    args=(identity, target, msg, conn, target_conn, timestamp),
                    daemon=True
                )
                t.start()

            else:
                # Normal relay
                try:
                    target_conn.send(json.dumps({
                        "from": identity,
                        "message": msg,
                        "timestamp": timestamp
                    }).encode())
                    log(f"{identity} → {target}: {msg}")
                except Exception:
                    conn.send(json.dumps({"error": "Failed to deliver message"}).encode())

    except (ConnectionResetError, json.JSONDecodeError):
        pass
    finally:
        if identity:
            with lock:
                if identity in clients:
                    del clients[identity]
                    ai_mode[identity] = False
                    log(f"Person {identity} disconnected")
                if len(clients) < 2:
                    both_connected.clear()
        conn.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(2)
    log(f"Server listening on port {PORT} — waiting for 2 clients...")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    main()