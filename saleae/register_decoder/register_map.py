from __future__ import annotations

from enum import Enum
import inspect
from typing import Optional, Dict, List, Union, Literal, Callable, Any, Iterator, Iterable, TypeVar, Generic


class ByteOrder(Enum):
    LITTLE = "little"
    BIG = "big"


T = TypeVar("T")


class Register(Generic[T]):
    """
    Represents a register within a :py:class:`~.RegisterMap`\\ .

    :ivar address: The address this register is mapped at.
    :ivar address_width: The number of addresses that make up this register. When addresses correspond to multiple bytes, this includes that multiplier.
    :ivar description: A human-readable description of this register's purpose.
    :ivar value_type: The type of value this register produces.
    """

    address: int
    address_width: int
    description: Optional[str]
    value_type: Optional[type]
    _value_parser: Optional[Callable[[bytes], Any]]
    _byte_order: Optional[ByteOrder]
    _text_encoding: Optional[str]
    _signed: Optional[bool]

    def __init__(
        self,
        address: int,
        *,
        description: Optional[str] = None,
        address_width: int = 1,
        value_parser: Optional[Callable[[bytes], T]] = None,
        value_type: Optional[Union[Literal[bytes], Literal[int], Literal[str]]] = None,
        byte_order: Optional[ByteOrder] = None,
        signed: Optional[bool] = None,
        text_encoding: Optional[str] = None,
    ):
        if address_width < 1:
            raise ValueError("address_width must be at least 1")

        self.address = address
        self.description = description
        self.address_width = address_width
        self._value_parser = None
        self._byte_order = None
        self._text_encoding = None
        self._signed = None
        if value_parser is not None:
            self._value_parser = value_parser
            if value_type is None:
                signature = inspect.signature(value_parser)
                if isinstance(signature.return_annotation, type):
                    self.value_type = signature.return_annotation
            else:
                self.value_type = value_type
        elif value_type is not None:
            if value_type not in [bytes, int, str]:
                raise ValueError("if value_parser is not specified, value_type must be bytes, int, or str")
            self.value_type = value_type

        else:
            self.value_type = bytes

        # Require byte_order and signed when using auto-integer
        if self.value_type is int and self._value_parser is None:
            if byte_order is None:
                raise ValueError("byte_order is required when value_type=int")
            if signed is None:
                raise ValueError("signed is required when value_type=int")
            self._byte_order = byte_order
            self._signed = signed
        else:
            if byte_order is not None:
                raise ValueError("byte_order is only allowed when value_type=int")
            elif signed is not None:
                raise ValueError("signed is only allowed when value_type=int")

        # Require text_encoding when using auto-str
        if self.value_type is str and self._value_parser is None:
            if text_encoding is None:
                raise ValueError("text_encoding is required when value_type=str")
            self._text_encoding = text_encoding
        elif text_encoding is not None:
            raise ValueError("text_encoding is only allowed when value_type=str")

        # This will be set by RegisterMap's metaclass constructor
        self._name = None

    @property
    def name(self) -> str:
        if self._name is None:
            raise RuntimeError("Register must be used as a class variable inside a RegisterMap")
        return self._name

    def deserialize(self, raw_data: bytes) -> T:
        if self._value_parser is not None:
            return self._value_parser(raw_data)
        elif self.value_type is bytes:
            return raw_data
        elif self.value_type is str:
            return raw_data.decode(self._text_encoding)
        elif self.value_type is int:
            return int.from_bytes(raw_data, byteorder=self._byte_order.value, signed=self._signed)

    def __repr__(self):
        s = f"Register({hex(self.address)}"
        if self.description is not None:
            s += f", description={self.description!r}"
        if self.address_width != 1:
            s += f", address_width={self.address_width!r}"
        if self._value_parser is not None:
            s += f", value_parser={self._value_parser!r}"
        if self.value_type is not None and self.value_type is not bytes:
            s += f", value_type={self.value_type!r}"
        if self._byte_order is not None:
            s += f", byte_order={self._byte_order!r}"
        if self._signed is not None:
            s += f", signed={self._signed!r}"
        if self._text_encoding is not None:
            s += f", text_encoding={self._text_encoding!r}"
        s += ")"
        return s


class RegisterMapMeta(type, Iterable[Register]):
    # Registers sorted by address
    _sorted_registers: List[Register]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Inherit parent class' address map, but duplicate it so we don't add entries to it
        self._sorted_registers = list(getattr(self, "_sorted_registers", []))

        for name, value in self.__dict__.items():
            if isinstance(value, Register):
                # Inform register objects what their assigned name is
                value._name = name

                # Ensure no existing registers overlap with this register
                intersecting = self.registers_intersecting(slice(value.address, value.address + value.address_width))
                if intersecting:
                    raise ValueError(f"the registers {name} and {intersecting[0].name} overlap")

                # Insert into sorted map
                self._sorted_registers.insert(self._register_binary_search_left(value.address), value)

    def __iter__(self) -> Iterator[Register]:
        return iter(self._sorted_registers)

    def register_containing(self, address: int) -> Optional[Register]:
        # Get the first register with `register.address + register.address_width` > given `address`. This is the only candidate for containing the
        # register, since:
        #   * Anything lower would have `register.address + register.address_width` <= `address`
        #   * Anything higher has a start address >= than this register's end address, meaning the start address > the given `address`
        register_index = self._register_binary_search_reg_end_right(address)
        if register_index == len(self._sorted_registers):
            return None
        register = self._sorted_registers[register_index]
        if register.address <= address and register.address + register.address_width > address:
            return register
        else:
            return None

    def registers_intersecting(self, address: slice) -> List[Register]:
        # Get the first register with `register.address + register.address_width` > given `address.start`. Precisely registers at >= this index will intersect with [address.start, inf) since:
        #   * This index itself has `address.start` < `register.address + register.address_width`, implying intersection with [address.start, inf)
        #   * Anything higher has a start address >= than this register's end address, meaning the start address > the given `address.start`, which implies intersection with [address.start, inf)
        #   * Anything lower would have `register.address + register.address_width` <= `address.start`, preventing intersection with [address.start, inf)
        left_index = self._register_binary_search_reg_end_right(address.start)
        # Get the first register with `register.address` >= `address.stop`. Precisely registers at < this index will intersect with [0, address.stop) since:
        #   * This index and higher satisefy `register.address` >= `address.stop`, which prevents intersection with [0, address.stop)
        #   * Anything lower has `register.address` < `address.stop`, which implies intersection with [0, address.stop)
        right_index = self._register_binary_search_left(address.stop)
        # Since [address.start, address.stop) is the intersection of [address.start, inf) and [0, address.stop), the registers that intersect with both of these are
        # precisely the registers that intersect with [address.start, address.stop)
        if left_index < right_index:
            return self._sorted_registers[left_index:right_index]
        else:
            return []

    def _register_binary_search_left(self, address: int) -> int:
        # Find the first register with `register.address` >= given `address`
        left = 0
        right = len(self._sorted_registers)
        while left < right:
            mid = (left + right) // 2
            if self._sorted_registers[mid].address < address:
                left = mid + 1
            else:
                right = mid
        return left

    def _register_binary_search_reg_end_right(self, address: int) -> int:
        # Find the first register with `register.address + register.address_width` > given `address`
        left = 0
        right = len(self._sorted_registers)
        while left < right:
            mid = (left + right) // 2
            if self._sorted_registers[mid].address + self._sorted_registers[mid].address_width > address:
                right = mid
            else:
                left = mid + 1
        return right

    def __repr__(self):
        s = f"class {self.__name__}(RegisterMap):\n"
        if self.address_byte_width != 1:
            s += f"  address_byte_width = {self.address_byte_width}\n"
        for register in self:
            s += f"  {register.name} = {register!r}\n"
        return s


class RegisterMap(metaclass=RegisterMapMeta):
    """
    Allows decoding reads and writes to a device that models its exposed state as a set of addressable registers.

    :cvar address_byte_width: The width of each address in the register map in bytes. Defaults to 1 byte.
    """

    address_byte_width: int = 1
    _address_max: int
    # The observed state of the register map
    _internal_state: bytearray
    # The addresses which have been observed.
    # The data at other addresses in `_internal_state` is not valid.
    _internal_state_mask: List[bool]

    def __init__(self):
        self._address_max = max((reg.address + reg.address_width for reg in self.__class__), default=0)
        self._internal_state = bytearray(self._address_max * self.address_byte_width)
        self._internal_state_mask = [False for _ in range(self._address_max)]

    def observe(self, address: int, data: bytes) -> List[Register]:
        """
        Updates the internal model with observed data.

        :returns: A list of registers observed by this operation.
        """

        if len(data) < 1:
            raise ValueError("data must be non-empty")
        if len(data) % self.address_byte_width != 0:
            raise ValueError("data's length must be divisible by the address width")
        end_address = address + len(data) // self.address_byte_width

        # Ignore out of range reads/writes
        if address >= self._address_max:
            return

        start_bytes = address * self.address_byte_width
        # Clamp bytes to the end of the internal state we understand
        end_bytes = min(end_address, self._address_max) * self.address_byte_width
        self._internal_state[start_bytes:end_bytes] = data[: end_bytes - start_bytes]
        for i in range(address, end_address):
            self._internal_state_mask[i] = True

        # Find the affected registers
        return self.__class__.registers_intersecting(slice(address, end_address))

    def deserialize(self, register: Register[T]) -> T:
        if not all(self._internal_state_mask[register.address : (register.address + register.address_width)]):
            raise RegisterNotObserved(f"register {register.name!r} has not been observed")

        start_bytes = register.address * self.address_byte_width
        end_bytes = start_bytes + register.address_width * self.address_byte_width
        raw_data = bytes(self._internal_state[start_bytes:end_bytes])

        return register.deserialize(raw_data)


class RegisterNotObserved(Exception):
    pass
