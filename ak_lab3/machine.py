import argparse
import logging
from collections import deque
from enum import StrEnum, auto

from ak_lab3.isa import Instruction, Opcode, read_code, IO_ADDR


class AluOperation(StrEnum):
    DIV = auto()
    SUB = auto()
    MUL = auto()
    ADD = auto()
    DEC = auto()
    INC = auto()
    OR = auto()
    AND = auto()
    INV = auto()
    XOR = auto()
    NEG = auto()


class AluInputMux(StrEnum):
    ZERO = auto()
    TOS = auto()


DATA_MEMORY_SIZE = 255
INSTR_MEMORY_SIZE = 255
STACK_SIZE = 100
RETURN_STACK_SIZE = 100


class IO:
    def __init__(self, input_buffer: list[int], is_int_io: bool):
        self.is_int_io = is_int_io
        self.output = ""
        self.input_buffer = deque(input_buffer)

    def write_byte(self, b: int):
        if self.is_int_io:
            self.output += str(b)
        elif b == 0:
            self.output += "\n"
        else:
            self.output += chr(b)

    def read_byte(self) -> int:
        if len(self.input_buffer) == 0:
            raise EOFError("Input is over")
        return self.input_buffer.popleft()

    def __repr__(self) -> str:
        return f"{map(chr, self.input_buffer)}, {self.output}"


class DataPath:
    ar: int = 0

    def __init__(self, data: list[int], mmio: dict[int, IO]):
        self.memory = data
        self.stack: list[int] = [0, 0]
        self.mmio = mmio

    def signal_pop(self):
        self.stack.pop()

    def signal_push(self, value: int):
        assert len(self.stack) <= STACK_SIZE, "Stack overflow"
        self.stack.append(value)

    def signal_write_second(self, value: int):
        self.stack[-2] = value

    def signal_write_first(self, value: int):
        self.stack[-1] = value

    def signal_read_memory(self) -> int:
        if self.ar in self.mmio:
            return self.mmio[self.ar].read_byte()
        data = self.memory[self.ar]
        return data

    def signal_write_memory(self, value: int):
        if self.ar in self.mmio:
            self.mmio[self.ar].write_byte(value)
            return
        self.memory[self.ar] = value

    def signal_latch_ar(self, value: int):
        self.ar = value

    def perform_alu_operation(
            self, alu_operation: AluOperation, left_mux: AluInputMux, right_mux: AluInputMux
    ) -> int:
        left = 0 if left_mux == AluInputMux.ZERO else self._get_first()
        right = 0 if right_mux == AluInputMux.ZERO else self._get_second()
        output_value: int
        match alu_operation:
            case AluOperation.ADD:
                output_value = left + right
            case AluOperation.SUB:
                output_value = right - left
            case AluOperation.MUL:
                output_value = left * right
            case AluOperation.DIV:
                output_value = right // left
            case AluOperation.XOR:
                output_value = left ^ right
            case AluOperation.INC:
                output_value = left + 1
            case AluOperation.DEC:
                output_value = left - 1
            case AluOperation.INV:
                output_value = -1 if left == 0 else 0
            case AluOperation.AND:
                output_value = left & right
            case AluOperation.OR:
                output_value = left | right
            case AluOperation.NEG:
                output_value = ~left + 1
            case _:
                raise NotImplementedError()
        return output_value

    def _get_first(self):
        return self.stack[-1]

    def _get_second(self):
        return self.stack[-2]

    def z_flag(self) -> bool:
        return self._get_first() == 0

    def n_flag(self) -> bool:
        return self._get_first() > 0


class ControlUnit: #pylint: disable=too-many-public-methods
    pc: int = 0
    _tick: int = 0

    def __init__(self, program: list[Instruction], data_path: DataPath):
        self.program = program
        self.data_path = data_path
        self.return_stack: list[int] = []

    def tick(self):
        self._tick += 1

    def current_tick(self):
        return self._tick

    def initialize_pc(self, start: int):
        self.pc = start

    def read_instruction_memory(self):
        return self.program[self.pc]

    def latch_pc(self, value: int):
        self.pc = value

    def push_pc(self):
        self.return_stack.append(self.pc)

    def pop_pc(self):
        self.pc = self.return_stack.pop()

    def decode_and_execute_instruction(self): # pylint: disable=too-many-branches
        instruction = self.read_instruction_memory()
        self.tick()
        self.latch_pc(self.pc + 1)
        self.tick()
        if instruction.opcode == Opcode.NOP:
            pass
        elif instruction.opcode == Opcode.LIT:
            self.execute_lit(instruction)
        elif instruction.opcode == Opcode.LOAD:
            self.execute_load()
        elif instruction.opcode == Opcode.SAVE:
            self.execute_save()
        elif instruction.opcode == Opcode.DUP:
            self.execute_dup()
        elif instruction.opcode == Opcode.OVER:
            self.execute_over()
        elif instruction.opcode == Opcode.POP:
            self.execute_pop()
        elif instruction.opcode == Opcode.SWAP:
            self.execute_swap()
        elif instruction.opcode in (
            Opcode.ADD, Opcode.SUB, Opcode.DIV, Opcode.MUL,
            Opcode.AND, Opcode.OR, Opcode.XOR
        ):
            self.execute_double_operand_alu_operation(instruction)
        elif instruction.opcode in (
            Opcode.INC, Opcode.DEC,
            Opcode.INV, Opcode.NEG
        ):
            self.perform_single_operand_alu_operation(instruction)
        elif instruction.opcode == Opcode.GT:
            self.execute_gt()
        elif instruction.opcode == Opcode.JMP:
            self.execute_jmp(instruction)
        elif instruction.opcode == Opcode.JNZ:
            self.execute_jnz(instruction)
        elif instruction.opcode == Opcode.JZ:
            self.execute_jz(instruction)
        elif instruction.opcode == Opcode.CALL:
            self.execute_call(instruction)
        elif instruction.opcode == Opcode.RET:
            self.execute_ret()
        elif instruction.opcode == Opcode.HLT:
            self.execute_hlt(instruction)
        else:
            raise NotImplementedError



    def execute_lit(self, instruction: Instruction):
        assert isinstance(instruction.arg, int)
        self.data_path.signal_push(instruction.arg)
        self.tick()

    def execute_load(self):
        self.data_path.signal_latch_ar(
            self.data_path.perform_alu_operation(
                AluOperation.ADD,
                AluInputMux.TOS,
                AluInputMux.ZERO
            )
        )
        self.tick()
        self.data_path.signal_write_first(
            self.data_path.signal_read_memory()
        )
        self.tick()

    def execute_save(self):
        self.data_path.signal_latch_ar(
            self.data_path.perform_alu_operation(
                AluOperation.ADD,
                AluInputMux.TOS,
                AluInputMux.ZERO
            )
        )
        self.tick()
        self.data_path.signal_write_memory(
            self.data_path.perform_alu_operation(
                AluOperation.ADD,
                AluInputMux.ZERO,
                AluInputMux.TOS
            )
        )
        self.tick()
        self.data_path.signal_pop()
        self.tick()


    def execute_dup(self):
        self.data_path.signal_push(
            self.data_path.perform_alu_operation(
                AluOperation.ADD,
                AluInputMux.TOS,
                AluInputMux.ZERO
            )
        )
        self.tick()


    def execute_over(self):
        self.data_path.signal_push(
            self.data_path.perform_alu_operation(
                AluOperation.ADD,
                AluInputMux.ZERO,
                AluInputMux.TOS
            )
        )
        self.tick()


    def execute_pop(self):
        self.data_path.signal_pop()
        self.tick()


    def execute_swap(self):
        self.data_path.signal_write_first(
            self.data_path.perform_alu_operation(
                AluOperation.XOR, AluInputMux.TOS, AluInputMux.TOS
            )
        )
        self.tick()
        self.data_path.signal_write_second(
            self.data_path.perform_alu_operation(
                AluOperation.XOR, AluInputMux.TOS, AluInputMux.TOS
            )
        )
        self.tick()
        self.data_path.signal_write_first(
            self.data_path.perform_alu_operation(
                AluOperation.XOR, AluInputMux.TOS, AluInputMux.TOS
            )
        )
        self.tick()

    def perform_single_operand_alu_operation(self, instruction: Instruction):
        self.data_path.signal_write_first(
            self.data_path.perform_alu_operation(
                AluOperation[instruction.opcode.upper()],
                AluInputMux.TOS,
                AluInputMux.ZERO,
            )
        )
        self.tick()

    def execute_double_operand_alu_operation(self, instruction: Instruction):
        self.data_path.signal_write_second(
            self.data_path.perform_alu_operation(
                AluOperation[instruction.opcode.upper()],
                AluInputMux.TOS,
                AluInputMux.TOS,
            )
        )
        self.tick()
        self.data_path.signal_pop()
        self.tick()


    def execute_gt(self):
        self.data_path.signal_write_first(
            self.data_path.perform_alu_operation(
                AluOperation.SUB,
                AluInputMux.TOS,
                AluInputMux.TOS
            )
        )
        self.tick()
        if self.data_path.n_flag():
            self.data_path.signal_write_first(
                self.data_path.perform_alu_operation(
                    AluOperation.ADD,
                    AluInputMux.ZERO,
                    AluInputMux.ZERO
                )
            )
            self.tick()
        else:
            self.data_path.signal_write_first(
                self.data_path.perform_alu_operation(
                    AluOperation.DEC,
                    AluInputMux.ZERO,
                    AluInputMux.ZERO
                )
            )
            self.tick()



    def execute_jmp(self, instruction: Instruction):
        assert isinstance(instruction.arg, int)
        self.latch_pc(instruction.arg)
        self.tick()

    def execute_jnz(self, instruction: Instruction):
        if self.data_path.z_flag():
            return
        self.execute_jmp(instruction)

    def execute_jz(self, instruction: Instruction):
        if not self.data_path.z_flag():
            self.data_path.signal_pop()
            return
        self.data_path.signal_pop()
        self.execute_jmp(instruction)

    def execute_call(self, instruction: Instruction):
        self.push_pc()
        self.tick()
        self.execute_jmp(instruction)


    def execute_ret(self):
        self.pop_pc()
        self.tick()


    def execute_hlt(self, instruction: Instruction):
        raise StopIteration

    def __repr__(self):
        state_repr = (
            f"TICK: {self.current_tick():4} "
            f"PC: {self.pc:4} "
            f"AR: {self.data_path.ar:4} "
            f"Z_FLAG: {self.data_path.z_flag():1} "
            f"N_FLAG: {self.data_path.n_flag():1} "
        )
        stack_repr = f"DATA_STACK: {self.data_path.stack}"
        return_repr = f"RETURN_STACK: {self.return_stack}"
        instr_repr = str(self.program[self.pc])

        return f"{state_repr} \t{instr_repr:32} \t{stack_repr:64} \t{return_repr}"


def simulation(code_raw: list[dict],
               data: list[int],
               start: int,
               input_tokens,
               is_int_io: bool) \
        -> tuple[str, int, int]:
    limit = 1000
    io = IO(input_tokens, is_int_io)
    ios = {IO_ADDR: io}
    code = list(map(Instruction.from_dict, code_raw))
    data_path = DataPath(data, ios)
    control_unit = ControlUnit(code, data_path)
    control_unit.initialize_pc(start)
    instr_counter = 0
    logging.debug("%s", control_unit)
    try:
        while instr_counter < limit:
            control_unit.decode_and_execute_instruction()
            instr_counter += 1
            logging.debug("%s", control_unit)
    except EOFError:
        logging.warning("Input buffer is empty!")
    except StopIteration:
        pass

    if instr_counter >= limit:
        logging.warning("Limit exceeded!")
    logging.info("output buffer: %s", io.output)
    return io.output, instr_counter, control_unit.current_tick()


def main(code_filename: str, input_filename: str, is_int_io: bool):
    code, data, start = read_code(code_filename)
    with open(input_filename, encoding="utf-8") as file:
        input_text = file.read()
        input_token = list(map(ord, input_text + "\0"))
    output, instr_counter, ticks = simulation(code, data, start, input_token, is_int_io)
    print("output:", "".join(output))
    print("instr_counter: ", instr_counter, "ticks: ", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    parser = argparse.ArgumentParser(description="Machine")
    parser.add_argument("input_file", type=str, nargs=1, help="input_file")
    parser.add_argument("output_file", type=str, nargs=1, help="output_file")
    parser.add_argument(
        "--iotype",
        type=str,
        nargs="?",
        help='"int" for int io output and str for str io output',
        default="str",
    )
    args = parser.parse_args()
    main(args.input_file[0], args.output_file[0], args.iotype == "int")
