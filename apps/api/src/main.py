from fastapi import FastAPI

app = FastAPI(title="Finance Agent API")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
