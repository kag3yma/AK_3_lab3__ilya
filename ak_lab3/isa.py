import json
from dataclasses import dataclass, asdict
from enum import StrEnum, auto, Enum
from typing import Optional


IO_ADDR = 255


class Opcode(StrEnum):
    NOP = auto()
    LIT = auto()

    LOAD = auto()
    SAVE = auto()

    DUP = auto()
    OVER = auto()
    POP = auto()
    SWAP = auto()

    ADD = auto()
    SUB = auto()
    DIV = auto()
    MUL = auto()
    INC = auto()
    DEC = auto()

    AND = auto()
    OR = auto()
    XOR = auto()
    INV = auto()
    NEG = auto()

    GT = auto()
    JMP = auto()
    JNZ = auto()
    JZ = auto()

    CALL = auto()
    RET = auto()

    HLT = auto()


@dataclass(frozen=True)
class Label:
    name: str


@dataclass
class Instruction:
    opcode: Opcode
    arg: Optional[int | str | Label] = None

    def to_dict(self):
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}

    @staticmethod
    def from_dict(data: dict):
        assert "opcode" in data, "Parsing Instruction failed! Check translator"
        return Instruction(data["opcode"], data["arg"] if "arg" in data else None)

    def __str__(self) -> str:
        return str(self.to_dict())


class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Instruction):
            return o.to_dict()
        if isinstance(o, Enum):
            return o.value
        return json.JSONEncoder.default(self, o)


def write_code(filename: str, code: list, data: list, start_addr: int) -> None:
    file_data = {
        "code": code,
        "data": data,
        "start": start_addr
    }
    with open(filename, "w", encoding="utf-8") as file:
        file.write(json.dumps(file_data, cls=CustomEncoder, indent=2))


def read_code(filename: str) -> tuple[list[dict], list[int], int]:
    with open(filename, encoding="utf-8") as file:
        data = json.load(file)
    return data["code"], data["data"], data["start"]
