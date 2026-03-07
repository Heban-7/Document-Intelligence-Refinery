# Document Intelligence Refinery — reproducible deploy
# Build: docker build -t refinery .
# Run:  docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/.refinery:/app/.refinery refinery triage /app/data/your.pdf

FROM python:3.13-slim

WORKDIR /app

# System deps for pdfplumber/pymupdf (optional, for some PDFs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Install project
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY src/ src/
COPY rubric/ rubric/
COPY scripts/ scripts/

# Default: run triage on first PDF in /app/data (override with CMD)
ENV REFINERY_REPO_ROOT=/app
RUN mkdir -p /app/data /app/.refinery

# Optional: set OPENROUTER_API_KEY for Strategy C (vision)
# ENV OPENROUTER_API_KEY=

# Run with: docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/.refinery:/app/.refinery refinery python -m src.cli.triage /app/data/your.pdf
# Or: docker run ... refinery python -m src.cli.extract /app/data/
CMD ["python", "-m", "src.cli.triage", "--help"]
