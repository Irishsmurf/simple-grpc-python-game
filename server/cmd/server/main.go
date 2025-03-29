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
)

// NewGameServer creates an instance of our game server
func NewGameServer() *gameServer {
	return &gameServer{
		state:         game.NewState(),                                  // Initialize the state manager
		activeStreams: make(map[string]pb.GameService_GameStreamServer), // Initialize the stream map
	}
}

// GameStream implements the bidirectional stream RPC
// This is the core method where clients connect and interact
func (s *gameServer) GameStream(stream pb.GameService_GameStreamServer) error {
	log.Println("Player connecting...")          // Changed log message slightly
	playerID := fmt.Sprintf("player_%p", stream) // Still temporary ID! Needs fixing.

	player := s.state.AddPlayer(playerID, 100, 100)
	log.Printf("Player %s joined game state.", player.GetId())
	s.addStream(playerID, stream) // Add the stream to the active streams map

	defer func() {
		log.Printf("Player %s disconnecting...", playerID)
		s.state.RemovePlayer(playerID) // Remove player from state manager
		s.removeStream(playerID)       // Remove the stream from the active streams map
		log.Printf("Player %s removed from active streams.", playerID)
		s.broadcastState() // Broadcast the updated state to all remaining players
	}()

	mapGrid, mapW, mapH, mapErr := s.state.GetMapDataAndDimensions()
	if mapErr != nil {
		log.Printf("Error loading map for %s: %v", playerID, mapErr)
		return mapErr
	}

	initialMap := &pb.InitialMapData{
		TileWidth:  int32(mapW),
		TileHeight: int32(mapH),
		Rows:       make([]*pb.MapRow, mapH),
	}

	for y, rowData := range mapGrid {
		rowTiles := make([]int32, mapW)
		for x, tileID := range rowData {
			rowTiles[x] = int32(tileID)
		}
		initialMap.Rows[y] = &pb.MapRow{Tiles: rowTiles}
	}

	mapMessage := &pb.ServerMessage{
		Message: &pb.ServerMessage_InitialMapData{
			InitialMapData: initialMap,
		},
	}
	log.Printf("Sending initial map to player %s: %v", playerID, mapMessage)
	if err := stream.Send(mapMessage); err != nil {
		log.Printf("Error sending initial map to player %s: %v", playerID, err)
		return err
	}

	log.Printf("Player %s connected. Total streams: %d", playerID, len(s.activeStreams))
	s.broadcastState() // Broadcast the initial state to all players

	for {
		req, err := stream.Recv()
		if err == io.EOF {
			log.Printf("Player %s disconnected (EOF).", playerID)
			return nil // Exit if EOF
		}
		if err != nil {
			log.Printf("Error receiving from player %s: %v", playerID, err)
			return err // Exit if error
		}

		updatedPlayer, ok := s.state.ApplyInput(playerID, req.Direction)
		if ok {
			log.Printf("Player %s moved to (%f, %f)", playerID, updatedPlayer.XPos, updatedPlayer.YPos)
			s.broadcastState()
		} else {
			log.Printf("Failed to apply input for player %s (not found?)", playerID)
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

func (s *gameServer) broadcastState() {
	s.muStreams.Lock() // Lock the stream map for reading/potential modification
	defer s.muStreams.Unlock()

	if len(s.activeStreams) == 0 {
		return // No one to broadcast to
	}

	// Get the current state ONCE - reading from game.State is thread-safe via its own mutexes
	allPlayers := s.state.GetAllPlayers()
	currentState := &pb.GameState{Players: allPlayers}

	stateMessage := &pb.ServerMessage{
		Message: &pb.ServerMessage_GameState{
			GameState: currentState,
		},
	}

	// Iterate over a copy of the keys to avoid issues if removeStream is called concurrently?
	// Or handle errors carefully inside the loop. Let's handle errors carefully.
	deadStreams := []string{} // Keep track of streams that error out

	for playerID, stream := range s.activeStreams {
		err := stream.Send(stateMessage)
		if err != nil {
			log.Printf("Error sending state to player %s: %v. Marking stream for removal.", playerID, err)
			// Don't modify the map while iterating over it. Mark for removal.
			deadStreams = append(deadStreams, playerID)
		}
	}

	// Remove dead streams after iteration (still under the lock)
	for _, playerID := range deadStreams {
		delete(s.activeStreams, playerID)
		log.Printf("Dead stream removed during broadcast cleanup for player %s. Total streams: %d", playerID, len(s.activeStreams))
	}
}

func (s *gameServer) gameTick() {
	playerIds := s.state.GetAllPlayerIDs()
	stateChangedSinceLastTick := false
	for _, playerID := range playerIds {
		trackedPlayer, exists := s.state.GetTrackedPlayer(playerID)
		if !exists {
			log.Printf("Player %s not found in state during game tick.", playerID)
			continue
		}
		// Check if the player has moved since the last tick

		isMoving := trackedPlayer.LastDirection != pb.PlayerInput_UNKNOWN
		timeout := time.Since(trackedPlayer.LastInputTime) > movementTimeout
		if isMoving && timeout {
			updated := s.state.UpdatePlayerDirection(playerID, pb.PlayerInput_UNKNOWN)
			if updated {
				log.Printf("Player %s input timed out. Direction reset to UNKNOWN.", trackedPlayer.PlayerData.Id)
				stateChangedSinceLastTick = true
			}
		}
	}

	if stateChangedSinceLastTick {
		log.Println("Game state changed during tick. Broadcasting updated state.")
		s.broadcastState()
	} else {
		s.broadcastState()
	}
}

func main() {
	port := ":50051" // Port for the gRPC server to listen on
	lis, err := net.Listen("tcp", port)
	if err != nil {
		log.Fatalf("Failed to listen on port %s: %v", port, err)
	}

	// Create a new gRPC server instance
	grpcServer := grpc.NewServer()

	// Create an instance of our game server implementation
	gServer := NewGameServer()

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

	log.Printf("Starting gRPC server on %s", port)
	// Start listening for incoming connections
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC server: %v", err)
	}
}
