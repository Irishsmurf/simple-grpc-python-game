// Package game manages the core game state.
package game

import (
	"log"
	"sync"
	"time"

	// Assuming your module path allows this import based on previous steps
	pb "simple-grpc-game/gen/go/game" // Adjust if your module path is different!
)

const (
	WorldMinX float32 = 0.0
	WorldMaxX float32 = 5000.0
	WorldMinY float32 = 0.0
	WorldMaxY float32 = 5000.0

	PlayerHalfWidth     float32 = 16.0
	PlayerRadius        float32 = 16.0
	MinPlayerSeperation float32 = PlayerRadius * 2.0

	TileSize      int = 32
	MapTileWidth  int = 25
	MapTileHeight int = 20
)

// State manages the shared game state in a thread-safe manner.
type State struct {
	mu      sync.RWMutex // Read-write mutex for finer-grained locking (optional, Mutex is fine too)
	players map[string]*trackedPlayer

	worldMap [][]int
}

type trackedPlayer struct {
	PlayerData    *pb.Player
	LastInputTime time.Time
	LastDirection pb.PlayerInput_Direction
}

// NewState creates and initializes a new game state manager.
func NewState() *State {

	tileMap := make([][]int, MapTileHeight)
	for y := range tileMap {
		tileMap[y] = make([]int, MapTileWidth)
		for x := range tileMap[y] {
			if x == 0 || x == MapTileWidth-1 || y == 0 || y == MapTileHeight-1 {
				tileMap[y][x] = 1 // Wall
			} else {
				tileMap[y][x] = 0 // Empty space
			}
		}
	}

	tileMap[5][5] = 1
	tileMap[5][6] = 1
	tileMap[5][7] = 1
	tileMap[6][7] = 1
	tileMap[7][7] = 1

	return &State{
		players:  make(map[string]*trackedPlayer),
		worldMap: tileMap,
	}
}

func (s *State) CheckPlayerCollision(playerID string, potentialX, potentialY float32) bool {
	for id, trackedPlayer := range s.players {
		if id == playerID {
			continue // Skip self
		}

		otherX := trackedPlayer.PlayerData.XPos
		otherY := trackedPlayer.PlayerData.YPos

		// Check distance between players
		dx := potentialX - otherX
		dy := potentialY - otherY

		distanceSquared := (dx * dx) + (dy * dy)
		if distanceSquared < MinPlayerSeperation*MinPlayerSeperation {
			log.Print("Collision detected between players: ", playerID, " and ", id)
			return true // Collision detected
		}
	}
	return false // No collision
}

func (s *State) CheckMapCollision(pixelX, pixelY float32) bool {
	// Basic collision check against world boundaries
	tileX := int(pixelX / float32(TileSize))
	tileY := int(pixelY / float32(TileSize))

	if tileX < 0 || tileX >= MapTileWidth || tileY < 0 || tileY >= MapTileHeight {
		return true // Out of bounds
	}
	if s.worldMap[tileY][tileX] == 1 {
		return true // Collision with wall
	}
	return false
}

// GetAllPlayerIDs returns a slice of current player IDs. Thread-safe.
func (s *State) GetAllPlayerIDs() []string {
	s.mu.RLock() // Read lock is sufficient
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.players))
	for id := range s.players {
		ids = append(ids, id)
	}
	return ids
}

func (s *State) GetTrackedPlayer(playerID string) (*trackedPlayer, bool) {
	s.mu.RLock() // Read lock
	defer s.mu.RUnlock()
	// Return pointer directly for efficiency in gameTick's checks.
	// Relies on gameTick not modifying the fields improperly.
	tp, exists := s.players[playerID]
	return tp, exists
}

func (s *State) UpdatePlayerDirection(playerID string, dir pb.PlayerInput_Direction) bool {
	s.mu.Lock() // Write lock needed
	defer s.mu.Unlock()
	tp, exists := s.players[playerID]
	if !exists {
		return false // Player might have disconnected
	}
	// Only update if the direction actually changes
	if tp.LastDirection != dir {
		tp.LastDirection = dir
		return true // Indicate that an update happened
	}
	return false // No change needed
}

// AddPlayer adds a new player to the game state.
// It returns the added player object.
func (s *State) AddPlayer(playerID string, startX, startY float32) *pb.Player {
	s.mu.Lock() // Use exclusive lock for writing
	defer s.mu.Unlock()

	playerData := &pb.Player{
		Id:   playerID,
		XPos: startX,
		YPos: startY,
	}

	tracked := &trackedPlayer{
		PlayerData:    playerData,
		LastInputTime: time.Now(),
		LastDirection: pb.PlayerInput_UNKNOWN,
	}

	s.players[playerID] = tracked
	return playerData
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
	player.PlayerData.XPos = newX
	player.PlayerData.YPos = newY
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

	player.LastInputTime = time.Now() // Update the last input time
	player.LastDirection = direction  // Update the last direction

	currentX := player.PlayerData.XPos
	currentY := player.PlayerData.YPos
	potentialX := currentX
	potentialY := currentY
	isMoving := false
	moveAttemptBlocked := false

	if direction != pb.PlayerInput_UNKNOWN {
		isMoving = true
		moveSpeed := float32(1.0) // Example speed - could be configurable
		switch direction {
		case pb.PlayerInput_UP:
			potentialY -= moveSpeed
		case pb.PlayerInput_DOWN:
			potentialY += moveSpeed
		case pb.PlayerInput_LEFT:
			potentialX -= moveSpeed
		case pb.PlayerInput_RIGHT:
			potentialX += moveSpeed
		}

		if potentialX < WorldMinX {
			potentialX = WorldMinX
		} else if potentialX > WorldMaxX {
			potentialX = WorldMaxX
		}

		collidesWithMap := s.CheckMapCollision(potentialX, potentialY)
		if collidesWithMap {
			log.Printf("Collision detected with map for player %s at (%f, %f)", playerID, potentialX, potentialY)
			moveAttemptBlocked = true
		}

		if !moveAttemptBlocked {
			collidesWithPlayer := s.CheckPlayerCollision(playerID, potentialX, potentialY)
			if collidesWithPlayer {
				log.Printf("Collision detected with player %s at (%f, %f)", playerID, potentialX, potentialY)
				moveAttemptBlocked = true
			}
		}

		if isMoving && !moveAttemptBlocked {
			player.PlayerData.XPos = potentialX
			player.PlayerData.YPos = potentialY
		}

		print("Player moved to: ", player.PlayerData.XPos, player.PlayerData.YPos)

	}

	// Return a copy to potentially avoid data races if used outside lock, though less critical here
	playerCopy := &pb.Player{
		Id:   player.PlayerData.Id,
		XPos: player.PlayerData.XPos,
		YPos: player.PlayerData.YPos,
	}

	return playerCopy, true
}

// GetPlayer retrieves a player's data by ID.
// Returns the player object and true if found, nil and false otherwise.
// Uses a read lock, allowing concurrent reads.
func (s *State) GetPlayer(playerID string) (*pb.Player, bool) {
	s.mu.RLock() // Use read lock for reading
	defer s.mu.RUnlock()

	trackedPlayer, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	// Return a copy to prevent modification of the internal map data via the pointer
	playerCopy := &pb.Player{
		Id:   trackedPlayer.PlayerData.Id,
		XPos: trackedPlayer.PlayerData.XPos,
		YPos: trackedPlayer.PlayerData.YPos,
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
			Id:   p.PlayerData.Id,
			XPos: p.PlayerData.XPos,
			YPos: p.PlayerData.YPos,
		}
		playerList = append(playerList, playerCopy)
	}
	return playerList
}
