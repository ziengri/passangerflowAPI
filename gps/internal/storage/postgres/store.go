package postgres

import (
	"context"
	"fmt"

	"passangerbackendserver/gps/internal/config"
	"passangerbackendserver/gps/internal/model"
	"passangerbackendserver/gps/internal/service"

	"github.com/jackc/pgx/v5/pgxpool"
	log "github.com/sirupsen/logrus"
)

type Store struct {
	pool   *pgxpool.Pool
	logger *log.Logger
}

func New(cfg config.DatabaseConfig, logger *log.Logger) (*Store, error) {
	poolConfig, err := pgxpool.ParseConfig(cfg.DSN)
	if err != nil {
		return nil, fmt.Errorf("parse dsn: %w", err)
	}
	poolConfig.MaxConns = cfg.MaxConnections

	pool, err := pgxpool.NewWithConfig(context.Background(), poolConfig)
	if err != nil {
		return nil, fmt.Errorf("create pool: %w", err)
	}
	if err := pool.Ping(context.Background()); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping postgres: %w", err)
	}

	return &Store{pool: pool, logger: logger}, nil
}

func (s *Store) SaveGPSPoint(ctx context.Context, point model.GPSPoint) (service.SaveResult, error) {
	if err := point.Validate(); err != nil {
		return service.SaveResult{}, err
	}
	rawJSON := point.RawJSON
	if len(rawJSON) == 0 {
		rawJSON = []byte(`{}`)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return service.SaveResult{}, fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	var trackerCreated bool
	if err := tx.QueryRow(
		ctx,
		`
		INSERT INTO bus_trackers (
		    device_id,
		    first_seen_at,
		    last_seen_at,
		    meta_json,
		    created_at,
		    updated_at
		)
		VALUES ($1, $2, $2, '{}'::jsonb, $2, $2)
		ON CONFLICT (device_id) DO UPDATE
		SET last_seen_at = EXCLUDED.last_seen_at,
		    updated_at = EXCLUDED.updated_at
		RETURNING (xmax = 0) AS inserted
		`,
		point.DeviceID,
		point.ReceivedTime,
	).Scan(&trackerCreated); err != nil {
		return service.SaveResult{}, fmt.Errorf("upsert bus_trackers: %w", err)
	}

	if _, err := tx.Exec(
		ctx,
		`
		INSERT INTO gps_timeline (
		    device_id,
		    packet_id,
		    navigation_unix_time,
		    navigation_time,
		    received_unix_time,
		    received_time,
		    latitude,
		    longitude,
		    speed,
		    pdop,
		    hdop,
		    vdop,
		    nsat,
		    ns,
		    course
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
		`,
		point.DeviceID,
		point.PacketID,
		point.NavigationUnixTime,
		point.NavigationTime,
		point.ReceivedUnixTime,
		point.ReceivedTime,
		point.Latitude,
		point.Longitude,
		point.Speed,
		point.Pdop,
		point.Hdop,
		point.Vdop,
		point.Nsat,
		point.Ns,
		point.Course,
	); err != nil {
		return service.SaveResult{}, fmt.Errorf("insert gps_timeline: %w", err)
	}

	if _, err := tx.Exec(
		ctx,
		`
		INSERT INTO gps_current_position (
		    device_id,
		    packet_id,
		    navigation_unix_time,
		    navigation_time,
		    received_unix_time,
		    received_time,
		    latitude,
		    longitude,
		    speed,
		    pdop,
		    hdop,
		    vdop,
		    nsat,
		    ns,
		    course,
		    raw_json,
		    created_at,
		    updated_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16::jsonb, $6, $6)
		ON CONFLICT (device_id) DO UPDATE
		SET packet_id = EXCLUDED.packet_id,
		    navigation_unix_time = EXCLUDED.navigation_unix_time,
		    navigation_time = EXCLUDED.navigation_time,
		    received_unix_time = EXCLUDED.received_unix_time,
		    received_time = EXCLUDED.received_time,
		    latitude = EXCLUDED.latitude,
		    longitude = EXCLUDED.longitude,
		    speed = EXCLUDED.speed,
		    pdop = EXCLUDED.pdop,
		    hdop = EXCLUDED.hdop,
		    vdop = EXCLUDED.vdop,
		    nsat = EXCLUDED.nsat,
		    ns = EXCLUDED.ns,
		    course = EXCLUDED.course,
		    raw_json = EXCLUDED.raw_json,
		    updated_at = EXCLUDED.updated_at
		WHERE gps_current_position.navigation_time <= EXCLUDED.navigation_time
		`,
		point.DeviceID,
		point.PacketID,
		point.NavigationUnixTime,
		point.NavigationTime,
		point.ReceivedUnixTime,
		point.ReceivedTime,
		point.Latitude,
		point.Longitude,
		point.Speed,
		point.Pdop,
		point.Hdop,
		point.Vdop,
		point.Nsat,
		point.Ns,
		point.Course,
		string(rawJSON),
	); err != nil {
		return service.SaveResult{}, fmt.Errorf("upsert gps_current_position: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return service.SaveResult{}, fmt.Errorf("commit transaction: %w", err)
	}

	return service.SaveResult{TrackerCreated: trackerCreated}, nil
}

func (s *Store) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *Store) Close() {
	s.pool.Close()
}
