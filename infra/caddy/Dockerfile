FROM golang:1.26.5-alpine3.23@sha256:622e56dbc11a8cfe87cafa2331e9a201877271cbff918af53d3be315f3da88cc AS builder

WORKDIR /src
COPY go.mod go.sum main.go ./
RUN go mod download \
    && go mod verify \
    && CGO_ENABLED=0 go build \
        -buildvcs=false \
        -trimpath \
        -ldflags='-s -w' \
        -o /out/caddy .

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -S -g 101 caddy \
    && adduser -S -D -H -u 100 -G caddy caddy \
    && install -d -o caddy -g caddy -m 0750 /config /data \
    && install -d -m 0755 /etc/caddy /srv

COPY --from=builder /out/caddy /usr/bin/caddy

ENV XDG_CONFIG_HOME=/config
ENV XDG_DATA_HOME=/data
WORKDIR /srv
USER caddy

EXPOSE 80 443 443/udp 2019
VOLUME ["/data", "/config"]
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:2019/config/ || exit 1
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
