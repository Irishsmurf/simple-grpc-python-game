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

	pb "simple-grpc-game/gen/go/game" // Adjust import path if needed

	"google.golang.org/protobuf/proto"
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

type State struct {
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

func loadMapFromFile(filePath string) ([][]TileType, int, int, error) { /* ... (no change) ... */
	file, err := os.Open(filePath)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("failed to open map file '%s': %w", filePath, err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	var tileMap [][]TileType
	width := -1
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		parts := strings.Fields(line)
		currentWidth := len(parts)
		if width == -1 {
			width = currentWidth
		} else if currentWidth != width {
			return nil, 0, 0, fmt.Errorf("inconsistent row length (expected %d, got %d)", width, currentWidth)
		}
		if width == 0 {
			return nil, 0, 0, fmt.Errorf("map row has zero width")
		}
		row := make([]TileType, width)
		for i, part := range parts {
			tileInt, err := strconv.Atoi(part)
			if err != nil {
				return nil, 0, 0, fmt.Errorf("invalid tile ID '%s': %w", part, err)
			}
			tileID := TileType(tileInt)
			if tileID != TileTypeEmpty && tileID != TileTypeWall {
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

func NewState() (*State, error) { /* ... (no change) ... */
	loadedMap, width, height, err := loadMapFromFile(MapFilePath)
	if err != nil {
		return nil, fmt.Errorf("error loading map: %w", err)
	}
	tileSize := DefaultTileSize
	worldPixelWidth := float32(width * tileSize)
	worldPixelHeight := float32(height * tileSize)
	newState := &State{
		players: make(map[string]*trackedPlayer), worldMap: loadedMap, mapTileWidth: width, mapTileHeight: height, tileSize: tileSize,
		worldMinX: 0.0, worldMaxX: worldPixelWidth, worldMinY: 0.0, worldMaxY: worldPixelHeight,
		lastBroadcastPlayers: make(map[string]*pb.Player),
	}
	log.Printf("Game state initialized. World boundaries: X(%.1f, %.1f), Y(%.1f, %.1f)", newState.worldMinX, newState.worldMaxX, newState.worldMinY, newState.worldMaxY)
	return newState, nil
}

// *** CHANGED: AddPlayer now accepts username ***
func (s *State) AddPlayer(playerID string, username string, startX, startY float32) *pb.Player {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Basic username validation/sanitization (optional but recommended)
	if username == "" {
		username = "Player_" + playerID[:4] // Assign a default if empty
	}
	// Could add length limits, character filtering etc.

	startX = clamp(startX, s.worldMinX+PlayerHalfWidth, s.worldMaxX-PlayerHalfWidth)
	startY = clamp(startY, s.worldMinY+PlayerHalfHeight, s.worldMaxY-PlayerHalfHeight)

	playerData := &pb.Player{
		Id:                    playerID,
		Username:              username, // Set username
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

func (s *State) ApplyInput(playerID string, direction pb.PlayerInput_Direction) (*pb.Player, bool) { /* ... (no change needed, already updates internal state) ... */
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

// *** CHANGED: GenerateDeltaUpdate checks username in proto.Equal ***
func (s *State) GenerateDeltaUpdate() (*pb.DeltaUpdate, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	delta := &pb.DeltaUpdate{UpdatedPlayers: make([]*pb.Player, 0), RemovedPlayerIds: make([]string, 0)}
	changed := false
	currentPlayerStateSnapshot := make(map[string]*pb.Player)

	for id, trackedP := range s.players {
		currentPlayerClone := proto.Clone(trackedP.PlayerData).(*pb.Player) // Clone current data
		currentPlayerStateSnapshot[id] = currentPlayerClone

		lastP, existsInLast := s.lastBroadcastPlayers[id]

		// Check if new or changed (proto.Equal compares all fields, including username now)
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
		s.lastBroadcastPlayers = currentPlayerStateSnapshot // Update snapshot only if changed
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

func clamp(value, min, max float32) float32 { /* ... (no change) ... */
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}
