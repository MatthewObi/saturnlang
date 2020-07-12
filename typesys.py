from llvmlite import ir

class Type():
    def __init__(self, name, irtype, tclass, qualifiers=[], traits=[]):
        self.name = name
        self.tclass = tclass
        self.irtype = irtype
        self.qualifiers = qualifiers
        self.traits = traits

    def make_array(self, size):
        self.qualifiers.append(('array', 5))

    def get_array_of(self, size):
        return Type(self.name, 
            ir.ArrayType(self.irtype, size), 
            self.tclass, 
            qualifiers=self.qualifiers + [('array', size)],
            traits=self.traits
        )

    def make_pointer(self):
        self.qualifiers.append(('ptr',))

    def get_pointer_to(self):
        return Type(self.name, 
            self.irtype.as_pointer(), 
            self.tclass, 
            qualifiers=self.qualifiers + [('ptr',)],
            traits=self.traits
        )

    def make_const(self):
        self.qualifiers.append(('const',))

    def get_const_of(self):
        return Type(self.name, 
            self.irtype, 
            self.tclass, 
            qualifiers=self.qualifiers + [('const',)],
            traits=self.traits
        )

    def make_immut(self):
        self.qualifiers.append(('immut',))

    def get_immut_of(self):
        return Type(self.name, 
            self.irtype, 
            self.tclass, 
            qualifiers=self.qualifiers + [('immut',)],
            traits=self.traits
        )

    def add_trait(self, trait):
        if trait not in self.traits:
            self.traits.append(trait)

    def has_trait(self, trait):
        return trait in self.traits

    def is_array(self):
        return self.qualifiers[-1][0] == 'array'

    def is_pointer(self):
        return self.qualifiers[-1][0] == 'ptr'

    def is_const(self):
        return self.qualifiers[-1][0] == 'const'

    def is_value(self):
        return not (self.is_array() or self.is_pointer())

    def is_unsigned(self):
        return self.tclass == 'uint'

    def is_integer_class(self):
        return self.tclass == 'int' or self.tclass == 'uint'

    def __str__(self):
        s = str()
        for q in self.qualifiers:
            if q[0] == 'const':
                s += 'const '
            elif q[0] == 'immut':
                s += 'immut '
            elif q[0] == 'mut':
                s += 'mut '
            elif q[0] == 'ptr':
                s += '*'
            elif q[0] == 'array':
                s += '[%d]' % q[1]
        s += self.name
        return s

types = {
    "void": Type("void", ir.VoidType(), 'void', traits=['TNoType']),
    "int": Type("int", ir.IntType(32), 'int', traits=['TIntAny']),
    "int32": Type("int32", ir.IntType(32), 'int'),
    "int64": Type("int64", ir.IntType(64), 'int'),
    "int16": Type("int16", ir.IntType(16), 'int'),
    "byte": Type("byte", ir.IntType(8), 'uint'),
    "uint": Type("uint", ir.IntType(32), 'uint', traits=['TIntAny']),
    "uint64": Type("uint64", ir.IntType(64), 'uint'),
    "uint32": Type("uint32", ir.IntType(32), 'uint'),
    "uint16": Type("uint16", ir.IntType(16), 'uint'),
    "float32": Type("float32", ir.FloatType(), 'float'),
    "float64": Type("float64", ir.DoubleType(), 'float'),
    "bool": Type("bool", ir.IntType(1), 'bool'),
    "cstring": Type("cstring", ir.IntType(8).as_pointer(), 'string', traits=['TOpaquePtr']),
}

class FuncType():
    def __init__(self, name, rtype, atypes=[]):
        self.name = name
        self.rtype = rtype
        self.atypes = atypes