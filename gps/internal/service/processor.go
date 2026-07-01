package service

import (
	"context"
	"fmt"

	"passangerbackendserver/gps/internal/model"

	egtsstorage "github.com/kuznetsovin/egts-protocol/cli/receiver/storage"
	log "github.com/sirupsen/logrus"
)

type SaveResult struct {
	TrackerCreated bool
}

type Store interface {
	SaveGPSPoint(context.Context, model.GPSPoint) (SaveResult, error)
	Ping(context.Context) error
	Close()
}

type Processor struct {
	store  Store
	logger *log.Logger
}

func NewProcessor(store Store, logger *log.Logger) *Processor {
	return &Processor{
		store:  store,
		logger: logger,
	}
}

func (p *Processor) HandleNavRecord(ctx context.Context, record *egtsstorage.NavRecord) error {
	point, err := model.NewPointFromNavRecord(record)
	if err != nil {
		return fmt.Errorf("build gps point: %w", err)
	}

	result, err := p.store.SaveGPSPoint(ctx, point)
	if err != nil {
		return fmt.Errorf("save gps point: %w", err)
	}

	if result.TrackerCreated {
		p.logger.WithField("device_id", point.DeviceID).Info("created tracker for new device")
	}

	return nil
}
