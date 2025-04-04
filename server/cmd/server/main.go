package main

import (
	// Add context import
	"fmt" // Needed for reading from stream
	"io"
	"log"
	"net"
	"sync"
	"time"

	// Needed for basic state management later
	"simple-grpc-game/server/internal/game"

	// Import the generated gRPC code
	// The path is based on our go.mod path + the gen/go/game structure
	pb "simple-grpc-game/gen/go/game"

	"google.golang.org/grpc"
)

type gameServer struct {
	pb.UnimplementedGameServiceServer
	state         *game.State                                // Use the state manager from internal/game
	muStreams     sync.Mutex                                 // Mutex to protect the activeStreams map
	activeStreams map[string]pb.GameService_GameStreamServer // Map playerID to their stream
}

const (
	movementTimeout = 200 * time.Millisecond // Time between game ticks
	tickRate        = 100 * time.Millisecond
	// TileSize, worldPixelW, worldPixelH are now primarily managed within the game state based on the map
)

// NewGameServer creates an instance of our game server.
// It now returns an error if state initialization fails.
func NewGameServer() (*gameServer, error) {
	// Initialize the state manager, handling potential errors
	gameState, err := game.NewState()
	if err != nil {
		return nil, fmt.Errorf("failed to initialize game state: %w", err)
	}

	return &gameServer{
		state:         gameState,
		activeStreams: make(map[string]pb.GameService_GameStreamServer), // Initialize the stream map
	}, nil
}

// GameStream implements the bidirectional stream RPC
// This is the core method where clients connect and interact
func (s *gameServer) GameStream(stream pb.GameService_GameStreamServer) error {
	log.Println("Player connecting...")
	// TODO: Implement a more robust player ID generation/assignment mechanism
	// Using the stream pointer address is temporary and not suitable for production.
	playerID := fmt.Sprintf("player_%p", &stream)

	// Add player to the game state
	// Use default start position for now, could be configurable or based on map spawn points
	player := s.state.AddPlayer(playerID, 100, 100)
	log.Printf("Player %s joined game state.", player.GetId())

	// Add the client's stream to our map of active streams
	s.addStream(playerID, stream)

	// Ensure player and stream are removed on disconnect/error
	defer func() {
		log.Printf("Player %s disconnecting...", playerID)
		s.state.RemovePlayer(playerID) // Remove player from state manager
		s.removeStream(playerID)       // Remove the stream from the active streams map
		log.Printf("Player %s removed.", playerID)
		s.broadcastState() // Broadcast the updated state (player left)
	}()

	// --- Send Initial Map Data ---
	mapGrid, mapW, mapH, tileSize, mapErr := s.state.GetMapDataAndDimensions()
	if mapErr != nil {
		log.Printf("Error getting map data for player %s: %v", playerID, mapErr)
		return mapErr // Disconnect client if map data isn't available
	}
	worldW, worldH := s.state.GetWorldPixelDimensions()

	initialMap := &pb.InitialMapData{
		TileWidth:        int32(mapW),
		TileHeight:       int32(mapH),
		Rows:             make([]*pb.MapRow, mapH),
		WorldPixelHeight: worldH,
		WorldPixelWidth:  worldW,
		TileSizePixels:   int32(tileSize),
		AssignedPlayerId: playerID,
	}

	// Convert the internal TileType map to the protobuf format
	for y, rowData := range mapGrid {
		// Ensure rowTiles has the correct capacity based on mapWidth
		rowTiles := make([]int32, mapW)
		for x, tileID := range rowData {
			if x < len(rowTiles) { // Bounds check for safety
				rowTiles[x] = int32(tileID)
			} else {
				log.Printf("Warning: Map data inconsistency for row %d, index %d out of bounds (width %d)", y, x, mapW)
			}
		}
		if y < len(initialMap.Rows) { // Bounds check for safety
			initialMap.Rows[y] = &pb.MapRow{Tiles: rowTiles}
		} else {
			log.Printf("Warning: Map data inconsistency, row index %d out of bounds (height %d)", y, mapH)
		}
	}

	mapMessage := &pb.ServerMessage{
		Message: &pb.ServerMessage_InitialMapData{
			InitialMapData: initialMap,
		},
	}
	log.Printf("Sending initial map to player %s", playerID)
	if err := stream.Send(mapMessage); err != nil {
		log.Printf("Error sending initial map to player %s: %v", playerID, err)
		return err // Disconnect if initial send fails
	}
	// --- End Send Initial Map Data ---

	log.Printf("Player %s connected successfully. Total streams: %d", playerID, len(s.activeStreams))
	s.broadcastState() // Broadcast the state including the new player

	// --- Receive Loop ---
	// Continuously listen for input messages from this client
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			// Client closed the stream cleanly
			log.Printf("Player %s disconnected (EOF).", playerID)
			return nil // Exit the handler for this client
		}
		if err != nil {
			// An error occurred reading from the stream
			log.Printf("Error receiving input from player %s: %v", playerID, err)
			return err // Exit the handler, triggering the defer cleanup
		}

		// Apply the received input to the game state
		_, ok := s.state.ApplyInput(playerID, req.Direction)
		if ok {
			// If input was applied successfully, broadcast the new state
			s.broadcastState()
		} else {
			// This might happen if the player was removed between Recv and ApplyInput (rare)
			log.Printf("Failed to apply input for player %s (not found in state?)", playerID)
			// Optionally return an error or just log
			// return fmt.Errorf("player %s not found during input processing", playerID)
		}
	}
}

// addStream safely adds a client stream to the map.
func (s *gameServer) addStream(playerID string, stream pb.GameService_GameStreamServer) {
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	s.activeStreams[playerID] = stream
	log.Printf("Stream added for player %s. Total streams: %d", playerID, len(s.activeStreams))
}

// removeStream safely removes a client stream from the map.
func (s *gameServer) removeStream(playerID string) {
	s.muStreams.Lock()
	defer s.muStreams.Unlock()
	delete(s.activeStreams, playerID)
	log.Printf("Stream removed for player %s. Total streams: %d", playerID, len(s.activeStreams))
}

// broadcastState sends the current game state to all connected clients.
func (s *gameServer) broadcastState() {
	s.muStreams.Lock() // Lock the stream map while iterating and sending
	defer s.muStreams.Unlock()

	if len(s.activeStreams) == 0 {
		return // No clients connected
	}

	// Get the current state ONCE - reading from game.State is thread-safe via its own mutexes
	allPlayers := s.state.GetAllPlayers()
	currentState := &pb.GameState{Players: allPlayers}

	stateMessage := &pb.ServerMessage{
		Message: &pb.ServerMessage_GameState{
			GameState: currentState,
		},
	}

	deadStreams := []string{} // Keep track of streams that error out during send

	for playerID, stream := range s.activeStreams {
		err := stream.Send(stateMessage)
		if err != nil {
			log.Printf("Error sending state to player %s: %v. Marking stream for removal.", playerID, err)
			// Don't modify the map while iterating. Mark for removal.
			deadStreams = append(deadStreams, playerID)
			// Also remove the player from the game state if their stream is dead
			// Do this outside the broadcast lock if possible, or carefully here.
			// Let's defer state removal until after the loop.
		}
	}

	// Remove dead streams after iteration (still under the muStreams lock)
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during broadcast cleanup for player %s. Total streams: %d", playerID, len(s.activeStreams))
		// Now remove from game state as well (needs separate lock or careful handling)
		// Since we are cleaning up *after* a broadcast, removing here is okay,
		// but ideally, the disconnect logic in GameStream's defer handles state removal.
		// Let's rely on the defer in GameStream for state removal for now.
		// s.state.RemovePlayer(playerID) // Potentially redundant if GameStream defer runs
	}
}

// gameTick performs periodic game logic updates (like input timeouts).
func (s *gameServer) gameTick() {
	// Get all player IDs first (uses RLock internally)
	playerIds := s.state.GetAllPlayerIDs()
	stateChangedSinceLastTick := false

	for _, playerID := range playerIds {
		// Get the tracked player info (uses RLock internally)
		trackedPlayer, exists := s.state.GetTrackedPlayer(playerID)
		if !exists {
			// Player might have disconnected between GetAllPlayerIDs and GetTrackedPlayer
			// log.Printf("Player %s not found in state during game tick.", playerID)
			continue
		}

		// Check if the player's input should time out
		isMoving := trackedPlayer.LastDirection != pb.PlayerInput_UNKNOWN
		inputTimedOut := time.Since(trackedPlayer.LastInputTime) > movementTimeout

		if isMoving && inputTimedOut {
			// Reset direction if input timed out (uses Lock internally)
			updated := s.state.UpdatePlayerDirection(playerID, pb.PlayerInput_UNKNOWN)
			if updated {
				// log.Printf("Player %s input timed out. Direction reset to UNKNOWN.", trackedPlayer.PlayerData.Id)
				stateChangedSinceLastTick = true
			}
		}
	}

	// Broadcast state only if something changed due to the tick (like timeout)
	// Or broadcast periodically anyway? Let's broadcast always for simplicity now.
	if stateChangedSinceLastTick {
		log.Println("Game state changed during tick. Broadcasting updated state.")
		s.broadcastState()
	}
}

func main() {
	// TODO: Make IP/Port configurable (e.g., flags, env vars)
	listenIP := "0.0.0.0" // Listen on all interfaces
	listenPort := "50051" // Port for the gRPC server to listen on

	listenAddress := net.JoinHostPort(listenIP, listenPort)
	lis, err := net.Listen("tcp", listenAddress)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", listenAddress, err)
	}

	// Create a new gRPC server instance
	grpcServer := grpc.NewServer()

	// Create an instance of our game server implementation
	// *** CHANGE: Handle potential error from NewGameServer ***
	gServer, err := NewGameServer()
	if err != nil {
		log.Fatalf("Failed to create game server: %v", err)
	}

	// Register the game server implementation with the gRPC server
	pb.RegisterGameServiceServer(grpcServer, gServer)

	// --- Start the Game Tick Loop ---
	log.Printf("Starting game tick loop (Rate: %v)", tickRate)
	ticker := time.NewTicker(tickRate)
	defer ticker.Stop() // Ensure ticker is stopped if main exits

	go func() { // Run the ticker checking in a separate goroutine
		for range ticker.C { // This loop executes every tick
			gServer.gameTick() // Call the game logic function
		}
	}()
	// --- End Game Tick Loop ---

	log.Printf("Starting gRPC server on %s...", listenAddress)
	// Start listening for incoming connections
	if err := grpcServer.Serve(lis); err != nil {
		// Log fatal error if server fails to start
		log.Fatalf("Failed to serve gRPC server: %v", err)
	}
}
