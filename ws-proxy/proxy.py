#!/usr/bin/env python3
"""WebSocket proxy - forwards connections to host rein daemon."""
import asyncio
import websockets
import os

HOST_WS = os.environ.get('UPSTREAM_WS', 'ws://host.docker.internal:8765')
LISTEN_PORT = int(os.environ.get('PORT', '8765'))

async def proxy_handler(client_ws):
    """Proxy WebSocket connection to upstream."""
    try:
        async with websockets.connect(HOST_WS) as upstream_ws:
            async def client_to_upstream():
                async for msg in client_ws:
                    await upstream_ws.send(msg)

            async def upstream_to_client():
                async for msg in upstream_ws:
                    await client_ws.send(msg)

            await asyncio.gather(
                client_to_upstream(),
                upstream_to_client()
            )
    except Exception as e:
        print(f"[PROXY] Error: {e}")

async def main():
    print(f"[PROXY] Starting on port {LISTEN_PORT}, upstream: {HOST_WS}")
    async with websockets.serve(proxy_handler, "0.0.0.0", LISTEN_PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
