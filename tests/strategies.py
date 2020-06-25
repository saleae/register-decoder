import hypothesis
from hypothesis import given, assume, strategies
from hypothesis.strategies import integers
import pytest

from saleae.register_decoder import RegisterMap, Register


@strategies.composite
def register_maps(
    draw,
    register_gap=integers(min_value=0, max_value=100),
    register_width=integers(min_value=1, max_value=100),
    register_count=integers(min_value=0, max_value=10),
):
    current_addr = 0
    # Generate some registers prior to the targeted register
    registers = []
    for _ in range(draw(integers(min_value=0, max_value=10))):
        # Skip some address entries
        current_addr += draw(register_gap)
        # Add a register
        address_width = draw(register_width)
        registers.append(Register(current_addr, address_width=address_width))
        current_addr += address_width

    members = {}
    for register in registers:
        members[draw(strategies.from_regex(r"[A-Za-z_]+"))] = register

    return RegisterMap.__class__("MyRegMap", (RegisterMap,), members)
