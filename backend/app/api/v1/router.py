from fastapi import APIRouter

from app.api.v1 import auth, cost, glossaries, orders, quotas, tasks, users


api_v1_router: APIRouter = APIRouter()

api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(users.router, prefix="/users", tags=["users"])
api_v1_router.include_router(quotas.router, prefix="/quotas", tags=["quotas"])
api_v1_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_v1_router.include_router(glossaries.router, prefix="/glossaries", tags=["glossaries"])
api_v1_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_v1_router.include_router(cost.router, prefix="/cost", tags=["cost"])