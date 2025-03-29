// Package game manages the core game state.
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

	// Assuming your module path allows this import based on previous steps
	pb "simple-grpc-game/gen/go/game" // Adjust if your module path is different!
)

var (
	WorldMinX float32 = 0.0
	WorldMaxX float32 = 5000.0
	WorldMinY float32 = 0.0
	WorldMaxY float32 = 5000.0
)

const (
	PlayerHalfWidth  float32 = 64.0
	PlayerHalfHeight float32 = 64.0

	TileSize      int = 32
	MapTileWidth  int = 25
	MapTileHeight int = 20
)

type TileType int

const (
	TileTypeEmpty TileType = iota
	TileTypeWall
)

// State manages the shared game state in a thread-safe manner.
type State struct {
	mu      sync.RWMutex // Read-write mutex for finer-grained locking (optional, Mutex is fine too)
	players map[string]*trackedPlayer

	worldMap      [][]TileType
	mapTileWidth  int
	mapTileHeight int
}

type trackedPlayer struct {
	PlayerData    *pb.Player
	LastInputTime time.Time
	LastDirection pb.PlayerInput_Direction
}

func loadMapFromFile(filePath string) ([][]TileType, int, int, error) {

	file, err := os.Open(filePath)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("failed to open map file: %s - %w", filePath, err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	var tileMap [][]TileType
	width := -1

	rowCount := 0
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		parts := strings.Fields(line)
		currentPartsCount := len(parts)

		if width == -1 {
			width = currentPartsCount
		} else if currentPartsCount != width {
			return nil, 0, 0, fmt.Errorf("inconsistent row length in map file")
		}

		row := make([]TileType, width)
		for i, part := range parts {
			tileInt, err := strconv.Atoi(part)
			if err != nil {
				log.Printf("Invalid TileID")
				return nil, 0, 0, fmt.Errorf("invalid tile ID in map file: %s - %w", part, err)
			}
			tileID := TileType(tileInt)
			if tileID < TileTypeEmpty || tileID > TileTypeWall {
				log.Printf("Invalid tile ID %d in map file, setting to Empty", tileID)
				tileID = TileTypeEmpty
			}
			if i < len(row) {
				row[i] = tileID
			} else {
				log.Printf("ERROR: Index %d out of bounds for row slice with len %d (width %d)", i, len(row), width)
			}
		}
		tileMap = append(tileMap, row)
		rowCount++
	}

	if err := scanner.Err(); err != nil {
		return nil, 0, 0, fmt.Errorf("error reading map file: %s - %w", filePath, err)
	}

	if len(tileMap) == 0 || width == -1 {
		return nil, 0, 0, fmt.Errorf("map file is empty or invalid")
	}

	height := len(tileMap)
	log.Printf("Loaded map from file: %s, dimensions: %dx%d", filePath, width, height)
	return tileMap, width, height, nil
}

// NewState creates and initializes a new game state manager.
func NewState() *State {

	mapFilePath := "map.txt"
	loadedMap, width, height, err := loadMapFromFile(mapFilePath)
	if err != nil {
		log.Fatalf("Error loading map from file: %s - using default map", err)
	}
	if width == 0 || height == 0 {
		log.Fatalf("Invalid map dimensions: %dx%d - using default map", width, height)
	}

	newState := &State{
		players:       make(map[string]*trackedPlayer),
		worldMap:      loadedMap,
		mapTileHeight: height,
		mapTileWidth:  width,
	}

	// Logging
	actualHeight := len(newState.worldMap)
	actualWidth := 0

	if actualHeight > 0 {
		// Check the length of the first row to get the actual width
		actualWidth = len(newState.worldMap[0])
	}

	log.Printf("Map Loaded. Stored Dims: %d x %d. Actual Slice Dims: %d x %d.",
		newState.mapTileWidth, newState.mapTileHeight,
		actualWidth, actualHeight) // Note: Width/Height order convention

	if newState.mapTileHeight != actualHeight || newState.mapTileWidth != actualWidth {
		log.Printf("!!!! WARNING: Stored map dimensions do NOT match actual slice dimensions !!!!")
		newState.mapTileWidth = actualWidth
		newState.mapTileHeight = actualHeight
	}

	WorldMaxX = float32(newState.mapTileWidth * TileSize)
	WorldMaxY = float32(newState.mapTileHeight * TileSize)
	log.Printf("World boundaries set to: X(%f, %f), Y(%f, %f)", WorldMinX, WorldMaxX, WorldMinY, WorldMaxY)

	return newState
}

func (s *State) CheckPlayerCollision(playerID string, potentialX, potentialY float32) bool {
	moveLeft := potentialX - PlayerHalfWidth
	moveRight := potentialX + PlayerHalfWidth
	moveTop := potentialY - PlayerHalfHeight
	moveBottom := potentialY + PlayerHalfHeight

	for id, trackedPlayer := range s.players {
		if id == playerID {
			continue // Skip self
		}

		otherX := trackedPlayer.PlayerData.XPos
		otherY := trackedPlayer.PlayerData.YPos
		otherLeft := otherX - PlayerHalfWidth
		otherRight := otherX + PlayerHalfWidth
		otherTop := otherY - PlayerHalfHeight
		otherBottom := otherY + PlayerHalfHeight

		xOverlap := (moveLeft < otherRight) && (moveRight > otherLeft)
		yOverlap := (moveTop < otherBottom) && (moveBottom > otherTop)

		if xOverlap && yOverlap {
			return true // Collision detected
		}
	}
	return false // No collision
}

func (s *State) CheckMapCollision(pixelX, pixelY float32) bool {

	minX := pixelX - PlayerHalfWidth
	maxX := pixelX + PlayerHalfWidth
	minY := pixelY - PlayerHalfHeight
	maxY := pixelY + PlayerHalfHeight

	log.Printf("DEBUG CheckMapCollision: Pixel Bounds (MinX:%.1f, MaxX:%.1f, MinY:%.1f, MaxY:%.1f)", minX, maxX, minY, maxY)

	epsilon := float32(0.0001)
	startTileX := int(minX / float32(TileSize))
	endTileX := int((maxX - epsilon) / float32(TileSize))
	startTileY := int(minY / float32(TileSize))
	endTileY := int((maxY - epsilon) / float32(TileSize))

	log.Printf("DEBUG CheckMapCollision: Tile Range Check (X: %d to %d, Y: %d to %d)", startTileX, endTileX, startTileY, endTileY)

	for ty := startTileY; ty <= endTileY; ty++ {
		for tx := startTileX; tx <= endTileX; tx++ {
			log.Printf("DEBUG CheckMapCollision: Checking tile (%d, %d)", tx, ty)

			if tx < 0 || tx >= s.mapTileWidth || ty < 0 || ty >= s.mapTileHeight {
				log.Printf("DEBUG CheckMapCollision: Collision! Tile (%d, %d) is outside map bounds (%dx%d)", tx, ty, s.mapTileWidth, s.mapTileHeight)

				return true
			}

			tileType := s.worldMap[ty][tx]
			if tileType == TileTypeWall { // Assuming 1 is a wall
				log.Printf("DEBUG CheckMapCollision: Collision! Tile (%d, %d) is a Wall (%v)", tx, ty, tileType)

				return true
			}
		}
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
		moveSpeed := float32(2) // Example speed - could be configurable
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

		if potentialX-PlayerHalfWidth < WorldMinX {
			potentialX = WorldMinX
		} else if potentialX+PlayerHalfWidth > WorldMaxX {
			potentialX = WorldMaxX
		}

		if potentialY-PlayerHalfHeight < WorldMinY {
			potentialY = WorldMinY
		} else if potentialY+PlayerHalfHeight > WorldMaxY {
			potentialY = WorldMaxY
		}

		collidesWithMap := s.CheckMapCollision(potentialX, potentialY)
		if collidesWithMap {
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

		currentAnimationState := pb.AnimationState_IDLE

		switch p.LastDirection {
		case pb.PlayerInput_UP:
			currentAnimationState = pb.AnimationState_RUNNING_UP
		case pb.PlayerInput_DOWN:
			currentAnimationState = pb.AnimationState_RUNNING_DOWN
		case pb.PlayerInput_LEFT:
			currentAnimationState = pb.AnimationState_RUNNING_LEFT
		case pb.PlayerInput_RIGHT:
			currentAnimationState = pb.AnimationState_RUNNING_RIGHT
		default:
			currentAnimationState = pb.AnimationState_IDLE
		}

		// Create copies to prevent external modification of internal state
		playerCopy := &pb.Player{
			Id:                    p.PlayerData.Id,
			XPos:                  p.PlayerData.XPos,
			YPos:                  p.PlayerData.YPos,
			CurrentAnimationState: currentAnimationState,
		}
		playerList = append(playerList, playerCopy)
	}
	return playerList
}

func (s *State) GetMapData() ([][]TileType, int, int) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	// Return a copy? Or assume caller won't modify? For now, return direct reference.
	// Be careful if map could change later!
	return s.worldMap, s.mapTileWidth, s.mapTileHeight
}

func (s *State) GetMapDataAndDimensions() ([][]TileType, int, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.worldMap == nil || s.mapTileHeight == 0 || s.mapTileWidth == 0 {
		return nil, 0, 0, fmt.Errorf("map data not loaded or invalid")
	}
	// Consider returning a deep copy if map could change, but okay for now
	return s.worldMap, s.mapTileWidth, s.mapTileHeight, nil
}

func (t TileType) String() string {
	switch t {
	case TileTypeEmpty:
		return "Empty"
	case TileTypeWall:
		return "Wall"
	default:
		return "Unknown"
	}
}
