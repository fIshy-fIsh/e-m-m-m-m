from fastapi import FastAPI

app = FastAPI(title="CS2 BUFF Trade-up Opportunity Scanner")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "cs2-buff-tradeup-scanner",
    }
