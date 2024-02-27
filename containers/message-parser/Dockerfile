FROM python:3.10-slim

WORKDIR /code

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y git curl

ENV VIRTUAL_ENV=/opt/venv \
  PATH="/opt/venv/bin:$PATH"

ADD https://astral.sh/uv/install.sh /install.sh
RUN chmod -R 655 /install.sh && /install.sh && rm /install.sh
COPY ./requirements.txt /code/requirements.txt
RUN /root/.cargo/bin/uv venv /opt/venv && \
  /root/.cargo/bin/uv pip install --no-cache -r requirements.txt

COPY ./app /code/app
COPY ./assets /code/assets
COPY ./description.md /code/description.md

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port 8080
