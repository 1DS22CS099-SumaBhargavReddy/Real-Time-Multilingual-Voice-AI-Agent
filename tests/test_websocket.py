import asyncio
import json
import websockets

async def test_inbound_booking():
    url = "ws://localhost:8000/ws/voice?patient_id=P101&session_id=test_sess_py"
    print(f"Connecting to {url}...")
    
    async with websockets.connect(url) as ws:
        # 1. Receive Greeting and State
        print("\n--- Handshake and Greeting ---")
        for _ in range(5): # Read first few JSON responses
            msg = await ws.recv()
            if isinstance(msg, bytes):
                print(f"[WS Binary] Received audio chunk of size {len(msg)} bytes")
            else:
                data = json.loads(msg)
                print(f"[WS JSON] Type: {data.get('type')}")
                if data.get("type") == "agent_response":
                    print(f"Agent greeting: '{data.get('text')}'")
                elif data.get("type") == "state":
                    print(f"State: {data.get('state')}")
        
        # 2. Send booking request
        print("\n--- Sending Booking Request ---")
        user_message = {
            "type": "text_transcript",
            "text": "I want to book an appointment with Dr. Ramesh Sharma tomorrow at 10:00"
        }
        await ws.send(json.dumps(user_message))
        print(f"Sent: {user_message['text']}")
        
        # 3. Read agent reasoning and response
        print("\n--- Reading Agent Response ---")
        response_received = False
        while not response_received:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                print(f"[WS Binary] Received audio response chunk of size {len(msg)} bytes")
            else:
                data = json.loads(msg)
                print(f"[WS JSON] Type: {data.get('type')}")
                if data.get("type") == "thinking":
                    print(f"Thinking: {data.get('log')}")
                elif data.get("type") == "agent_response":
                    print(f"Agent response: '{data.get('text')}'")
                    response_received = True
                elif data.get("type") == "state":
                    print(f"Updated State: {data.get('state')}")
                elif data.get("type") == "latency":
                    print(f"Latency Metrics: {data.get('metrics')}")

if __name__ == "__main__":
    asyncio.run(test_inbound_booking())
