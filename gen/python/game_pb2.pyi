from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AnimationState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN_STATE: _ClassVar[AnimationState]
    IDLE: _ClassVar[AnimationState]
    RUNNING_UP: _ClassVar[AnimationState]
    RUNNING_DOWN: _ClassVar[AnimationState]
    RUNNING_LEFT: _ClassVar[AnimationState]
    RUNNING_RIGHT: _ClassVar[AnimationState]
UNKNOWN_STATE: AnimationState
IDLE: AnimationState
RUNNING_UP: AnimationState
RUNNING_DOWN: AnimationState
RUNNING_LEFT: AnimationState
RUNNING_RIGHT: AnimationState

class Player(_message.Message):
    __slots__ = ("id", "x_pos", "y_pos", "current_animation_state", "username")
    ID_FIELD_NUMBER: _ClassVar[int]
    X_POS_FIELD_NUMBER: _ClassVar[int]
    Y_POS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_ANIMATION_STATE_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    id: str
    x_pos: float
    y_pos: float
    current_animation_state: AnimationState
    username: str
    def __init__(self, id: _Optional[str] = ..., x_pos: _Optional[float] = ..., y_pos: _Optional[float] = ..., current_animation_state: _Optional[_Union[AnimationState, str]] = ..., username: _Optional[str] = ...) -> None: ...

class GameState(_message.Message):
    __slots__ = ("players",)
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class PlayerInput(_message.Message):
    __slots__ = ("direction",)
    class Direction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[PlayerInput.Direction]
        UP: _ClassVar[PlayerInput.Direction]
        DOWN: _ClassVar[PlayerInput.Direction]
        LEFT: _ClassVar[PlayerInput.Direction]
        RIGHT: _ClassVar[PlayerInput.Direction]
    UNKNOWN: PlayerInput.Direction
    UP: PlayerInput.Direction
    DOWN: PlayerInput.Direction
    LEFT: PlayerInput.Direction
    RIGHT: PlayerInput.Direction
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    direction: PlayerInput.Direction
    def __init__(self, direction: _Optional[_Union[PlayerInput.Direction, str]] = ...) -> None: ...

class MapRow(_message.Message):
    __slots__ = ("tiles",)
    TILES_FIELD_NUMBER: _ClassVar[int]
    tiles: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, tiles: _Optional[_Iterable[int]] = ...) -> None: ...

class InitialMapData(_message.Message):
    __slots__ = ("rows", "tile_width", "tile_height", "world_pixel_height", "world_pixel_width", "tile_size_pixels", "assigned_player_id")
    ROWS_FIELD_NUMBER: _ClassVar[int]
    TILE_WIDTH_FIELD_NUMBER: _ClassVar[int]
    TILE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    WORLD_PIXEL_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    WORLD_PIXEL_WIDTH_FIELD_NUMBER: _ClassVar[int]
    TILE_SIZE_PIXELS_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    rows: _containers.RepeatedCompositeFieldContainer[MapRow]
    tile_width: int
    tile_height: int
    world_pixel_height: float
    world_pixel_width: float
    tile_size_pixels: int
    assigned_player_id: str
    def __init__(self, rows: _Optional[_Iterable[_Union[MapRow, _Mapping]]] = ..., tile_width: _Optional[int] = ..., tile_height: _Optional[int] = ..., world_pixel_height: _Optional[float] = ..., world_pixel_width: _Optional[float] = ..., tile_size_pixels: _Optional[int] = ..., assigned_player_id: _Optional[str] = ...) -> None: ...

class DeltaUpdate(_message.Message):
    __slots__ = ("updated_players", "removed_player_ids")
    UPDATED_PLAYERS_FIELD_NUMBER: _ClassVar[int]
    REMOVED_PLAYER_IDS_FIELD_NUMBER: _ClassVar[int]
    updated_players: _containers.RepeatedCompositeFieldContainer[Player]
    removed_player_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, updated_players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ..., removed_player_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class ServerMessage(_message.Message):
    __slots__ = ("initial_map_data", "delta_update")
    INITIAL_MAP_DATA_FIELD_NUMBER: _ClassVar[int]
    DELTA_UPDATE_FIELD_NUMBER: _ClassVar[int]
    initial_map_data: InitialMapData
    delta_update: DeltaUpdate
    def __init__(self, initial_map_data: _Optional[_Union[InitialMapData, _Mapping]] = ..., delta_update: _Optional[_Union[DeltaUpdate, _Mapping]] = ...) -> None: ...

class ClientHello(_message.Message):
    __slots__ = ("desired_username",)
    DESIRED_USERNAME_FIELD_NUMBER: _ClassVar[int]
    desired_username: str
    def __init__(self, desired_username: _Optional[str] = ...) -> None: ...

class ClientMessage(_message.Message):
    __slots__ = ("player_input", "client_hello")
    PLAYER_INPUT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_HELLO_FIELD_NUMBER: _ClassVar[int]
    player_input: PlayerInput
    client_hello: ClientHello
    def __init__(self, player_input: _Optional[_Union[PlayerInput, _Mapping]] = ..., client_hello: _Optional[_Union[ClientHello, _Mapping]] = ...) -> None: ...
