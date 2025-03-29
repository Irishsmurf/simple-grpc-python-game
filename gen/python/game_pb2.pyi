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
    __slots__ = ("id", "x_pos", "y_pos", "current_animation_state")
    ID_FIELD_NUMBER: _ClassVar[int]
    X_POS_FIELD_NUMBER: _ClassVar[int]
    Y_POS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_ANIMATION_STATE_FIELD_NUMBER: _ClassVar[int]
    id: str
    x_pos: float
    y_pos: float
    current_animation_state: AnimationState
    def __init__(self, id: _Optional[str] = ..., x_pos: _Optional[float] = ..., y_pos: _Optional[float] = ..., current_animation_state: _Optional[_Union[AnimationState, str]] = ...) -> None: ...

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

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class MapRow(_message.Message):
    __slots__ = ("tiles",)
    TILES_FIELD_NUMBER: _ClassVar[int]
    tiles: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, tiles: _Optional[_Iterable[int]] = ...) -> None: ...

class InitialMapData(_message.Message):
    __slots__ = ("rows", "tile_width", "tile_height", "world_pixel_height", "world_pixel_width", "tile_size_pixels")
    ROWS_FIELD_NUMBER: _ClassVar[int]
    TILE_WIDTH_FIELD_NUMBER: _ClassVar[int]
    TILE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    WORLD_PIXEL_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    WORLD_PIXEL_WIDTH_FIELD_NUMBER: _ClassVar[int]
    TILE_SIZE_PIXELS_FIELD_NUMBER: _ClassVar[int]
    rows: _containers.RepeatedCompositeFieldContainer[MapRow]
    tile_width: int
    tile_height: int
    world_pixel_height: float
    world_pixel_width: float
    tile_size_pixels: int
    def __init__(self, rows: _Optional[_Iterable[_Union[MapRow, _Mapping]]] = ..., tile_width: _Optional[int] = ..., tile_height: _Optional[int] = ..., world_pixel_height: _Optional[float] = ..., world_pixel_width: _Optional[float] = ..., tile_size_pixels: _Optional[int] = ...) -> None: ...

class ServerMessage(_message.Message):
    __slots__ = ("initial_map_data", "game_state")
    INITIAL_MAP_DATA_FIELD_NUMBER: _ClassVar[int]
    GAME_STATE_FIELD_NUMBER: _ClassVar[int]
    initial_map_data: InitialMapData
    game_state: GameState
    def __init__(self, initial_map_data: _Optional[_Union[InitialMapData, _Mapping]] = ..., game_state: _Optional[_Union[GameState, _Mapping]] = ...) -> None: ...
