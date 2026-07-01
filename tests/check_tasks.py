import requests, json
r = requests.post('http://localhost:8000/api/v1/auth/login', json={'account':'test@paper.com','password':'Test123456','account_type':'email'})
token = r.json()['access_token']
r2 = requests.get('http://localhost:8000/api/v1/tasks?page_size=3', headers={'Authorization': f'Bearer {token}'})
tasks = r2.json()['items']
for i, t in enumerate(tasks):
    print(f"\nTask {i}: id={t['id']} status={t['status']}")
    print(f"  filename={t.get('filename')}")
    print(f"  source_url={t.get('source_url')}")
    print(f"  error={str(t.get('error_message', ''))[:200]}")
    print(f"  page_count={t.get('page_count')}")
