FROM python:3.12-slim
WORKDIR /app
COPY . .
EXPOSE 5555
CMD ["python", "serve.py"]
