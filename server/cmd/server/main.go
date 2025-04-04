package main

import (
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"simple-grpc-game/server/internal/game"
	"strings"
	"sync"
	"time"

	pb "simple-grpc-game/gen/go/game"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type gameServer struct {
	pb.UnimplementedGameServiceServer
	state         *game.State
	muStreams     sync.Mutex
	activeStreams map[string]pb.GameService_GameStreamServer
	playerInfo    sync.Map // Store playerID -> username mapping for chat
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
		playerInfo:    sync.Map{}, // Initialize the sync.Map
	}, nil
}

// GameStream implements the bidirectional stream RPC
func (s *gameServer) GameStream(stream pb.GameService_GameStreamServer) error {
	log.Println("Player connecting, waiting for ClientHello...")
	var playerID string
	var username string

	// Wait for ClientHello
	initialMsg, err := stream.Recv()
	if err != nil {
		if err == io.EOF {
			log.Println("Client disconnected before ClientHello.")
		} else {
			log.Printf("Error receiving initial message: %v", err)
		}
		return err // Return EOF or the actual error
	}
	helloMsg := initialMsg.GetClientHello()
	if helloMsg == nil {
		log.Println("Error: First message was not ClientHello.")
		return status.Errorf(codes.InvalidArgument, "ClientHello must be the first message")
	}

	username = helloMsg.GetDesiredUsername()
	if username == "" {
		username = "AnonPlayer"
	}
	playerID = fmt.Sprintf("player_%p", &stream) // TODO: Robust ID generation
	s.state.AddPlayer(playerID, username, 100, 100)
	s.playerInfo.Store(playerID, username) // Store username for chat lookup
	log.Printf("Received ClientHello: Player %s ('%s') joining.", playerID, username)
	s.addStream(playerID, stream)

	defer func() {
		log.Printf("Player %s ('%s') disconnecting...", playerID, username)
		s.state.RemovePlayer(playerID)
		s.removeStream(playerID)
		s.playerInfo.Delete(playerID) // Remove from username map
		log.Printf("Player %s removed.", playerID)
		s.broadcastDeltaState() // Let others know player left
	}()

	// Send Initial Map Data (unchanged)
	_, _, _, _, mapErr := s.state.GetMapDataAndDimensions()
	if mapErr != nil {
		log.Printf("Error getting map data for %s: %v", playerID, mapErr)
		return mapErr
	}
	// ... (rest of map sending logic as before) ...
	mapGrid, mapW, mapH, tileSize, _ := s.state.GetMapDataAndDimensions() // Error already checked
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
		log.Printf("Error sending initial map to %s: %v", playerID, err)
		return err
	}

	// Send Initial State Delta (unchanged)
	initialDelta := s.state.GetInitialStateDelta()
	if len(initialDelta.UpdatedPlayers) > 0 {
		initialStateMessage := &pb.ServerMessage{Message: &pb.ServerMessage_DeltaUpdate{DeltaUpdate: initialDelta}}
		log.Printf("Sending initial state delta (%d players) to player %s ('%s')", len(initialDelta.UpdatedPlayers), playerID, username)
		if err := stream.Send(initialStateMessage); err != nil {
			log.Printf("Error sending initial state delta to %s: %v", playerID, err)
			return err
		}
	}

	// Let other players know about the new player
	s.broadcastDeltaState()
	log.Printf("Player %s ('%s') connected successfully. Total streams: %d", playerID, username, len(s.activeStreams))

	// --- Receive Loop ---
	for {
		clientMsg, err := stream.Recv()
		if err != nil { // Handle EOF and other errors
			if err == io.EOF {
				log.Printf("Player %s ('%s') disconnected (EOF).", playerID, username)
			} else {
				log.Printf("Error receiving from %s ('%s'): %v", playerID, username, err)
			}
			return err // Return error (or nil for EOF) to trigger defer
		}

		// Process based on ClientMessage type
		if playerInputMsg := clientMsg.GetPlayerInput(); playerInputMsg != nil {
			_, ok := s.state.ApplyInput(playerID, playerInputMsg.Direction)
			if ok {
				s.broadcastDeltaState() // Broadcast movement/state changes
			} else {
				log.Printf("Failed input for %s ('%s')", playerID, username)
			}
		} else if chatReq := clientMsg.GetSendChatMessage(); chatReq != nil {
			// *** ADDED: Handle incoming chat message ***
			chatText := strings.TrimSpace(chatReq.GetMessageText())
			// Basic validation (e.g., non-empty, length limit)
			if chatText != "" && len(chatText) < 200 { // Limit chat message length
				// Retrieve sender's username (should exist)
				senderUsername := username // Use username established at connection
				log.Printf("Chat from %s ('%s'): %s", playerID, senderUsername, chatText)
				// Broadcast the chat message to everyone
				s.broadcastChatMessage(senderUsername, chatText)
			} else {
				log.Printf("Player %s ('%s') sent invalid chat message (empty or too long).", playerID, username)
			}
		} else if clientMsg.GetClientHello() != nil {
			log.Printf("Warning: Player %s ('%s') sent unexpected ClientHello.", playerID, username)
		} else {
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
			log.Printf("Error sending delta to %s: %v. Marking.", playerID, err)
			deadStreams = append(deadStreams, playerID)
		}
	}
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during delta broadcast for %s. Total: %d", playerID, len(s.activeStreams))
	}
}

// *** NEW: Function to broadcast chat messages ***
func (s *gameServer) broadcastChatMessage(senderUsername, messageText string) {
	s.muStreams.Lock() // Lock stream map for iteration
	defer s.muStreams.Unlock()

	if len(s.activeStreams) == 0 {
		return // No one to send to
	}

	chatMsgProto := &pb.ChatMessage{
		SenderUsername: senderUsername,
		MessageText:    messageText,
	}
	serverMsg := &pb.ServerMessage{
		Message: &pb.ServerMessage_ChatMessage{ChatMessage: chatMsgProto},
	}

	deadStreams := []string{}
	for playerID, stream := range s.activeStreams {
		err := stream.Send(serverMsg)
		if err != nil {
			log.Printf("Error sending chat message to player %s: %v. Marking stream.", playerID, err)
			deadStreams = append(deadStreams, playerID)
		}
	}

	// Clean up dead streams
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during chat broadcast for player %s. Total streams: %d", playerID, len(s.activeStreams))
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
	ipFlag := flag.String("ip", "192.168.41.108", "IP address")
	portFlag := flag.String("port", "50051", "Port")
	flag.Parse()
	listenIP := *ipFlag
	listenPort := *portFlag
	listenAddress := net.JoinHostPort(listenIP, listenPort)
	lis, err := net.Listen("tcp", listenAddress)
	if err != nil {
		log.Fatalf("Listen failed: %v", err)
	}
	grpcServer := grpc.NewServer()
	gServer, err := NewGameServer()
	if err != nil {
		log.Fatalf("Server creation failed: %v", err)
	}
	pb.RegisterGameServiceServer(grpcServer, gServer)
	log.Printf("Starting tick loop (Rate: %v)", tickRate)
	ticker := time.NewTicker(tickRate)
	defer ticker.Stop()
	go func() {
		for range ticker.C {
			gServer.gameTick()
		}
	}()
	log.Printf("Starting gRPC server on %s...", listenAddress)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Serve failed: %v", err)
	}
}
