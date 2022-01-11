from llvmlite import ir
import struct


def _get_exponent(exp: str, frac: str):
    is_less_than_one = int(exp) == 0
    if is_less_than_one:
        a = int(frac[0])
        n = 1
        b = 5 ** n
        for _ in range(14):
            out = 0
            for __ in range(8):
                out <<= 1
                if a >= b:
                    return -n, str(a-b)
                a *= 10
                a += int(frac[n]) if n < len(frac) else 0
                n += 1
                b = 5 ** n
        return -n, str(a)
    else:
        e = int(exp)
        iexp = 63
        n = 0
        while iexp > 0:
            if e & (1 << iexp):
                e = e - (1 << iexp)
                n = iexp
                break
            else:
                iexp = iexp - 1
        return n, str(e)


def _parse_significand(exp: str, frac: str, base_exp: int) -> list:
    out_bytes = []
    if base_exp >= 0:
        a = int(frac[0])
    elif 1-base_exp >= len(frac):
        a = int(frac) * (10 ** max(-base_exp - len(frac), 0))
    else:
        a = int(frac[0:1-base_exp])
    n = 1 if base_exp >= 0 else 1 - base_exp
    b = 5 ** n
    e = int(exp)
    iexp = base_exp
    # leftover = 7 - ((base_exp - 1) % 8)
    for _ in range(14):
        out = 0
        for __ in range(8):
            out <<= 1
            if iexp > 0:
                if e & (1 << iexp):
                    e = e - (1 << iexp)
                    # print(f'2^{iexp}=1')
                    iexp = iexp - 1
                    out |= 1
                else:
                    # print(f'2^{iexp}=0')
                    iexp = iexp - 1
            else:
                if a >= b:
                    a = a - b
                    out |= 1
                    # print(f'2^-{n}=1')
                else:
                    pass  # print(f'2^-{n}=0')
                a *= 10
                a += int(frac[n]) if n < len(frac) else 0
                n += 1
                b = 5 ** n
        out_bytes.append(out)
    return out_bytes


def _format_float_as_hex(value, packfmt, unpackfmt):
    x = value.split('.')
    e, f = x[0], x[1] if len(x) > 1 else '0'
    base_exp, rem = _get_exponent(e, f)
    n = 0x3FFF + base_exp
    if base_exp < 0:
        f = rem
    else:
        e = rem
    sbytes = _parse_significand(e, f, base_exp)
    raw = struct.pack(packfmt, *reversed(sbytes[:]), n)
    interp = struct.unpack(unpackfmt, raw)
    quad1, quad2 = interp[0], interp[1]
    out = f'0xL{quad1:016x}{quad2:016x}'
    return out


def _format_quad(value):
    """
    Format *value* as a hexadecimal string of its IEEE quad precision
    representation.
    """
    return _format_float_as_hex(value, 'B'*14 + 'H', '<QQ')


class FP128Type(ir.types.Type):
    """
    The type for quad-precision floats.
    """
    _instance_cache = 'fp128'

    def __new__(cls):
        return cls._instance_cache

    def __eq__(self, other):
        return isinstance(other, type(self))

    def __hash__(self):
        return hash(type(self))

    @classmethod
    def _create_instance(cls):
        cls._instance_cache = super(FP128Type, cls).__new__(cls)

    null = '0.0'
    intrinsic_name = 'f128'

    def __str__(self):
        return 'fp128'

    def format_constant(self, value):
        return _format_quad(value)


FP128Type._create_instance()


class TokenType(ir.types.Type):

    def _to_string(self):
        return "token"

    def __eq__(self, other):
        return isinstance(other, TokenType)

    def __hash__(self):
        return hash(TokenType)
