package model

import (
	"encoding/json"
	"fmt"
	"time"

	egtsstorage "github.com/kuznetsovin/egts-protocol/cli/receiver/storage"
)

type GPSPoint struct {
	DeviceID           int64
	PacketID           int32
	NavigationUnixTime int64
	NavigationTime     time.Time
	ReceivedUnixTime   int64
	ReceivedTime       time.Time
	Latitude           float64
	Longitude          float64
	Speed              int32
	Pdop               int32
	Hdop               int32
	Vdop               int32
	Nsat               int32
	Ns                 int32
	Course             int32
	RawJSON            []byte
}

func NewPointFromNavRecord(record *egtsstorage.NavRecord) (GPSPoint, error) {
	if record == nil {
		return GPSPoint{}, fmt.Errorf("nav record is nil")
	}

	point := GPSPoint{
		DeviceID:           int64(record.Client),
		PacketID:           int32(record.PacketID),
		NavigationUnixTime: record.NavigationTimestamp,
		NavigationTime:     time.Unix(record.NavigationTimestamp, 0).UTC(),
		ReceivedUnixTime:   record.ReceivedTimestamp,
		ReceivedTime:       time.Unix(record.ReceivedTimestamp, 0).UTC(),
		Latitude:           record.Latitude,
		Longitude:          record.Longitude,
		Speed:              int32(record.Speed),
		Pdop:               int32(record.Pdop),
		Hdop:               int32(record.Hdop),
		Vdop:               int32(record.Vdop),
		Nsat:               int32(record.Nsat),
		Ns:                 int32(record.Ns),
		Course:             int32(record.Course),
	}

	raw, err := json.Marshal(record)
	if err != nil {
		return GPSPoint{}, fmt.Errorf("marshal raw payload: %w", err)
	}
	point.RawJSON = raw

	if err := point.Validate(); err != nil {
		return GPSPoint{}, err
	}
	return point, nil
}

func (p GPSPoint) Validate() error {
	switch {
	case p.DeviceID <= 0:
		return fmt.Errorf("device_id must be greater than 0")
	case p.Latitude < -90 || p.Latitude > 90:
		return fmt.Errorf("latitude out of range")
	case p.Longitude < -180 || p.Longitude > 180:
		return fmt.Errorf("longitude out of range")
	case p.NavigationUnixTime <= 0:
		return fmt.Errorf("navigation_unix_time must be greater than 0")
	case p.ReceivedUnixTime <= 0:
		return fmt.Errorf("received_unix_time must be greater than 0")
	default:
		return nil
	}
}
