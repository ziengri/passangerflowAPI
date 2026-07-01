package server

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"strings"
	"sync"
	"time"

	"passangerbackendserver/gps/internal/service"

	egtsstorage "github.com/kuznetsovin/egts-protocol/cli/receiver/storage"
	"github.com/kuznetsovin/egts-protocol/libs/egts"
	log "github.com/sirupsen/logrus"
)

const (
	egtsPcOk  = 0
	headerLen = 10
)

type Server struct {
	addr           string
	ttl            time.Duration
	dispatcherHost string
	processor      *service.Processor
	logger         *log.Logger
	listener       net.Listener
	wg             sync.WaitGroup
}

func New(addr string, ttl time.Duration, dispatcherHost string, processor *service.Processor, logger *log.Logger) *Server {
	return &Server{
		addr:           addr,
		ttl:            ttl,
		dispatcherHost: dispatcherHost,
		processor:      processor,
		logger:         logger,
	}
}

func (s *Server) Start() error {
	ln, err := net.Listen("tcp", s.addr)
	if err != nil {
		return err
	}
	s.listener = ln

	go s.acceptLoop()
	return nil
}

func (s *Server) Shutdown(ctx context.Context) error {
	if s.listener != nil {
		_ = s.listener.Close()
	}

	done := make(chan struct{})
	go func() {
		defer close(done)
		s.wg.Wait()
	}()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-done:
		return nil
	}
}

func (s *Server) acceptLoop() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			if isClosedNetworkError(err) {
				return
			}
			s.logger.WithError(err).Error("failed to accept egts connection")
			continue
		}

		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			s.handleConn(conn)
		}()
	}
}

func (s *Server) handleConn(conn net.Conn) {
	defer conn.Close()
	s.logger.WithField("remote_addr", conn.RemoteAddr().String()).Info("gps device connected")
	defer s.logger.WithField("remote_addr", conn.RemoteAddr().String()).Info("gps device disconnected")

	var client uint32

	for {
		if err := conn.SetReadDeadline(time.Now().Add(s.ttl)); err != nil {
			s.logger.WithError(err).Error("failed to set read deadline")
			return
		}

		headerBuf := make([]byte, headerLen)
		if _, err := io.ReadFull(conn, headerBuf); err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				s.logger.WithField("remote_addr", conn.RemoteAddr().String()).Warn("connection closed by timeout")
				return
			}
			if err != io.EOF {
				s.logger.WithError(err).Error("failed to read egts header")
			}
			return
		}

		if headerBuf[0] != 0x01 {
			s.logger.WithField("remote_addr", conn.RemoteAddr().String()).Warn("received non-egts packet")
			return
		}

		bodyLen := binary.LittleEndian.Uint16(headerBuf[5:7])
		packetLen := uint16(headerBuf[3])
		if bodyLen > 0 {
			packetLen += bodyLen + 2
		}

		body := make([]byte, packetLen-headerLen)
		if _, err := io.ReadFull(conn, body); err != nil {
			s.logger.WithError(err).Error("failed to read egts body")
			return
		}

		receivedPacket := append(headerBuf, body...)
		pkg := egts.Package{}
		receivedUnix := time.Now().UTC().Unix()

		serviceType := uint8(0)
		srResponses := egts.RecordDataSet(nil)
		srResultCode := []byte(nil)

		resultCode, err := pkg.Decode(receivedPacket)
		if err != nil {
			s.logger.WithError(err).Error("failed to decode egts packet")
			resp, responseErr := createPtResponse(pkg.PacketIdentifier, resultCode, serviceType, nil)
			if responseErr == nil {
				_, _ = conn.Write(resp)
			}
			continue
		}

		if pkg.PacketType != egts.PtAppdataPacket {
			continue
		}

		for _, rec := range *pkg.ServicesFrameData.(*egts.ServiceDataSet) {
			serviceType = rec.SourceServiceType
			navRecord := &egtsstorage.NavRecord{
				PacketID: uint32(pkg.PacketIdentifier),
			}
			hasPosition := false
			packetIDBytes := make([]byte, 4)

			srResponses = append(srResponses, egts.RecordData{
				SubrecordType:   egts.SrRecordResponseType,
				SubrecordLength: 3,
				SubrecordData: &egts.SrResponse{
					ConfirmedRecordNumber: rec.RecordNumber,
					RecordStatus:          egtsPcOk,
				},
			})

			if rec.ObjectIDFieldExists == "1" {
				client = rec.ObjectIdentifier
			}

			for _, subRec := range rec.RecordDataSet {
				switch subRecData := subRec.SubrecordData.(type) {
				case *egts.SrTermIdentity:
					client = subRecData.TerminalIdentifier
					srResultCode, _ = createAuthServiceResponse(pkg.PacketIdentifier, egtsPcOk, s.dispatcherHost)
				case *egts.SrAuthInfo:
					srResultCode, _ = createAuthServiceResponse(pkg.PacketIdentifier, egtsPcOk, s.dispatcherHost)
				case *egts.SrResponse:
					continue
				case *egts.SrPosData:
					hasPosition = true
					navRecord.NavigationTimestamp = subRecData.NavigationTime.Unix()
					navRecord.ReceivedTimestamp = receivedUnix
					navRecord.Latitude = subRecData.Latitude
					navRecord.Longitude = subRecData.Longitude
					navRecord.Speed = subRecData.Speed
					navRecord.Course = subRecData.Direction
				case *egts.SrExtPosData:
					navRecord.Nsat = subRecData.Satellites
					navRecord.Pdop = subRecData.PositionDilutionOfPrecision
					navRecord.Hdop = subRecData.HorizontalDilutionOfPrecision
					navRecord.Vdop = subRecData.VerticalDilutionOfPrecision
					navRecord.Ns = subRecData.NavigationSystem
				case *egts.SrAbsCntrData:
					switch subRecData.CounterNumber {
					case 110:
						binary.BigEndian.PutUint32(packetIDBytes, subRecData.CounterValue)
						navRecord.PacketID = subRecData.CounterValue
					case 111:
						tmpBuf := make([]byte, 4)
						binary.BigEndian.PutUint32(tmpBuf, subRecData.CounterValue)
						packetIDBytes[3] = tmpBuf[3]
						navRecord.PacketID = binary.LittleEndian.Uint32(packetIDBytes)
					}
				}
			}

			navRecord.Client = client
			if hasPosition {
				if err := s.processor.HandleNavRecord(context.Background(), navRecord); err != nil {
					s.logger.WithError(err).WithField("device_id", navRecord.Client).Error("failed to process gps point")
				}
			}
		}

		resp, err := createPtResponse(pkg.PacketIdentifier, resultCode, serviceType, srResponses)
		if err != nil {
			s.logger.WithError(err).Error("failed to encode egts response")
			continue
		}
		_, _ = conn.Write(resp)
		if len(srResultCode) > 0 {
			_, _ = conn.Write(srResultCode)
		}
	}
}

func createPtResponse(pid uint16, resultCode, serviceType uint8, srResponses egts.RecordDataSet) ([]byte, error) {
	respSection := egts.PtResponse{
		ResponsePacketID: pid,
		ProcessingResult: resultCode,
	}

	if srResponses != nil {
		respSection.SDR = &egts.ServiceDataSet{
			buildResponseRecord(serviceType, srResponses),
		}
	}

	respPkg := egts.Package{
		ProtocolVersion:   1,
		SecurityKeyID:     0,
		Prefix:            "00",
		Route:             "0",
		EncryptionAlg:     "00",
		Compression:       "0",
		Priority:          "00",
		HeaderLength:      11,
		HeaderEncoding:    0,
		FrameDataLength:   respSection.Length(),
		PacketIdentifier:  pid + 1,
		PacketType:        egts.PtResponsePacket,
		ServicesFrameData: &respSection,
	}

	return respPkg.Encode()
}

func createAuthServiceResponse(pid uint16, resultCode uint8, dispatcherHost string) ([]byte, error) {
	rds := egts.RecordDataSet{
		{
			SubrecordType:   egts.SrResultCodeType,
			SubrecordLength: uint16(1),
			SubrecordData: &egts.SrResultCode{
				ResultCode: resultCode,
			},
		},
	}
	if dispatcherID, err := resolveDispatcherID(dispatcherHost); err != nil {
		return nil, err
	} else if dispatcherID != 0 {
		rds = append(rds, egts.RecordData{
			SubrecordType:   egts.SrDispatcherIdentityType,
			SubrecordLength: uint16(5),
			SubrecordData: &egts.SrDispatcherIdentity{
				DispatcherType: 0,
				DispatcherID:   dispatcherID,
			},
		})
	}

	sfd := egts.ServiceDataSet{
		buildResponseRecord(egts.AuthService, rds),
	}
	respSection := egts.PtResponse{
		ResponsePacketID: pid,
		ProcessingResult: resultCode,
		SDR:              &sfd,
	}

	respPkg := egts.Package{
		ProtocolVersion:   1,
		SecurityKeyID:     0,
		Prefix:            "00",
		Route:             "0",
		EncryptionAlg:     "00",
		Compression:       "0",
		Priority:          "00",
		HeaderLength:      11,
		HeaderEncoding:    0,
		FrameDataLength:   respSection.Length(),
		PacketIdentifier:  pid + 1,
		PacketType:        egts.PtResponsePacket,
		ServicesFrameData: &respSection,
	}

	return respPkg.Encode()
}

func resolveDispatcherID(dispatcherHost string) (uint32, error) {
	dispatcherHost = strings.TrimSpace(dispatcherHost)
	if dispatcherHost == "" {
		return 0, nil
	}

	if ip := net.ParseIP(dispatcherHost); ip != nil {
		if ip4 := ip.To4(); ip4 != nil {
			return binary.LittleEndian.Uint32(ip4), nil
		}
		return 0, fmt.Errorf("dispatcher host %q resolved to non-ipv4 address", dispatcherHost)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	ips, err := net.DefaultResolver.LookupIP(ctx, "ip4", dispatcherHost)
	if err != nil {
		return 0, fmt.Errorf("resolve dispatcher host %q: %w", dispatcherHost, err)
	}
	for _, ip := range ips {
		if ip4 := ip.To4(); ip4 != nil {
			return binary.LittleEndian.Uint32(ip4), nil
		}
	}

	return 0, fmt.Errorf("dispatcher host %q has no ipv4 address", dispatcherHost)
}

func buildResponseRecord(serviceType uint8, recordDataSet egts.RecordDataSet) egts.ServiceDataRecord {
	return egts.ServiceDataRecord{
		RecordLength:             recordDataSet.Length(),
		RecordNumber:             1,
		SourceServiceOnDevice:    "0",
		RecipientServiceOnDevice: "1",
		Group:                    "0",
		RecordProcessingPriority: "00",
		TimeFieldExists:          "0",
		EventIDFieldExists:       "0",
		ObjectIDFieldExists:      "0",
		SourceServiceType:        serviceType,
		RecipientServiceType:     serviceType,
		RecordDataSet:            recordDataSet,
	}
}

func isClosedNetworkError(err error) bool {
	return err != nil && (err.Error() == "use of closed network connection" || fmt.Sprintf("%T", err) == "*net.OpError")
}
