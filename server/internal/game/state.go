// Package game manages the core game state for the gRPC server.
package game

import (
	"bufio"
	"fmt"
	"log" // Go 1.21+ needed for maps.Clone
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	// Adjust the import path based on your Go module setup
	pb "simple-grpc-game/gen/go/game"

	"google.golang.org/protobuf/proto" // Needed for cloning protobuf messages
)

// --- Constants ---
const (
	PlayerHalfWidth  float32 = 64.0
	PlayerHalfHeight float32 = 64.0
	PlayerMoveSpeed  float32 = 16.0
	DefaultTileSize  int     = 32
	MapFilePath      string  = "map.txt"
	movementTimeout          = 200 * time.Millisecond
)

type TileType int32

const (
	TileTypeEmpty TileType = 0
	TileTypeWall  TileType = 1
)

func (t TileType) String() string { return "" } // Keep String method

// trackedPlayer holds the game state data for a player along with server-side tracking info.
type trackedPlayer struct {
	PlayerData    *pb.Player               // Protobuf representation sent to clients
	LastInputTime time.Time                // Timestamp of the last received input
	LastDirection pb.PlayerInput_Direction // Last movement direction received
}

// State manages the shared game state in a thread-safe manner.
type State struct {
	mu sync.RWMutex // Protects players map and lastBroadcastPlayers

	players map[string]*trackedPlayer // Current state of all players

	// World map data (loaded once)
	worldMap      [][]TileType
	mapTileWidth  int
	mapTileHeight int
	tileSize      int

	// Calculated world boundaries
	worldMinX float32
	worldMaxX float32
	worldMinY float32
	worldMaxY float32

	// State tracking for delta updates
	// Protected by the main 'mu' RWMutex
	lastBroadcastPlayers map[string]*pb.Player // Snapshot of player data from last broadcast
}

// loadMapFromFile reads a map definition from a text file. (No changes needed)
func loadMapFromFile(filePath string) ([][]TileType, int, int, error) {
	// ... (implementation from previous version) ...
	file, err := os.Open(filePath)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("failed to open map file '%s': %w", filePath, err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	var tileMap [][]TileType
	width := -1 // Initialize width as unknown

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue // Skip empty lines
		}

		parts := strings.Fields(line)
		currentWidth := len(parts)

		if width == -1 {
			width = currentWidth
		} else if currentWidth != width {
			return nil, 0, 0, fmt.Errorf("inconsistent row length in map file (expected %d, got %d)", width, currentWidth)
		}

		if width == 0 {
			return nil, 0, 0, fmt.Errorf("map row has zero width")
		}

		row := make([]TileType, width)
		for i, part := range parts {
			tileInt, err := strconv.Atoi(part)
			if err != nil {
				return nil, 0, 0, fmt.Errorf("invalid non-integer tile ID '%s' in map file: %w", part, err)
			}

			tileID := TileType(tileInt)
			if tileID != TileTypeEmpty && tileID != TileTypeWall {
				log.Printf("Warning: Invalid tile ID %d found in map file at row %d, col %d. Treating as Empty.", tileID, len(tileMap), i)
				tileID = TileTypeEmpty
			}
			row[i] = tileID
		}
		tileMap = append(tileMap, row)
	}

	if err := scanner.Err(); err != nil {
		return nil, 0, 0, fmt.Errorf("error reading map file '%s': %w", filePath, err)
	}

	if len(tileMap) == 0 || width <= 0 {
		return nil, 0, 0, fmt.Errorf("map file '%s' is empty or invalid", filePath)
	}

	height := len(tileMap)
	log.Printf("Loaded map from '%s', dimensions: %d x %d tiles.", filePath, width, height)
	return tileMap, width, height, nil
}

// NewState creates and initializes a new game state manager.
func NewState() (*State, error) {
	loadedMap, width, height, err := loadMapFromFile(MapFilePath)
	if err != nil {
		return nil, fmt.Errorf("error loading map: %w", err)
	}

	tileSize := DefaultTileSize
	worldPixelWidth := float32(width * tileSize)
	worldPixelHeight := float32(height * tileSize)

	newState := &State{
		players:              make(map[string]*trackedPlayer),
		worldMap:             loadedMap,
		mapTileWidth:         width,
		mapTileHeight:        height,
		tileSize:             tileSize,
		worldMinX:            0.0,
		worldMaxX:            worldPixelWidth,
		worldMinY:            0.0,
		worldMaxY:            worldPixelHeight,
		lastBroadcastPlayers: make(map[string]*pb.Player), // Initialize the map for delta tracking
	}

	log.Printf("Game state initialized. World boundaries: X(%.1f, %.1f), Y(%.1f, %.1f)",
		newState.worldMinX, newState.worldMaxX, newState.worldMinY, newState.worldMaxY)

	return newState, nil
}

// --- Player Management (AddPlayer, RemovePlayer - Minor changes for delta tracking) ---

// AddPlayer adds a new player. Returns the created Player object. Thread-safe.
func (s *State) AddPlayer(playerID string, startX, startY float32) *pb.Player {
	s.mu.Lock()
	defer s.mu.Unlock()

	startX = clamp(startX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
	startY = clamp(startY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)

	playerData := &pb.Player{
		Id:                    playerID,
		XPos:                  startX,
		YPos:                  startY,
		CurrentAnimationState: pb.AnimationState_IDLE,
	}

	tracked := &trackedPlayer{
		PlayerData:    playerData,
		LastInputTime: time.Now(),
		LastDirection: pb.PlayerInput_UNKNOWN,
	}
	s.players[playerID] = tracked

	// NOTE: We don't add to lastBroadcastPlayers here.
	// The GenerateDeltaUpdate function will detect this as a new player
	// the next time it runs and include it in updated_players.

	log.Printf("Player %s added at (%.1f, %.1f)", playerID, startX, startY)
	return playerData // Return the initial data
}

// RemovePlayer removes a player. Thread-safe.
func (s *State) RemovePlayer(playerID string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Remove from current players
	_, exists := s.players[playerID]
	if exists {
		delete(s.players, playerID)
		log.Printf("Player %s removed from active players.", playerID)
	} else {
		log.Printf("Attempted to remove non-existent player %s", playerID)
	}

	// NOTE: We don't immediately remove from lastBroadcastPlayers here.
	// GenerateDeltaUpdate will detect the player is missing from the current
	// state compared to the last broadcast and add the ID to removed_player_ids.
}

// --- State Access (GetPlayer, GetAllPlayers - No changes needed) ---
func (s *State) GetPlayer(playerID string) (*pb.Player, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	trackedPlayer, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	playerCopy := *trackedPlayer.PlayerData
	return &playerCopy, true
}
func (s *State) GetAllPlayers() []*pb.Player { /* ... (no change, still useful for initial state) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	playerList := make([]*pb.Player, 0, len(s.players))
	for _, trackedP := range s.players {
		currentAnimationState := pb.AnimationState_IDLE
		switch trackedP.LastDirection {
		case pb.PlayerInput_UP:
			currentAnimationState = pb.AnimationState_RUNNING_UP
		case pb.PlayerInput_DOWN:
			currentAnimationState = pb.AnimationState_RUNNING_DOWN
		case pb.PlayerInput_LEFT:
			currentAnimationState = pb.AnimationState_RUNNING_LEFT
		case pb.PlayerInput_RIGHT:
			currentAnimationState = pb.AnimationState_RUNNING_RIGHT
		}
		playerCopy := *trackedP.PlayerData
		playerCopy.CurrentAnimationState = currentAnimationState
		playerList = append(playerList, &playerCopy)
	}
	return playerList
}
func (s *State) GetAllPlayerIDs() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.players))
	for id := range s.players {
		ids = append(ids, id)
	}
	return ids
}
func (s *State) GetTrackedPlayer(playerID string) (*trackedPlayer, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	tp, exists := s.players[playerID]
	return tp, exists
}
func (s *State) UpdatePlayerDirection(playerID string, dir pb.PlayerInput_Direction) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	tp, exists := s.players[playerID]
	if !exists {
		return false
	}
	changed := false
	if tp.LastDirection != dir {
		tp.LastDirection = dir
		changed = true
	}
	return changed
}

// --- Input & Movement (ApplyInput - No change needed in core logic) ---
func (s *State) ApplyInput(playerID string, direction pb.PlayerInput_Direction) (*pb.Player, bool) {
	// ... (implementation from previous version - it modifies s.players directly) ...
	// ... (ensure it updates PlayerData.CurrentAnimationState correctly based on direction) ...
	s.mu.Lock()
	defer s.mu.Unlock()

	trackedP, exists := s.players[playerID]
	if !exists {
		log.Printf("ApplyInput: Player %s not found.", playerID)
		return nil, false
	}

	trackedP.LastInputTime = time.Now()
	trackedP.LastDirection = direction

	currentX := trackedP.PlayerData.XPos
	currentY := trackedP.PlayerData.YPos
	potentialX := currentX
	potentialY := currentY
	moved := false
	intendedAnimation := pb.AnimationState_IDLE // Default

	if direction != pb.PlayerInput_UNKNOWN {
		switch direction {
		case pb.PlayerInput_UP:
			potentialY -= PlayerMoveSpeed
			intendedAnimation = pb.AnimationState_RUNNING_UP
		case pb.PlayerInput_DOWN:
			potentialY += PlayerMoveSpeed
			intendedAnimation = pb.AnimationState_RUNNING_DOWN
		case pb.PlayerInput_LEFT:
			potentialX -= PlayerMoveSpeed
			intendedAnimation = pb.AnimationState_RUNNING_LEFT
		case pb.PlayerInput_RIGHT:
			potentialX += PlayerMoveSpeed
			intendedAnimation = pb.AnimationState_RUNNING_RIGHT
		}

		potentialX = clamp(potentialX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
		potentialY = clamp(potentialY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)

		canMove := true
		if s.checkMapCollision(potentialX, potentialY) {
			canMove = false
		} else if s.checkPlayerCollision(playerID, potentialX, potentialY) {
			canMove = false
		}

		if canMove {
			trackedP.PlayerData.XPos = potentialX
			trackedP.PlayerData.YPos = potentialY
			moved = true
		}
	} else {
		intendedAnimation = pb.AnimationState_IDLE
	}

	// Update the animation state directly on the tracked player data
	// Use intended animation if moving/attempting, otherwise IDLE
	if moved || direction != pb.PlayerInput_UNKNOWN {
		trackedP.PlayerData.CurrentAnimationState = intendedAnimation
	} else {
		trackedP.PlayerData.CurrentAnimationState = pb.AnimationState_IDLE
	}

	// Return a copy for safety, reflecting the *actual* state after applying input
	playerCopy := *trackedP.PlayerData
	return &playerCopy, true
}

// --- Collision Detection (checkMapCollision, checkPlayerCollision - No changes needed) ---
func (s *State) checkMapCollision(centerX, centerY float32) bool {
	minX := centerX - PlayerHalfWidth
	maxX := centerX + PlayerHalfWidth
	minY := centerY - PlayerHalfHeight
	maxY := centerY + PlayerHalfHeight
	epsilon := float32(0.001)
	startTileX := int(minX / float32(s.tileSize))
	endTileX := int((maxX - epsilon) / float32(s.tileSize))
	startTileY := int(minY / float32(s.tileSize))
	endTileY := int((maxY - epsilon) / float32(s.tileSize))
	for ty := startTileY; ty <= endTileY; ty++ {
		for tx := startTileX; tx <= endTileX; tx++ {
			if tx < 0 || tx >= s.mapTileWidth || ty < 0 || ty >= s.mapTileHeight {
				return true
			}
			if s.worldMap[ty][tx] == TileTypeWall {
				return true
			}
		}
	}
	return false
}
func (s *State) checkPlayerCollision(playerID string, potentialX, potentialY float32) bool {
	moveLeft := potentialX - PlayerHalfWidth
	moveRight := potentialX + PlayerHalfWidth
	moveTop := potentialY - PlayerHalfHeight
	moveBottom := potentialY + PlayerHalfHeight
	for otherID, otherTrackedPlayer := range s.players {
		if otherID == playerID {
			continue
		}
		otherX := otherTrackedPlayer.PlayerData.XPos
		otherY := otherTrackedPlayer.PlayerData.YPos
		otherLeft := otherX - PlayerHalfWidth
		otherRight := otherX + PlayerHalfWidth
		otherTop := otherY - PlayerHalfHeight
		otherBottom := otherY + PlayerHalfHeight
		xOverlap := (moveLeft < otherRight) && (moveRight > otherLeft)
		yOverlap := (moveTop < otherBottom) && (moveBottom > otherTop)
		if xOverlap && yOverlap {
			return true
		}
	}
	return false
}

// --- Map Data Access (GetMapDataAndDimensions, GetWorldPixelDimensions - No changes needed) ---
func (s *State) GetMapDataAndDimensions() ([][]TileType, int, int, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.worldMap == nil || s.mapTileHeight == 0 || s.mapTileWidth == 0 {
		return nil, 0, 0, 0, fmt.Errorf("map data not loaded or invalid")
	}
	return s.worldMap, s.mapTileWidth, s.mapTileHeight, s.tileSize, nil
}
func (s *State) GetWorldPixelDimensions() (float32, float32) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.worldMaxX, s.worldMaxY
}

// --- Delta Update Generation ---

// GenerateDeltaUpdate compares the current player state to the last broadcast state
// and creates a DeltaUpdate message containing only the changes.
// It also updates the last broadcast state snapshot. Thread-safe.
// Returns the generated DeltaUpdate and a boolean indicating if any changes occurred.
func (s *State) GenerateDeltaUpdate() (*pb.DeltaUpdate, bool) {
	s.mu.Lock() // Need exclusive lock to compare and update lastBroadcastPlayers
	defer s.mu.Unlock()

	delta := &pb.DeltaUpdate{
		UpdatedPlayers:   make([]*pb.Player, 0),
		RemovedPlayerIds: make([]string, 0),
	}
	changed := false
	currentPlayerStateSnapshot := make(map[string]*pb.Player) // Snapshot for the *next* comparison

	// Check for updated/new players
	for id, trackedP := range s.players {
		// Make a clone of the current player data for the snapshot
		// Using proto.Clone ensures we don't hold references to the mutable PlayerData
		currentPlayerClone := proto.Clone(trackedP.PlayerData).(*pb.Player)
		currentPlayerStateSnapshot[id] = currentPlayerClone // Store clone in new snapshot

		lastP, existsInLast := s.lastBroadcastPlayers[id]

		// Check if player is new or has changed state since last broadcast
		if !existsInLast || !proto.Equal(lastP, currentPlayerClone) {
			// Player is new or updated, add a clone to the delta
			delta.UpdatedPlayers = append(delta.UpdatedPlayers, currentPlayerClone) // Add the clone
			changed = true
		}
	}

	// Check for removed players
	for id := range s.lastBroadcastPlayers {
		if _, existsInCurrent := s.players[id]; !existsInCurrent {
			delta.RemovedPlayerIds = append(delta.RemovedPlayerIds, id)
			changed = true
		}
	}

	// Update the last broadcast state snapshot *only if* changes occurred
	// This prevents sending empty deltas if nothing changed between checks.
	if changed {
		// Use the snapshot we built during the comparison
		s.lastBroadcastPlayers = currentPlayerStateSnapshot
		// log.Printf("Delta generated: Updated=%d, Removed=%d", len(delta.UpdatedPlayers), len(delta.RemovedPlayerIds)) // Debug log
	}

	return delta, changed
}

// GetInitialStateDelta creates a DeltaUpdate containing the full current state.
// Used to send the initial state to a newly connected client. Thread-safe.
func (s *State) GetInitialStateDelta() *pb.DeltaUpdate {
	s.mu.RLock() // Read lock sufficient to get all players
	defer s.mu.RUnlock()

	initialDelta := &pb.DeltaUpdate{
		UpdatedPlayers:   make([]*pb.Player, 0, len(s.players)),
		RemovedPlayerIds: make([]string, 0), // No removed players for initial state
	}

	for _, trackedP := range s.players {
		// Clone player data to avoid race conditions if state changes concurrently
		playerClone := proto.Clone(trackedP.PlayerData).(*pb.Player)
		initialDelta.UpdatedPlayers = append(initialDelta.UpdatedPlayers, playerClone)
	}
	return initialDelta
}

// --- Utility ---
func clamp(value, min, max float32) float32 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}
