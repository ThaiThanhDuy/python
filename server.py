import asyncio
import websockets
import datetime


async def handler(websocket):
    async for message in websocket:
        print(f"[{datetime.datetime.now()}] Server nhận: {message}")
        response = f"Server đã nhận: {message} lúc {datetime.datetime.now()}"
        await websocket.send(response)


async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print(
            f"[{datetime.datetime.now()}] WebSocket server đang chạy tại ws://localhost:8765"
        )
        await asyncio.Future()  # Chạy server mãi mãi


if __name__ == "__main__":
    asyncio.run(main())
