FROM python:3.10-slim

WORKDIR /app

COPY . /app

RUN pip install "poetry==1.7.1"

RUN poetry install --no-interaction --no-ansi

# EXPOSE 80

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
