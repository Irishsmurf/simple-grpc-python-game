# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: game.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'game.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\ngame.proto\x12\x04game\"{\n\x06Player\x12\n\n\x02id\x18\x01 \x01(\t\x12\r\n\x05x_pos\x18\x02 \x01(\x02\x12\r\n\x05y_pos\x18\x03 \x01(\x02\x12\x35\n\x17\x63urrent_animation_state\x18\x04 \x01(\x0e\x32\x14.game.AnimationState\x12\x10\n\x08username\x18\x05 \x01(\t\"*\n\tGameState\x12\x1d\n\x07players\x18\x01 \x03(\x0b\x32\x0c.game.Player\"~\n\x0bPlayerInput\x12.\n\tdirection\x18\x01 \x01(\x0e\x32\x1b.game.PlayerInput.Direction\"?\n\tDirection\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x06\n\x02UP\x10\x01\x12\x08\n\x04\x44OWN\x10\x02\x12\x08\n\x04LEFT\x10\x03\x12\t\n\x05RIGHT\x10\x04\"\x17\n\x06MapRow\x12\r\n\x05tiles\x18\x01 \x03(\x05\"\xc2\x01\n\x0eInitialMapData\x12\x1a\n\x04rows\x18\x01 \x03(\x0b\x32\x0c.game.MapRow\x12\x12\n\ntile_width\x18\x02 \x01(\x05\x12\x13\n\x0btile_height\x18\x03 \x01(\x05\x12\x1a\n\x12world_pixel_height\x18\x04 \x01(\x02\x12\x19\n\x11world_pixel_width\x18\x05 \x01(\x02\x12\x18\n\x10tile_size_pixels\x18\x06 \x01(\x05\x12\x1a\n\x12\x61ssigned_player_id\x18\x07 \x01(\t\"P\n\x0b\x44\x65ltaUpdate\x12%\n\x0fupdated_players\x18\x01 \x03(\x0b\x32\x0c.game.Player\x12\x1a\n\x12removed_player_ids\x18\x02 \x03(\t\"w\n\rServerMessage\x12\x30\n\x10initial_map_data\x18\x01 \x01(\x0b\x32\x14.game.InitialMapDataH\x00\x12)\n\x0c\x64\x65lta_update\x18\x03 \x01(\x0b\x32\x11.game.DeltaUpdateH\x00\x42\t\n\x07message\"\'\n\x0b\x43lientHello\x12\x18\n\x10\x64\x65sired_username\x18\x01 \x01(\t\"w\n\rClientMessage\x12)\n\x0cplayer_input\x18\x01 \x01(\x0b\x32\x11.game.PlayerInputH\x00\x12)\n\x0c\x63lient_hello\x18\x02 \x01(\x0b\x32\x11.game.ClientHelloH\x00\x42\x10\n\x0e\x63lient_message*t\n\x0e\x41nimationState\x12\x11\n\rUNKNOWN_STATE\x10\x00\x12\x08\n\x04IDLE\x10\x01\x12\x0e\n\nRUNNING_UP\x10\x02\x12\x10\n\x0cRUNNING_DOWN\x10\x03\x12\x10\n\x0cRUNNING_LEFT\x10\x04\x12\x11\n\rRUNNING_RIGHT\x10\x05\x32I\n\x0bGameService\x12:\n\nGameStream\x12\x13.game.ClientMessage\x1a\x13.game.ServerMessage(\x01\x30\x01\x42\x1eZ\x1csimple-grpc-game/gen/go/gameb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'game_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  _globals['DESCRIPTOR']._loaded_options = None
  _globals['DESCRIPTOR']._serialized_options = b'Z\034simple-grpc-game/gen/go/game'
  _globals['_ANIMATIONSTATE']._serialized_start=904
  _globals['_ANIMATIONSTATE']._serialized_end=1020
  _globals['_PLAYER']._serialized_start=20
  _globals['_PLAYER']._serialized_end=143
  _globals['_GAMESTATE']._serialized_start=145
  _globals['_GAMESTATE']._serialized_end=187
  _globals['_PLAYERINPUT']._serialized_start=189
  _globals['_PLAYERINPUT']._serialized_end=315
  _globals['_PLAYERINPUT_DIRECTION']._serialized_start=252
  _globals['_PLAYERINPUT_DIRECTION']._serialized_end=315
  _globals['_MAPROW']._serialized_start=317
  _globals['_MAPROW']._serialized_end=340
  _globals['_INITIALMAPDATA']._serialized_start=343
  _globals['_INITIALMAPDATA']._serialized_end=537
  _globals['_DELTAUPDATE']._serialized_start=539
  _globals['_DELTAUPDATE']._serialized_end=619
  _globals['_SERVERMESSAGE']._serialized_start=621
  _globals['_SERVERMESSAGE']._serialized_end=740
  _globals['_CLIENTHELLO']._serialized_start=742
  _globals['_CLIENTHELLO']._serialized_end=781
  _globals['_CLIENTMESSAGE']._serialized_start=783
  _globals['_CLIENTMESSAGE']._serialized_end=902
  _globals['_GAMESERVICE']._serialized_start=1022
  _globals['_GAMESERVICE']._serialized_end=1095
# @@protoc_insertion_point(module_scope)
