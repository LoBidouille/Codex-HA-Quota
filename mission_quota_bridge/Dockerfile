FROM python:3.13-alpine3.23 AS codex
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl \
    && case "$TARGETARCH" in \
        arm64) arch=aarch64; sha=0b99526c185a4425fe96a2214fb7b6a6a7f7c1471883b7afbebe97e15e83e79e ;; \
        amd64) arch=x86_64; sha=a2342a8f7f68f088be30620ccfe9cb84162c93a6b56177855961cda3ed6be392 ;; \
        *) exit 1 ;; \
    esac \
    && asset="codex-$arch-unknown-linux-musl" \
    && curl --fail --silent --show-error --location --retry 3 \
        "https://github.com/openai/codex/releases/download/rust-v0.172.0/$asset.tar.gz" -o /tmp/codex.tar.gz \
    && echo "$sha  /tmp/codex.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/codex.tar.gz -C /tmp "$asset" \
    && install -m 0755 "/tmp/$asset" /usr/local/bin/codex \
    && /usr/local/bin/codex --version

FROM python:3.13-alpine3.23
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/mission-quota
COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex
COPY requirements.txt requirements-ha.txt ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt -r requirements-ha.txt
COPY bridge.py codex_client.py quota.py ha_config.py ha_app.py ./
COPY web ./web
CMD ["python3", "ha_app.py"]
