from fastapi import FastAPI

app = FastAPI(title="Review Evidence Engine")

@app.get("/health")
def health() -> dict[str, str]:
    """Servisin ayakta olup olmadigini bildirir."""
    return {"status": "ok"}

