package model

import (
	"encoding/json"
	"testing"
	"time"

	egtsstorage "github.com/kuznetsovin/egts-protocol/cli/receiver/storage"
)

func TestNewPointFromNavRecordMapsClientAndTimes(t *testing.T) {
	record := &egtsstorage.NavRecord{
		Client:              194918639,
		PacketID:            139,
		NavigationTimestamp: 1782073519,
		ReceivedTimestamp:   1782814577,
		Latitude:            55.713711682640415,
		Longitude:           52.342378295106435,
	}

	point, err := NewPointFromNavRecord(record)
	if err != nil {
		t.Fatalf("NewPointFromNavRecord() error = %v", err)
	}

	if point.DeviceID != 194918639 {
		t.Fatalf("expected device id 194918639, got %d", point.DeviceID)
	}
	if point.NavigationTime != time.Unix(1782073519, 0).UTC() {
		t.Fatalf("unexpected navigation time: %s", point.NavigationTime)
	}
	if point.ReceivedTime != time.Unix(1782814577, 0).UTC() {
		t.Fatalf("unexpected received time: %s", point.ReceivedTime)
	}
	if len(point.RawJSON) == 0 {
		t.Fatal("expected raw json to be populated")
	}

	var raw map[string]any
	if err := json.Unmarshal(point.RawJSON, &raw); err != nil {
		t.Fatalf("expected valid raw json, got error: %v", err)
	}
}

func TestNewPointFromNavRecordRejectsInvalidLatitude(t *testing.T) {
	record := &egtsstorage.NavRecord{
		Client:              1,
		PacketID:            1,
		NavigationTimestamp: 1782073519,
		ReceivedTimestamp:   1782814577,
		Latitude:            95,
		Longitude:           52,
	}

	if _, err := NewPointFromNavRecord(record); err == nil {
		t.Fatal("expected validation error for latitude")
	}
}

func TestNewPointFromNavRecordRejectsInvalidLongitude(t *testing.T) {
	record := &egtsstorage.NavRecord{
		Client:              1,
		PacketID:            1,
		NavigationTimestamp: 1782073519,
		ReceivedTimestamp:   1782814577,
		Latitude:            55,
		Longitude:           181,
	}

	if _, err := NewPointFromNavRecord(record); err == nil {
		t.Fatal("expected validation error for longitude")
	}
}
