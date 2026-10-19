# Image backend chạy trên Render (gói Free, 512 MB RAM).
# Build từ THƯ MỤC GỐC project (cần cả graphrag/ và configs/):
#   docker build -f backend/Dockerfile -t graphrag-api .
#   docker run --env-file .env.cloud -p 8000:8000 graphrag-api
# Trên Render: Dockerfile Path = ./backend/Dockerfile, Docker Build Context = . (thư mục gốc)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=cloud \
    GRAPHRAG_ROOT=/app

WORKDIR /app

# 1) Cài thư viện (chỉ nhóm "api", KHÔNG cài torch / sentence-transformers cho nhẹ)
COPY pyproject.toml ./
COPY graphrag/ ./graphrag/
RUN pip install ".[api]"

# 2) Chép cấu hình và mã backend
COPY configs/ ./configs/
COPY backend/ ./backend/

# Chạy bằng người dùng thường, không dùng root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Render cấp cổng qua biến PORT
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
