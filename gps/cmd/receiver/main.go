package main

import (
	"context"
	"flag"
	"os"
	"os/signal"
	"syscall"
	"time"

	"passangerbackendserver/gps/internal/config"
	"passangerbackendserver/gps/internal/health"
	"passangerbackendserver/gps/internal/server"
	"passangerbackendserver/gps/internal/service"
	postgresstore "passangerbackendserver/gps/internal/storage/postgres"

	log "github.com/sirupsen/logrus"
)

func main() {
	var configPath string
	flag.StringVar(&configPath, "c", "", "Path to YAML config file")
	flag.Parse()

	cfg, err := config.Load(configPath)
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	logger := log.New()
	logger.SetFormatter(&log.JSONFormatter{})
	logger.SetOutput(os.Stdout)
	logger.SetLevel(cfg.LogLevel())

	store, err := postgresstore.New(cfg.Database, logger)
	if err != nil {
		logger.Fatalf("failed to initialize postgres store: %v", err)
	}
	defer store.Close()

	processor := service.NewProcessor(store, logger)
	tcpServer := server.New(
		cfg.Server.ListenAddress(),
		cfg.Server.ConnectionTTL(),
		cfg.Server.DispatcherHost,
		processor,
		logger,
	)
	healthServer := health.New(cfg.Health.ListenAddress(), store, logger)

	if err := tcpServer.Start(); err != nil {
		logger.Fatalf("failed to start tcp server: %v", err)
	}
	if err := healthServer.Start(); err != nil {
		_ = tcpServer.Shutdown(context.Background())
		logger.Fatalf("failed to start health server: %v", err)
	}

	logger.WithFields(log.Fields{
		"tcp_addr":    cfg.Server.ListenAddress(),
		"health_addr": cfg.Health.ListenAddress(),
	}).Info("gps egts service started")

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	<-ctx.Done()
	logger.Info("shutdown signal received")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := healthServer.Shutdown(shutdownCtx); err != nil {
		logger.WithError(err).Error("failed to shutdown health server")
	}
	if err := tcpServer.Shutdown(shutdownCtx); err != nil {
		logger.WithError(err).Error("failed to shutdown tcp server")
	}
}
