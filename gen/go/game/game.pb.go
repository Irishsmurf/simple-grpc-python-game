// Code generated by protoc-gen-go. DO NOT EDIT.
// versions:
// 	protoc-gen-go v1.28.1
// 	protoc        v3.6.1
// source: game.proto

package game

import (
	protoreflect "google.golang.org/protobuf/reflect/protoreflect"
	protoimpl "google.golang.org/protobuf/runtime/protoimpl"
	reflect "reflect"
	sync "sync"
)

const (
	// Verify that this generated code is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(20 - protoimpl.MinVersion)
	// Verify that runtime/protoimpl is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(protoimpl.MaxVersion - 20)
)

type PlayerInput_Direction int32

const (
	PlayerInput_UNKNOWN PlayerInput_Direction = 0
	PlayerInput_UP      PlayerInput_Direction = 1
	PlayerInput_DOWN    PlayerInput_Direction = 2
	PlayerInput_LEFT    PlayerInput_Direction = 3
	PlayerInput_RIGHT   PlayerInput_Direction = 4
)

// Enum value maps for PlayerInput_Direction.
var (
	PlayerInput_Direction_name = map[int32]string{
		0: "UNKNOWN",
		1: "UP",
		2: "DOWN",
		3: "LEFT",
		4: "RIGHT",
	}
	PlayerInput_Direction_value = map[string]int32{
		"UNKNOWN": 0,
		"UP":      1,
		"DOWN":    2,
		"LEFT":    3,
		"RIGHT":   4,
	}
)

func (x PlayerInput_Direction) Enum() *PlayerInput_Direction {
	p := new(PlayerInput_Direction)
	*p = x
	return p
}

func (x PlayerInput_Direction) String() string {
	return protoimpl.X.EnumStringOf(x.Descriptor(), protoreflect.EnumNumber(x))
}

func (PlayerInput_Direction) Descriptor() protoreflect.EnumDescriptor {
	return file_game_proto_enumTypes[0].Descriptor()
}

func (PlayerInput_Direction) Type() protoreflect.EnumType {
	return &file_game_proto_enumTypes[0]
}

func (x PlayerInput_Direction) Number() protoreflect.EnumNumber {
	return protoreflect.EnumNumber(x)
}

// Deprecated: Use PlayerInput_Direction.Descriptor instead.
func (PlayerInput_Direction) EnumDescriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{2, 0}
}

// Represents a player in the game
type Player struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Id   string  `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"` // Unique player identifier
	XPos float32 `protobuf:"fixed32,2,opt,name=x_pos,json=xPos,proto3" json:"x_pos,omitempty"`
	YPos float32 `protobuf:"fixed32,3,opt,name=y_pos,json=yPos,proto3" json:"y_pos,omitempty"` // Could add sprite type, color, etc. later
}

func (x *Player) Reset() {
	*x = Player{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[0]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *Player) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*Player) ProtoMessage() {}

func (x *Player) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[0]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use Player.ProtoReflect.Descriptor instead.
func (*Player) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{0}
}

func (x *Player) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

func (x *Player) GetXPos() float32 {
	if x != nil {
		return x.XPos
	}
	return 0
}

func (x *Player) GetYPos() float32 {
	if x != nil {
		return x.YPos
	}
	return 0
}

// Represents the entire game state to be sent to clients
type GameState struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Players []*Player `protobuf:"bytes,1,rep,name=players,proto3" json:"players,omitempty"` // List of all players currently in the game
}

func (x *GameState) Reset() {
	*x = GameState{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[1]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *GameState) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*GameState) ProtoMessage() {}

func (x *GameState) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[1]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use GameState.ProtoReflect.Descriptor instead.
func (*GameState) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{1}
}

func (x *GameState) GetPlayers() []*Player {
	if x != nil {
		return x.Players
	}
	return nil
}

// Input from a client (e.g., movement direction)
type PlayerInput struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Direction PlayerInput_Direction `protobuf:"varint,1,opt,name=direction,proto3,enum=game.PlayerInput_Direction" json:"direction,omitempty"` // Could add delta time or magnitude later
}

func (x *PlayerInput) Reset() {
	*x = PlayerInput{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[2]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *PlayerInput) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*PlayerInput) ProtoMessage() {}

func (x *PlayerInput) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[2]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use PlayerInput.ProtoReflect.Descriptor instead.
func (*PlayerInput) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{2}
}

func (x *PlayerInput) GetDirection() PlayerInput_Direction {
	if x != nil {
		return x.Direction
	}
	return PlayerInput_UNKNOWN
}

// Empty message often useful for simple notifications or stream triggers
type Empty struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields
}

func (x *Empty) Reset() {
	*x = Empty{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[3]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *Empty) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*Empty) ProtoMessage() {}

func (x *Empty) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[3]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use Empty.ProtoReflect.Descriptor instead.
func (*Empty) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{3}
}

type MapRow struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Tiles []int32 `protobuf:"varint,1,rep,packed,name=tiles,proto3" json:"tiles,omitempty"`
}

func (x *MapRow) Reset() {
	*x = MapRow{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[4]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *MapRow) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MapRow) ProtoMessage() {}

func (x *MapRow) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[4]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use MapRow.ProtoReflect.Descriptor instead.
func (*MapRow) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{4}
}

func (x *MapRow) GetTiles() []int32 {
	if x != nil {
		return x.Tiles
	}
	return nil
}

type InitialMapData struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Rows       []*MapRow `protobuf:"bytes,1,rep,name=rows,proto3" json:"rows,omitempty"`
	TileWidth  int32     `protobuf:"varint,2,opt,name=tile_width,json=tileWidth,proto3" json:"tile_width,omitempty"`
	TileHeight int32     `protobuf:"varint,3,opt,name=tile_height,json=tileHeight,proto3" json:"tile_height,omitempty"`
}

func (x *InitialMapData) Reset() {
	*x = InitialMapData{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[5]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *InitialMapData) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*InitialMapData) ProtoMessage() {}

func (x *InitialMapData) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[5]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use InitialMapData.ProtoReflect.Descriptor instead.
func (*InitialMapData) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{5}
}

func (x *InitialMapData) GetRows() []*MapRow {
	if x != nil {
		return x.Rows
	}
	return nil
}

func (x *InitialMapData) GetTileWidth() int32 {
	if x != nil {
		return x.TileWidth
	}
	return 0
}

func (x *InitialMapData) GetTileHeight() int32 {
	if x != nil {
		return x.TileHeight
	}
	return 0
}

type ServerMessage struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Types that are assignable to Message:
	//
	//	*ServerMessage_InitialMapData
	//	*ServerMessage_GameState
	Message isServerMessage_Message `protobuf_oneof:"message"`
}

func (x *ServerMessage) Reset() {
	*x = ServerMessage{}
	if protoimpl.UnsafeEnabled {
		mi := &file_game_proto_msgTypes[6]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ServerMessage) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ServerMessage) ProtoMessage() {}

func (x *ServerMessage) ProtoReflect() protoreflect.Message {
	mi := &file_game_proto_msgTypes[6]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ServerMessage.ProtoReflect.Descriptor instead.
func (*ServerMessage) Descriptor() ([]byte, []int) {
	return file_game_proto_rawDescGZIP(), []int{6}
}

func (m *ServerMessage) GetMessage() isServerMessage_Message {
	if m != nil {
		return m.Message
	}
	return nil
}

func (x *ServerMessage) GetInitialMapData() *InitialMapData {
	if x, ok := x.GetMessage().(*ServerMessage_InitialMapData); ok {
		return x.InitialMapData
	}
	return nil
}

func (x *ServerMessage) GetGameState() *GameState {
	if x, ok := x.GetMessage().(*ServerMessage_GameState); ok {
		return x.GameState
	}
	return nil
}

type isServerMessage_Message interface {
	isServerMessage_Message()
}

type ServerMessage_InitialMapData struct {
	InitialMapData *InitialMapData `protobuf:"bytes,1,opt,name=initial_map_data,json=initialMapData,proto3,oneof"`
}

type ServerMessage_GameState struct {
	GameState *GameState `protobuf:"bytes,2,opt,name=game_state,json=gameState,proto3,oneof"`
}

func (*ServerMessage_InitialMapData) isServerMessage_Message() {}

func (*ServerMessage_GameState) isServerMessage_Message() {}

var File_game_proto protoreflect.FileDescriptor

var file_game_proto_rawDesc = []byte{
	0x0a, 0x0a, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x12, 0x04, 0x67, 0x61,
	0x6d, 0x65, 0x22, 0x42, 0x0a, 0x06, 0x50, 0x6c, 0x61, 0x79, 0x65, 0x72, 0x12, 0x0e, 0x0a, 0x02,
	0x69, 0x64, 0x18, 0x01, 0x20, 0x01, 0x28, 0x09, 0x52, 0x02, 0x69, 0x64, 0x12, 0x13, 0x0a, 0x05,
	0x78, 0x5f, 0x70, 0x6f, 0x73, 0x18, 0x02, 0x20, 0x01, 0x28, 0x02, 0x52, 0x04, 0x78, 0x50, 0x6f,
	0x73, 0x12, 0x13, 0x0a, 0x05, 0x79, 0x5f, 0x70, 0x6f, 0x73, 0x18, 0x03, 0x20, 0x01, 0x28, 0x02,
	0x52, 0x04, 0x79, 0x50, 0x6f, 0x73, 0x22, 0x33, 0x0a, 0x09, 0x47, 0x61, 0x6d, 0x65, 0x53, 0x74,
	0x61, 0x74, 0x65, 0x12, 0x26, 0x0a, 0x07, 0x70, 0x6c, 0x61, 0x79, 0x65, 0x72, 0x73, 0x18, 0x01,
	0x20, 0x03, 0x28, 0x0b, 0x32, 0x0c, 0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x50, 0x6c, 0x61, 0x79,
	0x65, 0x72, 0x52, 0x07, 0x70, 0x6c, 0x61, 0x79, 0x65, 0x72, 0x73, 0x22, 0x89, 0x01, 0x0a, 0x0b,
	0x50, 0x6c, 0x61, 0x79, 0x65, 0x72, 0x49, 0x6e, 0x70, 0x75, 0x74, 0x12, 0x39, 0x0a, 0x09, 0x64,
	0x69, 0x72, 0x65, 0x63, 0x74, 0x69, 0x6f, 0x6e, 0x18, 0x01, 0x20, 0x01, 0x28, 0x0e, 0x32, 0x1b,
	0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x50, 0x6c, 0x61, 0x79, 0x65, 0x72, 0x49, 0x6e, 0x70, 0x75,
	0x74, 0x2e, 0x44, 0x69, 0x72, 0x65, 0x63, 0x74, 0x69, 0x6f, 0x6e, 0x52, 0x09, 0x64, 0x69, 0x72,
	0x65, 0x63, 0x74, 0x69, 0x6f, 0x6e, 0x22, 0x3f, 0x0a, 0x09, 0x44, 0x69, 0x72, 0x65, 0x63, 0x74,
	0x69, 0x6f, 0x6e, 0x12, 0x0b, 0x0a, 0x07, 0x55, 0x4e, 0x4b, 0x4e, 0x4f, 0x57, 0x4e, 0x10, 0x00,
	0x12, 0x06, 0x0a, 0x02, 0x55, 0x50, 0x10, 0x01, 0x12, 0x08, 0x0a, 0x04, 0x44, 0x4f, 0x57, 0x4e,
	0x10, 0x02, 0x12, 0x08, 0x0a, 0x04, 0x4c, 0x45, 0x46, 0x54, 0x10, 0x03, 0x12, 0x09, 0x0a, 0x05,
	0x52, 0x49, 0x47, 0x48, 0x54, 0x10, 0x04, 0x22, 0x07, 0x0a, 0x05, 0x45, 0x6d, 0x70, 0x74, 0x79,
	0x22, 0x1e, 0x0a, 0x06, 0x4d, 0x61, 0x70, 0x52, 0x6f, 0x77, 0x12, 0x14, 0x0a, 0x05, 0x74, 0x69,
	0x6c, 0x65, 0x73, 0x18, 0x01, 0x20, 0x03, 0x28, 0x05, 0x52, 0x05, 0x74, 0x69, 0x6c, 0x65, 0x73,
	0x22, 0x72, 0x0a, 0x0e, 0x49, 0x6e, 0x69, 0x74, 0x69, 0x61, 0x6c, 0x4d, 0x61, 0x70, 0x44, 0x61,
	0x74, 0x61, 0x12, 0x20, 0x0a, 0x04, 0x72, 0x6f, 0x77, 0x73, 0x18, 0x01, 0x20, 0x03, 0x28, 0x0b,
	0x32, 0x0c, 0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x4d, 0x61, 0x70, 0x52, 0x6f, 0x77, 0x52, 0x04,
	0x72, 0x6f, 0x77, 0x73, 0x12, 0x1d, 0x0a, 0x0a, 0x74, 0x69, 0x6c, 0x65, 0x5f, 0x77, 0x69, 0x64,
	0x74, 0x68, 0x18, 0x02, 0x20, 0x01, 0x28, 0x05, 0x52, 0x09, 0x74, 0x69, 0x6c, 0x65, 0x57, 0x69,
	0x64, 0x74, 0x68, 0x12, 0x1f, 0x0a, 0x0b, 0x74, 0x69, 0x6c, 0x65, 0x5f, 0x68, 0x65, 0x69, 0x67,
	0x68, 0x74, 0x18, 0x03, 0x20, 0x01, 0x28, 0x05, 0x52, 0x0a, 0x74, 0x69, 0x6c, 0x65, 0x48, 0x65,
	0x69, 0x67, 0x68, 0x74, 0x22, 0x8e, 0x01, 0x0a, 0x0d, 0x53, 0x65, 0x72, 0x76, 0x65, 0x72, 0x4d,
	0x65, 0x73, 0x73, 0x61, 0x67, 0x65, 0x12, 0x40, 0x0a, 0x10, 0x69, 0x6e, 0x69, 0x74, 0x69, 0x61,
	0x6c, 0x5f, 0x6d, 0x61, 0x70, 0x5f, 0x64, 0x61, 0x74, 0x61, 0x18, 0x01, 0x20, 0x01, 0x28, 0x0b,
	0x32, 0x14, 0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x49, 0x6e, 0x69, 0x74, 0x69, 0x61, 0x6c, 0x4d,
	0x61, 0x70, 0x44, 0x61, 0x74, 0x61, 0x48, 0x00, 0x52, 0x0e, 0x69, 0x6e, 0x69, 0x74, 0x69, 0x61,
	0x6c, 0x4d, 0x61, 0x70, 0x44, 0x61, 0x74, 0x61, 0x12, 0x30, 0x0a, 0x0a, 0x67, 0x61, 0x6d, 0x65,
	0x5f, 0x73, 0x74, 0x61, 0x74, 0x65, 0x18, 0x02, 0x20, 0x01, 0x28, 0x0b, 0x32, 0x0f, 0x2e, 0x67,
	0x61, 0x6d, 0x65, 0x2e, 0x47, 0x61, 0x6d, 0x65, 0x53, 0x74, 0x61, 0x74, 0x65, 0x48, 0x00, 0x52,
	0x09, 0x67, 0x61, 0x6d, 0x65, 0x53, 0x74, 0x61, 0x74, 0x65, 0x42, 0x09, 0x0a, 0x07, 0x6d, 0x65,
	0x73, 0x73, 0x61, 0x67, 0x65, 0x32, 0x47, 0x0a, 0x0b, 0x47, 0x61, 0x6d, 0x65, 0x53, 0x65, 0x72,
	0x76, 0x69, 0x63, 0x65, 0x12, 0x38, 0x0a, 0x0a, 0x47, 0x61, 0x6d, 0x65, 0x53, 0x74, 0x72, 0x65,
	0x61, 0x6d, 0x12, 0x11, 0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x50, 0x6c, 0x61, 0x79, 0x65, 0x72,
	0x49, 0x6e, 0x70, 0x75, 0x74, 0x1a, 0x13, 0x2e, 0x67, 0x61, 0x6d, 0x65, 0x2e, 0x53, 0x65, 0x72,
	0x76, 0x65, 0x72, 0x4d, 0x65, 0x73, 0x73, 0x61, 0x67, 0x65, 0x28, 0x01, 0x30, 0x01, 0x42, 0x1e,
	0x5a, 0x1c, 0x73, 0x69, 0x6d, 0x70, 0x6c, 0x65, 0x2d, 0x67, 0x72, 0x70, 0x63, 0x2d, 0x67, 0x61,
	0x6d, 0x65, 0x2f, 0x67, 0x65, 0x6e, 0x2f, 0x67, 0x6f, 0x2f, 0x67, 0x61, 0x6d, 0x65, 0x62, 0x06,
	0x70, 0x72, 0x6f, 0x74, 0x6f, 0x33,
}

var (
	file_game_proto_rawDescOnce sync.Once
	file_game_proto_rawDescData = file_game_proto_rawDesc
)

func file_game_proto_rawDescGZIP() []byte {
	file_game_proto_rawDescOnce.Do(func() {
		file_game_proto_rawDescData = protoimpl.X.CompressGZIP(file_game_proto_rawDescData)
	})
	return file_game_proto_rawDescData
}

var file_game_proto_enumTypes = make([]protoimpl.EnumInfo, 1)
var file_game_proto_msgTypes = make([]protoimpl.MessageInfo, 7)
var file_game_proto_goTypes = []interface{}{
	(PlayerInput_Direction)(0), // 0: game.PlayerInput.Direction
	(*Player)(nil),             // 1: game.Player
	(*GameState)(nil),          // 2: game.GameState
	(*PlayerInput)(nil),        // 3: game.PlayerInput
	(*Empty)(nil),              // 4: game.Empty
	(*MapRow)(nil),             // 5: game.MapRow
	(*InitialMapData)(nil),     // 6: game.InitialMapData
	(*ServerMessage)(nil),      // 7: game.ServerMessage
}
var file_game_proto_depIdxs = []int32{
	1, // 0: game.GameState.players:type_name -> game.Player
	0, // 1: game.PlayerInput.direction:type_name -> game.PlayerInput.Direction
	5, // 2: game.InitialMapData.rows:type_name -> game.MapRow
	6, // 3: game.ServerMessage.initial_map_data:type_name -> game.InitialMapData
	2, // 4: game.ServerMessage.game_state:type_name -> game.GameState
	3, // 5: game.GameService.GameStream:input_type -> game.PlayerInput
	7, // 6: game.GameService.GameStream:output_type -> game.ServerMessage
	6, // [6:7] is the sub-list for method output_type
	5, // [5:6] is the sub-list for method input_type
	5, // [5:5] is the sub-list for extension type_name
	5, // [5:5] is the sub-list for extension extendee
	0, // [0:5] is the sub-list for field type_name
}

func init() { file_game_proto_init() }
func file_game_proto_init() {
	if File_game_proto != nil {
		return
	}
	if !protoimpl.UnsafeEnabled {
		file_game_proto_msgTypes[0].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*Player); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[1].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*GameState); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[2].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*PlayerInput); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[3].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*Empty); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[4].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*MapRow); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[5].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*InitialMapData); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_game_proto_msgTypes[6].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ServerMessage); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
	}
	file_game_proto_msgTypes[6].OneofWrappers = []interface{}{
		(*ServerMessage_InitialMapData)(nil),
		(*ServerMessage_GameState)(nil),
	}
	type x struct{}
	out := protoimpl.TypeBuilder{
		File: protoimpl.DescBuilder{
			GoPackagePath: reflect.TypeOf(x{}).PkgPath(),
			RawDescriptor: file_game_proto_rawDesc,
			NumEnums:      1,
			NumMessages:   7,
			NumExtensions: 0,
			NumServices:   1,
		},
		GoTypes:           file_game_proto_goTypes,
		DependencyIndexes: file_game_proto_depIdxs,
		EnumInfos:         file_game_proto_enumTypes,
		MessageInfos:      file_game_proto_msgTypes,
	}.Build()
	File_game_proto = out.File
	file_game_proto_rawDesc = nil
	file_game_proto_goTypes = nil
	file_game_proto_depIdxs = nil
}
