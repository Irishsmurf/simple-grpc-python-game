package main

import (
	// Need context for stream operations
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
	"google.golang.org/grpc/codes"  // Added
	"google.golang.org/grpc/status" // Added
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
	return &gameServer{state: gameState, activeStreams: make(map[string]pb.GameService_GameStreamServer)}, nil
}

// GameStream implements the bidirectional stream RPC
func (s *gameServer) GameStream(stream pb.GameService_GameStreamServer) error {
	log.Println("Player connecting, waiting for ClientHello...")

	// *** CHANGE: Expect ClientHello as the first message ***
	var playerID string // Server-assigned ID
	var username string

	// Wait for the first message, which must be ClientHello
	initialMsg, err := stream.Recv()
	if err == io.EOF {
		log.Println("Client disconnected before sending ClientHello.")
		return nil
	}
	if err != nil {
		log.Printf("Error receiving initial message: %v", err)
		return err
	}

	// Check if the first message is actually ClientHello
	helloMsg := initialMsg.GetClientHello()
	if helloMsg == nil {
		log.Println("Error: First message from client was not ClientHello.")
		return status.Errorf(codes.InvalidArgument, "ClientHello must be the first message")
	}

	username = helloMsg.GetDesiredUsername()
	if username == "" {
		username = "AnonPlayer" // Default username if client sends empty
	}
	// TODO: Add username validation/uniqueness check here if desired

	// Generate player ID (still temporary) and add player to state
	playerID = fmt.Sprintf("player_%p", &stream)              // TODO: Robust ID generation
	player := s.state.AddPlayer(playerID, username, 100, 100) // Pass username
	log.Printf("Received ClientHello: Player %s ('%s') joining.", player.Id, username)

	// Add the client's stream to our map *after* successful hello
	s.addStream(playerID, stream)

	// Ensure player and stream are removed on disconnect/error
	defer func() {
		log.Printf("Player %s ('%s') disconnecting...", playerID, username)
		s.state.RemovePlayer(playerID)
		s.removeStream(playerID)
		log.Printf("Player %s removed.", playerID)
		s.broadcastDeltaState() // Let others know this player left
	}()

	// --- Send Initial Map Data ---
	// (No changes needed in map sending logic itself)
	mapGrid, mapW, mapH, tileSize, mapErr := s.state.GetMapDataAndDimensions()
	if mapErr != nil {
		log.Printf("Error getting map data for player %s: %v", playerID, mapErr)
		return mapErr
	}
	worldW, worldH := s.state.GetWorldPixelDimensions()
	initialMap := &pb.InitialMapData{TileWidth: int32(mapW), TileHeight: int32(mapH), Rows: make([]*pb.MapRow, mapH), WorldPixelHeight: worldH, WorldPixelWidth: worldW, TileSizePixels: int32(tileSize), AssignedPlayerId: playerID}
	for y, rowData := range mapGrid {
		rowTiles := make([]int32, mapW)
		for x, tileID := range rowData {
			if x < len(rowTiles) {
				rowTiles[x] = int32(tileID)
			}
		}
		if y < len(initialMap.Rows) {
			initialMap.Rows[y] = &pb.MapRow{Tiles: rowTiles}
		}
	}
	mapMessage := &pb.ServerMessage{Message: &pb.ServerMessage_InitialMapData{InitialMapData: initialMap}}
	log.Printf("Sending initial map to player %s ('%s')", playerID, username)
	if err := stream.Send(mapMessage); err != nil {
		log.Printf("Error sending initial map to player %s: %v", playerID, err)
		return err
	}
	// --- End Send Initial Map Data ---

	// --- Send Initial State Delta ---
	initialDelta := s.state.GetInitialStateDelta()
	// Send initial state only if there are players (including the new one)
	if len(initialDelta.UpdatedPlayers) > 0 {
		initialStateMessage := &pb.ServerMessage{Message: &pb.ServerMessage_DeltaUpdate{DeltaUpdate: initialDelta}}
		log.Printf("Sending initial state delta (%d players) to player %s ('%s')", len(initialDelta.UpdatedPlayers), playerID, username)
		if err := stream.Send(initialStateMessage); err != nil {
			log.Printf("Error sending initial state delta to player %s: %v", playerID, err)
			return err
		}
	}
	// --- End Send Initial State Delta ---

	// Let *other* players know about the new player immediately after initial state sent to new player
	s.broadcastDeltaState()

	log.Printf("Player %s ('%s') connected successfully. Total streams: %d", playerID, username, len(s.activeStreams))

	// --- Receive Loop (Handles PlayerInput now) ---
	for {
		// *** CHANGE: Expect ClientMessage wrapper ***
		clientMsg, err := stream.Recv()
		if err == io.EOF {
			log.Printf("Player %s ('%s') disconnected (EOF).", playerID, username)
			return nil
		}
		if err != nil {
			log.Printf("Error receiving message from player %s ('%s'): %v", playerID, username, err)
			return err
		}

		// *** CHANGE: Process PlayerInput from the wrapper ***
		playerInputMsg := clientMsg.GetPlayerInput()
		if playerInputMsg != nil {
			// Apply the received input to the game state
			_, ok := s.state.ApplyInput(playerID, playerInputMsg.Direction)
			if ok {
				// If input was applied successfully, broadcast the delta state
				s.broadcastDeltaState()
			} else {
				log.Printf("Failed to apply input for player %s ('%s') (not found in state?)", playerID, username)
			}
		} else if clientMsg.GetClientHello() != nil {
			// Client sent another ClientHello after the first one - ignore or treat as error
			log.Printf("Warning: Player %s ('%s') sent unexpected ClientHello message.", playerID, username)
			// Optionally disconnect: return status.Errorf(codes.InvalidArgument, "Cannot send ClientHello more than once")
		} else {
			// Unknown message type within the oneof
			log.Printf("Warning: Player %s ('%s') sent unknown message type.", playerID, username)
		}
	}
}

func (s *gameServer) addStream(playerID string, stream pb.GameService_GameStreamServer) {
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	s.activeStreams[playerID] = stream
	log.Printf("Stream added for player %s. Total streams: %d", playerID, len(s.activeStreams))
}
func (s *gameServer) removeStream(playerID string) {
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	delete(s.activeStreams, playerID)
	log.Printf("Stream removed for player %s. Total streams: %d", playerID, len(s.activeStreams))
}
func (s *gameServer) broadcastDeltaState() { /* ... (no change needed here) ... */
	delta, changed := s.state.GenerateDeltaUpdate()
	if !changed {
		return
	}
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	if len(s.activeStreams) == 0 {
		return
	}
	deltaMessage := &pb.ServerMessage{Message: &pb.ServerMessage_DeltaUpdate{DeltaUpdate: delta}}
	deadStreams := []string{}
	for playerID, stream := range s.activeStreams {
		err := stream.Send(deltaMessage)
		if err != nil {
			log.Printf("Error sending delta to player %s: %v. Marking.", playerID, err)
			deadStreams = append(deadStreams, playerID)
		}
	}
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during delta broadcast for player %s. Total: %d", playerID, len(s.activeStreams))
	}
}
func (s *gameServer) gameTick() { /* ... (no change needed here) ... */
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
	if stateChangedDuringTick {
		s.broadcastDeltaState()
	}
}

func main() { /* ... (no change needed here) ... */
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
