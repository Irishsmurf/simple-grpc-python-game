// Code generated by protoc-gen-go-grpc. DO NOT EDIT.
// versions:
// - protoc-gen-go-grpc v1.2.0
// - protoc             v3.6.1
// source: game.proto

package game

import (
	context "context"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
)

// This is a compile-time assertion to ensure that this generated file
// is compatible with the grpc package it is being compiled against.
// Requires gRPC-Go v1.32.0 or later.
const _ = grpc.SupportPackageIsVersion7

// GameServiceClient is the client API for GameService service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://pkg.go.dev/google.golang.org/grpc/?tab=doc#ClientConn.NewStream.
type GameServiceClient interface {
	// A bidirectional stream for real-time game updates and input
	GameStream(ctx context.Context, opts ...grpc.CallOption) (GameService_GameStreamClient, error)
}

type gameServiceClient struct {
	cc grpc.ClientConnInterface
}

func NewGameServiceClient(cc grpc.ClientConnInterface) GameServiceClient {
	return &gameServiceClient{cc}
}

func (c *gameServiceClient) GameStream(ctx context.Context, opts ...grpc.CallOption) (GameService_GameStreamClient, error) {
	stream, err := c.cc.NewStream(ctx, &GameService_ServiceDesc.Streams[0], "/game.GameService/GameStream", opts...)
	if err != nil {
		return nil, err
	}
	x := &gameServiceGameStreamClient{stream}
	return x, nil
}

type GameService_GameStreamClient interface {
	Send(*PlayerInput) error
	Recv() (*ServerMessage, error)
	grpc.ClientStream
}

type gameServiceGameStreamClient struct {
	grpc.ClientStream
}

func (x *gameServiceGameStreamClient) Send(m *PlayerInput) error {
	return x.ClientStream.SendMsg(m)
}

func (x *gameServiceGameStreamClient) Recv() (*ServerMessage, error) {
	m := new(ServerMessage)
	if err := x.ClientStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

// GameServiceServer is the server API for GameService service.
// All implementations must embed UnimplementedGameServiceServer
// for forward compatibility
type GameServiceServer interface {
	// A bidirectional stream for real-time game updates and input
	GameStream(GameService_GameStreamServer) error
	mustEmbedUnimplementedGameServiceServer()
}

// UnimplementedGameServiceServer must be embedded to have forward compatible implementations.
type UnimplementedGameServiceServer struct {
}

func (UnimplementedGameServiceServer) GameStream(GameService_GameStreamServer) error {
	return status.Errorf(codes.Unimplemented, "method GameStream not implemented")
}
func (UnimplementedGameServiceServer) mustEmbedUnimplementedGameServiceServer() {}

// UnsafeGameServiceServer may be embedded to opt out of forward compatibility for this service.
// Use of this interface is not recommended, as added methods to GameServiceServer will
// result in compilation errors.
type UnsafeGameServiceServer interface {
	mustEmbedUnimplementedGameServiceServer()
}

func RegisterGameServiceServer(s grpc.ServiceRegistrar, srv GameServiceServer) {
	s.RegisterService(&GameService_ServiceDesc, srv)
}

func _GameService_GameStream_Handler(srv interface{}, stream grpc.ServerStream) error {
	return srv.(GameServiceServer).GameStream(&gameServiceGameStreamServer{stream})
}

type GameService_GameStreamServer interface {
	Send(*ServerMessage) error
	Recv() (*PlayerInput, error)
	grpc.ServerStream
}

type gameServiceGameStreamServer struct {
	grpc.ServerStream
}

func (x *gameServiceGameStreamServer) Send(m *ServerMessage) error {
	return x.ServerStream.SendMsg(m)
}

func (x *gameServiceGameStreamServer) Recv() (*PlayerInput, error) {
	m := new(PlayerInput)
	if err := x.ServerStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

// GameService_ServiceDesc is the grpc.ServiceDesc for GameService service.
// It's only intended for direct use with grpc.RegisterService,
// and not to be introspected or modified (even as a copy)
var GameService_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "game.GameService",
	HandlerType: (*GameServiceServer)(nil),
	Methods:     []grpc.MethodDesc{},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "GameStream",
			Handler:       _GameService_GameStream_Handler,
			ServerStreams: true,
			ClientStreams: true,
		},
	},
	Metadata: "game.proto",
}
