# Tests that a `RegisterMap` can be initialized and provide the expected schema
import hypothesis
from hypothesis import given, assume, strategies
from hypothesis.strategies import integers
import pytest

from saleae.register_decoder import RegisterMap, Register


def test_simple_register():
    class MyRegMap(RegisterMap):
        status = Register(0x00, description="Status of device")
        data = Register(0x01, description="Data from device")

    assert MyRegMap.register_containing(0) == MyRegMap.status
    assert MyRegMap.register_containing(1) == MyRegMap.data
    assert MyRegMap.register_containing(2) == None


@given(integers(min_value=0), integers(min_value=1))
def test_error_on_duplicate_register(address, address_width):
    with pytest.raises(ValueError, match=r"\boverlap\b"):

        class MyRegMap(RegisterMap):
            status = Register(address, address_width=address_width, description="Status of device")
            data = Register(address, address_width=address_width, description="Data from device")


@given(integers(min_value=0), integers(min_value=1), integers(min_value=0), integers(min_value=1))
def test_error_on_overlapping_register(x_address, x_address_width, y_address, y_address_width):
    assume(x_address < y_address + y_address_width and y_address < x_address + x_address_width)
    with pytest.raises(ValueError, match=r"\boverlap\b"):

        class MyRegMap(RegisterMap):
            status = Register(x_address, address_width=x_address_width, description="Status of device")
            data = Register(y_address, address_width=y_address_width, description="Data from device")


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


@given(register_maps(), strategies.data())
def test_register_containing(register_map: RegisterMap, data):
    for register in register_map:
        if register.address > 0:
            assert (
                register_map.register_containing(data.draw(integers(min_value=0, max_value=register.address - 1)))
                != register
            )
        assert (
            register_map.register_containing(
                data.draw(integers(min_value=register.address, max_value=register.address + register.address_width - 1))
            )
            == register
        )
        assert (
            register_map.register_containing(data.draw(integers(min_value=register.address + register.address_width)))
            != register
        )


@given(register_maps(), strategies.data())
def test_registers_intersecting(register_map: RegisterMap, data):
    address_max = max((register.address + register.address_width for register in register_map), default=0)

    for register in register_map:
        hypothesis.note(f"register = {register!r}")
        # Should be contained in fully intersecting ranges
        start = data.draw(integers(min_value=0, max_value=register.address), label="full_intersect_start")
        stop = data.draw(integers(min_value=register.address + register.address_width), label="full_intersect_stop")
        assert register in register_map.registers_intersecting(slice(start, stop))
        # Should be contained in left intersecting ranges
        start = data.draw(integers(min_value=0, max_value=register.address))
        stop = data.draw(integers(min_value=register.address + 1, max_value=register.address + register.address_width))
        assert register in register_map.registers_intersecting(slice(start, stop))
        # Should be contained in right intersecting ranges
        start = data.draw(integers(min_value=register.address, max_value=register.address + register.address_width - 1))
        stop = data.draw(integers(min_value=register.address + register.address_width))
        assert register in register_map.registers_intersecting(slice(start, stop))
        # Should be contained in sub-ranges
        start = data.draw(integers(min_value=register.address, max_value=register.address + register.address_width - 1))
        stop = data.draw(integers(min_value=start + 1, max_value=register.address + register.address_width))
        assert register in register_map.registers_intersecting(slice(start, stop))
        # Shouldn't be contained in ranges less than
        start = data.draw(integers(min_value=0, max_value=register.address))
        stop = data.draw(integers(min_value=start, max_value=register.address))
        assert register not in register_map.registers_intersecting(slice(start, stop))
        # Shouldn't be contained in ranges greater than
        start = data.draw(integers(min_value=register.address + register.address_width))
        stop = data.draw(integers(min_value=start))
        assert register not in register_map.registers_intersecting(slice(start, stop))

