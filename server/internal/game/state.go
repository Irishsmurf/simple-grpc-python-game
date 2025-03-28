// Package game manages the core game state.
package game

import (
	"sync"

	// Assuming your module path allows this import based on previous steps
	pb "simple-grpc-game/gen/go/game" // Adjust if your module path is different!
)

// State manages the shared game state in a thread-safe manner.
type State struct {
	mu      sync.RWMutex // Read-write mutex for finer-grained locking (optional, Mutex is fine too)
	players map[string]*pb.Player
}

// NewState creates and initializes a new game state manager.
func NewState() *State {
	return &State{
		players: make(map[string]*pb.Player),
	}
}

// AddPlayer adds a new player to the game state.
// It returns the added player object.
func (s *State) AddPlayer(playerID string, startX, startY float32) *pb.Player {
	s.mu.Lock() // Use exclusive lock for writing
	defer s.mu.Unlock()

	player := &pb.Player{
		Id:   playerID,
		XPos: startX,
		YPos: startY,
	}
	s.players[playerID] = player
	return player
}

// RemovePlayer removes a player from the game state by ID.
func (s *State) RemovePlayer(playerID string) {
	s.mu.Lock() // Use exclusive lock for writing
	defer s.mu.Unlock()

	delete(s.players, playerID)
}

// UpdatePlayerPosition updates the position of an existing player.
// Returns true if the player was found and updated, false otherwise.
func (s *State) UpdatePlayerPosition(playerID string, newX, newY float32) bool {
	s.mu.Lock() // Use exclusive lock for writing
	defer s.mu.Unlock()

	player, exists := s.players[playerID]
	if !exists {
		return false
	}
	player.XPos = newX
	player.YPos = newY
	return true
}

// ApplyInput updates a player's position based on an input direction.
// Returns the updated player and true if successful, nil and false otherwise.
func (s *State) ApplyInput(playerID string, direction pb.PlayerInput_Direction) (*pb.Player, bool) {
	s.mu.Lock() // Use exclusive lock for writing
	defer s.mu.Unlock()

	player, exists := s.players[playerID]
	if !exists {
		return nil, false
	}

	moveSpeed := float32(5.0) // Example speed - could be configurable
	switch direction {
	case pb.PlayerInput_UP:
		player.YPos -= moveSpeed
	case pb.PlayerInput_DOWN:
		player.YPos += moveSpeed
	case pb.PlayerInput_LEFT:
		player.XPos -= moveSpeed
	case pb.PlayerInput_RIGHT:
		player.XPos += moveSpeed
	}

	// Return a copy to potentially avoid data races if used outside lock, though less critical here
	playerCopy := &pb.Player{
		Id:   player.Id,
		XPos: player.XPos,
		YPos: player.YPos,
	}

	return playerCopy, true
}

// GetPlayer retrieves a player's data by ID.
// Returns the player object and true if found, nil and false otherwise.
// Uses a read lock, allowing concurrent reads.
func (s *State) GetPlayer(playerID string) (*pb.Player, bool) {
	s.mu.RLock() // Use read lock for reading
	defer s.mu.RUnlock()

	player, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	// Return a copy to prevent modification of the internal map data via the pointer
	playerCopy := &pb.Player{
		Id:   player.Id,
		XPos: player.XPos,
		YPos: player.YPos,
	}
	return playerCopy, true
}

// GetAllPlayers returns a slice containing copies of all current players.
// Uses a read lock, allowing concurrent reads.
func (s *State) GetAllPlayers() []*pb.Player {
	s.mu.RLock() // Use read lock for reading
	defer s.mu.RUnlock()

	playerList := make([]*pb.Player, 0, len(s.players))
	for _, p := range s.players {
		// Create copies to prevent external modification of internal state
		playerCopy := &pb.Player{
			Id:   p.Id,
			XPos: p.XPos,
			YPos: p.YPos,
		}
		playerList = append(playerList, playerCopy)
	}
	return playerList
}
