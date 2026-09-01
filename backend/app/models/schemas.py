from pydantic import BaseModel, HttpUrl


class BrowserStartRequest(BaseModel):
    url: HttpUrl


class BrowserStartResponse(BaseModel):
    status: str
    url: str


class BrowserStopResponse(BaseModel):
    status: str


class HealthResponse(BaseModel):
    status: str
