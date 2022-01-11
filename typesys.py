from llvmlite import ir
from package import Symbol, Visibility, LinkageType
from irutil import FP128Type


class Type(Symbol):
    """
    A semantic type in Saturn.\n
    name: identifier for type.\n
    irtype: the underlying llvm type of this semantic type.\n
    tclass: a category for how the type is treated semantically.\n
    qualifiers: adds special qualifiers to the base type (pointers, arrays, const, immut...)\n
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
        self.qualifiers = qualifiers
        self.traits = traits
        self.bits = -1

    def get_integer_bits(self):
        if self.bits != -1:
            return self.bits
        if self.name == 'int' or self.name == 'int32' or self.name == 'uint' or self.name == 'uint32':
            self.bits = 32
            return 32
        elif self.name == 'int64' or self.name == 'uint64':
            self.bits = 64
            return 64
        elif self.name == 'byte' or self.name == 'int8':
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

    def get_array_count(self):
        array_size = -1
        for q in reversed(self.qualifiers):
            if q[0] == 'array':
                array_size = q[1]
                break
        return array_size

    def make_array(self, size):
        self.qualifiers.append(('array', size))

    def get_array_of(self, size):
        return Type(self.name,
            self.tclass,
            ir.ArrayType(self.irtype, size),
            qualifiers=self.qualifiers + [('array', size)],
            traits=self.traits
        )

    def make_pointer(self):
        self.qualifiers.append(('ptr',))
        self.irtype = self.irtype.as_pointer()

    def get_pointer_to(self):
        return Type(self.name,
            self.tclass,
            self.irtype.as_pointer(),
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def get_dereference_of(self):
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
            traits=self.traits
        )

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def get_element_of(self):
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
                traits=self.traits
            )
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

    def is_array(self):
        if len(self.qualifiers) > 0:
            return self.qualifiers[-1][0] == 'array'
        return False

    def is_pointer(self):
        return ('ptr',) in self.qualifiers or self.name == 'cstring' or self.name == 'null_t'

    def is_actual_pointer(self):
        return ('ptr',) in self.qualifiers

    def is_byte_pointer(self):
        return self.is_actual_pointer() and (self.name == 'byte' or self.name == 'C::char')

    def is_value(self):
        return not (self.is_array() or self.is_pointer())

    def is_unsigned(self):
        return self.tclass == 'uint'

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
        return ('ref',) in self.qualifiers

    def is_void(self):
        return self.tclass == 'void'

    def is_iterable(self):
        return self.is_array() or self.is_string()

    def is_const(self):
        return 'const' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers

    def is_atomic(self):
        return 'atomic' in self.qualifiers

    def has_dtor(self):
        return False

    def to_dict(self, full_def=True):
        d = super().to_dict()
        d['symbol_type'] = 'type'
        d['type'] = {}
        dt = d['type']
        for q in self.qualifiers:
            if q[0] == 'ptr':
                dt['type'] = 'pointer'
                dt['pointee'] = {}
                dt = dt['pointee']
            elif q[0] == 'array':
                dt['type'] = 'array'
                dt['size'] = q[1]
                dt['element'] = {}
                dt = dt['element']
        dt['type'] = 'named'
        dt['name'] = self.name
        dt['tclass'] = self.tclass
        d['tclass'] = self.tclass
        d['traits'] = self.traits
        d['name'] = self.name
        d['qualifiers'] = self.qualifiers
        # print(d)
        return d

    def __str__(self):
        s = str()
        for q in reversed(self.qualifiers):
            if q[0] == 'ptr':
                s += '*'
            elif q[0] == 'array':
                s += '[%d]' % q[1]
            elif q[0] == 'ref':
                s += '&'
        s += self.name
        return s

    def is_similar(self, other):
        """
        Checks whether the two values have similar types for the purpose of fundimental operations.
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
        return FuncType(self.name,
            self.irtype.as_pointer(),
            self.rtype,
            self.atypes.copy(),
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def __str__(self):
        s = ""
        if self.is_pointer():
            s += '*'
        arg_str = ""
        for atype in self.atypes:
            arg_str += f"{str(atype)}, "
        arg_str = arg_str.rstrip(", ")
        s += f"fn({arg_str}): {str(self.rtype)}"
        return s


class StructType(Type):
    """
    A structure type in Saturn.
    """
    def __init__(self, name, irtype, fields=None, qualifiers=None, traits=None, operators=None, methods=None):
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
        self.ctor = None
        self.dtor = None
        self.operator = operators.copy()
        self.methods = methods.copy()

    def get_ir_type(self):
        if self.irtype is None:
            pass
        return self.irtype

    def add_field(self, name, ftype, irvalue):
        if irvalue is not None:
            value = Value(name, ftype, irvalue.eval())
        else:
            value = Value(name, ftype, None)
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
        if not self.has_method(name):
            self.methods[name] = fn
            self[name] = fn
            fn.parent = self

    def get_array_of(self, size):
        return StructType(self.name,
                          ir.ArrayType(self.irtype, size),
                          self.fields,
                          qualifiers=self.qualifiers + [('array', size)],
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods
                          )

    def get_pointer_to(self):
        return StructType(self.name,
                          self.irtype.as_pointer(),
                          self.fields,
                          qualifiers=self.qualifiers + [('ptr',)],
                          traits=self.traits,
                          operators=self.operator,
                          methods=self.methods
                          )

    def get_reference_to(self):
        return ReferenceType(self.name,
                             self,
                             self.tclass)

    def get_dereference_of(self):
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
            operators=self.operator
        )

    def get_element_of(self):
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
            operators=self.operator
        )

    def to_dict(self, full_def=True):
        if not full_def:
            d = super().to_dict()
            return d
        d = super().to_dict()
        d['fields'] = {field.name: field.to_dict() for field in self.fields}
        d['operators'] = {key: func.to_dict() for key, func in self.operator.items()}
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
        self.type.add_operator(op, fn)

    def get_operator(self, op, fn):
        return self.type.get_operator(op)

    def to_dict(self, full_def=True):
        d = super().to_dict()
        d['symbol_type'] = 'type'
        d['type'] = {}
        dt = d['type']
        dt['type'] = 'named'
        dt['name'] = self.name
        d['tclass'] = self.tclass
        d['traits'] = self.traits
        d['name'] = self.name
        d['qualifiers'] = self.qualifiers
        # print(d)
        return d


def get_base_type(ty: Type):
    if ty.is_value():
        return ty
    if ty.is_actual_pointer():
        return get_base_type(ty.get_dereference_of())
    if ty.is_array():
        return get_base_type(ty.get_element_of())
    return ty


def mangle_name(name: str, atypes: list):
    mname = '_Z%d%sE' % (len(name), name)
    if len(atypes) == 0:
        mname += 'v'
        return mname
    for atype in atypes:
        if atype.is_const():
            mname += 'K'
        for q in atype.qualifiers:
            if q[0] == 'ptr':
                mname += 'P'
            elif q[0] == 'ref':
                mname += 'R'
        if atype.is_atomic():
            mname += 'A'
        atype = get_base_type(atype)
        if atype.irtype == types['int'].irtype:
            mname += 'i'
        elif atype.irtype == types['int64'].irtype:
            mname += 'l'
        elif atype.irtype == types['int16'].irtype:
            mname += 's'
        elif atype.irtype == types['int8'].irtype:
            mname += 'c'
        elif atype.irtype == types['cstring'].irtype:
            mname += 'Pc'
        elif atype.irtype == ir.FloatType():
            mname += 'f'
        elif atype.irtype == ir.DoubleType():
            mname += 'd'
        elif atype.irtype == ir.IntType(1):
            mname += 'b'
        elif atype.irtype == ir.VoidType():
            mname += 'v'
        elif atype.is_struct():
            mname += 'S%d%s' % (len(atype.name), atype.name)
        else:
            mname += 'u'
    return mname


def demangle_name(name: str):
    pass


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
    def __init__(self, name, fn, rtype, atypes=None, traits=None):
        if traits is None:
            traits = {}
        if atypes is None:
            atypes = []
        self.name = name
        self.fn = fn
        self.rtype = rtype
        self.atypes = atypes
        self.traits = traits
        self._key = ''

    def __str__(self):
        s = f"overload {self.name} fn({print_types(self.atypes)})"
        return s

    def key(self):
        if self._key == '':
            self._key = mangle_name('', self.atypes)
        return self._key

    def to_dict(self):
        d = {'name': self.name,
             'symbol_type': 'overload',
             'traits': self.traits,
             'atypes': [ty.to_dict(False) for ty in self.atypes]}
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


def get_arg_list_match_value(expected: list, actual: list):
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
                          get_arg_list_match_value(expected.atypes, actual),
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

    def add_overload(self, atypes, fn):
        key = mangle_name('', atypes)
        self.overloads[key] = FuncOverload(key, fn, self.rtype, atypes, self.traits)

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
    def __init__(self, name, irtype, elements=None, qualifiers=None, traits=None):
        if qualifiers is None:
            qualifiers = []
        if traits is None:
            traits = {}
        if elements is None:
            elements = []
        self.name = name
        self.irtype = irtype
        self.elements = elements.copy()
        self.tclass = 'tuple'
        self.qualifiers = qualifiers
        self.traits = traits
        self.visibility = Visibility.DEFAULT
        self.link_type = LinkageType.PRIVATE
        self._next_element_idx = 0

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
        return TupleType(self.name,
            self.irtype.as_pointer(),
            self.elements.copy(),
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def get_dereference_of(self):
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

    def get_element_of(self):
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
    def __init__(self, name, irtype, element, qualifiers=None, traits=None):
        super().__init__(name, 'slice', irtype, qualifiers, traits)
        if qualifiers is None:
            qualifiers = []
        if traits is None:
            traits = {}
        self.element = element
        self.qualifiers = qualifiers
        self.traits = traits

    def get_ir_type(self):
        if self.irtype is None:
            i64 = ir.IntType(64)
            self.irtype = ir.LiteralStructType([i64, self.element.get_ir_type().as_pointer()])
        return self.irtype

    def get_base_type(self):
        return self.element

    def get_pointer_to(self):
        return SliceType(self.name,
                         self.get_ir_type().as_pointer(),
                         self.element,
                         qualifiers=self.qualifiers + [('ptr',)],
                         traits=self.traits)

    def get_dereference_of(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'ptr':
                ql.pop(i)
                break
        ql.reverse()
        return SliceType(self.name,
                         self.get_ir_type().pointee,
                         self.element,
                         qualifiers=ql,
                         traits=self.traits)

    def get_element_of(self):
        return self.element

    def __str__(self):
        s = f"[]{str(self.element)}"
        return s


def make_slice_type(ty: Type):
    s = SliceType("",
                  None,
                  ty)
    return s


def array_to_slice(ty: Type):
    elty = ty.get_element_of()
    destty = make_slice_type(elty)
    array_size = 0
    for q in reversed(ty.qualifiers):
        if q[0] == 'array':
            array_size = q[1]
            break
    irtype = destty.get_ir_type()
    return destty, ir.Constant(irtype, [array_size, irtype(irtype.null)])


def parse_type_from_dict(package, module, d, parent=None):
    if d['type'] == 'pointer':
        return parse_type_from_dict(package, module, d['pointee'], d).get_pointer_to()
    if package.lookup_symbol(d['name']) is not None:
        name = d['name']
        ty = package.lookup_symbol(name)
        return ty
    elif d['name'] in types:
        return types[d['name']]
    return Type(d['name'],
                d['tclass'],
                irtype=None,
                qualifiers=d['qualifiers'],
                traits=d['traits'])


def symbol_from_dict(package, module, d, parent=None):
    ty = d['symbol_type']
    c_decl = False if 'c_decl' not in d else d['c_decl']
    if ty == 'type':
        if d['tclass'] != 'struct':
            return parse_type_from_dict(package, module, d['type'], d)
        else:
            name = d['name']
            if package.lookup_symbol(name) is not None:
                ty = package.lookup_symbol(name)
                if isinstance(d['type'], dict):
                    dty = d['type']
                    if dty['type'] == 'pointer':
                        ty = ty.get_pointer_to()
                return ty
            elif name in types:
                return types[name]
            operators = {} if 'operators' not in d else d['operators']
            struct = StructType(name,
                                module.context.get_identified_type(name),
                                [],
                                qualifiers=d['qualifiers'],
                                traits=d['traits'])
            irtypes = []
            for name, field in d['fields'].items():
                ty = symbol_from_dict(package, module, field['value_type'], field)
                struct.add_field(name, ty, None)
                irtypes.append(ty.get_ir_type())
            for op, val in operators.items():
                opfn = symbol_from_dict(package, module, val)
                struct.add_operator(op, opfn)
            name = d['name']
            if module.context.get_identified_type(name).is_opaque and len(d['fields']) > 0:
                idstruct = module.context.get_identified_type(name)
                idstruct.set_body(*irtypes)
                struct.irtype = idstruct
            return struct
    elif ty == 'value':
        valty = symbol_from_dict(package, module, d['value_type'], d)
        val = Value(d['name'], valty,
                     None, d['qualifiers'], d['obj_type'],
                     Visibility.INDEX[d['visible']])
        return val
    elif ty == 'function':
        name = d['name']
        rtype = symbol_from_dict(package, module, d['rtype'], d)
        func = Func(name, rtype,
                    traits=d['traits'],
                    visibility=Visibility.INDEX[d['visible']],
                    link_type=LinkageType.INDEX[d['link_type']])
        for key, overload in d['overloads'].items():
            atypes = [symbol_from_dict(package, module, v, overload) for v in overload['atypes']]
            irtypes = [] if len(atypes) == 1 and atypes[0].is_void() else [atype.get_ir_type() for atype in atypes]
            fnty = ir.FunctionType(rtype.get_ir_type(), irtypes)
            if not c_decl:
                fname = mangle_name(name, atypes)
            else:
                fname = name
            try:
                fn = module.get_global(fname)
            except KeyError:
                fn = ir.Function(module, fnty, fname)
            func.add_overload(atypes, fn)
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
