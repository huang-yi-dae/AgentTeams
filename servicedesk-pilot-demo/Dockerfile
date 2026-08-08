# ServiceDesk Pilot —— Docker 形态（服务化运行）
# 纯 Python 标准库，无需 pip install。
FROM python:3.13-slim

WORKDIR /app

# 复制整个 demo 目录（mock 数据、agents、skills、adapters 等）
COPY . .

EXPOSE 8080

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8080"]
