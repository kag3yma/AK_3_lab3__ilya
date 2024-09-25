import argparse
import re
import sys
from typing import Optional

from ak_lab3.isa import Instruction, Label, Opcode, IO_ADDR, write_code


def remove_comments(source: str) -> str:
    return re.sub(r'\(.*\)', '', source)


def split_to_terms(source: str) -> list[str]:
    return re.findall(r'."[^"]*"|[^ \n]+', source)


def check_balance(source: list[str]) -> bool:
    stack = []
    for term in source:
        if term in (":", "begin"):
            stack.append(term)
            continue
        if term not in (";", "until"):
            continue
        if term == ";" and stack.pop() != ":":
            return False
        if term == "until" and stack.pop() != "begin":
            return False
    return len(stack) == 0


def preprocess(source_raw: str) -> list[str]:
    """
    Препроцессинг
        - Удаление комментариев
        - Разделение на термы
        - Проверка парности операторов
    """
    source_raw = remove_comments(source_raw)
    source = split_to_terms(source_raw)
    if not check_balance(source):
        print("Code is unbalanced!")
        sys.exit(1)
    return source


translations_map: dict[str, list[Instruction]] = {
    "key": [
        Instruction(Opcode.LIT, IO_ADDR),
        Instruction(Opcode.LOAD)
    ],
    ".": [
        Instruction(Opcode.LIT, IO_ADDR),
        Instruction(Opcode.SAVE)
    ],
    "!": [Instruction(Opcode.SAVE)],
    "+!": [
        Instruction(Opcode.SWAP),
        Instruction(Opcode.OVER),
        Instruction(Opcode.LOAD),
        Instruction(Opcode.ADD),
        Instruction(Opcode.SWAP),
        Instruction(Opcode.SAVE),
        Instruction(Opcode.POP),
    ],
    "@": [Instruction(Opcode.LOAD)],
    "=": [
        Instruction(Opcode.SUB),
        Instruction(Opcode.INV)
    ],
    "+": [Instruction(Opcode.ADD)],
    "-": [Instruction(Opcode.SUB)],
    "*": [Instruction(Opcode.MUL)],
    "/": [Instruction(Opcode.DIV)],
    ">": [Instruction(Opcode.GT)],
    "?": [
        Instruction(Opcode.LOAD),
        Instruction(Opcode.LIT, IO_ADDR),
        Instruction(Opcode.SAVE)
    ],
    "and": [Instruction(Opcode.AND)],
    "or": [Instruction(Opcode.OR)],
    "xor": [Instruction(Opcode.XOR)],
    "inv": [Instruction(Opcode.INV)],
    "neg": [Instruction(Opcode.NEG)],
    "dup": [Instruction(Opcode.DUP)],
    "pop": [Instruction(Opcode.POP)],
    "over": [Instruction(Opcode.OVER)],
    "swap": [Instruction(Opcode.SWAP)],
}


def translate_to_assembly(source: list[str]): #pylint: disable=too-many-branches, too-many-statements
    instructions: list[Instruction] = []
    data: list[str | int] = []
    label_data_index: dict[Label, int] = {}
    label_instr_index: dict[Label, int] = {}
    return_stack: list[Label] = []
    first_instruction_address: Optional[int] = None
    in_procedure = False
    i = 0
    while i < len(source):
        term = source[i]
        if i + 1 < len(source) and source[i + 1] == "allot":
            i += 1
            data += [0] * int(term)
        elif term == "variable":
            i += 1
            label = source[i]
            label_data_index.update({Label(label): len(data)})
            data.append(0)
        elif term == ":":
            in_procedure = True
            i += 1
            label = source[i]
            label_instr_index.update({Label(label): len(instructions)})
        elif term == ";":
            in_procedure = False
            instructions.append(Instruction(Opcode.RET))
        elif term == "begin":
            label = f"begin_{len(instructions)}"
            return_stack.append(Label(label))
            label_instr_index.update({Label(label): len(instructions)})
        elif term == "until":
            instructions.append(Instruction(Opcode.JZ, return_stack.pop()))
        elif term.isdigit():
            if not in_procedure and first_instruction_address is None:
                first_instruction_address = len(instructions)
            instructions.append(Instruction(Opcode.LIT, int(term)))
        elif term in translations_map:
            if not in_procedure and first_instruction_address is None:
                first_instruction_address = len(instructions)
            instructions += translations_map[term]
        elif term.startswith('."'):
            if not in_procedure and first_instruction_address is None:
                first_instruction_address = len(instructions)
            string = term[2:-1]
            label_data_name = "data_" + string
            label_instr_name = "instr_" + string
            label_data_index.update({Label(label_data_name): len(data)})
            data.append(len(string))
            data += list(string)

            label_instr_index.update({Label(label_instr_name): len(instructions) + 3})

            instructions += [
                Instruction(Opcode.LIT, Label(label_data_name)),
                Instruction(Opcode.DUP),
                Instruction(Opcode.LOAD),
                Instruction(Opcode.SWAP),
                Instruction(Opcode.INC),
                Instruction(Opcode.DUP),
                Instruction(Opcode.LOAD),
                Instruction(Opcode.LIT, IO_ADDR),
                Instruction(Opcode.SAVE),
                Instruction(Opcode.POP),
                Instruction(Opcode.SWAP),
                Instruction(Opcode.DEC),
                Instruction(Opcode.JNZ, Label(label_instr_name)),
                Instruction(Opcode.POP),
                Instruction(Opcode.POP),
            ]
        else:
            if not in_procedure and first_instruction_address is None:
                first_instruction_address = len(instructions)
            instructions.append(Instruction(Opcode.NOP, Label(term)))
        i += 1
    instructions.append(Instruction(Opcode.HLT))
    return instructions, data, label_data_index, label_instr_index, first_instruction_address


def instructions_map_labels(instructions: list[Instruction],
                            label_instr_index: dict[Label, int],
                            label_data_index: dict[Label, int]) -> list[Instruction]:
    for instr in instructions:
        if not isinstance(instr.arg, Label):
            continue
        if instr.opcode == Opcode.NOP:
            if instr.arg in label_instr_index:
                instr.opcode = Opcode.CALL
                instr.arg = label_instr_index[instr.arg]
            elif instr.arg in label_data_index:
                instr.opcode = Opcode.LIT
                instr.arg = label_data_index[instr.arg]
            else:
                print(f"Лейбл {instr.arg} не найден! Ошибка!")
                sys.exit(1)
        elif instr.arg in label_instr_index:
            instr.arg = label_instr_index[instr.arg]
        elif instr.arg in label_data_index:
            instr.arg = label_data_index[instr.arg]
        else:
            print(f"Лейбл {instr.arg} не найден для {instr.opcode}! Ошибка!")
            sys.exit(1)
    return instructions


def convert_data_to_int(data: list[str | int]) -> list[int]:
    return [
        ord(it) if isinstance(it, str) else it
        for it in data
    ]


def translate(source_raw: str):
    source = preprocess(source_raw)
    instructions, data, label_data_index, label_instr_index, start = translate_to_assembly(source)
    # print(start)
    instructions = instructions_map_labels(instructions, label_instr_index, label_data_index)
    data = convert_data_to_int(data)
    return instructions, data, start
    # print(*instructions, sep="\n")
    # print(*data, sep="\n")


def main(input_file: str, output_file: str) -> None:
    with open(input_file, encoding="utf-8") as in_f:
        source = in_f.read()

    code, data, start = translate(source)
    write_code(output_file, code, data, start)
    # print(data)
    # print(code)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Translator")
    parser.add_argument("input_file", type=str, nargs=1, help="input_file")
    parser.add_argument("output_file", type=str, nargs=1, help="output_file")
    args = parser.parse_args()
    main(args.input_file[0], args.output_file[0])
