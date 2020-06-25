import hypothesis
from hypothesis import given, strategies
from hypothesis.strategies import integers, sampled_from

from saleae.register_decoder import RegisterMap, Register, ByteOrder


@given(
    integers(min_value=1, max_value=16),
    integers(min_value=1, max_value=8),
    integers(min_value=0, max_value=0x1000),
    sampled_from([ByteOrder.BIG, ByteOrder.LITTLE]),
    strategies.data(),
)
def test_parse_unsigned_integer(address_width: int, addr_byte_width: int, address: int, byte_order: ByteOrder, data):
    class MyRegMap(RegisterMap):
        address_byte_width = addr_byte_width

        my_reg = Register(address, address_width=address_width, value_type=int, byte_order=byte_order, signed=False)

    byte_count = address_width * addr_byte_width
    value = data.draw(integers(min_value=0, max_value=2 ** (byte_count * 8) - 1))
    reg_map = MyRegMap()

    reg_map.observe(address, value.to_bytes(byte_count, byteorder=byte_order.value, signed=False))
    assert reg_map.deserialize(MyRegMap.my_reg) == value


@given(
    integers(min_value=1, max_value=16),
    integers(min_value=1, max_value=8),
    integers(min_value=0, max_value=0x1000),
    sampled_from([ByteOrder.BIG, ByteOrder.LITTLE]),
    strategies.data(),
)
def test_parse_signed_integer(address_width: int, addr_byte_width: int, address: int, byte_order: ByteOrder, data):
    class MyRegMap(RegisterMap):
        address_byte_width = addr_byte_width

        my_reg = Register(address, address_width=address_width, value_type=int, byte_order=byte_order, signed=True)

    byte_count = address_width * addr_byte_width
    value = data.draw(integers(min_value=-(2 ** (byte_count * 8 - 1)), max_value=2 ** (byte_count * 8 - 1) - 1))
    reg_map = MyRegMap()

    reg_map.observe(address, value.to_bytes(byte_count, byteorder=byte_order.value, signed=True))
    assert reg_map.deserialize(MyRegMap.my_reg) == value
