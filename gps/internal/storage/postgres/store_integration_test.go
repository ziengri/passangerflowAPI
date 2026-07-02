package postgres

import (
	"context"
	"os"
	"testing"
	"time"

	"passangerbackendserver/gps/internal/config"
	"passangerbackendserver/gps/internal/model"

	"github.com/jackc/pgx/v5/pgxpool"
	log "github.com/sirupsen/logrus"
)

func TestSaveGPSPointIntegration(t *testing.T) {
	dsn := os.Getenv("GPS_INTEGRATION_DSN")
	if dsn == "" {
		t.Skip("GPS_INTEGRATION_DSN is not set")
	}

	ctx := context.Background()
	adminPool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New() error = %v", err)
	}
	defer adminPool.Close()

	if _, err := adminPool.Exec(ctx, "TRUNCATE TABLE gps_current_position, gps_timeline, bus_trackers RESTART IDENTITY CASCADE"); err != nil {
		t.Fatalf("cleanup error = %v", err)
	}

	store, err := New(config.DatabaseConfig{
		DSN:            dsn,
		MaxConnections: 4,
	}, log.New())
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	defer store.Close()

	first := model.GPSPoint{
		DeviceID:           194918639,
		PacketID:           139,
		NavigationUnixTime: 1782073519,
		NavigationTime:     time.Unix(1782073519, 0).UTC(),
		ReceivedUnixTime:   1782814577,
		ReceivedTime:       time.Unix(1782814577, 0).UTC(),
		Latitude:           55.713711682640415,
		Longitude:          52.342378295106435,
	}

	result, err := store.SaveGPSPoint(ctx, first)
	if err != nil {
		t.Fatalf("SaveGPSPoint(first) error = %v", err)
	}
	if !result.TrackerCreated {
		t.Fatal("expected tracker to be created for first packet")
	}

	var trackerCount, timelineCount, currentCount int
	var busNumberIsNull bool
	if err := adminPool.QueryRow(ctx, "SELECT COUNT(*), COALESCE(bool_and(bus_number IS NULL), true) FROM bus_trackers").Scan(&trackerCount, &busNumberIsNull); err != nil {
		t.Fatalf("query bus_trackers error = %v", err)
	}
	if err := adminPool.QueryRow(ctx, "SELECT COUNT(*) FROM gps_timeline").Scan(&timelineCount); err != nil {
		t.Fatalf("query gps_timeline error = %v", err)
	}
	if err := adminPool.QueryRow(ctx, "SELECT COUNT(*) FROM gps_current_position").Scan(&currentCount); err != nil {
		t.Fatalf("query gps_current_position error = %v", err)
	}

	if trackerCount != 1 || timelineCount != 1 || currentCount != 1 {
		t.Fatalf("unexpected row counts: trackers=%d timeline=%d current=%d", trackerCount, timelineCount, currentCount)
	}
	if !busNumberIsNull {
		t.Fatal("expected bus_number to stay NULL")
	}

	newer := first
	newer.PacketID = 140
	newer.NavigationUnixTime = 1782073619
	newer.NavigationTime = time.Unix(1782073619, 0).UTC()
	if _, err := store.SaveGPSPoint(ctx, newer); err != nil {
		t.Fatalf("SaveGPSPoint(newer) error = %v", err)
	}

	older := first
	older.PacketID = 138
	older.NavigationUnixTime = 1782073419
	older.NavigationTime = time.Unix(1782073419, 0).UTC()
	if _, err := store.SaveGPSPoint(ctx, older); err != nil {
		t.Fatalf("SaveGPSPoint(older) error = %v", err)
	}

	var currentPacketID int
	if err := adminPool.QueryRow(ctx, "SELECT packet_id FROM gps_current_position WHERE device_id = $1", first.DeviceID).Scan(&currentPacketID); err != nil {
		t.Fatalf("query current position error = %v", err)
	}
	if currentPacketID != 140 {
		t.Fatalf("expected latest packet_id 140, got %d", currentPacketID)
	}

	if err := adminPool.QueryRow(ctx, "SELECT COUNT(*) FROM gps_timeline WHERE device_id = $1", first.DeviceID).Scan(&timelineCount); err != nil {
		t.Fatalf("query timeline count error = %v", err)
	}
	if timelineCount != 3 {
		t.Fatalf("expected timeline to keep all 3 points, got %d", timelineCount)
	}
}
