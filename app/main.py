from fastapi import FastAPI

from app.api.import_api import router as import_router
from app.api.receiving_analytics_api import router as receiving_analytics_router

app = FastAPI()
app.include_router(import_router)
app.include_router(receiving_analytics_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
