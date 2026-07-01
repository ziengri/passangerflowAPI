package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadUsesDefaultsAndEnvOverrides(t *testing.T) {
	t.Setenv("GPS_EGTS_HOST", "127.0.0.2")
	t.Setenv("GPS_EGTS_PORT", "9100")
	t.Setenv("GPS_DATABASE_DSN", "postgres://user:pass@localhost:5432/test?sslmode=disable")
	t.Setenv("GPS_LOG_LEVEL", "debug")

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Host != "127.0.0.2" {
		t.Fatalf("expected host override, got %q", cfg.Server.Host)
	}
	if cfg.Server.Port != 9100 {
		t.Fatalf("expected port override, got %d", cfg.Server.Port)
	}
	if cfg.Database.DSN != "postgres://user:pass@localhost:5432/test?sslmode=disable" {
		t.Fatalf("expected dsn override, got %q", cfg.Database.DSN)
	}
	if cfg.LogLevel().String() != "debug" {
		t.Fatalf("expected debug level, got %s", cfg.LogLevel())
	}
}

func TestLoadReadsYaml(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.yaml")
	content := []byte(`
server:
  host: 127.0.0.1
  port: 9001
  connection_live_seconds: 45
database:
  dsn: postgres://user:pass@localhost:5432/sample?sslmode=disable
  max_connections: 12
logging:
  level: warn
health:
  host: 127.0.0.1
  port: 9002
`)
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatalf("os.WriteFile() error = %v", err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Port != 9001 || cfg.Health.Port != 9002 || cfg.Database.MaxConnections != 12 {
		t.Fatalf("unexpected config values: %+v", cfg)
	}
}
