FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
COPY static/ ./static/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "review_evidence.main:app", "--host", "0.0.0.0", "--port", "8000"]
