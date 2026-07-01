import json, sqlite3, urllib.request

# 1. Login
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login',
    method='POST', data=json.dumps({'account':'test@paper.com','password':'Test123456','account_type':'email'}).encode(),
    headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
token = json.loads(resp.read())['access_token']
print('Token:', token[:30])

# 2. Get latest completed task
conn = sqlite3.connect(r'd:\AI编程\PDF论文翻译\paper-translate\backend\paper_translate.db')
cur = conn.cursor()
cur.execute("SELECT id, status, result_url FROM tasks WHERE status='COMPLETED' AND user_id='7d0f33fd-233a-4405-a353-611d3efc2e6d' ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
task_id = row[0] if row else None
print(f'Latest completed task: {task_id}')
conn.close()

if task_id:
    # 3. Test download WITH Bearer token
    req2 = urllib.request.Request(f'http://127.0.0.1:8000/api/v1/tasks/{task_id}/download?format=pdf',
        headers={'Authorization': f'Bearer {token}'})
    try:
        resp2 = urllib.request.urlopen(req2)
        data = resp2.read()
        is_pdf = data[:4] == b'%PDF'
        print(f'[WITH Token] status={resp2.status} len={len(data)} is_pdf={is_pdf}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f'[WITH Token] ERROR {e.code}: {body}')

    # 4. Test download WITHOUT token (should fail)
    req3 = urllib.request.Request(f'http://127.0.0.1:8000/api/v1/tasks/{task_id}/download?format=pdf')
    try:
        resp3 = urllib.request.urlopen(req3)
        data = resp3.read()
        print(f'[WITHOUT Token] status={resp3.status} len={len(data)}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        print(f'[WITHOUT Token] ERROR {e.code}: {body}')
