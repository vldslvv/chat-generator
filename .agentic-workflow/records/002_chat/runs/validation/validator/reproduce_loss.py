import asyncio
import json
from pathlib import Path
from uuid import uuid4
from websockets.asyncio.server import serve

root = Path('/home/vv/assignment/chat-generator')

async def one(component, command):
    async def peer(ws):
        request = json.loads(await ws.recv())
        await ws.send(json.dumps({'type':'login_ok','correlation_id':request['correlation_id'], 'data': {'id':str(uuid4()),'name':'alice'}}))
        await asyncio.sleep(0.05)
        ws.transport.abort()
    async with serve(peer,'127.0.0.1',0) as server:
        port = server.sockets[0].getsockname()[1]
        process = await asyncio.create_subprocess_exec(*command,'--url',f'ws://127.0.0.1:{port}/ws',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        process.stdin.write(b'/connect alice\n')
        await process.stdin.drain()
        lines = []
        async with asyncio.timeout(5):
            while True:
                line = (await process.stdout.readline()).decode()
                assert line
                lines.append(line)
                if 'Disconnected' in line:
                    break
        process.stdin.write(b'/status\n/quit\n')
        await process.stdin.drain()
        out, err = await process.communicate()
        return {'component':component,'stdout':''.join(lines)+out.decode(),'stderr':err.decode(),'exit_code':process.returncode}

async def main():
    results=[]
    for component,path in [('python','python-client/.venv/bin/chat-python'),('rust','rust-client/target/debug/chat-rust')]:
        results.append(await one(component,[str(root/'apps/chat'/path)]))
    print(json.dumps(results,indent=2,ensure_ascii=False))
asyncio.run(main())
