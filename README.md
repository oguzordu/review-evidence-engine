# Review Evidence Engine

A Q&A service over product reviews that **counts instead of samples**, and
grounds every answer in the reviews it's based on.

## The problem

A product has hundreds of reviews. You want to ask "does the battery
actually last?" but you can't read them all.

Standard review-summary systems — including the "AI summary" features
shipped by major e-commerce platforms — read a handful of similar reviews
and generate a confident-sounding answer. When the relevant reviews outnumber
what the system actually reads, the rest are silently ignored. Amazon's own
AI review summaries have been reported to draw conclusions from a small
fraction of the available reviews, misrepresenting the overall picture.

## The approach

This service evaluates **every** relevant review individually instead of
sampling a handful. It reports:

- How many reviews actually address the question
- How they split — positive / negative / unclear
- Whether opinions conflict, without hiding the disagreement
- Whether sentiment has shifted recently (possible product/batch change)
- The exact reviews each claim is based on

Example:

```
"Is it waterproof?"  ->  47 relevant reviews

   31 reviews: no leaks
   12 reviews: leaks
    4 reviews: unclear

   Warning: 9 of the negative reviews are concentrated in the last 3 months.
```

## Tech stack

Python, FastAPI, PostgreSQL, a vector store for semantic search, and an LLM
for classification — packaged with Docker.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run

```powershell
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Test

```powershell
.venv\Scripts\python.exe -m pytest -v
```
