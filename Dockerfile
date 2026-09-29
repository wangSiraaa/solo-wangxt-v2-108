# 后端 + 已构建前端的一体化镜像
FROM python:3.11-slim AS backend
WORKDIR /srv

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scripts ./scripts
# 前端静态产物（本地先执行 `cd frontend && npm ci && npm run build`）
COPY frontend/dist ./frontend/dist

EXPOSE 8000
# 默认 SQLite；docker-compose 通过 DATABASE_URL 覆盖为 PostgreSQL
ENV DATABASE_URL="sqlite+pysqlite:////srv/data/roast.db"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
