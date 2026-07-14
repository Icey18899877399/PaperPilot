FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        fontconfig \
        fonts-noto-cjk \
        fonts-noto-core \
        libgl1 \
        libglib2.0-0 \
        libgomp1 && \
    fc-cache -fv && \
    rm -rf /var/lib/apt/lists/*

# CPU-only course deployment: install the pipeline dependencies without vLLM.
RUN python -m pip install --upgrade pip && \
    python -m pip install "mineru[pipeline]==3.4.0"

# MinerU 3.4 pipeline imports six at runtime but does not declare it.
RUN python -m pip install "six>=1.16,<2"

# MinerU 3.4 expects pdftext's pre-0.7 iterable character list API.
RUN python -m pip install --force-reinstall --no-deps "pdftext==0.6.3"

WORKDIR /app
EXPOSE 8000

CMD ["mineru-api", "--host", "0.0.0.0", "--port", "8000"]
