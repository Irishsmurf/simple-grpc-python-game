package main

import (
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"simple-grpc-game/server/internal/game"
	"sync"
	"time"

	pb "simple-grpc-game/gen/go/game"

	"google.golang.org/grpc"
	// "google.golang.org/protobuf/proto" // May be needed if deep copying protos manually
)

type gameServer struct {
	pb.UnimplementedGameServiceServer
	state         *game.State
	muStreams     sync.Mutex
	activeStreams map[string]pb.GameService_GameStreamServer
}

const (
	movementTimeout = 200 * time.Millisecond
	tickRate        = 100 * time.Millisecond
)

func NewGameServer() (*gameServer, error) {
	gameState, err := game.NewState()
	if err != nil {
		return nil, fmt.Errorf("failed to initialize game state: %w", err)
	}
	return &gameServer{
		state:         gameState,
		activeStreams: make(map[string]pb.GameService_GameStreamServer),
	}, nil
}

// GameStream implements the bidirectional stream RPC
func (s *gameServer) GameStream(stream pb.GameService_GameStreamServer) error {
	log.Println("Player connecting...")
	playerID := fmt.Sprintf("player_%p", &stream) // TODO: Robust ID generation

	player := s.state.AddPlayer(playerID, 100, 100)
	log.Printf("Player %s joined game state.", player.GetId())
	s.addStream(playerID, stream)

	defer func() {
		log.Printf("Player %s disconnecting...", playerID)
		s.state.RemovePlayer(playerID)
		s.removeStream(playerID)
		log.Printf("Player %s removed.", playerID)
		// Broadcast removal after stream is closed
		s.broadcastDeltaState() // Let others know this player left
	}()

	// --- Send Initial Map Data ---
	mapGrid, mapW, mapH, tileSize, mapErr := s.state.GetMapDataAndDimensions()
	if mapErr != nil {
		log.Printf("Error getting map data for player %s: %v", playerID, mapErr)
		return mapErr
	}
	worldW, worldH := s.state.GetWorldPixelDimensions()
	initialMap := &pb.InitialMapData{ /* ... (populate as before) ... */
		TileWidth:        int32(mapW),
		TileHeight:       int32(mapH),
		Rows:             make([]*pb.MapRow, mapH),
		WorldPixelHeight: worldH,
		WorldPixelWidth:  worldW,
		TileSizePixels:   int32(tileSize),
		AssignedPlayerId: playerID,
	}
	for y, rowData := range mapGrid {
		rowTiles := make([]int32, mapW)
		for x, tileID := range rowData {
			if x < len(rowTiles) {
				rowTiles[x] = int32(tileID)
			} else {
				log.Printf("Warn: Map inconsistency row %d, col %d", y, x)
			}
		}
		if y < len(initialMap.Rows) {
			initialMap.Rows[y] = &pb.MapRow{Tiles: rowTiles}
		} else {
			log.Printf("Warn: Map inconsistency row %d", y)
		}
	}
	mapMessage := &pb.ServerMessage{Message: &pb.ServerMessage_InitialMapData{InitialMapData: initialMap}}
	log.Printf("Sending initial map to player %s", playerID)
	if err := stream.Send(mapMessage); err != nil {
		log.Printf("Error sending initial map to player %s: %v", playerID, err)
		return err
	}
	// --- End Send Initial Map Data ---

	// *** CHANGE: Send the *current full state* as the first delta update ***
	initialDelta := s.state.GetInitialStateDelta()
	if len(initialDelta.UpdatedPlayers) > 0 { // Only send if there are players
		initialStateMessage := &pb.ServerMessage{
			Message: &pb.ServerMessage_DeltaUpdate{DeltaUpdate: initialDelta},
		}
		log.Printf("Sending initial state delta (%d players) to player %s", len(initialDelta.UpdatedPlayers), playerID)
		if err := stream.Send(initialStateMessage); err != nil {
			log.Printf("Error sending initial state delta to player %s: %v", playerID, err)
			return err
		}
	}
	// *** End Send Initial State Delta ***

	// Let *other* players know about the new player (if any others exist)
	// This broadcast will now generate a delta including the new player.
	s.broadcastDeltaState()

	log.Printf("Player %s connected successfully. Total streams: %d", playerID, len(s.activeStreams))

	// --- Receive Loop ---
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			log.Printf("Player %s disconnected (EOF).", playerID)
			return nil
		}
		if err != nil {
			log.Printf("Error receiving input from player %s: %v", playerID, err)
			return err
		}

		_, ok := s.state.ApplyInput(playerID, req.Direction)
		if ok {
			// *** CHANGE: Broadcast delta after applying input ***
			s.broadcastDeltaState()
		} else {
			log.Printf("Failed to apply input for player %s (not found in state?)", playerID)
		}
	}
}

// addStream safely adds a client stream.
func (s *gameServer) addStream(playerID string, stream pb.GameService_GameStreamServer) { /* ... (no change) ... */
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	s.activeStreams[playerID] = stream
	log.Printf("Stream added for player %s. Total streams: %d", playerID, len(s.activeStreams))
}

// removeStream safely removes a client stream.
func (s *gameServer) removeStream(playerID string) { /* ... (no change) ... */
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	delete(s.activeStreams, playerID)
	log.Printf("Stream removed for player %s. Total streams: %d", playerID, len(s.activeStreams))
}

// *** RENAMED and CHANGED: broadcastDeltaState generates and sends delta updates ***
func (s *gameServer) broadcastDeltaState() {
	// Generate the delta update based on changes since last broadcast
	// This locks the state internally to compare and update the last snapshot
	delta, changed := s.state.GenerateDeltaUpdate()

	// Only proceed if there are actual changes to broadcast
	if !changed {
		// log.Println("broadcastDeltaState: No changes detected, skipping broadcast.") // Optional debug log
		return
	}

	// Lock the stream map only when we actually need to send
	s.muStreams.Lock()
	defer s.muStreams.Unlock()

	if len(s.activeStreams) == 0 {
		return // No clients connected
	}

	// Create the ServerMessage containing the delta
	deltaMessage := &pb.ServerMessage{
		Message: &pb.ServerMessage_DeltaUpdate{
			DeltaUpdate: delta,
		},
	}

	deadStreams := []string{} // Track streams that fail during send

	// log.Printf("Broadcasting delta: Updated=%d, Removed=%d", len(delta.UpdatedPlayers), len(delta.RemovedPlayerIds)) // Debug log

	for playerID, stream := range s.activeStreams {
		err := stream.Send(deltaMessage)
		if err != nil {
			log.Printf("Error sending delta state to player %s: %v. Marking stream for removal.", playerID, err)
			deadStreams = append(deadStreams, playerID)
		}
	}

	// Clean up dead streams
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during delta broadcast cleanup for player %s. Total streams: %d", playerID, len(s.activeStreams))
		// Note: Actual player state removal is handled by the GameStream defer func when the stream errors/closes.
	}
}

// gameTick performs periodic game logic updates.
func (s *gameServer) gameTick() {
	playerIds := s.state.GetAllPlayerIDs()
	stateChangedDuringTick := false

	for _, playerID := range playerIds {
		trackedPlayer, exists := s.state.GetTrackedPlayer(playerID)
		if !exists {
			continue
		}

		isMoving := trackedPlayer.LastDirection != pb.PlayerInput_UNKNOWN
		inputTimedOut := time.Since(trackedPlayer.LastInputTime) > movementTimeout

		if isMoving && inputTimedOut {
			updated := s.state.UpdatePlayerDirection(playerID, pb.PlayerInput_UNKNOWN)
			if updated {
				stateChangedDuringTick = true
			}
		}
	}

	// *** CHANGE: Broadcast delta state if tick logic caused changes ***
	if stateChangedDuringTick {
		s.broadcastDeltaState()
	}
}

func main() { /* ... (Flag parsing and server setup - no changes needed here from previous version) ... */
	ipFlag := flag.String("ip", "192.168.41.108", "IP address for the server to listen on")
	portFlag := flag.String("port", "50051", "Port for the server to listen on")
	flag.Parse()

	listenIP := *ipFlag
	listenPort := *portFlag

	listenAddress := net.JoinHostPort(listenIP, listenPort)
	lis, err := net.Listen("tcp", listenAddress)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", listenAddress, err)
	}

	grpcServer := grpc.NewServer()
	gServer, err := NewGameServer()
	if err != nil {
		log.Fatalf("Failed to create game server: %v", err)
	}
	pb.RegisterGameServiceServer(grpcServer, gServer)

	log.Printf("Starting game tick loop (Rate: %v)", tickRate)
	ticker := time.NewTicker(tickRate)
	defer ticker.Stop()
	go func() {
		for range ticker.C {
			gServer.gameTick()
		}
	}()

	log.Printf("Starting gRPC server on %s...", listenAddress)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC server: %v", err)
	}
}
