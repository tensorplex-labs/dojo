FROM alpine:latest

ARG TARGETARCH
ARG APP_NAME

WORKDIR /app

COPY --from=binaries ${APP_NAME}-linux-${TARGETARCH} ./app

RUN chmod +x ./app

CMD ["./app"]
