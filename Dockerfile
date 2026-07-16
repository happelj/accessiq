FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 accessiq \
    && useradd --uid 10001 --gid accessiq --home-dir /app --shell /usr/sbin/nologin accessiq

ARG ACCESSIQ_VERSION=0.1.0
ARG ACCESSIQ_GIT_SHA=unknown
ARG ACCESSIQ_GIT_TAG=
ARG ACCESSIQ_BUILD_TIMESTAMP=

LABEL org.opencontainers.image.title="AccessIQ API"
LABEL org.opencontainers.image.version="${ACCESSIQ_VERSION}"
LABEL org.opencontainers.image.revision="${ACCESSIQ_GIT_SHA}"
LABEL org.opencontainers.image.ref.name="${ACCESSIQ_GIT_TAG}"
LABEL org.opencontainers.image.created="${ACCESSIQ_BUILD_TIMESTAMP}"

COPY --chown=accessiq:accessiq . .

EXPOSE 8000

USER 10001:10001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
