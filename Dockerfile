FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY static/ ./static/
COPY scripts/ ./scripts/
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "review_evidence.main:app", "--host", "0.0.0.0", "--port", "8000"]
