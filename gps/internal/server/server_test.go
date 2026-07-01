package server

import (
	"context"
	"encoding/binary"
	"net"
	"testing"
	"time"

	"github.com/kuznetsovin/egts-protocol/libs/egts"
	log "github.com/sirupsen/logrus"
	"passangerbackendserver/gps/internal/model"
	"passangerbackendserver/gps/internal/service"
)

func TestServerRespondsToPacket(t *testing.T) {
	logger := log.New()
	store := &nopStore{}
	processor := service.NewProcessor(store, logger)

	srv := New("127.0.0.1:5900", 2*time.Second, "", processor, logger)
	if err := srv.Start(); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	defer srv.Shutdown(context.Background())

	time.Sleep(200 * time.Millisecond)

	message := []byte{0x01, 0x00, 0x00, 0x0B, 0x00, 0xB1, 0x00, 0xE8, 0x04, 0x01, 0x4E, 0xA6, 0x00, 0xA1, 0x0A, 0x81, 0x34, 0xF6, 0xE9, 0x01,
		0x02, 0x02, 0x10, 0x1A, 0x00, 0x4F, 0x5F, 0xE5, 0x10, 0x00, 0xBE, 0xCD, 0x9E, 0x80, 0x7F, 0x8B, 0x35, 0x93, 0x9B, 0x80, 0x2F, 0xF9, 0x80,
		0x02, 0x01, 0x00, 0x92, 0x00, 0x00, 0x00, 0x00, 0x11, 0x06, 0x00, 0x0E, 0x46, 0x00, 0x00, 0x00, 0x0C, 0x12, 0x1C, 0x00, 0x01, 0x0F, 0xFF,
		0x01, 0x44, 0x6D, 0x00, 0xB8, 0x00, 0x00, 0x0B, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x14, 0x05, 0x00, 0x02, 0xFF, 0x00, 0x29, 0x04, 0x1B, 0x07, 0x00, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1B, 0x07, 0x00,
		0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1B, 0x07, 0x00, 0x03, 0x01, 0x00, 0x5A, 0x08, 0x00, 0x00, 0x1B, 0x07, 0x00, 0x04, 0x02, 0x00,
		0x00, 0x00, 0x00, 0x00, 0x19, 0x04, 0x00, 0x64, 0x77, 0x2A, 0x04, 0x19, 0x04, 0x00, 0x65, 0x00, 0x00, 0x00, 0x19, 0x04, 0x00, 0x66, 0x01,
		0x00, 0x00, 0x19, 0x04, 0x00, 0x67, 0x77, 0x2A, 0x04, 0x19, 0x04, 0x00, 0x68, 0x77, 0x2A, 0x04, 0x19, 0x04, 0x00, 0x69, 0x4F, 0x9A, 0x22,
		0x19, 0x04, 0x00, 0x6E, 0x77, 0x2A, 0x04, 0x41, 0xF6}

	conn, err := net.Dial("tcp", "127.0.0.1:5900")
	if err != nil {
		t.Fatalf("Dial() error = %v", err)
	}
	defer conn.Close()

	if _, err := conn.Write(message); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	buf := make([]byte, 29)
	if _, err := conn.Read(buf); err != nil {
		t.Fatalf("Read() error = %v", err)
	}

	if len(buf) != 29 {
		t.Fatalf("expected 29 response bytes, got %d", len(buf))
	}
}

func TestCreatePtResponseUsesRecordResponseFormatExpectedByRelay(t *testing.T) {
	resp, err := createPtResponse(0x04E8, egtsPcOk, egts.TeledataService, egts.RecordDataSet{
		{
			SubrecordType:   egts.SrRecordResponseType,
			SubrecordLength: 3,
			SubrecordData: &egts.SrResponse{
				ConfirmedRecordNumber: 0x000A,
				RecordStatus:          egtsPcOk,
			},
		},
	})
	if err != nil {
		t.Fatalf("createPtResponse() error = %v", err)
	}

	if got := resp[14:16]; got[0] != 0x06 || got[1] != 0x00 {
		t.Fatalf("expected RL to be 06 00, got % X", got)
	}
	if got := resp[18]; got != 0x40 {
		t.Fatalf("expected record flags to be 0x40 (RSOD), got 0x%02X", got)
	}

	pkg := egts.Package{}
	if _, err := pkg.Decode(resp); err != nil {
		t.Fatalf("Decode() error = %v", err)
	}

	ptResponse, ok := pkg.ServicesFrameData.(*egts.PtResponse)
	if !ok {
		t.Fatalf("expected PtResponse, got %T", pkg.ServicesFrameData)
	}
	if ptResponse.ResponsePacketID != 0x04E8 {
		t.Fatalf("expected RPID to match incoming PID, got %d", ptResponse.ResponsePacketID)
	}

	sdr, ok := ptResponse.SDR.(*egts.ServiceDataSet)
	if !ok {
		t.Fatalf("expected service data set, got %T", ptResponse.SDR)
	}
	record := (*sdr)[0]
	if record.RecordLength != 6 {
		t.Fatalf("expected RecordLength 6, got %d", record.RecordLength)
	}
	if record.RecipientServiceOnDevice != "1" {
		t.Fatalf("expected RSOD flag to be set")
	}
}

func TestCreateAuthServiceResponseAddsResolvedDispatcherIdentity(t *testing.T) {
	resp, err := createAuthServiceResponse(0x04E8, egtsPcOk, "203.0.113.10")
	if err != nil {
		t.Fatalf("createAuthServiceResponse() error = %v", err)
	}

	pkg := egts.Package{}
	if _, err := pkg.Decode(resp); err != nil {
		t.Fatalf("Decode() error = %v", err)
	}

	ptResponse, ok := pkg.ServicesFrameData.(*egts.PtResponse)
	if !ok {
		t.Fatalf("expected PtResponse, got %T", pkg.ServicesFrameData)
	}

	sdr, ok := ptResponse.SDR.(*egts.ServiceDataSet)
	if !ok {
		t.Fatalf("expected service data set, got %T", ptResponse.SDR)
	}
	if len(*sdr) != 1 {
		t.Fatalf("expected one service data record, got %d", len(*sdr))
	}

	recordData := (*sdr)[0].RecordDataSet
	if len(recordData) != 2 {
		t.Fatalf("expected result code and dispatcher identity, got %d subrecords", len(recordData))
	}
	dispatcherSubrecord, ok := recordData[1].SubrecordData.(*egts.SrDispatcherIdentity)
	if !ok {
		t.Fatalf("expected dispatcher identity subrecord, got %T", recordData[1].SubrecordData)
	}
	if dispatcherSubrecord.DispatcherType != 0 {
		t.Fatalf("expected dispatcher type 0, got %d", dispatcherSubrecord.DispatcherType)
	}

	expectedID := binary.LittleEndian.Uint32(net.ParseIP("203.0.113.10").To4())
	if dispatcherSubrecord.DispatcherID != expectedID {
		t.Fatalf("expected dispatcher id %d, got %d", expectedID, dispatcherSubrecord.DispatcherID)
	}
}

func TestResolveDispatcherIDRejectsHostWithoutIPv4(t *testing.T) {
	if _, err := resolveDispatcherID("::1"); err == nil {
		t.Fatal("expected ipv4 resolution error")
	}
}

type nopStore struct{}

func (n *nopStore) SaveGPSPoint(_ context.Context, _ model.GPSPoint) (service.SaveResult, error) {
	return service.SaveResult{}, nil
}

func (n *nopStore) Ping(context.Context) error { return nil }
func (n *nopStore) Close()                     {}
