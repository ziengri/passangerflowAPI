FROM public.ecr.aws/docker/library/golang:1.26 AS build

WORKDIR /src

COPY egts /src/egts
COPY gps /src/gps

WORKDIR /src/gps
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/gps-receiver ./cmd/receiver

FROM public.ecr.aws/docker/library/debian:bookworm-slim

WORKDIR /app

COPY --from=build /out/gps-receiver /usr/local/bin/gps-receiver
COPY gps/configs/receiver.yaml /app/receiver.yaml

EXPOSE 9000 8001

CMD ["gps-receiver", "-c", "/app/receiver.yaml"]
