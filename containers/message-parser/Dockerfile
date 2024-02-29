FROM python:3.10-slim AS python-base

WORKDIR /code

RUN apt-get update && apt-get install -y \
  git \
  curl \
  && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -LsSf https://github.com/astral-sh/uv/releases/download/0.1.12/uv-installer.sh | sh

ENV PATH="/root/.cargo/bin:${PATH}"

COPY ./requirements.txt /code/requirements.txt

RUN uv pip install --python python3.10 --no-cache -r requirements.txt

COPY ./app /code/app
COPY ./assets /code/assets
COPY ./description.md /code/description.md

EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port 8080
