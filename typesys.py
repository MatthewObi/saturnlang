from llvmlite import ir

class Type():
    """
    A semantic type in Saturn.\n
    name: identifier for type.\n
    irtype: the underlying llvm type of this semantic type.\n
    tclass: a category for how the type is treated semantically.\n
    qualifiers: adds special qualifiers to the base type (pointers, arrays, const, immut...)\n
    traits: special instances that change how a type is treated by the compiler.
    """
    def __init__(self, name, irtype, tclass, qualifiers=[], traits=[]):
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

    def make_array(self, size):
        self.qualifiers.append(('array', size))

    def get_array_of(self, size):
        return Type(self.name, 
            ir.ArrayType(self.irtype, size), 
            self.tclass, 
            qualifiers=self.qualifiers + [('array', size)],
            traits=self.traits
        )

    def make_pointer(self):
        self.qualifiers.append(('ptr',))
        self.irtype = self.irtype.as_pointer()

    def get_pointer_to(self):
        return Type(self.name, 
            self.irtype.as_pointer(), 
            self.tclass, 
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def get_deference_of(self):
        ql = self.qualifiers.copy()
        ql.reverse()
        for i in range(len(ql)):
            if ql[i][0] == 'ptr':
                ql.pop(i)
                break
        ql.reverse()
        return Type(self.name, 
            self.irtype.pointee, 
            self.tclass, 
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
        return Type(self.name, 
            self.irtype.element, 
            self.tclass, 
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

    def is_string(self):
        return self.tclass == 'string'

    def is_struct(self):
        return self.tclass == 'struct'

    def is_iterable(self):
        return self.is_array() or self.is_string()

    def is_const(self):
        return 'const' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers
    
    def is_atomic(self):
        return 'atomic' in self.qualifiers

    def __str__(self):
        s = str()
        for q in self.qualifiers:
            if q[0] == 'ptr':
                s += '*'
            elif q[0] == 'array':
                s += '[%d]' % q[1]
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
        return False

    def is_convertable(self, other):
        if self.tclass == other.tclass:
            return True
        return False

types = {
    "void": Type("void", ir.VoidType(), 'void', traits=['TNoType']),
    "int": Type("int", ir.IntType(32), 'int', traits=['TIntAny']),
    "int32": Type("int32", ir.IntType(32), 'int'),
    "int64": Type("int64", ir.IntType(64), 'int'),
    "int16": Type("int16", ir.IntType(16), 'int'),
    "int8": Type("int8", ir.IntType(8), 'int'),
    "byte": Type("byte", ir.IntType(8), 'uint'),
    "uint": Type("uint", ir.IntType(32), 'uint', traits=['TIntAny']),
    "uint64": Type("uint64", ir.IntType(64), 'uint'),
    "uint32": Type("uint32", ir.IntType(32), 'uint'),
    "uint16": Type("uint16", ir.IntType(16), 'uint'),
    "float32": Type("float32", ir.FloatType(), 'float'),
    "float64": Type("float64", ir.DoubleType(), 'float'),
    "bool": Type("bool", ir.IntType(1), 'bool'),
    "cstring": Type("cstring", ir.IntType(8).as_pointer(), 'string', traits=['TOpaquePtr']),
    "null_t": Type("null_t", ir.IntType(8).as_pointer(), 'null', traits=['TNoDereference', 'TOpaquePtr']),
}

class Value():
    """
    A saturn value.
    """
    def __init__(self, name, stype, irvalue, qualifiers=[]):
        self.name = name
        self.type = stype
        self.irvalue = irvalue
        self.qualifiers=qualifiers

    def is_const(self):
        return 'const' in self.qualifiers

    def is_immut(self):
        return 'immut' in self.qualifiers
    
    def is_atomic(self):
        return 'atomic' in self.qualifiers

class FuncType():
    """
    A semantic function type in Saturn.
    """
    def __init__(self, name, rtype, atypes=[]):
        self.name = name
        self.rtype = rtype
        self.atypes = atypes


class StructType(Type):
    """
    A structure type in Saturn.
    """
    def __init__(self, name, irtype, fields=[], qualifiers=[], traits={}):
        self.name = name
        self.irtype = irtype
        self.fields = fields
        self.tclass = 'struct'
        self.qualifiers = qualifiers
        self.traits = traits
        self.ctor = None
        self.dtor = None
        self.operator = {}

    def add_field(self, name, ftype, irvalue):
        if irvalue is not None:
            self.fields.append(Value(name.value, ftype, irvalue.eval()))
        else:
            self.fields.append(Value(name.value, ftype, None))

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
        return op in self.operator

    def add_operator(self, op, fn):
        print('adding operator ', op)
        if not self.has_operator(op):
            self.operator[op] = fn
    
    def get_pointer_to(self):
        return StructType(self.name, 
            self.irtype.as_pointer(), 
            self.fields, 
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def get_deference_of(self):
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
            traits=self.traits
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
            traits=self.traits
        )

def mangle_name(name: str, atypes: list):
    mname = '_Z%s_' % name
    if len(atypes) == 0:
        mname += 'v'
        return mname
    for atype in atypes:
        if atype.is_const():
            mname += 'K'
        if atype.is_pointer():
            mname += 'P'
        if atype.is_atomic():
            mname += 'A'
        if atype.is_integer():
            if atype.get_integer_bits() == 32:
                mname += 'i'
            elif atype.get_integer_bits() == 64:
                mname += 'l'
            elif atype.get_integer_bits() == 16:
                mname += 's'
            elif atype.get_integer_bits() == 8:
                mname += 'c'
        elif atype.name == 'cstring':
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
            mname += 'S' + atype.name + '_'
    return mname

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

class Func():
    """
    A function value in Saturn.
    """
    def __init__(self, name, rtype, overloads={}, traits={}):
        self.name = name
        self.rtype = rtype
        self.overloads = overloads.copy()
        self.traits = traits

    def add_overload(self, atypes, fn):
        key = mangle_name('', atypes)
        self.overloads[key] = fn

    def get_overload(self, atypes):
        key = mangle_name('', atypes)
        if key in self.overloads:
            return self.overloads[key]
        return None