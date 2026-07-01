"""Verify WebSocket stays connected using in-memory fallback."""
import asyncio
import json
import sqlite3
import urllib.request

import websockets


async def main():
    login_req = urllib.request.Request(
        'http://127.0.0.1:8000/api/v1/auth/login',
        method='POST',
        data=json.dumps(
            {'account': 'test@paper.com', 'password': 'Test1234', 'account_type': 'email'}
        ).encode(),
        headers={'Content-Type': 'application/json'},
    )
    try:
        resp = urllib.request.urlopen(login_req, timeout=5)
        body = json.loads(resp.read())
        token = body.get('access_token')
        print(f'login ok, token len={len(token)}')
    except urllib.error.HTTPError as e:
        print(f'login failed: {e.code} {e.read().decode()[:200]}')
        return

    conn = sqlite3.connect(
        r'd:\AI编程\PDF论文翻译\paper-translate\backend\paper_translate.db'
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM tasks WHERE user_id='7d0f33fd-233a-4405-a353-611d3efc2e6d' ORDER BY created_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    task_id = row[0] if row else '00000000-0000-0000-0000-000000000000'
    conn.close()
    print(f'task_id = {task_id}')

    for label, host in [('direct-backend', '127.0.0.1:8000'), ('via-vite', '127.0.0.1:5173')]:
        url = f'ws://{host}/api/v1/tasks/{task_id}/ws?token={token}'
        print(f'\n--- {label}: {url[:90]}... ---')
        try:
            async with websockets.connect(url, open_timeout=5) as ws:
                print('handshake ok, waiting for snapshot...')
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=4)
                    print(f'first message: {msg[:200]}')
                except asyncio.TimeoutError:
                    print('(no snapshot in 4s)')
                print('idle for 6s to check if server closes...')
                try:
                    while True:
                        extra = await asyncio.wait_for(ws.recv(), timeout=6)
                        print(f'  msg: {extra[:150]}')
                except asyncio.TimeoutError:
                    print('  ✓ still open after 6s idle (no forced close)')
        except websockets.ConnectionClosed as e:
            print(f'  ✗ closed by server: code={e.code} reason={e.reason!r}')
        except Exception as e:
            print(f'  ✗ error: {type(e).__name__}: {e}')


asyncio.run(main())
