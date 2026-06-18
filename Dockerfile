FROM python:3.12-slim

# 系统依赖（PGLite 场景按需添加）
# RUN apt-get update && apt-get install -y --no-install-suggests ... && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码
COPY core/       core/
COPY provider/   provider/
COPY config/     config/
COPY add_diy/    add_diy/
COPY server.py   .

# 运行用户
RUN useradd --no-create-home --shell /bin/false app && chown -R app:app /app
USER app

EXPOSE 8000

# ENTRYPOINT 由 docker-compose 或 k8s 覆盖
CMD ["python", "server.py"]
