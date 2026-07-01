import uuid

from locust import FastHttpUser, between, task


class PaperTranslateUser(FastHttpUser):
    wait_time = between(1, 3)
    token: str | None = None
    email: str | None = None

    def on_start(self):
        uid = uuid.uuid4().hex[:12]
        self.email = f"load-{uid}@example.com"
        register_payload = {
            "account": self.email,
            "password": "LoadTest123",
            "code": "123456",
            "account_type": "email",
        }
        with self.client.post(
            "/api/v1/auth/register",
            json=register_payload,
            catch_response=True,
            name="register",
        ) as resp:
            if resp.status_code == 201:
                data = resp.json()
                self.token = data["access_token"]
            else:
                resp.failure(f"register failed: {resp.status_code} {resp.text}")

    def _minimal_pdf(self) -> bytes:
        content = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n"
            b"0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n"
            b"190\n"
            b"%%EOF\n"
        )
        return content

    @task(3)
    def upload_and_translate(self):
        if not self.token:
            return
        pdf = self._minimal_pdf()
        files = {"file": ("paper.pdf", pdf, "application/pdf")}
        data = {
            "source_language": "en",
            "target_language": "zh",
            "output_formats": "pdf",
        }
        with self.client.post(
            "/api/v1/tasks",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="create_task",
        ) as resp:
            if resp.status_code == 201:
                task_data = resp.json()
                task_id = task_data["task_id"]
                with self.client.get(
                    f"/api/v1/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    catch_response=True,
                    name="get_task",
                ) as detail_resp:
                    if detail_resp.status_code != 200:
                        detail_resp.failure(
                            f"task detail failed: {detail_resp.status_code}"
                        )
            elif resp.status_code == 429:
                pass
            else:
                resp.failure(f"create task failed: {resp.status_code}")

    @task(1)
    def get_quotas(self):
        if not self.token:
            return
        with self.client.get(
            "/api/v1/quotas",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="get_quotas",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"get quotas failed: {resp.status_code}")

    @task(1)
    def get_me(self):
        if not self.token:
            return
        with self.client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="get_me",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"get me failed: {resp.status_code}")
