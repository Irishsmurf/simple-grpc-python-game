// Package game manages the core game state for the gRPC server.
package game

import (
	// "bufio" // No longer needed for map loading
	"fmt"
	"image"
	"image/color"
	_ "image/png" // Import for PNG decoding (register decoder)
	"log"         // Go 1.21+ needed for maps.Clone
	"os"

	// "strconv" // No longer needed for map loading
	// "strings" // No longer needed for map loading
	"sync"
	"time"

	pb "simple-grpc-game/gen/go/game" // Adjust import path if needed

	"google.golang.org/protobuf/proto"
)

// --- Constants ---
const (
	PlayerHalfWidth  float32 = 64.0
	PlayerHalfHeight float32 = 64.0
	PlayerMoveSpeed  float32 = 16.0
	DefaultTileSize  int     = 32
	MapFilePath      string  = "map.png" // Default map file name
	movementTimeout          = 200 * time.Millisecond
)

type TileType int32

const (
	TileTypeEmpty TileType = 0
	TileTypeWall  TileType = 1
)

func (t TileType) String() string { /* ... (no change) ... */
	switch t {
	case TileTypeEmpty:
		return "Empty"
	case TileTypeWall:
		return "Wall"
	default:
		return fmt.Sprintf("Unknown(%d)", t)
	}
}

type trackedPlayer struct {
	PlayerData    *pb.Player
	LastInputTime time.Time
	LastDirection pb.PlayerInput_Direction
}

type State struct { // ... (no change) ...
	mu                   sync.RWMutex
	players              map[string]*trackedPlayer
	worldMap             [][]TileType
	mapTileWidth         int
	mapTileHeight        int
	tileSize             int
	worldMinX            float32
	worldMaxX            float32
	worldMinY            float32
	worldMaxY            float32
	lastBroadcastPlayers map[string]*pb.Player
}

func loadMapFromPNG(filePath string) ([][]TileType, int, int, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("failed to open map file '%s': %w", filePath, err)
	}
	defer file.Close()

	img, format, err := image.Decode(file)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("failed to decode image file '%s': %w", filePath, err)
	}
	if format != "png" {
		log.Printf("Warning: Map file '%s' is format '%s', not png.", filePath, format)
		// Allow other formats if needed, but PNG is expected
	}

	bounds := img.Bounds()
	width := bounds.Dx()  // Width in pixels = width in tiles
	height := bounds.Dy() // Height in pixels = height in tiles

	if width <= 0 || height <= 0 {
		return nil, 0, 0, fmt.Errorf("map image '%s' has invalid dimensions (%dx%d)", filePath, width, height)
	}

	tileMap := make([][]TileType, height)
	for y := 0; y < height; y++ {
		tileMap[y] = make([]TileType, width)
		for x := 0; x < width; x++ {
			// Image coordinates start from bounds.Min (usually 0,0 but not guaranteed)
			pixelX := bounds.Min.X + x
			pixelY := bounds.Min.Y + y
			rgbaColor := color.RGBAModel.Convert(img.At(pixelX, pixelY)).(color.RGBA)

			// Determine TileType based on color
			// Comparing RGBA values directly
			if rgbaColor.R == 0 && rgbaColor.G == 0 && rgbaColor.B == 0 { // Black = Wall
				tileMap[y][x] = TileTypeWall
			} else if rgbaColor.R == 255 && rgbaColor.G == 255 && rgbaColor.B == 255 { // White = Empty
				tileMap[y][x] = TileTypeEmpty
				// } else if rgbaColor.R == 255 && rgbaColor.G == 0 && rgbaColor.B == 0 { // Example: Red = Lava (future)
				//     tileMap[y][x] = TileTypeLava
			} else {
				// Default for unknown colors
				// log.Printf("Warning: Unknown color %v at pixel (%d, %d) in map '%s'. Treating as Empty.", rgbaColor, pixelX, pixelY, filePath)
				tileMap[y][x] = TileTypeEmpty
			}
		}
	}

	log.Printf("Loaded map from PNG '%s', dimensions: %d x %d tiles.", filePath, width, height)
	return tileMap, width, height, nil
}

// NewState creates and initializes a new game state manager.
func NewState() (*State, error) {
	// Load map from PNG
	loadedMap, width, height, err := loadMapFromPNG(MapFilePath)
	if err != nil {
		// Return error instead of Fatalf
		return nil, fmt.Errorf("error loading map PNG: %w", err)
	}

	// Calculate world boundaries based on loaded map and tile size
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
		lastBroadcastPlayers: make(map[string]*pb.Player),
	}

	log.Printf("Game state initialized. World boundaries: X(%.1f, %.1f), Y(%.1f, %.1f)",
		newState.worldMinX, newState.worldMaxX, newState.worldMinY, newState.worldMaxY)

	return newState, nil
}

// --- Player Management ---
func (s *State) AddPlayer(playerID string, username string, startX, startY float32) *pb.Player { /* ... (no change) ... */
	s.mu.Lock()
	defer s.mu.Unlock()
	startX = clamp(startX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
	startY = clamp(startY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)
	playerData := &pb.Player{Id: playerID, Username: username, XPos: startX, YPos: startY, CurrentAnimationState: pb.AnimationState_IDLE}
	tracked := &trackedPlayer{PlayerData: playerData, LastInputTime: time.Now(), LastDirection: pb.PlayerInput_UNKNOWN}
	s.players[playerID] = tracked
	log.Printf("Player %s ('%s') added at (%.1f, %.1f)", playerID, username, startX, startY)
	return playerData
}
func (s *State) RemovePlayer(playerID string) { /* ... (no change) ... */
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.players[playerID]; exists {
		delete(s.players, playerID)
		log.Printf("Player %s removed.", playerID)
	}
}

// --- State Access ---
func (s *State) GetPlayer(playerID string) (*pb.Player, bool) { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	tp, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	pc := *tp.PlayerData
	return &pc, true
}
func (s *State) GetAllPlayers() []*pb.Player { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	pl := make([]*pb.Player, 0, len(s.players))
	for _, tp := range s.players {
		anim := pb.AnimationState_IDLE
		switch tp.LastDirection {
		case pb.PlayerInput_UP:
			anim = pb.AnimationState_RUNNING_UP
		case pb.PlayerInput_DOWN:
			anim = pb.AnimationState_RUNNING_DOWN
		case pb.PlayerInput_LEFT:
			anim = pb.AnimationState_RUNNING_LEFT
		case pb.PlayerInput_RIGHT:
			anim = pb.AnimationState_RUNNING_RIGHT
		}
		pc := *tp.PlayerData
		pc.CurrentAnimationState = anim
		pl = append(pl, &pc)
	}
	return pl
}
func (s *State) GetAllPlayerIDs() []string { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.players))
	for id := range s.players {
		ids = append(ids, id)
	}
	return ids
}
func (s *State) GetTrackedPlayer(playerID string) (*trackedPlayer, bool) { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	tp, exists := s.players[playerID]
	return tp, exists
}
func (s *State) UpdatePlayerDirection(playerID string, dir pb.PlayerInput_Direction) bool { /* ... (no change) ... */
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

// --- Input & Movement ---
func (s *State) ApplyInput(playerID string, direction pb.PlayerInput_Direction) (*pb.Player, bool) { /* ... (no change) ... */
	s.mu.Lock()
	defer s.mu.Unlock()
	trackedP, exists := s.players[playerID]
	if !exists {
		return nil, false
	}
	trackedP.LastInputTime = time.Now()
	trackedP.LastDirection = direction
	currentX := trackedP.PlayerData.XPos
	currentY := trackedP.PlayerData.YPos
	potentialX := currentX
	potentialY := currentY
	moved := false
	intendedAnimation := pb.AnimationState_IDLE
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
	if moved || direction != pb.PlayerInput_UNKNOWN {
		trackedP.PlayerData.CurrentAnimationState = intendedAnimation
	} else {
		trackedP.PlayerData.CurrentAnimationState = pb.AnimationState_IDLE
	}
	playerCopy := *trackedP.PlayerData
	return &playerCopy, true
}

// --- Collision Detection ---
func (s *State) checkMapCollision(centerX, centerY float32) bool { /* ... (no change) ... */
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
func (s *State) checkPlayerCollision(playerID string, potentialX, potentialY float32) bool { /* ... (no change) ... */
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

// --- Map Data Access ---
func (s *State) GetMapDataAndDimensions() ([][]TileType, int, int, int, error) { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.worldMap == nil || s.mapTileHeight == 0 || s.mapTileWidth == 0 {
		return nil, 0, 0, 0, fmt.Errorf("map data not loaded or invalid")
	}
	return s.worldMap, s.mapTileWidth, s.mapTileHeight, s.tileSize, nil
}
func (s *State) GetWorldPixelDimensions() (float32, float32) { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.worldMaxX, s.worldMaxY
}

// --- Delta Update Generation ---
func (s *State) GenerateDeltaUpdate() (*pb.DeltaUpdate, bool) { /* ... (no change) ... */
	s.mu.Lock()
	defer s.mu.Unlock()
	delta := &pb.DeltaUpdate{UpdatedPlayers: make([]*pb.Player, 0), RemovedPlayerIds: make([]string, 0)}
	changed := false
	currentPlayerStateSnapshot := make(map[string]*pb.Player)
	for id, trackedP := range s.players {
		currentPlayerClone := proto.Clone(trackedP.PlayerData).(*pb.Player)
		currentPlayerStateSnapshot[id] = currentPlayerClone
		lastP, existsInLast := s.lastBroadcastPlayers[id]
		if !existsInLast || !proto.Equal(lastP, currentPlayerClone) {
			delta.UpdatedPlayers = append(delta.UpdatedPlayers, currentPlayerClone)
			changed = true
		}
	}
	for id := range s.lastBroadcastPlayers {
		if _, existsInCurrent := s.players[id]; !existsInCurrent {
			delta.RemovedPlayerIds = append(delta.RemovedPlayerIds, id)
			changed = true
		}
	}
	if changed {
		s.lastBroadcastPlayers = currentPlayerStateSnapshot
	}
	return delta, changed
}
func (s *State) GetInitialStateDelta() *pb.DeltaUpdate { /* ... (no change) ... */
	s.mu.RLock()
	defer s.mu.RUnlock()
	initialDelta := &pb.DeltaUpdate{UpdatedPlayers: make([]*pb.Player, 0, len(s.players)), RemovedPlayerIds: make([]string, 0)}
	for _, trackedP := range s.players {
		playerClone := proto.Clone(trackedP.PlayerData).(*pb.Player)
		initialDelta.UpdatedPlayers = append(initialDelta.UpdatedPlayers, playerClone)
	}
	return initialDelta
}

// --- Utility ---
func clamp(value, min, max float32) float32 { /* ... (no change) ... */
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}
