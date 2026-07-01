package health

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	log "github.com/sirupsen/logrus"
)

type Checker interface {
	Ping(context.Context) error
}

type Server struct {
	httpServer *http.Server
	logger     *log.Logger
}

func New(addr string, checker Checker, logger *log.Logger) *Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		w.Header().Set("Content-Type", "application/json")
		if err := checker.Ping(ctx); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(map[string]string{
				"status":   "error",
				"database": "unavailable",
			})
			return
		}

		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	return &Server{
		httpServer: &http.Server{
			Addr:    addr,
			Handler: mux,
		},
		logger: logger,
	}
}

func (s *Server) Start() error {
	go func() {
		if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			s.logger.WithError(err).Error("health server stopped with error")
		}
	}()
	return nil
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}
