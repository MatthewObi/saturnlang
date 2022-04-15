import typing

from llvmlite import ir

import irutil
from package import Symbol, Visibility, LinkageType
from irutil import FP128Type
from typing import Union


class DebugTypeInfo:
    def __init__(self, kind, params, distinct=False):
        self.kind = kind
        self.params = params
        self.distinct = distinct


class Type(Symbol):
    """
    A semantic type in Saturn.\n
    name: identifier for type.\n
    irtype: the underlying llvm type of this semantic type.\n
    tclass: a category for how the type is treated semantically.\n
    qualifiers: adds special qualifiers to the base type (pointers, arrays, const, mut...)\n
    traits: special instances that change how a type is treated by the compiler.\n
    c_decl: Whether the function is a C declaration.\n
    """
    def __init__(self, name, tclass, irtype=None, qualifiers=None, traits=None, c_decl=False):
        super().__init__(name, visibility=Visibility.PUBLIC, link_type=LinkageType.DEFAULT, c_decl=c_decl)
        if traits is None:
            traits = []
        if qualifiers is None:
            qualifiers = []
        self.name = name
        self.tclass = tclass
        self.irtype = irtype
        self.debug_info = self._auto_debug_info()
        self.dtype = {}
        self.qualifiers = qualifiers
        self.traits = traits
        self.bits = -1

    def get_integer_bits(self):
        if self.bits != -1:
            return self.bits
        if self.name == 'int' or self.name == 'int32' or self.name == 'uint' or self.name == 'uint32'\
                or self.name == 'C::unsigned.long' or self.name == 'C::long':
            self.bits = 32
            return 32
        elif self.name == 'int64' or self.name == 'uint64'\
                or self.name == 'C::unsigned.long.long' or self.name == 'C::long.long':
            self.bits = 64
            return 64
        elif self.name == 'byte' or self.name == 'int8'\
                or self.name == 'C::unsigned.char' or self.name == 'C::char':
            self.bits = 8
            return 8
        elif self.name == 'int16' or self.name == 'uint16':
            self.bits = 16
            return 16
        return -1

    def get_ir_type(self):
        if self.irtype is None:
            raise RuntimeError(f"{self.name} has no defined ir type.")
        return self.irtype

    def add_debug_info(self, debug_info: DebugTypeInfo):
        self.debug_info = debug_info

    def _auto_debug_info(self):
        irtype: ir.Type = self.irtype
        name = self.name
        if irtype is not None:
            size = 32
            if self.tclass == 'uint':
                encoding = ir.DIToken("DW_ATE_unsigned")
            elif self.tclass == 'int':
                encoding = ir.DIToken("DW_ATE_signed")
            elif self.tclass == 'float':
                encoding = ir.DIToken("DW_ATE_float")
            else:
                encoding = ir.DIToken("DW_ATE_signed")
        else:
            size = 8
            encoding = ir.DIToken("DW_ATE_signed")
        return DebugTypeInfo("DIBasicType", {"name": name, "size": size, "encoding": encoding})

    def get_debug_type(self, module: ir.Module):
        key = hash(module)
        if key not in self.dtype:
            self.dtype[key] = module.add_debug_info(self.debug_info.kind,
                                                    self.debug_info.params,
                                                    self.debug_info.distinct)
        return self.dtype[key]

    def get_array_count_old(self):
        array_size = -1
        for q in reversed(self.qualifiers):
            if q[0] == 'array':
                array_size = q[1]
                break
        return array_size

    def get_array_count(self):
        return 1

    def make_array(self, size):
        self.qualifiers.append(('array', size))

    def get_array_of(self, size):
        return ArrayType(self, size)

    def get_array_of_old(self, size):
        return Type(self.name,
                    self.tclass,
                    ir.ArrayType(self.irtype, size),
                    qualifiers=self.qualifiers + [('array', size)],
                    traits=self.traits)

    def get_hvector_of(self, size):
        return HVectorType(self, size)

    def get_slice_of(self):
        return SliceType(self)

    def get_pointer_to(self):
        return PointerType(self)

    def get_pointer_to_old(self):
        return Type(self.name,
                    self.tclass,
                    self.irtype.as_pointer(),
                    qualifiers=self.qualifiers + [('ptr',)],
                    traits=self.traits)

    def get_dereference_of(self):
        return self

    def get_dereference_of_old(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'ptr':
                ql.pop(i)
                break
        ql.reverse()
        return Type(self.name,
                    self.tclass,
                    self.irtype.pointee,
                    qualifiers=ql,
                    traits=self.traits)

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def get_element_of(self):
        return self

    def get_element_of_old(self):
        if self.is_pointer():
            ql = self.qualifiers.copy()
            ql.reverse()
            for i in range(len(ql)):
                if ql[i][0] == 'ptr':
                    ql.pop(i)
                    break
            ql.reverse()
            return Type(self.name,
                        self.tclass,
                        self.irtype.pointee,
                        qualifiers=ql,
                        traits=self.traits)
        else:
            ql = self.qualifiers.copy()
            ql.reverse()
            for i in range(len(ql)):
                if ql[i][0] == 'array':
                    ql.pop(i)
                    break
            ql.reverse()
            return Type(self.name,
                self.tclass,
                self.irtype.element,
                qualifiers=ql,
                traits=self.traits
            )

    def add_trait(self, trait):
        if trait not in self.traits:
            self.traits.append(trait)

    def has_trait(self, trait):
        return trait in self.traits

    def get_base_type(self):
        return self

    def is_array_old(self):
        if len(self.qualifiers) > 0:
            return self.qualifiers[-1][0] == 'array'
        return False

    def is_array(self):
        return False

    def is_hvector(self):
        return False

    def get_mutable_of(self):
        return Type(self.name,
                    self.tclass,
                    self.irtype.as_pointer(),
                    qualifiers=self.qualifiers + [('mut',)],
                    traits=self.traits)

    def get_const_of(self):
        return Type(self.name,
                    self.tclass,
                    self.irtype.as_pointer(),
                    qualifiers=self.qualifiers + [('const',)],
                    traits=self.traits)

    def is_pointer_old(self):
        return ('ptr',) in self.qualifiers or self.name == 'cstring' or self.name == 'null_t'

    def is_pointer(self):
        return self.name == 'cstring' or self.name == 'null_t'

    def is_actual_pointer(self):
        return False

    def is_actual_pointer_old(self):
        return ('ptr',) in self.qualifiers

    def is_byte_pointer(self):
        base_ty = self.get_base_type()
        return self.is_actual_pointer() and (base_ty.name == 'byte' or base_ty.name == 'C::char')

    def is_slice(self):
        return False

    def is_value(self):
        return not (self.is_array()
                    or self.is_hvector()
                    or self.is_pointer()
                    or self.is_actual_pointer()
                    or self.is_reference())

    def is_unsigned(self):
        return self.tclass == 'uint'

    def is_signed(self):
        return self.tclass == 'int'

    def is_integer(self):
        return self.tclass == 'int' or self.tclass == 'uint'

    def is_float(self):
        return self.tclass == 'float'

    def is_number(self):
        return self.is_float() or self.is_integer()

    def is_bool(self):
        return self.tclass == 'bool'

    def is_string(self):
        return self.tclass == 'string'

    def is_struct(self):
        return self.tclass == 'struct'

    def is_function(self):
        return self.tclass == 'function'

    def is_tuple(self):
        return self.tclass == 'tuple'

    def is_optional(self):
        return self.tclass == 'optional'

    def is_reference(self):
        return False

    def is_enum(self):
        return self.tclass == 'enum'

    def is_void(self):
        return self.tclass == 'void'

    def is_iterable(self):
        return self.is_array() or self.is_string()

    def is_const(self):
        return 'const' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers

    def is_mutable(self):
        return not (self.is_const() or self.is_immut())

    def is_atomic(self):
        return 'atomic' in self.qualifiers

    def has_dtor(self):
        return False

    def to_dict(self, full_def=True):
        d = super().to_dict()
        d['symbol_type'] = 'type'
        d['qualifiers'] = self.qualifiers
        d['type'] = 'named'
        d['tclass'] = self.tclass
        d['traits'] = self.traits
        d['name'] = self.name
        # print(d)
        return d

    def __str__(self):
        s = str()
        for q in reversed(self.qualifiers):
            if q[0] == 'const':
                s += 'const '
            elif q[0] == 'mut':
                s += 'mut '
            elif q[0] == 'immut':
                s += 'immut '
        s += self.name
        return s

    def is_similar(self, other):
        """
        Checks whether the two values have similar types for the purpose of fundamental operations.
        """
        if self is other:
            return True
        if self.name == other.name:
            if self.is_value() and other.is_value():
                return True
            if self.is_pointer() and other.is_pointer():
                return True
            if self.is_array() and other.is_array():
                return True
            if self.is_hvector() and other.is_hvector():
                return self.get_array_count() == other.get_array_count() \
                       and self.get_element_of().is_similar(other.get_element_of())
        if self.tclass == other.tclass and self.is_integer():
            return True
        return False

    def is_convertable(self, other):
        if self.tclass == other.tclass:
            return True
        return False


types = {
    "void":     Type("void",    'void',     ir.VoidType(), traits=['TNoType']),
    "int":      Type("int",     'int',      ir.IntType(32), traits=['TIntAny']),
    "int32":    Type("int32",   'int',      ir.IntType(32)),
    "int64":    Type("int64",   'int',      ir.IntType(64)),
    "int16":    Type("int16",   'int',      ir.IntType(16)),
    "int8":     Type("int8",    'int',      ir.IntType(8)),
    "byte":     Type("byte",    'uint',     ir.IntType(8)),
    "uint":     Type("uint",    'uint',     ir.IntType(32), traits=['TIntAny']),
    "uint64":   Type("uint64",  'uint',     ir.IntType(64)),
    "uint32":   Type("uint32",  'uint',     ir.IntType(32)),
    "uint16":   Type("uint16",  'uint',     ir.IntType(16)),
    "float32":  Type("float32", 'float',    ir.FloatType()),
    "float64":  Type("float64", 'float',    ir.DoubleType()),
    "float16":  Type("float16", 'float',    ir.HalfType()),
    "float128": Type("float128",'float',    FP128Type()),
    "bool":     Type("bool",    'bool',     ir.IntType(1)),
    "cstring":  Type("cstring", 'string',   ir.IntType(8).as_pointer(), traits=['TOpaquePtr']),
    "null_t":   Type("null_t",  'null',     ir.IntType(8).as_pointer(), traits=['TNoDereference', 'TOpaquePtr']),
    # C types
    "C::float":                 Type("C::float",                'float',    ir.FloatType(),  c_decl=True),
    "C::double":                Type("C::double",               'float',    ir.DoubleType(), c_decl=True),
    "C::long.double":           Type("C::long.double",          'float',    FP128Type(),     c_decl=True),
    "C::int":                   Type("C::int",                  'int',      ir.IntType(32),  c_decl=True),
    "C::short":                 Type("C::short",                'int',      ir.IntType(16),  c_decl=True),
    "C::long":                  Type("C::long",                 'int',      ir.IntType(32),  c_decl=True),
    "C::long.long":             Type("C::long.long",            'int',      ir.IntType(64),  c_decl=True),
    "C::void":                  Type("C::void",                 'void',     ir.VoidType(),   c_decl=True),
    "C::char":                  Type("C::char",                 'int',      ir.IntType(8),   c_decl=True),
    "C::unsigned":              Type("C::unsigned",             'uint',     ir.IntType(32),  c_decl=True),
    "C::signed.char":           Type("C::signed.char",          'int',      ir.IntType(8),   c_decl=True),
    "C::unsigned.char":         Type("C::unsigned.char",        'uint',     ir.IntType(8),   c_decl=True),
    "C::unsigned.int":          Type("C::unsigned.int",         'uint',     ir.IntType(32),  c_decl=True),
    "C::unsigned.short":        Type("C::unsigned.short",       'uint',     ir.IntType(16),  c_decl=True),
    "C::unsigned.long":         Type("C::unsigned.long",        'uint',     ir.IntType(32),  c_decl=True),
    "C::unsigned.long.long":    Type("C::unsigned.long.long",   'uint',     ir.IntType(64),  c_decl=True),
    "C::signed.int":            Type("C::signed.int",           'int',      ir.IntType(32),  c_decl=True),
    "C::short.int":             Type("C::short.int",            'int',      ir.IntType(16),  c_decl=True),
    "C::long.int":              Type("C::long.int",             'int',      ir.IntType(32),  c_decl=True),
    "C::long.long.int":         Type("C::long.long.int",        'int',      ir.IntType(64),  c_decl=True),
    "C::signed.short.int":      Type("C::signed.short.int",     'int',      ir.IntType(16),  c_decl=True),
    "C::signed.long.int":       Type("C::signed.long.int",      'int',      ir.IntType(32),  c_decl=True),
    "C::signed.long.long.int":  Type("C::signed.long.long.int", 'int',      ir.IntType(64),  c_decl=True),
    "C::unsigned.short.int":    Type("C::unsigned.short.int",   'uint',     ir.IntType(16),  c_decl=True),
    "C::unsigned.long.int":     Type("C::unsigned.long.int",    'uint',     ir.IntType(32),  c_decl=True),
    "C::unsigned.long.long.int":Type("C::unsigned.long.long.int",'uint',    ir.IntType(64),  c_decl=True),
    "C::wchar_t":               Type("C::wchar_t",              'int',      ir.IntType(64),  c_decl=True),
    "C::uintptr_t":             Type("C::uintptr_t",            'uint',     ir.IntType(64),  c_decl=True),
    "C::__time64_t":            Type("C::__time64_t",           'uint',     ir.IntType(64),  c_decl=True),
    "C::errno_t":               Type("C::errno_t",              'int',      ir.IntType(32),  c_decl=True),
    "C::size_t":                Type("C::size_t",               'uint',     ir.IntType(64),  c_decl=True),
    "C::_Bool":                 Type("C::_Bool",                'bool',     ir.IntType(8),   c_decl=True),
}

# Aliases
types['float'] = types['float32']
types['double'] = types['float64']
types['uint8'] = types['byte']


def print_qualifiers(ql: list):
    s = ''
    if 'const' in ql:
        s += 'const '
    if 'immut' in ql:
        s += 'immut '
    if 'readonly' in ql:
        s += 'readonly '
    if 'atomic' in ql:
        s += 'atomic '
    s = s.rstrip(' ')
    return s


class Value(Symbol):
    """
    A saturn value.
    """
    def __init__(self, name, stype, irvalue, qualifiers=None, objtype='stack', visibility=Visibility.DEFAULT):
        super().__init__(name, visibility)
        if qualifiers is None:
            qualifiers = []
        self.type = stype
        self.objtype = objtype
        self.irvalue = irvalue
        self.qualifiers = qualifiers.copy()

    def is_const(self):
        return 'const' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers

    def is_mut(self):
        return 'mut' in self.qualifiers

    def is_readonly(self):
        return 'readonly' in self.qualifiers

    def is_atomic(self):
        return 'atomic' in self.qualifiers

    def is_stack_object(self):
        return self.objtype == 'stack'

    def is_shared_object(self):
        return self.objtype == 'shared'

    def is_owned_object(self):
        return self.objtype == 'owned'

    def is_global(self):
        return self.objtype == 'global'

    def is_heap_object(self):
        return self.objtype == 'shared' or self.objtype == 'owned'

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} {self.objtype} {print_qualifiers(self.qualifiers)} value {self.name}: {str(self.type)}"
        return s

    def to_dict(self):
        d = super().to_dict()
        d['name'] = self.name
        d['symbol_type'] = 'value'
        d['value_type'] = self.type.to_dict()
        d['obj_type'] = self.objtype
        d['qualifiers'] = self.qualifiers
        return d


class GlobalValue(Symbol):
    """
    A global saturn value.
    """
    def __init__(self, name, stype, base_irvalue, qualifiers=None, objtype='global', visibility=Visibility.DEFAULT):
        super().__init__(name, visibility)
        if qualifiers is None:
            qualifiers = []
        self.type = stype
        self.objtype = objtype
        self.irvalue = {}
        self.base_irvalue = base_irvalue
        self.qualifiers = qualifiers.copy()

    def add_ir_value(self, module, ir_value):
        self.irvalue[hash(module)] = ir_value

    def get_ir_value(self, module: ir.Module):
        key = hash(module)
        if key not in self.irvalue:
            if isinstance(self.base_irvalue, ir.GlobalVariable):
                try:
                    new_irvalue = module.get_global(self.base_irvalue.name)
                except KeyError:
                    new_irvalue = ir.GlobalVariable(module, self.base_irvalue.type, self.base_irvalue.name)
                self.irvalue[key] = new_irvalue
                return self.irvalue[key]
            return None
        return self.irvalue[key]

    def is_const(self):
        return 'const' in self.qualifiers

    def is_mut(self):
        return 'mut' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers

    def is_readonly(self):
        return 'readonly' in self.qualifiers

    def is_atomic(self):
        return 'atomic' in self.qualifiers

    def is_stack_object(self):
        return self.objtype == 'stack'

    def is_shared_object(self):
        return self.objtype == 'shared'

    def is_owned_object(self):
        return self.objtype == 'owned'

    def is_global(self):
        return self.objtype == 'global'

    def is_heap_object(self):
        return self.objtype == 'shared' or self.objtype == 'owned'

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} {self.objtype} {print_qualifiers(self.qualifiers)} value {self.name}: {str(self.type)}"
        return s

    def to_dict(self):
        d = super().to_dict()
        d['name'] = self.name
        d['symbol_type'] = 'value'
        d['value_type'] = self.type.to_dict()
        d['obj_type'] = self.objtype
        d['qualifiers'] = self.qualifiers
        return d


class ConstexprValue(Symbol):
    """
    A saturn constexpr value.
    """
    def __init__(self, name, stype, value, objtype='stack', visibility=Visibility.DEFAULT):
        super().__init__(name, visibility)
        self.type = stype
        self.objtype = objtype
        self.value = value

    def get_ir_type(self):
        return self.type.get_ir_type()

    def is_stack_object(self):
        return self.objtype == 'stack'

    def is_shared_object(self):
        return self.objtype == 'shared'

    def is_owned_object(self):
        return self.objtype == 'owned'

    def is_global(self):
        return self.objtype == 'global'

    def is_heap_object(self):
        return self.objtype == 'shared' or self.objtype == 'owned'

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} constexpr value {self.name}: {str(self.type)} = {str(self.value)}"
        return s

    def to_dict(self):
        d = super().to_dict()
        d['name'] = self.name
        d['symbol_type'] = 'value'
        d['value_type'] = self.type.to_dict()
        d['obj_type'] = self.objtype
        d['value'] = self.value
        return d


# Float constants
types["float64"].symbols["max"] = ConstexprValue('max', types['float64'], 1.7976931348623157e+308)
types["float64"].symbols["min"] = ConstexprValue('min', types['float64'], -1.7976931348623157e+308)
types["float64"].symbols["nan"] = ConstexprValue('nan', types['float64'], float('NaN'))
types["float64"].symbols["inf"] = ConstexprValue('inf', types['float64'], float('infinity'))
types["float64"].symbols["negative_inf"] = ConstexprValue("negative_inf", types['float64'], -float('infinity'))

types["float32"].symbols["max"] = ConstexprValue('max', types['float32'], 3.4028234663852886e+38)
types["float32"].symbols["min"] = ConstexprValue('min', types['float32'], -3.4028234663852886e+38)
types["float32"].symbols["nan"] = ConstexprValue('nan', types['float32'], float('NaN'))
types["float32"].symbols["inf"] = ConstexprValue('inf', types['float32'], float('infinity'))
types["float32"].symbols["negative_inf"] = ConstexprValue("negative_inf", types['float32'], -float('infinity'))

# Integer constants
types["int8"].symbols["max"] = ConstexprValue('max', types["int8"], 0x7f)
types["int8"].symbols["min"] = ConstexprValue('min', types["int8"], 0-0x80)
types["byte"].symbols["max"] = ConstexprValue('max', types["byte"], 0xff)
types["byte"].symbols["min"] = ConstexprValue('min', types["byte"], 0)
types["int16"].symbols["max"] = ConstexprValue('max', types["int16"], 0x7fff)
types["int16"].symbols["min"] = ConstexprValue('min', types["int16"], 0-0x8000)
types["int32"].symbols["max"] = ConstexprValue('max', types["int32"], 0x7fffffff)
types["int32"].symbols["min"] = ConstexprValue('min', types["int32"], 0-0x80000000)
types["uint32"].symbols["max"] = ConstexprValue('max', types["uint32"], 0xffffffff)
types["uint32"].symbols["min"] = ConstexprValue('min', types["uint32"], 0)
types["int64"].symbols["max"] = ConstexprValue('max', types["int64"], 0x7fffffffffffffff)
types["int64"].symbols["min"] = ConstexprValue('min', types["int64"], 0-0x8000000000000000)
types["uint64"].symbols["max"] = ConstexprValue('max', types["uint64"], 0xffffffffffffffff)
types["uint64"].symbols["min"] = ConstexprValue('min', types["uint64"], 0)


class PointerType(Type):
    def __init__(self, pointee_type, qualifiers=None, traits=None):
        if qualifiers is None:
            qualifiers = []
        super().__init__(pointee_type.name, pointee_type.tclass, None, qualifiers=qualifiers.copy(), traits=traits)
        self.pointee = pointee_type

    def get_ir_type(self):
        return self.pointee.get_ir_type().as_pointer()

    def is_pointer(self):
        return True

    def is_actual_pointer(self):
        return True

    def get_dereference_of(self):
        return self.pointee

    def get_element_of(self):
        return self.pointee.get_element_of()

    def get_pointer_to(self):
        return PointerType(self)

    def get_base_type(self):
        return self.pointee.get_base_type()

    def to_dict(self, full_def=True):
        d = super().to_dict(full_def)
        d['type'] = 'pointer'
        d['pointee'] = self.pointee.to_dict(full_def)
        return d

    def __str__(self):
        return f'*{str(self.pointee)}'


class ArrayType(Type):
    """
    An array type in Saturn
    """
    def __init__(self, element_type, count, qualifiers=None, traits=None):
        super().__init__(element_type.name, element_type.tclass, None, qualifiers=qualifiers, traits=traits)
        self.element = element_type
        self.count = count

    def get_array_count(self):
        return self.count

    def get_ir_type(self):
        return ir.ArrayType(self.element.get_ir_type(), self.count)

    def is_array(self):
        return True

    def get_pointer_to(self):
        return PointerType(self)

    def get_array_of(self, size):
        return ArrayType(self, size)

    def get_element_of(self):
        return self.element

    def get_slice_of(self):
        return SliceType(self)

    def get_base_type(self):
        return self.element.get_base_type()

    def to_dict(self, full_def=True):
        d = super().to_dict(full_def)
        d['type'] = 'array'
        d['count'] = self.count
        d['element'] = self.element.to_dict(full_def)
        return d

    def __str__(self):
        return f'[{self.count}]{str(self.element)}'


class HVectorType(Type):
    """
    A hardware vector type suitable for SIMD operations.\n
    Supports parallel binary operations.
    """
    def __init__(self, element_type, count, qualifiers=None, traits=None):
        super().__init__('', element_type.tclass, None, qualifiers=qualifiers, traits=traits)
        self.element = element_type
        self.count = count

    def get_array_count(self):
        return self.count

    def get_ir_type(self):
        return ir.VectorType(self.element.get_ir_type(), self.count)

    def is_hvector(self):
        return True

    def get_pointer_to(self):
        return PointerType(self, self.qualifiers, self.traits)

    def get_element_of(self):
        return self.element

    def get_array_of(self, size):
        return ArrayType(self, size)

    def __str__(self):
        return f'[<{self.count}>]{str(self.element)}'

    def to_dict(self, full_def=True):
        d = super().to_dict(full_def)
        d['type'] = 'hvector'
        d['count'] = self.count
        d['element'] = self.element.to_dict(full_def)
        return d


class FuncType(Type):
    """
    A semantic function type in Saturn.
    """
    def __init__(self, name, irtype, rtype, atypes=None, qualifiers=None, traits=None):
        if atypes is None:
            atypes = []
        if traits is None:
            traits = {}
        if qualifiers is None:
            qualifiers = []
        super().__init__(name, 'function', irtype, qualifiers=qualifiers, traits=traits)
        self.rtype = rtype
        self.atypes = atypes

    def get_return_type(self):
        return self.rtype

    def get_pointer_to(self):
        return FuncPointerType(self.name,
                               self.irtype.as_pointer(),
                               self.rtype,
                               self.atypes.copy(),
                               qualifiers=self.qualifiers,
                               traits=self.traits)

    def __str__(self):
        s = ""
        arg_str = ""
        for atype in self.atypes:
            arg_str += f"{str(atype)}, "
        arg_str = arg_str.rstrip(", ")
        s += f"fn({arg_str}): {str(self.rtype)}"
        return s

    def to_dict(self, full_def=True):
        d = super().to_dict(full_def)
        d['type'] = 'fn'
        d['rtype'] = self.rtype.to_dict(full_def)
        d['atypes'] = [atype.to_dict(full_def) for atype in self.atypes]
        return d


class FuncPointerType(Type):
    """
    A semantic function reference type in Saturn.
    """
    def __init__(self, name, irtype, rtype, atypes=None, qualifiers=None, traits=None):
        if atypes is None:
            atypes = []
        if traits is None:
            traits = {}
        if qualifiers is None:
            qualifiers = []
        super().__init__(name, 'function', irtype, qualifiers=qualifiers, traits=traits)
        self.rtype = rtype
        self.atypes = atypes

    def get_return_type(self):
        return self.rtype

    def get_dereference_of(self):
        return FuncType(self.name,
                        self.irtype.pointee,
                        self.rtype,
                        self.atypes.copy(),
                        qualifiers=self.qualifiers,
                        traits=self.traits)

    def get_pointer_to(self):
        return PointerType(self)

    def __str__(self):
        s = "*"
        arg_str = ""
        for atype in self.atypes:
            arg_str += f"{str(atype)}, "
        arg_str = arg_str.rstrip(", ")
        s += f"fn({arg_str}): {str(self.rtype)}"
        return s

    def to_dict(self, full_def=True):
        d = super().to_dict(full_def)
        d['type'] = 'fn_ptr'
        d['rtype'] = self.rtype.to_dict(full_def)
        d['atypes'] = [atype.to_dict(full_def) for atype in self.atypes]
        return d


class StructType(Type):
    """
    A structure type in Saturn.
    """
    def __init__(self, name, irtype, fields=None,
                 qualifiers=None, traits=None,
                 operators=None, methods=None, ctor=None, dtor=None):
        if operators is None:
            operators = {}
        if methods is None:
            methods = {}
        if traits is None:
            traits = {}
        if qualifiers is None:
            qualifiers = []
        if fields is None:
            fields = []
        super().__init__(name, 'struct', irtype, qualifiers=qualifiers, traits=traits)
        self.name = name
        self.irtype = irtype
        self.fields = fields
        self.tclass = 'struct'
        self.qualifiers = qualifiers
        self.traits = traits
        self.ctor = ctor
        self.dtor = dtor
        self.operator = operators.copy()
        self.methods = methods.copy()

    def get_ir_type(self):
        if self.irtype is None:
            pass
        return self.irtype

    def add_field(self, name, ftype, irvalue, qualifiers=None):
        if irvalue is not None:
            value = Value(name, ftype, irvalue.eval(), qualifiers=qualifiers)
        else:
            value = Value(name, ftype, None, qualifiers=qualifiers)
        self.fields.append(value)
        self[name] = value

    def get_field_index(self, name):
        for i in range(len(self.fields)):
            if self.fields[i].name == name:
                return i
        return -1

    def get_field_type(self, index):
        return self.fields[index].type

    def get_fields_with_init(self):
        withinit = []
        for f in self.fields:
            if f.irvalue is not None:
                withinit.append(f)
        return withinit

    def has_ctor(self):
        return self.ctor is not None

    def get_ctor(self):
        return self.ctor

    def add_ctor(self, ctor):
        if not self.has_ctor():
            self.ctor = ctor

    def has_dtor(self):
        return self.dtor is not None

    def get_dtor(self):
        return self.dtor

    def add_dtor(self, dtor):
        if not self.has_dtor():
            self.dtor = dtor

    def has_operator(self, op):
        return op in self.operator.keys()

    def add_operator(self, op, fn):
        if not self.has_operator(op):
            self.operator[op] = fn

    def get_operator(self, op):
        return self.operator[op] if op in self.operator.keys() else None

    def has_method(self, name):
        return name in self.methods.keys()

    def add_method(self, name, fn):
        # print(self.name, name, fn)
        if not self.has_method(name):
            self.methods[name] = fn
            self[name] = fn
            fn.parent = self

    def get_array_of_old(self, size):
        return StructType(self.name,
                          ir.ArrayType(self.irtype, size),
                          self.fields,
                          qualifiers=self.qualifiers + [('array', size)],
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods,
                          ctor=self.ctor,
                          dtor=self.dtor)

    def get_pointer_to_old(self):
        return StructType(self.name,
                          self.irtype.as_pointer(),
                          self.fields,
                          qualifiers=self.qualifiers + [('ptr',)],
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods,
                          ctor=self.ctor,
                          dtor=self.dtor)

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def get_dereference_of_old(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'ptr':
                ql.pop(i)
                break
        return StructType(self.name,
                          self.irtype.pointee,
                          self.fields,
                          qualifiers=ql,
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods,
                          ctor=self.ctor,
                          dtor=self.dtor)

    def get_element_of_old(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'array':
                ql.pop(i)
                break
        return StructType(self.name,
                          self.irtype.element,
                          self.fields,
                          qualifiers=ql,
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods,
                          ctor=self.ctor,
                          dtor=self.dtor)

    def to_dict(self, full_def=True):
        if not full_def:
            d = super().to_dict()
            return d
        d = super().to_dict()
        d['fields'] = {field.name: field.to_dict() for field in self.fields}
        d['operators'] = {key: func.to_dict() for key, func in self.operator.items()}
        d['methods'] = {key: func.to_dict() for key, func in self.methods.items()}
        if self.dtor is not None:
            d['dtor'] = self.dtor.to_dict()
        if self.ctor is not None:
            d['ctor'] = self.ctor.to_dict()
        return d


class EnumType(Type):
    """
    An enumeration type in Saturn.
    """
    def __init__(self, name, base_type,
                 qualifiers=None, traits=None):
        if traits is None:
            traits = {}
        if qualifiers is None:
            qualifiers = []
        super().__init__(name, 'enum', None, qualifiers=qualifiers, traits=traits)
        self.name = name
        self.base_type = base_type
        self.irtype = None
        self.tclass = 'enum'
        self.qualifiers = qualifiers
        self.traits = traits

    def get_ir_type(self):
        if self.irtype is None:
            self.irtype = self.base_type.get_ir_type()
        return self.irtype

    def add_value(self, name, value):
        val = ConstexprValue(name, self.base_type, value)
        self[name] = val

    def get_array_of(self, size):
        return self

    def get_pointer_to(self):
        return self

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def get_dereference_of(self):
        return self

    def get_element_of(self):
        return self

    def to_dict(self, full_def=True):
        if not full_def:
            d = super().to_dict()
            return d
        d = super().to_dict()
        d['children'] = {k: v.to_dict() for k, v in self.symbols.items()}
        return d


class ReferenceType(Type):
    """
    A reference type in Saturn. Can hold a raw pointer, stack allocated object, or shared object.
    Performs automatic dereferencing.
    """
    HAS_SHARED_OWNERSHIP = (1 << 0)
    IS_HEAP_OBJECT       = (1 << 1)

    def __init__(self, name, stype, tclass):
        self.type = stype
        super().__init__(name, tclass, self.type.get_ir_type().as_pointer(), None, None)
        self.qualifiers = self.type.qualifiers.copy() + [('ref',)]
        self.traits = self.type.traits.copy()
        self.bits = -1

    def get_base_type(self):
        return self.type.get_base_type()

    def add_field(self, name, ftype, irvalue):
        self.type.add_field(name, ftype, irvalue)

    def get_field_index(self, name):
        return self.type.get_field_index(name)

    def get_field_type(self, index):
        return self.type.get_field_type(index)

    def get_fields_with_init(self):
        return self.type.get_fields_with_init()

    def has_ctor(self):
        return self.type.has_ctor()

    def get_ctor(self):
        return self.type.get_ctor()

    def add_ctor(self, ctor):
        self.type.add_ctor(ctor)

    def has_dtor(self):
        return self.type.has_dtor()

    def get_dtor(self):
        return self.type.get_dtor()

    def add_dtor(self, dtor):
        self.type.add_dtor(dtor)

    def has_operator(self, op):
        return self.type.has_operator(op)

    def add_operator(self, op, fn):
        # print(self.name, fn.name)
        self.type.add_operator(op, fn)

    def get_operator(self, op, fn):
        return self.type.get_operator(op)

    def is_reference(self):
        return True

    def to_dict(self, full_def=True):
        d = super().to_dict()
        d['symbol_type'] = 'type'
        d['type'] = 'reference'
        d['base'] = self.type.to_dict(full_def)
        # print(d)
        return d

    def __str__(self):
        return f'&{str(self.type)}'


class GenericType(Type):
    """
    A generic type in Saturn.
    """
    def __init__(self, name, base, type_args=None,
                 qualifiers=None, traits=None):
        if traits is None:
            traits = {}
        if qualifiers is None:
            qualifiers = []
        super().__init__(name, 'generic', None, qualifiers=qualifiers, traits=traits)
        self.name = name
        self.base: Type = base
        self.type_args = type_args
        self.qualifiers = qualifiers
        self.traits = traits
        self.specl = {}

    def specialize(self, module: ir.Module, targs):
        type_str = f'T{len(targs)}'
        for targ in targs:
            type_str += mangle_type(targ.get_type())
        uid = (module, type_str)
        type_name_to_arg = {}
        for i, arg in enumerate(self.type_args):
            type_name_to_arg[arg.name] = targs[i]
        if uid not in self.specl.keys():
            if isinstance(self.base, StructType):
                irtype = module.context.get_identified_type(self.base.name + type_str)
                spec = StructType(self.base.name, irtype,
                                  [],
                                  self.qualifiers.copy(),
                                  self.traits.copy())
                from ast import TupleTypeExpr
                for fld in self.base.fields:
                    base_type = fld.type.get_base_type()
                    if not isinstance(base_type, TupleTypeExpr):
                        if base_type.lvalue.name in type_name_to_arg.keys():
                            if base_type.is_generic_type():
                                fld_type = base_type.replace_types([
                                   (type_arg, type_name_to_arg[type_arg.name]) for type_arg in self.type_args])
                            else:
                                fld_type = fld.type.replace_base_type(type_name_to_arg[base_type.lvalue.name])
                        else:
                            if base_type.is_generic_type():
                                fld_type = base_type.replace_types([
                                   (type_arg, type_name_to_arg[type_arg.name]) for type_arg in self.type_args])
                                fld_type = fld.type.replace_base_type(fld_type)
                            else:
                                fld_type = fld.type.copy().get_type()
                    else:
                        replace_table = []
                        for ty in base_type.types:
                            if ty.is_generic_type():
                                new_type = ty.replace_types([
                                    (type_arg, type_name_to_arg[type_arg.name]) for type_arg in self.type_args])
                                replace_table.append((ty, new_type))
                        tuple_type = base_type.replace_types(replace_table + [
                            (type_arg, type_name_to_arg[type_arg.name]) for type_arg in self.type_args])
                        fld_type = fld.type.replace_base_type(tuple_type)
                    print(fld_type)
                    spec.add_field(fld.name, fld_type, None)
                    spec[fld.name].irvalue = fld.irvalue
                irtype.elements = [fld.type.get_ir_type() for fld in spec.fields]
                spec.irtype = irtype
            else:
                spec = None
            self.specl[uid] = spec
        return self.specl[uid]

    def get_ir_type(self):
        if self.irtype is None:
            pass
        return self.irtype

    def get_array_of(self, size):
        return ArrayType(self, size)

    def get_pointer_to(self):
        return PointerType(self)

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def to_dict(self, full_def=True):
        if not full_def:
            d = super().to_dict()
            return d
        d = super().to_dict()
        return d

    def __str__(self):
        s = f'{self.name}<['
        for arg in self.type_args:
            s += f'{str(arg)}, '
        s = s.rstrip(', ') + ']>'
        return s


def get_base_type(ty: Type):
    if ty.is_reference() and isinstance(ty, ReferenceType):
        return get_base_type(ty.type)
    if ty.is_actual_pointer():
        return get_base_type(ty.get_dereference_of())
    if ty.is_value():
        return ty
    if ty.is_array():
        return get_base_type(ty.get_element_of())
    return ty


def mangle_type(atype: Type):
    mname = ''
    if atype.is_const():
        mname += 'K'
    if atype.is_atomic():
        mname += 'V'
    if isinstance(atype, PointerType):
        mname += 'P'
        mname += mangle_type(atype.pointee)
        return mname
    if isinstance(atype, HVectorType):
        mname += f'H{atype.count}_'
        mname += mangle_type(atype.element)
        return mname
    if isinstance(atype, ArrayType):
        mname += f'A{atype.count}_'
        mname += mangle_type(atype.element)
        return mname
    if isinstance(atype, ReferenceType):
        mname += 'R'
        mname += mangle_type(atype.type)
        return mname
    if isinstance(atype, OptionalType):
        mname += 'O'
        mname += mangle_type(atype.base)
        return mname
    if isinstance(atype, FuncPointerType):
        mname += 'PF' + mangle_fn(atype)
        return mname
    if isinstance(atype, FuncType):
        mname += 'F' + mangle_fn(atype)
        return mname
    atype = get_base_type(atype)
    if atype.is_integer():
        if atype.get_integer_bits() == 8:
            mname += 'c' if atype.is_unsigned() else 'a'
        elif atype.get_integer_bits() == 16:
            mname += 't' if atype.is_unsigned() else 's'
        elif atype.get_integer_bits() == 32:
            mname += 'j' if atype.is_unsigned() else 'i'
        elif atype.get_integer_bits() == 64:
            mname += 'm' if atype.is_unsigned() else 'l'
        else:
            mname += 'j' if atype.is_unsigned() else 'i'
    elif atype.irtype == ir.FloatType():
        mname += 'f'
    elif atype.irtype == ir.DoubleType():
        mname += 'd'
    elif atype.irtype == irutil.FP128Type():
        mname += 'q'
    elif atype.is_bool():
        mname += 'b'
    elif atype.is_void():
        mname += 'v'
    elif atype.is_struct():
        mname += 'S%d%s' % (len(atype.name), atype.name)
    elif atype.is_tuple():
        tuple_elements = ''
        for ty in atype.type_list:
            tuple_elements += mangle_type(ty)
        mname += f'U{len(atype.type_list)}'
    else:
        mname += 'u'
    return mname


def mangle_generic(ty: GenericType):
    mname = '_ZN%s' % (mangle_symbol_name(ty))
    mname += f'T{len(ty.type_args)}'
    for arg in ty.type_args:
        mname += mangle_type(arg)


def mangle_fn(ty: Union[FuncType, FuncPointerType]):
    tcount = len(ty.atypes)
    out = f'{mangle_type(ty.get_return_type())}{tcount}'
    for atype in ty.atypes:
        out += mangle_type(atype)
    return out


def mangle_symbol_name(symbol: Symbol):
    full_name = symbol.get_full_name()
    mangled = ''
    segments = full_name.split('::')
    for segment in segments:
        mangled += f'{len(segment)}{segment}'
    return mangled


def mangle_symbol(symbol: Symbol, **kwargs):
    mname = '_ZN%s' % (mangle_symbol_name(symbol))
    if isinstance(symbol, Func):
        mname += 'E'
        atypes = kwargs['atypes']
        if len(atypes) == 0:
            mname += 'v'
            return mname
        for atype in atypes:
            mname += mangle_type(atype)
    return mname


def mangle_name(name: str, atypes: list):
    mname = '_ZN%d%sE' % (len(name), name)
    if len(atypes) == 0:
        mname += 'v'
        return mname
    for atype in atypes:
        mname += mangle_type(atype)
    return mname


def is_name_mangled(name: str) -> bool:
    return name.startswith('_Z')


def is_legal_user_defined_name(name: str) -> bool:
    if '.' in name:
        return False
    if is_name_mangled(name):
        return False
    if name.startswith('__saturn'):
        return False
    return True


def _consume_number(s: str) -> (int, str):
    num_s = ''
    while len(s) > 0 and s[0].isdigit():
        num_s += s[0]
        s = s[1:]
    if num_s == '':
        return 0, s
    return int(num_s), s


def demangle_type(name: str) -> (str, str, bool):
    if name[0] == 'P':
        return '*', name[1:], False
    if name[0] == 'R':
        return '&', name[1:], False
    if name[0] == 'V':
        return 'atomic ', name[1:], False
    if name[0] == 'K':
        return 'const ', name[1:], False
    if name[0] == 'M':
        return 'mut ', name[1:], False
    if name[0] == 'v':
        return 'void', name[1:], True
    if name[0] == 'i':
        return 'int', name[1:], True
    if name[0] == 'j':
        return 'uint', name[1:], True
    if name[0] == 's':
        return 'int16', name[1:], True
    if name[0] == 't':
        return 'uint16', name[1:], True
    if name[0] == 'l':
        return 'int64', name[1:], True
    if name[0] == 'm':
        return 'uint64', name[1:], True
    if name[0] == 'b':
        return 'bool', name[1:], True
    if name[0] == 'a':
        return 'int8', name[1:], True
    if name[0] == 'c':
        return 'byte', name[1:], True
    if name[0] == 'f':
        return 'float32', name[1:], True
    if name[0] == 'h':
        return 'float16', name[1:], True
    if name[0] == 'd':
        return 'float64', name[1:], True
    if name[0] == 'q':
        return 'float128', name[1:], True
    if name[0] == 'F':
        name = name[1:]
        stop = False
        ret_type = ''
        while not stop:
            ret_type_s, name, stop = demangle_type(name)
            ret_type += ret_type_s
        arg_count, name = _consume_number(name)
        out_str = 'fn('
        for i in range(arg_count):
            stop = False
            arg_type = ''
            while not stop:
                arg_type_s, name, stop = demangle_type(name)
                arg_type += arg_type_s
            out_str += arg_type + ', '
        out_str = out_str.rstrip(', ')
        out_str += f') {ret_type}'
        return out_str, name, True
    if name[0] == '_':
        name = name[1:]
        type_arg_index, name = _consume_number(name)
        type_args = [chr(ord('T') + i) for i in range(6)] + [chr(ord('A') + i) for i in range(10)]
        return type_args[type_arg_index], name, True
    if name[0] == 'S':
        name = name[2:]
        struct_name = ''
        while len(name) > 0 and name[0].isdigit():
            name_len, name = _consume_number(name)
            struct_name += name[:name_len] + '::'
            name = name[name_len:]
        struct_name = struct_name.rstrip('::')
        if len(name) > 0 and name[0] == 'T':
            name = name[1:]
            type_len, name = _consume_number(name)
            gtype_str = '<'
            for i in range(type_len):
                stop = False
                arg_type = ''
                while not stop:
                    arg_type_s, name, stop = demangle_type(name)
                    arg_type += arg_type_s
                gtype_str += arg_type + ', '
            gtype_str = gtype_str.rstrip(', ') + '>'
            struct_name += gtype_str
        return struct_name, name, True
    if name[0] == 'A':
        name = name[1:]
        array_len, name = _consume_number(name)
        out_str = f"[{array_len}]"
        return out_str, name, False
    if name[0] == 'H':
        name = name[1:]
        hvector_len, name = _consume_number(name)
        out_str = f"[<{hvector_len}>]"
        return out_str, name, False
    return 'Unk', name[1:], True


def demangle_symbol(name: str) -> (str, str):
    if not name.startswith('N'):
        return '', name
    symbol = ''
    while name.startswith('N'):
        name = name.strip('N')
        length, name = _consume_number(name)
        symbol += name[:length] + '::'
        name = name[length:]
    symbol = symbol.rstrip('::')
    if name.startswith('E'):
        name = name.strip('E')
        args = []
        arg = ''
        while len(name) > 0:
            parg, name, stop = demangle_type(name)
            arg += parg
            if not stop:
                continue
            args.append(arg)
            arg = ''
        args_string = ''
        for arg in args:
            args_string += arg + ', '
        args_string = args_string.rstrip(', ')
        return f'fn {symbol}({args_string});', ''
    return symbol, name


def demangle_name(name: str) -> (str, str):
    if not name.startswith('_ZN'):
        return name, ''
    name = name.strip('_ZN')
    fn_name = ''
    while len(name) > 0 and name[0].isdigit():
        name_size_s = ''
        while name[0].isdigit():
            name_size_s += name[0]
            name = name[1:]
        name_size = int(name_size_s)
        fn_name += name[:name_size] + '::'
        name = name[name_size:]
    fn_name = fn_name.rstrip('::')
    if len(name) > 0 and name[0] == 'T':
        name = name[1:]
        type_len, name = _consume_number(name)
        type_args = [chr(ord('T') + i) for i in range(7)] + [chr(ord('A') + i) for i in range(9)]
        gtype_str = '<'
        for i in range(type_len):
            stop = False
            arg_type = f'{type_args[i]} = '
            while not stop:
                arg_type_s, name, stop = demangle_type(name)
                arg_type += arg_type_s
            gtype_str += arg_type + ', '
        gtype_str = gtype_str.rstrip(', ') + '>'
        fn_name += gtype_str
    name = name.strip('E')
    args = []
    arg = ''
    while len(name) > 0:
        parg, name, stop = demangle_type(name)
        arg += parg
        if not stop:
            continue
        args.append(arg)
        arg = ''
    args_string = ''
    for arg in args:
        args_string += arg + ', '
    args_string = args_string.rstrip(', ')
    return fn_name, args_string


def demangle_name_as_function(name: str) -> str:
    fn_name, args_string = demangle_name(name)
    return f"fn {fn_name}({args_string});"


def demangle_name_as_variable(name: str) -> str:
    fn_name, args_string = demangle_name(name)
    return f"var {fn_name};"


def print_types(types_list: list):
    if len(types_list) == 0:
        return 'void'
    else:
        s: str = ''
        for ty in types_list:
            s += str(ty)
            s += ', '
        s = s.rstrip(', ')
        return s


class FuncOverload:
    """
    A specific overload for a function.
    """
    def __init__(self, name, fn, rtype, atypes=None, default_args=None, traits=None):
        if traits is None:
            traits = {}
        if atypes is None:
            atypes = []
        self.name = name
        self.link_name = name
        self.fn = fn
        self.rtype = rtype
        self.atypes = atypes
        self.default_args = default_args
        self.traits = traits
        self._key = ''
        self.irvalue = None

    def __str__(self):
        s = f"overload {self.name} fn({print_types(self.atypes)}): {self.rtype}"
        return s

    def key(self):
        if self._key == '':
            self._key = mangle_name('', self.atypes)
        return self._key

    def to_dict(self):
        d = {'name': self.name,
             'symbol_type': 'overload',
             'rtype': self.rtype.to_dict(False),
             'traits': self.traits,
             'atypes': [ty.to_dict(False) for ty in self.atypes]}
        if self.link_name != self.name:
            d['link_name'] = self.link_name
        return d


def get_type_match_value(expected: Type, actual: Type):
    if expected is actual:
        return 10
    if expected.is_similar(actual):
        return 5
    if expected.is_reference() and expected.type is actual:
        return 5
    if expected.is_pointer() and actual is types['null_t']:
        return 5
    if expected.is_byte_pointer() and actual.is_pointer():
        return 5
    if isinstance(expected, FuncType) and isinstance(actual, FuncType):
        if len(expected.atypes) < len(actual.atypes):
            return 0
        if len(expected.atypes) == len(actual.atypes):
            retval = 10
            for i in range(len(expected.atypes)):
                val = get_type_match_value(expected.atypes[i], actual.atypes[i])
                if val == 0:
                    return 0
                if val == 5:
                    retval = 5
            return retval
    return 0


def get_implicit_conversion_for_match(expected: list, actual: list):
    if len(expected) < len(actual):
        return None
    if len(expected) == len(actual):
        conversions = {}
        for i in range(len(expected)):
            exp = expected[i]
            act = actual[i]
            val = get_type_match_value(exp, act)
            if val == 5:
                conversions[i] = exp
            i += 1
        return conversions
    return None


def get_arg_list_match_value(expected: list, actual: list, default: list):
    if default is None:
        default = []
    if len(expected) == len(actual) == 0:
        return 10
    if len(expected) < len(actual):
        return 0
    if len(expected) == len(actual):
        match = 0
        for i in range(len(expected)):
            exp = expected[i]
            act = actual[i]
            val = get_type_match_value(exp, act)
            if val == 0:
                return 0
            match += val
        return match
    if len(expected) > len(actual) >= len(expected) - len(default):
        match = 10 if len(actual) == 0 and len(expected) - len(default) == 0 else 0
        for i in range(len(expected) - len(default)):
            exp = expected[i]
            act = actual[i]
            val = get_type_match_value(exp, act)
            if val == 0:
                return 0
            match += val
        return match
    return 0


class OverloadMatch:
    def __init__(self, overload, actual_args, score, implicit_conversions=None):
        self.overload = overload
        self.actual_args = actual_args
        self.score = score
        self.requires_implicit_conversions = implicit_conversions is not None
        if implicit_conversions is None:
            self.implicit_conversions = {}
        else:
            self.implicit_conversions = implicit_conversions

    def __str__(self):
        s = f"Match: (score = {str(self.score)}) ({print_types(self.overload.atypes)}) ?= ({print_types(self.actual_args)})"
        return s


def get_overload_match(expected: FuncOverload, actual: list):
    match = OverloadMatch(expected, actual,
                          get_arg_list_match_value(expected.atypes, actual, expected.default_args),
                          get_implicit_conversion_for_match(expected.atypes, actual))
    return match


class Func(Symbol):
    """
    A function value in Saturn.
    """
    def __init__(self, name, rtype, overloads=None, traits=None,
                 visibility=Visibility.DEFAULT, link_type=LinkageType.DEFAULT,
                 c_decl=False):
        super().__init__(name, visibility=visibility, link_type=link_type, c_decl=c_decl)
        if traits is None:
            traits = {}
        if overloads is None:
            overloads = {}
        self.rtype = rtype
        self.overloads = overloads.copy()
        self.traits = traits

    def add_overload(self, atypes, fn, rtype=None, default_args=None):
        key = mangle_name('', atypes)
        if rtype is None:
            rtype = self.rtype
        self.overloads[key] = FuncOverload(key, fn, rtype, atypes, default_args, self.traits)
        return self.overloads[key]

    def add_existing_overload(self, ovrld):
        self.overloads[ovrld.name] = ovrld

    def search_overload(self, atypes):
        """
        Searches all available overloads and chooses the best match that requires no
        explicit conversions.\n
        :param atypes:
        :return:
        """
        available_overloads = [get_overload_match(overload, atypes) for overload in self.overloads.values()]
        available_overloads.sort(key=lambda i: i.score, reverse=True)
        for overload_match in available_overloads:
            if overload_match.score != 0:
                return overload_match
        return None

    def get_overload(self, atypes):
        key = mangle_name('', atypes)
        if key in self.overloads:
            return self.overloads[key].fn
        return None

    def get_default_overload(self):
        return list(self.overloads.values())[0]

    def has_default_overload(self):
        return len(self.overloads) == 1

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} fn {self.name}: {str(self.rtype)}"
        for overload in self.overloads.values():
            s += f"\t{str(overload)}"
        return s

    def to_dict(self):
        d = super().to_dict()
        d['symbol_type'] = 'function'
        d['traits'] = self.traits
        d['rtype'] = self.rtype.to_dict(False)
        d['overloads'] = {name: overload.to_dict() for name, overload in self.overloads.items()}
        return d


class TupleType(Type):
    """
    A tuple type in Saturn.
    """
    def __init__(self, name, irvalue, type_list, elements=None, qualifiers=None, traits=None):
        if qualifiers is None:
            qualifiers = []
        if traits is None:
            traits = {}
        if elements is None:
            elements = []
        self.name = name
        self.irtype = irvalue
        self.type_list = type_list
        self.elements = elements.copy()
        self.tclass = 'tuple'
        self.qualifiers = qualifiers
        self.traits = traits
        self.visibility = Visibility.DEFAULT
        self.link_type = LinkageType.PRIVATE
        self._next_element_idx = 0

    def get_ir_type(self):
        self.irtype = ir.LiteralStructType([ty.get_ir_type() for ty in self.type_list])
        return self.irtype

    def add_element(self, ftype, irvalue):
        if irvalue is not None:
            self.elements.append(Value("_%d" % self._next_element_idx, ftype, irvalue.eval()))
        else:
            self.elements.append(Value("_%d" % self._next_element_idx, ftype, None))
        self._next_element_idx += 1

    def get_element_type(self, index):
        return self.elements[index].type

    def get_elements_with_value(self):
        withval = []
        for el in self.elements:
            if el.irvalue is not None:
                withval.append(el)
        return withval

    def get_pointer_to(self):
        return PointerType(self)

    def get_pointer_to_old(self):
        return TupleType(self.name,
                         ir.PointerType(self.get_ir_type()),
                         self.type_list.copy(),
                         self.elements.copy(),
                         qualifiers=self.qualifiers + [('ptr',)],
                         traits=self.traits)

    def get_dereference_of_old(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'ptr':
                ql.pop(i)
                break
        ql.reverse()
        return TupleType(self.name,
            self.irtype.pointee,
            self.elements,
            qualifiers=ql,
            traits=self.traits
        )

    def get_element_of_old(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'array':
                ql.pop(i)
                break
        ql.reverse()
        return TupleType(self.name,
            self.irtype,
            self.elements,
            qualifiers=ql,
            traits=self.traits
        )

    def to_dict(self, full_def=True):
        d = super().to_dict()
        d['elements'] = {k: v.to_dict() for k, v in self.elements}
        return d

    def __str__(self):
        s = 'tuple('
        for ty in self.type_list:
            s += f'{str(ty.lvalue.get_name())}, '
        s = s.rstrip(', ') + ')'
        return s


def make_tuple_type(els: list):
    s = TupleType("",
        ir.LiteralStructType([el.get_type().get_ir_type() for el in els]),
        [],
    )
    return s


class OptionalType(Type):
    """
    An optional type in Saturn.
    """
    def __init__(self, name, irtype, base, qualifiers=None, traits=None):
        super().__init__(name, 'optional', irtype, qualifiers, traits)
        if qualifiers is None:
            qualifiers = []
        if traits is None:
            traits = {}
        self.base = base
        self.qualifiers = qualifiers
        self.traits = traits

    def get_base_type(self):
        return self.base

    def get_pointer_to(self):
        return self

    def get_dereference_of(self):
        return self.base


def make_optional_type(base: Type):
    s = OptionalType("",
                     ir.LiteralStructType([ir.IntType(1), base.get_ir_type()]),
                     base)
    return s


class SliceType(Type):
    """
    An immutable array reference in Saturn.
    """

    def __init__(self, element_type, qualifiers=None, traits=None):
        super().__init__(element_type.name, element_type.tclass, None, qualifiers=qualifiers, traits=traits)
        if qualifiers is None:
            qualifiers = []
        if traits is None:
            traits = {}
        self.element = element_type
        self.qualifiers = qualifiers
        self.traits = traits

    def get_ir_type(self):
        if self.irtype is None:
            i64 = ir.IntType(64)
            self.irtype = ir.LiteralStructType([ir.ArrayType(self.element.get_ir_type(), 0).as_pointer(), i64])
        return self.irtype

    def get_base_type(self):
        return self.element

    def is_slice(self):
        return True

    def get_element_of(self):
        return self.element

    def __str__(self):
        s = f"[]{str(self.element)}"
        return s


def array_to_slice(ty: Type):
    elty = ty.get_element_of()
    destty = None # make_slice_type(elty)
    array_size = 0
    for q in reversed(ty.qualifiers):
        if q[0] == 'array':
            array_size = q[1]
            break
    irtype = destty.get_ir_type()
    return destty, ir.Constant(irtype, [array_size, irtype(irtype.null)])


def struct_from_dict(package, module, d, parent=None):
    name = d['name']
    ctor = None if 'ctor' not in d else d['ctor']
    dtor = None if 'dtor' not in d else d['dtor']
    if package.lookup_symbol(name) is not None:
        ty = package.lookup_symbol(name)
        if isinstance(d['type'], dict):
            dty = d['type']
            if dty['type'] == 'pointer':
                ty = ty.get_pointer_to()
        return ty
    operators = {} if 'operators' not in d else d['operators']
    methods = {} if 'methods' not in d else d['methods']
    qualifiers = [] if 'qualifiers' not in d else d['qualifiers']
    traits = {} if 'traits' not in d else d['traits']
    struct = StructType(name,
                        module.context.get_identified_type(name),
                        [],
                        qualifiers=qualifiers,
                        traits=traits)
    package.add_symbol(name, struct)
    irtypes = []
    for name, field in d['fields'].items():
        ty = symbol_from_dict(package, module, field['value_type'], struct)
        struct.add_field(name, ty, None)
        irtypes.append(ty.get_ir_type())
    for op in operators.keys():
        opfn = symbol_from_dict(package, module, operators[op], struct)
        struct.add_operator(op, opfn)
        for overload in opfn.overloads.values():
            package.add_symbol(overload.name, opfn)
    for name, method in methods.items():
        methodfn = symbol_from_dict(package, module, method, struct)
        struct.add_method(name, methodfn)
        struct[name] = methodfn
        methodfn.parent = struct
    name = d['name']
    if module.context.get_identified_type(name).is_opaque and len(d['fields']) > 0:
        idstruct = module.context.get_identified_type(name)
        idstruct.set_body(*irtypes)
        struct.irtype = idstruct
    if ctor is not None:
        struct.add_ctor(symbol_from_dict(package, module, ctor, struct))
    if dtor is not None:
        struct.add_dtor(symbol_from_dict(package, module, dtor, struct))
    return struct


def parse_type_from_dict(package, module, d, parent=None):
    if d['type'] == 'pointer':
        ty = parse_type_from_dict(package, module, d['pointee'], d).get_pointer_to()
        ty.qualifiers = d['qualifiers'] if 'qualifiers' in d else {}
        return ty
    if d['type'] == 'fn_ptr':
        ty = FuncPointerType(d['name'], None, d['rtype'], d['atypes'])
        ty.qualifiers = d['qualifiers'] if 'qualifiers' in d else {}
        return ty
    if d['type'] == 'array':
        ty = parse_type_from_dict(package, module, d['element'], d).get_array_of(d['count'])
        ty.qualifiers = d['qualifiers'] if 'qualifiers' in d else {}
        return ty
    if d['type'] == 'reference':
        ty = parse_type_from_dict(package, module, d['base'], d).get_reference_to()
        ty.qualifiers = d['qualifiers'] if 'qualifiers' in d else {}
        return ty
    if package.lookup_symbol(d['name']) is not None:
        name = d['name']
        ty = package.lookup_symbol(name)
        return ty
    elif d['name'] in types:
        return types[d['name']]
    if d['tclass'] == 'struct':
        return struct_from_dict(package, module, d, parent)
    else:
        return Type(d['name'],
                    d['tclass'],
                    irtype=None,
                    qualifiers=d['qualifiers'],
                    traits=d['traits'])


def symbol_from_dict(package, module, d_, parent=None):
    d = d_.copy()
    ty = d['symbol_type']
    c_decl = False if 'c_decl' not in d else d['c_decl']
    if ty == 'type':
        return parse_type_from_dict(package, module, d)
    elif ty == 'value':
        valty = symbol_from_dict(package, module, d['value_type'].copy())
        val = GlobalValue(d['name'], valty,
                          ir.GlobalVariable(module, valty.get_ir_type(), d['name']), d['qualifiers'], d['obj_type'],
                          Visibility.INDEX[d['visible']])
        return val
    elif ty == 'function':
        name = d['name']
        link_name = d['link_name'] if 'link_name' in d else ''
        rtype = symbol_from_dict(package, module, d['rtype'].copy())
        # print(rtype, name)
        func = Func(name, rtype,
                    traits=d['traits'],
                    visibility=Visibility.INDEX[d['visible']],
                    link_type=LinkageType.INDEX[d['link_type']])
        func.parent = parent
        for key, overload in d['overloads'].items():
            atypes = [symbol_from_dict(package, module, v.copy(), overload) for v in overload['atypes']]
            irtypes = [] if len(atypes) == 1 and atypes[0].is_void() else [atype.get_ir_type() for atype in atypes]
            rtype = symbol_from_dict(package, module, overload['rtype'].copy())
            fnty = ir.FunctionType(rtype.get_ir_type(), irtypes)
            link_name = overload['link_name'] if 'link_name' in overload else ''

            ovld = FuncOverload(mangle_name('', atypes), None, func.rtype, atypes, func.traits.copy())
            if not c_decl:
                fname = mangle_symbol(func, atypes=atypes)
            else:
                fname = name
            if link_name != '':
                fname = link_name
            try:
                fn = module.get_global(fname)
            except KeyError:
                fn = ir.Function(module, fnty, fname)
            ovld.fn = fn
            func.add_existing_overload(ovld)
        return func
    else:
        return Symbol(d['name'], None,
                      visibility=Visibility.INDEX[d['visible']],
                      link_type=LinkageType.INDEX[d['link_type']])


def get_common_type(ty1: Type, ty2: Type):
    if ty1 is ty2:
        return ty1
    if ty1.is_integer() and ty2.is_integer():
        if ty1.get_integer_bits() > ty2.get_integer_bits():
            return ty1
        else:
            return ty2
    if ty1.is_float() and ty2.is_float():
        pass
    return None
