package config

import (
	"errors"
	"os"
	"strconv"
	"strings"
	"time"

	log "github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

type Config struct {
	Server   ServerConfig   `yaml:"server"`
	Database DatabaseConfig `yaml:"database"`
	Logging  LoggingConfig  `yaml:"logging"`
	Health   HealthConfig   `yaml:"health"`
}

type ServerConfig struct {
	Host                  string `yaml:"host"`
	Port                  int    `yaml:"port"`
	ConnectionLiveSeconds int    `yaml:"connection_live_seconds"`
	DispatcherHost        string `yaml:"dispatcher_host"`
}

type DatabaseConfig struct {
	DSN            string `yaml:"dsn"`
	MaxConnections int32  `yaml:"max_connections"`
}

type LoggingConfig struct {
	Level string `yaml:"level"`
}

type HealthConfig struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
}

func defaultConfig() Config {
	return Config{
		Server: ServerConfig{
			Host:                  "0.0.0.0",
			Port:                  9000,
			ConnectionLiveSeconds: 30,
			DispatcherHost:        "",
		},
		Database: DatabaseConfig{
			DSN:            "postgres://app_user:j0lxEv0sljXa@localhost:5432/app_db?sslmode=disable",
			MaxConnections: 10,
		},
		Logging: LoggingConfig{
			Level: "info",
		},
		Health: HealthConfig{
			Host: "0.0.0.0",
			Port: 8001,
		},
	}
}

func Load(path string) (Config, error) {
	cfg := defaultConfig()
	if path != "" {
		data, err := os.ReadFile(path)
		if err != nil {
			return Config{}, err
		}
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			return Config{}, err
		}
	}

	applyEnv(&cfg)
	if err := cfg.validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func (c Config) LogLevel() log.Level {
	switch strings.ToLower(strings.TrimSpace(c.Logging.Level)) {
	case "debug":
		return log.DebugLevel
	case "warn", "warning":
		return log.WarnLevel
	case "error":
		return log.ErrorLevel
	default:
		return log.InfoLevel
	}
}

func (s ServerConfig) ListenAddress() string {
	return s.Host + ":" + strconv.Itoa(s.Port)
}

func (s ServerConfig) ConnectionTTL() time.Duration {
	return time.Duration(s.ConnectionLiveSeconds) * time.Second
}

func (h HealthConfig) ListenAddress() string {
	return h.Host + ":" + strconv.Itoa(h.Port)
}

func applyEnv(cfg *Config) {
	if value := os.Getenv("GPS_EGTS_HOST"); value != "" {
		cfg.Server.Host = value
	}
	if value := os.Getenv("GPS_EGTS_PORT"); value != "" {
		if parsed, err := strconv.Atoi(value); err == nil {
			cfg.Server.Port = parsed
		}
	}
	if value := os.Getenv("GPS_EGTS_DISPATCHER_HOST"); value != "" {
		cfg.Server.DispatcherHost = value
	}
	if value := os.Getenv("GPS_DATABASE_DSN"); value != "" {
		cfg.Database.DSN = value
	}
	if value := os.Getenv("GPS_DATABASE_MAX_CONNECTIONS"); value != "" {
		if parsed, err := strconv.ParseInt(value, 10, 32); err == nil {
			cfg.Database.MaxConnections = int32(parsed)
		}
	}
	if value := os.Getenv("GPS_LOG_LEVEL"); value != "" {
		cfg.Logging.Level = value
	}
	if value := os.Getenv("GPS_HEALTH_HOST"); value != "" {
		cfg.Health.Host = value
	}
	if value := os.Getenv("GPS_HEALTH_PORT"); value != "" {
		if parsed, err := strconv.Atoi(value); err == nil {
			cfg.Health.Port = parsed
		}
	}
}

func (c Config) validate() error {
	switch {
	case strings.TrimSpace(c.Server.Host) == "":
		return errors.New("server.host must not be empty")
	case c.Server.Port <= 0:
		return errors.New("server.port must be greater than 0")
	case c.Server.ConnectionLiveSeconds <= 0:
		return errors.New("server.connection_live_seconds must be greater than 0")
	case strings.TrimSpace(c.Database.DSN) == "":
		return errors.New("database.dsn must not be empty")
	case c.Database.MaxConnections <= 0:
		return errors.New("database.max_connections must be greater than 0")
	case strings.TrimSpace(c.Health.Host) == "":
		return errors.New("health.host must not be empty")
	case c.Health.Port <= 0:
		return errors.New("health.port must be greater than 0")
	default:
		return nil
	}
}
