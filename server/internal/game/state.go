// Package game manages the core game state for the gRPC server.
package game

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	// Adjust the import path based on your Go module setup
	pb "simple-grpc-game/gen/go/game"
)

// --- Constants ---

const (
	// Player dimensions and speed
	PlayerHalfWidth  float32 = 64.0 // Half the player's width for collision calculations
	PlayerHalfHeight float32 = 64.0 // Half the player's height for collision calculations
	PlayerMoveSpeed  float32 = 16.0 // Pixels per update cycle when moving

	// Map and Tile configuration
	DefaultTileSize int    = 32        // Default size of each tile in pixels (can be overridden by map data)
	MapFilePath     string = "map.txt" // Path to the map file relative to server execution

	// Timeouts
	// movementTimeout = 200 * time.Millisecond // How long input direction persists without new input
)

// TileType represents the type of a map tile (e.g., walkable, wall).
type TileType int32 // Use int32 to match protobuf repeated field type

const (
	TileTypeEmpty TileType = 0 // Represents a walkable tile
	TileTypeWall  TileType = 1 // Represents a solid wall tile
)

// String provides a human-readable representation of a TileType.
func (t TileType) String() string {
	switch t {
	case TileTypeEmpty:
		return "Empty"
	case TileTypeWall:
		return "Wall"
	default:
		return fmt.Sprintf("Unknown(%d)", t)
	}
}

// trackedPlayer holds the game state data for a player along with
// server-side tracking information like last input time.
type trackedPlayer struct {
	PlayerData    *pb.Player               // Protobuf representation sent to clients
	LastInputTime time.Time                // Timestamp of the last received input
	LastDirection pb.PlayerInput_Direction // Last movement direction received
}

// State manages the shared game state in a thread-safe manner.
type State struct {
	mu sync.RWMutex // Read-write mutex for protecting concurrent access

	players map[string]*trackedPlayer // Map from playerID to their tracked state

	// World map data
	worldMap      [][]TileType // 2D slice representing the tile grid
	mapTileWidth  int          // Width of the map in tiles
	mapTileHeight int          // Height of the map in tiles
	tileSize      int          // Size of one tile in pixels (read from map data or default)

	// Calculated world boundaries in pixels
	worldMinX float32
	worldMaxX float32
	worldMinY float32
	worldMaxY float32
}

// loadMapFromFile reads a map definition from a text file.
// Expected format: space-separated integers per line, each representing a TileType.
// Returns the map grid, width (tiles), height (tiles), and any error encountered.
func loadMapFromFile(filePath string) ([][]TileType, int, int, error) {
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
			// First non-empty line determines the map width
			width = currentWidth
		} else if currentWidth != width {
			// Ensure all rows have the same length
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
			// Basic validation for known tile types (can be expanded)
			if tileID != TileTypeEmpty && tileID != TileTypeWall {
				log.Printf("Warning: Invalid tile ID %d found in map file at row %d, col %d. Treating as Empty.", tileID, len(tileMap), i)
				tileID = TileTypeEmpty // Default to empty/walkable for unknown types
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
// It loads the map from the file specified by the MapFilePath constant.
// Returns the initialized State or an error if map loading fails.
func NewState() (*State, error) {
	loadedMap, width, height, err := loadMapFromFile(MapFilePath)
	if err != nil {
		// Return error instead of Fatalf
		return nil, fmt.Errorf("error loading map: %w", err)
	}

	// Calculate world boundaries based on loaded map and tile size
	tileSize := DefaultTileSize // Use default for now, could be overridden if map format supports it
	worldPixelWidth := float32(width * tileSize)
	worldPixelHeight := float32(height * tileSize)

	newState := &State{
		players:       make(map[string]*trackedPlayer),
		worldMap:      loadedMap,
		mapTileWidth:  width,
		mapTileHeight: height,
		tileSize:      tileSize,
		// Set world boundaries (assuming origin 0,0)
		worldMinX: 0.0,
		worldMaxX: worldPixelWidth,
		worldMinY: 0.0,
		worldMaxY: worldPixelHeight,
	}

	log.Printf("Game state initialized. World boundaries: X(%.1f, %.1f), Y(%.1f, %.1f)",
		newState.worldMinX, newState.worldMaxX, newState.worldMinY, newState.worldMaxY)

	return newState, nil
}

// --- Player Management ---

// AddPlayer adds a new player to the game state with a given ID and starting position.
// Returns the created Player object. Thread-safe.
func (s *State) AddPlayer(playerID string, startX, startY float32) *pb.Player {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Clamp starting position to world boundaries just in case
	startX = clamp(startX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
	startY = clamp(startY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)

	playerData := &pb.Player{
		Id:                    playerID,
		XPos:                  startX,
		YPos:                  startY,
		CurrentAnimationState: pb.AnimationState_IDLE, // Start idle
	}

	tracked := &trackedPlayer{
		PlayerData:    playerData,
		LastInputTime: time.Now(), // Initialize last input time
		LastDirection: pb.PlayerInput_UNKNOWN,
	}

	s.players[playerID] = tracked
	log.Printf("Player %s added at (%.1f, %.1f)", playerID, startX, startY)
	return playerData
}

// RemovePlayer removes a player from the game state by ID. Thread-safe.
func (s *State) RemovePlayer(playerID string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.players[playerID]; exists {
		delete(s.players, playerID)
		log.Printf("Player %s removed", playerID)
	} else {
		log.Printf("Attempted to remove non-existent player %s", playerID)
	}
}

// GetPlayer retrieves a copy of a player's data by ID.
// Returns the player object and true if found, nil and false otherwise. Thread-safe (read lock).
func (s *State) GetPlayer(playerID string) (*pb.Player, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	trackedPlayer, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	// Return a copy to prevent external modification of internal state
	playerCopy := *trackedPlayer.PlayerData // Shallow copy is okay for protobuf message
	return &playerCopy, true
}

// GetAllPlayers returns a slice containing copies of all current players' data. Thread-safe (read lock).
func (s *State) GetAllPlayers() []*pb.Player {
	s.mu.RLock()
	defer s.mu.RUnlock()

	playerList := make([]*pb.Player, 0, len(s.players))
	for _, trackedP := range s.players {
		// Determine animation state based on last known direction
		// This logic could potentially be moved to the client if preferred,
		// but doing it here ensures consistency in the broadcasted state.
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
			// default is IDLE
		}

		// Create copies to prevent data races if the caller modifies the slice contents
		playerCopy := *trackedP.PlayerData                       // Create a copy of the player data
		playerCopy.CurrentAnimationState = currentAnimationState // Update animation state in the copy
		playerList = append(playerList, &playerCopy)
	}
	return playerList
}

// GetAllPlayerIDs returns a slice of all current player IDs. Thread-safe (read lock).
func (s *State) GetAllPlayerIDs() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.players))
	for id := range s.players {
		ids = append(ids, id)
	}
	return ids
}

// GetTrackedPlayer returns the internal trackedPlayer struct for server-side logic (like timeouts).
// Use with caution - modifying the returned pointer requires holding the State mutex.
// Returns the tracked player and true if found, nil and false otherwise. Thread-safe (read lock).
func (s *State) GetTrackedPlayer(playerID string) (*trackedPlayer, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	tp, exists := s.players[playerID]
	// Note: Returning pointer directly. Caller must handle locking if modifying.
	return tp, exists
}

// UpdatePlayerDirection updates only the LastDirection field for a player.
// Used by the server tick to reset direction on timeout. Thread-safe.
// Returns true if the direction was changed, false otherwise (or if player not found).
func (s *State) UpdatePlayerDirection(playerID string, dir pb.PlayerInput_Direction) bool {
	s.mu.Lock() // Write lock needed to modify trackedPlayer
	defer s.mu.Unlock()
	tp, exists := s.players[playerID]
	if !exists {
		return false // Player might have disconnected
	}
	// Only update if the direction actually changes
	changed := false
	if tp.LastDirection != dir {
		tp.LastDirection = dir
		changed = true
	}
	return changed
}

// --- Input & Movement ---

// ApplyInput updates a player's state based on an input direction.
// It handles movement, collision detection, and boundary checks.
// Returns the updated Player object and true if successful, nil and false if player not found. Thread-safe.
func (s *State) ApplyInput(playerID string, direction pb.PlayerInput_Direction) (*pb.Player, bool) {
	s.mu.Lock() // Exclusive lock needed for updating player state
	defer s.mu.Unlock()

	trackedP, exists := s.players[playerID]
	if !exists {
		log.Printf("ApplyInput: Player %s not found.", playerID)
		return nil, false
	}

	// Update tracking info regardless of movement success
	trackedP.LastInputTime = time.Now()
	trackedP.LastDirection = direction

	// Calculate potential new position
	currentX := trackedP.PlayerData.XPos
	currentY := trackedP.PlayerData.YPos
	potentialX := currentX
	potentialY := currentY
	moved := false

	if direction != pb.PlayerInput_UNKNOWN {
		switch direction {
		case pb.PlayerInput_UP:
			potentialY -= PlayerMoveSpeed
		case pb.PlayerInput_DOWN:
			potentialY += PlayerMoveSpeed
		case pb.PlayerInput_LEFT:
			potentialX -= PlayerMoveSpeed
		case pb.PlayerInput_RIGHT:
			potentialX += PlayerMoveSpeed
		}

		// Clamp potential position to world boundaries first
		potentialX = clamp(potentialX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
		potentialY = clamp(potentialY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)

		// Check for collisions *before* updating the actual position
		canMove := true
		if s.checkMapCollision(potentialX, potentialY) {
			// log.Printf("ApplyInput: Map collision detected for %s at (%.1f, %.1f)", playerID, potentialX, potentialY)
			canMove = false
		} else if s.checkPlayerCollision(playerID, potentialX, potentialY) {
			// log.Printf("ApplyInput: Player collision detected for %s at (%.1f, %.1f)", playerID, potentialX, potentialY)
			canMove = false
		}

		// Update position only if the move is valid
		if canMove {
			trackedP.PlayerData.XPos = potentialX
			trackedP.PlayerData.YPos = potentialY
			moved = true
		}
		// If move was attempted but blocked, we don't update X/Y but keep LastDirection
	}

	// Return a copy of the potentially updated player data
	playerCopy := *trackedP.PlayerData // Create a copy
	// Update animation state in the copy based on the *intended* direction (even if blocked)
	// or set to IDLE if direction is UNKNOWN
	if direction == pb.PlayerInput_UNKNOWN {
		playerCopy.CurrentAnimationState = pb.AnimationState_IDLE
	} else {
		switch direction { // Use intended direction for animation state
		case pb.PlayerInput_UP:
			playerCopy.CurrentAnimationState = pb.AnimationState_RUNNING_UP
		case pb.PlayerInput_DOWN:
			playerCopy.CurrentAnimationState = pb.AnimationState_RUNNING_DOWN
		case pb.PlayerInput_LEFT:
			playerCopy.CurrentAnimationState = pb.AnimationState_RUNNING_LEFT
		case pb.PlayerInput_RIGHT:
			playerCopy.CurrentAnimationState = pb.AnimationState_RUNNING_RIGHT
		default: // Should not happen if UNKNOWN is handled above
			playerCopy.CurrentAnimationState = pb.AnimationState_IDLE
		}
	}

	// If the player didn't move (either input was UNKNOWN or move was blocked),
	// ensure the animation state reflects IDLE if they aren't actively trying to move.
	if !moved && direction == pb.PlayerInput_UNKNOWN {
		playerCopy.CurrentAnimationState = pb.AnimationState_IDLE
	}

	return &playerCopy, true
}

// --- Collision Detection ---

// checkMapCollision checks if a given bounding box (defined by center and half-dimensions) collides with any wall tiles.
// Assumes read lock is already held or not needed if map is static.
// NOTE: This is called internally by ApplyInput which holds the write lock.
func (s *State) checkMapCollision(centerX, centerY float32) bool {
	// Calculate the bounding box edges
	minX := centerX - PlayerHalfWidth
	maxX := centerX + PlayerHalfWidth
	minY := centerY - PlayerHalfHeight
	maxY := centerY + PlayerHalfHeight

	// Determine the range of map tiles the bounding box could overlap with
	// Use a small epsilon to handle floating point inaccuracies near tile boundaries
	epsilon := float32(0.001)
	startTileX := int(minX / float32(s.tileSize))
	endTileX := int((maxX - epsilon) / float32(s.tileSize))
	startTileY := int(minY / float32(s.tileSize))
	endTileY := int((maxY - epsilon) / float32(s.tileSize))

	// Iterate through the potentially overlapping tiles
	for ty := startTileY; ty <= endTileY; ty++ {
		for tx := startTileX; tx <= endTileX; tx++ {
			// Check if the tile coordinates are within the map bounds
			if tx < 0 || tx >= s.mapTileWidth || ty < 0 || ty >= s.mapTileHeight {
				// Considered a collision if trying to move outside the map
				// log.Printf("DEBUG CheckMapCollision: Collision! Tile (%d, %d) is outside map bounds (%dx%d)", tx, ty, s.mapTileWidth, s.mapTileHeight)
				return true
			}

			// Check the tile type at the current coordinates
			if s.worldMap[ty][tx] == TileTypeWall {
				// log.Printf("DEBUG CheckMapCollision: Collision! Tile (%d, %d) is a Wall (%v)", tx, ty, s.worldMap[ty][tx])
				return true // Collision detected with a wall
			}
		}
	}

	return false // No collision detected with walls or map boundaries
}

// checkPlayerCollision checks if the bounding box of a player (potentialX/Y) collides with any *other* player.
// Assumes the appropriate lock (read or write) is already held by the caller (ApplyInput holds write lock).
func (s *State) checkPlayerCollision(playerID string, potentialX, potentialY float32) bool {
	moveLeft := potentialX - PlayerHalfWidth
	moveRight := potentialX + PlayerHalfWidth
	moveTop := potentialY - PlayerHalfHeight
	moveBottom := potentialY + PlayerHalfHeight

	for otherID, otherTrackedPlayer := range s.players {
		if otherID == playerID {
			continue // Don't check collision with self
		}

		otherX := otherTrackedPlayer.PlayerData.XPos
		otherY := otherTrackedPlayer.PlayerData.YPos
		otherLeft := otherX - PlayerHalfWidth
		otherRight := otherX + PlayerHalfWidth
		otherTop := otherY - PlayerHalfHeight
		otherBottom := otherY + PlayerHalfHeight

		// Standard AABB collision check
		xOverlap := (moveLeft < otherRight) && (moveRight > otherLeft)
		yOverlap := (moveTop < otherBottom) && (moveBottom > otherTop)

		if xOverlap && yOverlap {
			return true // Collision detected
		}
	}
	return false // No collision with other players
}

// --- Map Data Access ---

// GetMapDataAndDimensions returns the map grid and its dimensions. Thread-safe (read lock).
// Returns the map grid, width (tiles), height (tiles), tile size (pixels), and nil error on success.
func (s *State) GetMapDataAndDimensions() ([][]TileType, int, int, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.worldMap == nil || s.mapTileHeight == 0 || s.mapTileWidth == 0 {
		return nil, 0, 0, 0, fmt.Errorf("map data not loaded or invalid")
	}
	// Return direct references - assumes map is static after loading.
	// If map could change dynamically, a deep copy would be needed here.
	return s.worldMap, s.mapTileWidth, s.mapTileHeight, s.tileSize, nil
}

// GetWorldPixelDimensions returns the calculated width and height of the world in pixels.
func (s *State) GetWorldPixelDimensions() (float32, float32) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.worldMaxX, s.worldMaxY // Max values represent dimensions from 0,0 origin
}

// --- Utility ---

// clamp restricts a value to be within a minimum and maximum range.
func clamp(value, min, max float32) float32 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}
