from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_browser import router as browser_router
from app.api.routes_health import router as health_router

app = FastAPI(title="PS171 Browser Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(browser_router)
