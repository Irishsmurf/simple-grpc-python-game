from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Player(_message.Message):
    __slots__ = ("id", "x_pos", "y_pos")
    ID_FIELD_NUMBER: _ClassVar[int]
    X_POS_FIELD_NUMBER: _ClassVar[int]
    Y_POS_FIELD_NUMBER: _ClassVar[int]
    id: str
    x_pos: float
    y_pos: float
    def __init__(self, id: _Optional[str] = ..., x_pos: _Optional[float] = ..., y_pos: _Optional[float] = ...) -> None: ...

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
