from llvmlite import ir
from rply import Token
from typesys import TupleType, Type, make_tuple_type, types, FuncType, StructType, Value, mangle_name, print_types, \
    Func, GlobalValue, ConstexprValue, make_optional_type, mangle_symbol, mangle_symbol_name, demangle_name, \
    array_to_slice, EnumType, GenericType, HVectorType, mangle_type, SliceType
from serror import throw_saturn_error
from package import Visibility, LinkageType, Package

SCOPE = []
DECL_SCOPE = []
GLOBALS = {}


def clean_string_literal(str_lit: str) -> str:
    return str_lit.strip('\"').replace('\\n', '\n').replace('\\t', '\t')


def slice_new(base_type: Type, builder: ir.IRBuilder) -> ir.AllocaInstr:
    ptr = builder.alloca(base_type.get_slice_of().get_ir_type())
    return ptr


def slice_element_of(builder: ir.IRBuilder, module: ir.Module, value: Value, idx_value):
    i32 = ir.IntType(32)
    ir_value = value.get_ir_value(module)
    slice_type: SliceType = value.type
    bc = builder.bitcast(ir_value, slice_type.get_element_of().get_pointer_to().get_pointer_to().get_ir_type())
    ld = builder.load(bc)
    gep = builder.gep(ld, [idx_value], inbounds=True)
    return gep


class Scope:
    def __init__(self, builder, variables=None, is_guarded=False, passthrough=None):
        if passthrough is None:
            passthrough = []
        if variables is None:
            variables = {}
        self.builder = builder
        self.vars = variables.copy()
        self.is_guarded = is_guarded
        self.passthrough = passthrough
        self.continue_dest = None
        self.break_dest = None
        self.return_dest = None
        self.defer = []
        self.destructed = False

    def push_defer(self, defer):
        self.defer.append(defer)

    def eval_deferred(self):
        for stmt in self.defer:
            stmt.eval()
        self.defer = []

    def call_destructors(self):
        if not self.destructed:
            for var in self.vars.values():
                if var.type.is_value() and var.type.has_dtor():
                    fn = var.type.get_dtor()
                    ovrld = fn.get_overload([var.type.get_pointer_to()])
                    if ovrld:
                        self.builder.call(ovrld, [var.irvalue])
            self.destructed = True

    def keys(self):
        return self.vars.keys()

    def __getitem__(self, key):
        return self.vars[key]

    def __setitem__(self, key, value):
        self.vars[key] = value


def get_inner_scope():
    global SCOPE
    return SCOPE[-1]


def check_name_in_scope(name, start=-1):
    global SCOPE
    global GLOBALS
    if start == -1:
        start = 0
    for i in range(start, len(SCOPE)):
        s = SCOPE[-1-i]
        if name in s.keys():
            return s[name]
        if s.is_guarded:
            break
    if name in GLOBALS.keys():
        return GLOBALS[name]
    return None


def add_new_local(name, ptr):
    global SCOPE
    SCOPE[-1][name] = ptr


def push_new_scope(builder):
    global SCOPE
    scope = Scope(builder)
    SCOPE.append(scope)
    return scope


def push_existing_scope(scope):
    global SCOPE
    SCOPE.append(scope)
    return scope


def push_defer(defer):
    global SCOPE
    SCOPE[-1].push_defer(defer)


def eval_defer_scope():
    SCOPE[-1].eval_deferred()


def eval_dtor_scope():
    SCOPE[-1].call_destructors()


def pop_inner_scope():
    global SCOPE
    SCOPE[-1].call_destructors()
    SCOPE[-1].eval_deferred()
    SCOPE.pop(-1)


def get_inner_decl_scope():
    global DECL_SCOPE
    return DECL_SCOPE[-1]


def check_name_in_decl_scope(name):
    global DECL_SCOPE
    for i in range(len(DECL_SCOPE)):
        s = DECL_SCOPE[-1-i]
        if name in s.keys():
            return s[name]
    return None


def add_new_decl_local(name, ty):
    global DECL_SCOPE
    DECL_SCOPE[-1][name] = ty


def push_new_decl_scope():
    global DECL_SCOPE
    DECL_SCOPE.append({})


def pop_inner_decl_scope():
    global DECL_SCOPE
    SCOPE.pop(-1)


def set_continue_dest(dest):
    global SCOPE
    SCOPE[-1].continue_dest = dest


def set_break_dest(dest):
    global SCOPE
    SCOPE[-1].break_dest = dest


def get_continue_dest():
    global SCOPE
    for i in range(len(SCOPE)):
        dest = SCOPE[-1-i].continue_dest
        if dest is not None:
            return dest
    return None


def get_break_dest():
    global SCOPE
    for i in range(len(SCOPE)):
        dest = SCOPE[-1-i].break_dest
        if dest is not None:
            return dest
    return None


def implicit_define_function(module, fn):
    try:
        module.get_global(fn.name)
    except KeyError:
        fn = ir.Function(module,
                         fn.ftype,
                         fn.name)
    return fn


class ASTNode:
    """
    A single node in the abstract syntax tree.
    """
    def __init__(self, builder, module, package, spos):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos

    def getsourcepos(self):
        return self.spos


class Expr(ASTNode):
    """
    An expression which can be used as the value in other expressions/statements.
    """
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.is_constexpr = False

    def getsourcepos(self):
        return self.spos

    def get_type(self):
        return types['void']

    def get_ir_type(self):
        return self.get_type().get_ir_type()


class Number(Expr):
    """
    A number constant. Base class for integer and float constants.
    """
    def __init__(self, builder, module, package, spos, value, base=10):
        super().__init__(builder, module, package, spos)
        self.value = value
        self.base = base
        self.type = self.get_type()
        self.is_constexpr = True


class Integer(Number):
    """
    A 32-bit integer constant. (int)
    """
    def get_type(self):
        return types['int']

    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value, self.base))
        return i

    def consteval(self):
        return int(self.value, self.base)


class UInteger(Number):
    """
    A 32-bit unsigned integer constant. (uint)
    """
    def get_type(self):
        return types['uint']

    def eval(self):
        val = self.value.strip('u')
        i = ir.Constant(self.type.irtype, int(val, self.base))
        return i

    def consteval(self):
        return int(self.value.strip('u'), self.base)


class Integer64(Number):
    """
    A 64-bit integer constant. (int64)
    """
    def get_type(self):
        return types['int64']

    def eval(self):
        val = self.value.strip('l')
        i = ir.Constant(self.type.irtype, int(val, self.base))
        return i

    def consteval(self):
        return int(self.value.strip('l'), self.base)


class UInteger64(Number):
    """
    A 64-bit unsigned integer constant. (uint64)
    """
    def get_type(self):
        return types['uint64']

    def eval(self):
        val = self.value.strip('ul')
        i = ir.Constant(self.type.irtype, int(val, self.base))
        return i
    
    def consteval(self):
        return int(self.value.strip('ul'), self.base)


class Integer16(Number):
    """
    A 16-bit integer constant. (int16)
    """

    def get_type(self):
        return types['int16']

    def eval(self):
        val = self.value.strip('s')
        i = ir.Constant(self.type.irtype, int(val, self.base))
        return i

    def consteval(self):
        return int(self.value.strip('s'), self.base)


class UInteger16(Number):
    """
    A 16-bit unsigned integer constant. (uint16)
    """

    def get_type(self):
        return types['uint16']

    def eval(self):
        val = self.value.strip('us')
        i = ir.Constant(self.type.irtype, int(val, self.base))
        return i

    def consteval(self):
        return int(self.value.strip('us'), self.base)


class SByte(Number):
    """
    An 8-bit signed integer constant. (int8)
    """

    def get_type(self):
        return types['int8']

    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value.strip('sb'), self.base))
        return i

    def consteval(self):
        return int(self.value.strip('sb'), self.base)


class Byte(Number):
    """
    An 8-bit unsigned integer constant. (byte)
    """
    def get_type(self):
        return types['byte']
    
    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value.strip('b'), self.base))
        return i

    def consteval(self):
        return int(self.value.strip('b'), self.base)


class Float(Number):
    """
    A single-precision float constant. (float32)
    """
    def get_type(self):
        return types['float32']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value.strip('f')))
        return i

    def consteval(self):
        return float(self.value.strip('f'))


class Double(Number):
    """
    A double-precision float constant. (float64)
    """
    def get_type(self):
        return types['float64']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value))
        return i

    def consteval(self):
        return float(self.value)


class Quad(Number):
    """
    A quad-precision float constant. (float128)
    """
    def get_type(self):
        return types['float128']

    def eval(self):
        i = ir.Constant(self.type.irtype, self.value.strip('q'))
        return i

    def consteval(self):
        return float(self.value.strip('q'))


class HalfFloat(Number):
    """
    A half-precision float constant. (float16)
    """
    def get_type(self):
        return types['float16']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value))
        return i

    def consteval(self):
        return float(self.value.strip('h'))


class StringLiteral(Expr):
    """
    A null terminated string literal. (cstring)
    """
    def __init__(self, builder, module, package, spos, value):
        super().__init__(builder, module, package, spos)
        self.value = value  # bytearray(value, 'cp1252').decode('utf8')
        self.raw_value = clean_string_literal(self.value) + '\0'
        self.type = self.get_type()

    def get_type(self):
        return types['cstring']

    def get_reference(self):
        return self.value

    def eval(self):
        fmt = self.raw_value
        c_encoded = bytearray(fmt, 'utf8')
        c_fmt = ir.Constant(ir.ArrayType(ir.IntType(8), len(c_encoded)),
                            c_encoded)
        global_fmt = ir.GlobalVariable(self.module, c_fmt.type, name=self.module.get_unique_name("str"))
        global_fmt.linkage = 'private'
        global_fmt.global_constant = True
        global_fmt.unnamed_addr = True
        global_fmt.initializer = c_fmt
        self.value = self.builder.bitcast(global_fmt, self.type.get_ir_type())
        return self.value


class MultilineStringLiteral(Expr):
    """
    A multiline null terminated string literal. (cstring)
    """
    def __init__(self, builder, module, package, spos, value):
        super().__init__(builder, module, package, spos)
        self.value = value
        self.type = self.get_type()

    def get_type(self):
        return types['cstring']

    def get_reference(self):
        return self.value

    def eval(self):
        fmt = str(self.value).lstrip("R(\"").rstrip('\")R') + '\0'
        fmt = fmt.replace('\\n', '\n')
        c_fmt = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)),
                            bytearray(fmt.encode("utf8")))
        global_fmt = ir.GlobalVariable(self.module, c_fmt.type, name=self.module.get_unique_name("str"))
        global_fmt.linkage = 'internal'
        global_fmt.global_constant = True
        global_fmt.initializer = c_fmt
        self.value = self.builder.bitcast(global_fmt, self.type.irtype)
        return self.value


class Boolean(Expr):
    """
    A boolean constant. (bool)
    """
    def __init__(self, builder, module, package, spos, value: bool):
        super().__init__(builder, module, package, spos)
        self.value = value
        self.is_constexpr = True

    def get_type(self):
        return types['bool']

    def eval(self):
        i = ir.Constant(self.get_type().irtype, self.value)
        return i

    def consteval(self):
        return self.value


class Null(Expr):
    """
    A null constant. (null_t)
    """
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)

    def get_type(self):
        return types['null_t']

    def eval(self):
        int8ptr = ir.IntType(8).as_pointer()
        i = ir.Constant(int8ptr, int8ptr.null)
        return i


class ArrayLiteralElement(Expr):
    def __init__(self, builder, module, package, spos, expr, index=-1):
        super().__init__(builder, module, package, spos)
        self.expr = expr
        self.index = index
        self.is_constexpr = self.expr.is_constexpr

    def consteval(self):
        return self.expr.consteval()


class ArrayLiteralBody:
    def __init__(self, builder, module, package, spos):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.values = []
        self.is_constexpr = True

    def add_element(self, expr):
        if expr.index != -1:
            if expr.index >= len(self.values):
                for _ in range(len(self.values), expr.index):
                    self.values.append(None)
                self.values.append(expr)
            else:
                self.values[expr.index] = expr
        else:
            expr.index = len(self.values)
            self.values.append(expr)
        self.is_constexpr = self.is_constexpr and expr.is_constexpr


class ArrayLiteral(Expr):
    """
    An array literal constant.
    """
    def __init__(self, builder, module, package, spos, atype, body):
        super().__init__(builder, module, package, spos)
        self.atype = atype
        self.body = body
        self.type = self.get_type()

    def get_type(self):
        return self.atype.get_type().get_array_of(len(self.body.values))

    def eval(self):
        vals = []
        if self.body.is_constexpr:
            for val in self.body.values:
                if val is None:
                    vals.append(ir.Constant(self.get_type().get_element_of().get_ir_type(), None))
                else:
                    cast_v = cast_to(self.builder, self.module, self.package, val, self.get_type().get_element_of())
                    vals.append(cast_v)
            c = ir.Constant(self.get_type().get_ir_type(), vals)
        else:
            name = self.module.get_unique_name("_unnamed_array_literal")
            with self.builder.goto_entry_block():
                self.builder.position_at_start(self.builder.block)
                ptr = self.builder.alloca(self.get_type().get_ir_type(), name=name)
            val = Value(name, self.type, ptr)
            add_new_local(name, val)
            for value in self.body.values:
                if value is None:
                    continue
                gep = self.builder.gep(ptr, [
                    ir.Constant(ir.IntType(32), 0),
                    ir.Constant(ir.IntType(32), value.index)
                ])
                res = value.expr
                if isinstance(res, Null):
                    self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
                else:
                    cast_c = cast_to(self.builder, self.module, self.package, res, self.get_type().get_element_of())
                    self.builder.store(cast_c, gep)
            c = self.builder.load(ptr)
        return c


class StructLiteralElement(Expr):
    def __init__(self, builder, module, package, spos, name, expr):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.expr = expr


class StructLiteralBody:
    def __init__(self, builder, module, package, spos):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.values = {}

    def add_field(self, name, expr):
        self.values[name.value] = expr


class StructLiteral(Expr):
    """
    A struct literal constant.
    """
    def __init__(self, builder, module, package, spos, stype, body):
        super().__init__(builder, module, package, spos)
        self.stype = stype
        self.body = body
        self.type = None

    def get_type(self):
        if self.type is None:
            self.type = self.stype.get_type()
        return self.type

    def eval(self):
        name = self.module.get_unique_name("_unnamed_struct_literal")
        with self.builder.goto_entry_block():
            self.builder.position_at_start(self.builder.block)
            ptr = self.builder.alloca(self.get_type().irtype, name=name)
        val = Value(name, self.type, ptr)
        add_new_local(name, val)
        #for m in membervals:
        #    gep = self.builder.gep()
        #c = ir.Constant(self.stype.get_ir_type(), membervals)
        for name, value in self.body.values.items():
            gep = self.builder.gep(ptr, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), self.type.get_field_index(name))
            ])
            res = value.eval()
            if isinstance(res, ir.Constant) and res.constant == 'null':
                self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
            else:
                self.builder.store(res, gep)
        return self.builder.load(ptr)


class ValueLiteralElement(Expr):
    def __init__(self, builder, module, package, spos, key, value):
        super().__init__(builder, module, package, spos)
        self.key = key
        self.value = value


class ValueLiteralBody:
    def __init__(self, builder, module, package, spos):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.values = []

    def add_value(self, value_element):
        self.values.append(value_element)


class ValueLiteral(Expr):
    """
    A generic literal constant.\n
    (stype) { body }
    """
    def __init__(self, builder, module, package, spos, stype, body):
        super().__init__(builder, module, package, spos)
        self.stype = stype
        self.body = body
        self.type = None

    def get_type(self):
        if self.type is None:
            self.type = self.stype.get_type()
        return self.type

    def eval(self):
        if self.get_type().is_struct():
            name = self.module.get_unique_name("_unnamed_struct_literal")
            with self.builder.goto_entry_block():
                self.builder.position_at_start(self.builder.block)
                ptr = self.builder.alloca(self.get_type().irtype, name=name)
            val = Value(name, self.type, ptr)
            add_new_local(name, val)
            for name, value in self.body.values.items():
                gep = self.builder.gep(ptr, [
                    ir.Constant(ir.IntType(32), 0),
                    ir.Constant(ir.IntType(32), self.type.get_field_index(name))
                ])
                res = value.eval()
                if isinstance(res, ir.Constant) and res.constant == 'null':
                    self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
                else:
                    self.builder.store(res, gep)
            return self.builder.load(ptr)


class TupleLiteralElement(Expr):
    def __init__(self, builder, module, package, spos, expr):
        super().__init__(builder, module, package, spos)
        self.expr = expr

    def get_type(self):
        return self.expr.get_type()


class TupleLiteralBody(ASTNode):
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.elements = []

    def add_element(self, expr):
        self.elements.append(expr)


class TupleLiteral(Expr):
    """
    A tuple literal.
    """
    def __init__(self, builder, module, package, spos, body):
        super().__init__(builder, module, package, spos)
        self.ttype = make_tuple_type(body.elements)
        self.body = body
        self.type = self.get_type()

    def get_type(self):
        return self.ttype

    def get_ir_type(self):
        return self.ttype.irtype

    def eval(self):
        i = 0
        name = self.module.get_unique_name("_unnamed_tuple")
        with self.builder.goto_entry_block():
            self.builder.position_at_start(self.builder.block)
            ptr = self.builder.alloca(self.ttype.irtype, name=name)
        val = Value(name, self.ttype, ptr)
        add_new_local(name, val)
        for el in self.body.elements:
            gep = self.builder.gep(ptr, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), i)
            ])
            res = el.eval()
            if isinstance(res, ir.Constant) and res.constant == 'null':
                self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
            else:
                self.builder.store(res, gep)
            i += 1
        return self.builder.load(ptr)

        
class LValue(Expr):
    """
    Expression representing a named value in memory.
    """
    def __init__(self, builder, module, package, spos, name, lhs=None):
        super().__init__(builder, module, package, spos)
        self.lhs = lhs
        self.name = name
        self.value = None
        self.is_constexpr = False
        self.is_deref = False

    def get_type(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Could not find lvalue '{name}' in current scope.")
            if isinstance(ptr, Func):
                ptr = self.package.lookup_symbol(name)
                key = list(ptr.overloads.keys())[0]
                begin = '_Z%d' % len(name)
                key = begin + name + key[3:]
                ovrld = ptr.get_default_overload()
                irtype: ir.FunctionType = ovrld.fn.type
                ret_type: Type = ovrld.rtype
                arg_types = ovrld.atypes
                fnty = FuncType('', irtype, ret_type, arg_types)
                return fnty
        # if ptr.type.is_pointer():
        #     return ptr.type.get_dereference_of()
        return ptr.type

    def get_ir_type(self):
        name = self.get_name()
        #print(name)
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Could not find lvalue '{name}' in current scope.")
            ptr = ptr.irvalue
            #ptr = self.module.get_global(name)
        else:
            ptr = ptr.irvalue
        if ptr.type.is_pointer:
            return ptr.type.pointee
        return ptr.type

    def get_name(self):
        l = self.lhs
        ll = [self]
        s = ""
        while l is not None:
            ll.append(l)
            l = l.lhs
        ll.reverse()
        i = 1
        for l in ll:
            s += l.name
            if i < len(ll):
                s += "::"
                i = i + 1
        return s

    def get_pointer(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Could not find lvalue '{name}' in current scope.")
            if isinstance(ptr, Func):
                # if name not in self.module.sglobals:
                #     if name not in self.module.sfuncs:
                #         lineno = self.getsourcepos().lineno
                #         colno = self.getsourcepos().colno
                #         throw_saturn_error(self.builder, self.module, lineno, colno,
                #             "Could not find lvalue '%s' in current scope." % name
                #         )
                # ptr = self.module.sfuncs[name]
                if not ptr.has_default_overload():
                    lineno = self.getsourcepos().lineno
                    colno = self.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"Could not get pointer to function '{name}'. "
                                       f"Function has multiple overloads. Expression is ambiguous.")
                ovrld = ptr.get_default_overload()
                fn, key = ovrld.fn, ovrld.key()
                begin = '_Z%d' % len(name)
                key = begin + name + key[3:]
                irtype: ir.FunctionType = ovrld.fn.type
                ret_type: Type = ovrld.rtype
                arg_types = ovrld.atypes
                fnty = FuncType('', irtype, ret_type, arg_types)
                return Value('', fnty.get_pointer_to(), fn)
            # else:
            #    ptr = self.module.sglobals[name]
        if isinstance(ptr, GlobalValue):
            irvalue = ptr.get_ir_value(self.module)
        else:
            irvalue = ptr.irvalue
        if ptr.type.is_reference():
            i64 = ir.IntType(64)
            deref = self.builder.load(irvalue)
            v0 = self.builder.ptrtoint(deref, i64)
            v1 = self.builder.and_(v0, i64(-2))
            actualptr = self.builder.inttoptr(v1, self.get_ir_type())
            # (f"Reference: {actualptr}\nType:{ptr.type.type}")
            return Value(ptr.name, ptr.type.type, actualptr, qualifiers=ptr.qualifiers)
        return ptr

    def get_reference(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Could not find lvalue '{name}' in current scope.")
            if isinstance(ptr, Func):
                # if name not in self.module.sglobals:
                #     if name not in self.module.sfuncs:
                #         lineno = self.getsourcepos().lineno
                #         colno = self.getsourcepos().colno
                #         throw_saturn_error(self.builder, self.module, lineno, colno,
                #             "Could not find lvalue '%s' in current scope." % name
                #         )
                # ptr = self.module.sfuncs[name]
                if not ptr.has_default_overload():
                    lineno = self.getsourcepos().lineno
                    colno = self.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"Could not get pointer to function '{name}'. "
                                       f"Function has multiple overloads. Expression is ambiguous.")
                ovrld = ptr.get_default_overload()
                fn, key = ovrld.fn, ovrld.key()
                begin = '_Z%d' % len(name)
                key = begin + name + key[3:]
                fnty = self.module.sfunctys[key]
                return Value('', fnty.get_pointer_to(), fn)
            # else:
            #    ptr = self.module.sglobals[name]
        if isinstance(ptr, GlobalValue):
            irvalue = ptr.get_ir_value(self.module)
        else:
            irvalue = ptr.irvalue
        i64 = ir.IntType(64)
        deref = self.builder.load(irvalue)
        v0 = self.builder.ptrtoint(deref, i64)
        v1 = self.builder.and_(v0, i64(-2))
        actualptr = self.builder.inttoptr(v1, self.get_ir_type())
        return Value(ptr.name, ptr.type, actualptr, qualifiers=ptr.qualifiers)
    
    def eval(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Could not find lvalue '{name}' in current scope.")
            if isinstance(ptr, Func):
                ptr = ptr.get_default_overload()
            # if name not in self.module.sglobals:
            #     if name not in self.module.sfuncs:
            #         lineno = self.getsourcepos().lineno
            #         colno = self.getsourcepos().colno
            #         throw_saturn_error(self.builder, self.module, lineno, colno,
            #             "Could not find lvalue '%s' in current scope." % name
            #         )
            #     ptr = self.module.sfuncs[name].get_default_overload()
            # else:
            #     ptr = self.module.sglobals[name]
        if isinstance(ptr, ConstexprValue):
            return ir.Constant(ptr.get_ir_type(), ptr.value)
        if isinstance(ptr, GlobalValue):
            irvalue = ptr.get_ir_value(self.module)
        else:
            irvalue = ptr.irvalue
        if irvalue is None:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"IRValue for {self.get_name()} in module {self.module.name} is None.")
        if ptr.is_atomic():
            return self.builder.load_atomic(irvalue, 'seq_cst', 4)
        if self.get_type().is_reference():
            # print(self.get_type(), self.get_ir_type())
            i64 = ir.IntType(64)
            deref = self.builder.load(irvalue)
            v0 = self.builder.ptrtoint(deref, i64)
            v1 = self.builder.and_(v0, i64(-2))
            irtype = self.get_ir_type()
            actualptr = self.builder.inttoptr(v1, irtype)
            return self.builder.load(actualptr)
        return self.builder.load(irvalue)


class LValueField(Expr):
    def __init__(self, builder, module, package, spos, lvalue, fname):
        super().__init__(builder, module, package, spos)
        self.fname = fname
        self.lvalue = lvalue
        self.is_constexpr = False
        self.is_deref = False

    def get_type(self):
        stype = self.lvalue.get_type()
        if stype.is_slice():
            if self.fname == 'len':
                return types['uint64']
        stype = stype.get_base_type()
        if not stype.is_struct():
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Attempting to get field '{self.fname}' on lvalue '{self.lvalue.get_name()}', "
                               f"which is type '{str(stype)}', not a struct type.")
        return stype.get_field_type(stype.get_field_index(self.fname))

    def get_ir_type(self):
        irtype = self.lvalue.get_ir_type()
        stype = self.lvalue.get_type()
        if stype.is_slice():
            if self.fname == 'len':
                return types['uint64'].get_ir_type()
        findex = stype.get_field_index(self.fname)
        return irtype.gep(ir.Constant(ir.IntType(32), findex))

    def get_name(self):
        return self.lvalue.get_name()

    def get_pointer(self):
        stype = self.lvalue.get_type()
        ptr = self.lvalue.get_pointer()
        if stype.is_slice():
            if self.fname == 'len':
                i64 = ir.IntType(64)
                i32 = ir.IntType(32)
                gep = self.builder.gep(ptr.irvalue, [i64(0), i32(1)])
                return Value('', types['uint64'], gep)
        if stype.is_pointer():
            stype = stype.get_dereference_of()
        findex = stype.get_field_index(self.fname)
        if findex == -1:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot find field {self.fname} in struct {stype.name}.")
        # print('%s: %d' % (self.fname, findex))
        gep = None
        ptrty = ptr.type
        if ptrty.is_pointer():
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
        elif ptrty.is_reference():
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
        else:
            gep = self.builder.gep(ptr.irvalue, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
        quals = stype.fields[findex].qualifiers
        quals = ['mut'] if len(quals) == 0 else quals
        return Value(self.fname, stype.get_field_type(findex), gep, quals)

    def eval(self):
        stype = self.lvalue.get_type()
        ptr = self.lvalue.get_pointer()
        if stype.is_slice():
            if self.fname == 'len':
                i64 = ir.IntType(64)
                i32 = ir.IntType(32)
                gep = self.builder.gep(ptr.irvalue, [i64(0), i32(1)])
                return self.builder.load(gep)
        stype = stype.get_base_type()
        findex = stype.get_field_index(self.fname)
        if findex == -1:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot find field {self.fname} in struct {stype.name}."
                               )
        if not (ptr.type.is_pointer() or ptr.type.is_reference()):
            # print(ptr.type.fields, ptr.type.get_ir_type().is_opaque, ptr.irvalue)
            gep = self.builder.gep(ptr.irvalue, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
            return self.builder.load(gep)
        elif ptr.type.is_pointer():
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
            return self.builder.load(gep)
        else:
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
            return self.builder.load(gep)


class LValueGeneric(LValue):
    """
    Named value in memory with type arguments.\n
    lvalue <[type_list]>
    """
    def __init__(self, builder, module, package, spos, type_list, lhs):
        name = f"T{len(type_list)}"
        super().__init__(builder, module, package, spos, name, lhs)
        self.type_list = type_list


def cast_to(builder: ir.IRBuilder, module, package, expr, ctype):
    castt = ctype
    exprt = expr.get_type()
    if expr.is_constexpr:
        cast = ir.Constant(castt.irtype, expr.consteval())
    else:
        val = expr.eval()
        # print(val, expr)
        if castt.is_reference() and exprt.is_value():
            if not hasattr(expr, 'get_pointer'):
                _name = module.get_unique_name("_unnamed_reference_target")
                with builder.goto_entry_block():
                    ptr = builder.alloca(exprt.get_ir_type())
                    add_new_local(_name, ptr)
                builder.store(expr.eval(), ptr)
                val = ptr
            else:
                val = expr.get_pointer().irvalue
            cast = val
        if exprt.is_reference():
            exprt = exprt.type
        if exprt.is_pointer():
            if castt.is_pointer():
                cast = builder.bitcast(val, castt.get_ir_type())
            elif castt.is_integer():
                cast = builder.ptrtoint(val, castt.get_ir_type())
            elif castt.is_bool():
                # lhs = self.builder.ptrtoint(val, ir.IntType(64))
                # rhs = self.builder.ptrtoint(ir.Constant(exprt.irtype, exprt.irtype.null), ir.IntType(64))
                cast = builder.icmp_unsigned('!=', val, ir.Constant(exprt.get_ir_type(), exprt.get_ir_type().null))
        elif exprt.is_array():
            if castt.is_pointer():
                cast = builder.bitcast(val, castt.get_ir_type())
            elif castt.is_slice():
                i64 = ir.IntType(64)
                i32 = ir.IntType(32)
                _name = module.get_unique_name("_unnamed_slice_alloc")
                with builder.goto_entry_block():
                    ptr = builder.alloca(castt.get_ir_type())
                    value = Value(_name, castt, ptr)
                    add_new_local(_name, value)
                slice_data = builder.gep(ptr, [i64(0), i32(0)], inbounds=True)
                print(slice_data.type)
                array_ptr = builder.bitcast(expr.get_pointer().irvalue, exprt.get_element_of().get_pointer_to().get_ir_type())
                slice_data_ptr = builder.bitcast(slice_data,
                                                 exprt.get_element_of().get_pointer_to().get_pointer_to().get_ir_type())
                builder.store(array_ptr, slice_data_ptr)
                slice_len = builder.gep(ptr, [i64(0), i32(1)], inbounds=True)
                builder.store(i64(exprt.get_array_count()), slice_len)
                cast = builder.load(ptr)
        elif exprt.is_integer():
            if castt.is_pointer():
                cast = builder.inttoptr(val, castt.get_ir_type())
            elif castt.is_integer():
                if castt.get_integer_bits() < exprt.get_integer_bits():
                    cast = builder.trunc(val, castt.get_ir_type())
                elif castt.get_integer_bits() > exprt.get_integer_bits():
                    if castt.is_unsigned():
                        cast = builder.zext(val, castt.get_ir_type())
                    else:
                        cast = builder.sext(val, castt.get_ir_type())
                else:
                    cast = val
            elif castt.is_float():
                if exprt.is_unsigned():
                    cast = builder.uitofp(val, castt.get_ir_type())
                else:
                    cast = builder.sitofp(val, castt.get_ir_type())
            elif castt.is_bool():
                if exprt.is_unsigned():
                    cast = builder.icmp_unsigned('!=', val, ir.Constant(exprt.get_ir_type(), 0))
                elif exprt.is_integer():
                    cast = builder.icmp_signed('!=', val, ir.Constant(exprt.get_ir_type(), 0))
                elif exprt.is_float():
                    cast = builder.fcmp_ordered('!=', val, ir.Constant(exprt.get_ir_type(), 0.0))
                elif exprt.is_pointer():
                    null = exprt.get_ir_type().null
                    cast = builder.icmp_signed('!=', val, null)
            else:
                lineno = expr.getsourcepos().lineno
                colno = expr.getsourcepos().colno
                throw_saturn_error(builder, module, lineno, colno,
                                   f"Cannot cast from integer type to '{str(exprt)}'."
                                   )
        else:
            lineno = expr.getsourcepos().lineno
            colno = expr.getsourcepos().colno
            throw_saturn_error(builder, module, lineno, colno,
                               f"Cannot cast expression of type '{str(exprt)}' to '{str(castt)}'."
                               )
    return cast


class CastExpr(Expr):
    """
    A cast operation.\n
    cast<ctype>(expr)
    """
    def __init__(self, builder, module, package, spos, ctype, expr):
        super().__init__(builder, module, package, spos)
        self.ctype = ctype
        self.expr = expr
        self.is_constexpr = expr.is_constexpr

    def get_pointer(self):
        return self.expr.get_pointer()

    def get_type(self):
        return self.ctype.get_type()

    def eval(self):
        return cast_to(self.builder, self.module, self.package, self.expr, self.ctype.get_type())


class MakeExpr(Expr):
    """
    A make expression for creating new variables on the heap.\n
    make typeexpr;\n
    make typeexpr(args);\n
    make typeexpr{init};\n
    make owned typeexpr;\n
    make owned typeexpr(args);\n
    make owned typeexpr{init};
    """
    def __init__(self, builder, module, package, spos, typeexpr, args=None, init=None):
        super().__init__(builder, module, package, spos)
        self.typeexpr = typeexpr
        self.mtype = None
        self.type = None
        self.args = args
        self.init = init
        self.melement_count = 1
        self.stack_value = None

    def get_type(self):
        if self.type is None:
            self.mtype = self.typeexpr.get_type()
            if self.mtype.is_array():
                self.melement_count = self.mtype.get_array_count()
                self.mtype = self.mtype.get_element_of().get_pointer_to()
            self.type = self.mtype.get_reference_to()
            # print(self.mtype, self.type)
        return self.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        int32 = ir.IntType(32)
        self.get_type()
        malloc_fn = self.module.aligned_malloc
        if self.melement_count == 1:
            sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
        else:
            sizeof = self.builder.mul(ir.Constant(ir.IntType(32), self.melement_count),
                                      calc_sizeof_struct(self.builder, self.module, self.mtype))
        # asize = (size + 3) & ~3
        aligned_sizeof = self.builder.and_(
            self.builder.add(sizeof, int32(3)),
            int32(~3))
        malloc_args = [aligned_sizeof, ir.Constant(ir.IntType(32), 2)] if malloc_fn.name.startswith('_') \
            else [ir.Constant(ir.IntType(32), 2), aligned_sizeof]
        mallocptr = self.builder.call(malloc_fn, malloc_args)
        self.builder.call(self.module.memset, [
            mallocptr,
            ir.Constant(ir.IntType(8), 0),
            aligned_sizeof,
            ir.Constant(ir.IntType(1), 0),
        ])
        bitcast = self.builder.bitcast(mallocptr, self.type.irtype)

        _name = self.module.get_unique_name('_unnamed_make_expr')
        ptr = Value(_name, self.type, bitcast, objtype='heap')
        add_new_local(_name, ptr)
        lvalue = LValue(self.builder, self.module, self.package, self.spos, _name)
        push_defer(DestroyExpr(self.builder, self.module, self.package, self.spos, lvalue, self.type))
        return bitcast


class MakeUnsafeExpr(Expr):
    """
    A make expression for creating new variables on the heap.\n
    make unsafe typeexpr;\n
    make unsafe typeexpr(args);\n
    make unsafe typeexpr{init};\n
    """
    def __init__(self, builder, module, package, spos, typeexpr, args=None, init=None):
        super().__init__(builder, module, package, spos)
        self.typeexpr = typeexpr
        self.mtype = None
        self.type = None
        self.args = args
        self.init = init
        self.melement_count = 1
        self.stack_value = None

    def get_type(self):
        if self.type is None:
            self.mtype = self.typeexpr.get_type()
            if self.mtype.is_array():
                self.melement_count = self.mtype.get_array_count()
                self.mtype = self.mtype.get_element_of()
            self.type = self.mtype.get_pointer_to()
            # print(self.mtype, self.type)
        return self.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        int32 = ir.IntType(32)
        self.get_type()
        malloc_fn = self.module.aligned_malloc
        if self.melement_count == 1:
            sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
        else:
            sizeof = self.builder.mul(int32(self.melement_count),
                                      calc_sizeof_struct(self.builder, self.module, self.mtype))
        # asize = (size + 3) & ~3
        aligned_sizeof = self.builder.and_(
            self.builder.add(sizeof, int32(3)),
            int32(~3))
        malloc_args = [aligned_sizeof, int32(4)] if malloc_fn.name.startswith('_') \
            else [int32(4), aligned_sizeof]
        mallocptr = self.builder.call(malloc_fn, malloc_args)
        self.builder.call(self.module.memset, [
            mallocptr,
            ir.Constant(ir.IntType(8), 0),
            aligned_sizeof,
            ir.Constant(ir.IntType(1), 0),
        ])
        bitcast = self.builder.bitcast(mallocptr, self.type.irtype)

        _name = self.module.get_unique_name('_unnamed_unsafe_make_expr')
        ptr = Value(_name, self.type, bitcast, objtype='heap')
        add_new_local(_name, ptr)
        lvalue = LValue(self.builder, self.module, self.package, self.spos, _name)
        return bitcast


class MakeUnsafeArrayExpr(Expr):
    """
    A make expression for creating new arrays on the heap.\n
    make unsafe [count_expr]typeexpr;\n
    make unsafe [count_expr]typeexpr{init};\n
    """
    def __init__(self, builder, module, package, spos, typeexpr, count_expr, init=None):
        super().__init__(builder, module, package, spos)
        self.typeexpr = typeexpr
        self.mtype = None
        self.type = None
        self.count_expr = count_expr
        self.init = init
        self.melement_count = 1
        self.stack_value = None

    def get_type(self):
        if self.type is None:
            self.mtype = self.typeexpr.get_type()
            self.type = self.mtype.get_pointer_to()
            # print(self.mtype, self.type)
        return self.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        int32 = ir.IntType(32)
        self.get_ir_type()
        malloc_fn = self.module.aligned_malloc
        if self.count_expr.is_constexpr:
            el_count = self.count_expr.consteval()
            if el_count == 1:
                sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
            else:
                sizeof = self.builder.mul(int32(el_count),
                                          calc_sizeof_struct(self.builder, self.module, self.mtype))
        else:
            sizeof = self.builder.mul(self.count_expr.eval(),
                                      calc_sizeof_struct(self.builder, self.module, self.mtype))
        # asize = (size + 3) & ~3
        aligned_sizeof = self.builder.and_(
            self.builder.add(sizeof, int32(3)),
            int32(~3))
        malloc_args = [aligned_sizeof, int32(4)] if malloc_fn.name.startswith('_') \
            else [int32(4), aligned_sizeof]
        mallocptr = self.builder.call(malloc_fn, malloc_args)
        self.builder.call(self.module.memset, [
            mallocptr,
            ir.Constant(ir.IntType(8), 0),
            aligned_sizeof,
            ir.Constant(ir.IntType(1), 0),
        ])
        bitcast = self.builder.bitcast(mallocptr, self.type.get_ir_type())

        _name = self.module.get_unique_name('_unnamed_unsafe_make_expr')
        ptr = Value(_name, self.type, bitcast, objtype='heap')
        add_new_local(_name, ptr)
        lvalue = LValue(self.builder, self.module, self.package, self.spos, _name)
        return bitcast


class DestroyExpr(Expr):
    """
    An expression for freeing memory from the heap.
    destroy lvalue;
    """
    def __init__(self, builder, module, package, spos, lvalue, stype=None):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.type = None

    def get_type(self):
        return self.type if self.type is not None else self.lvalue.get_type()

    def get_ir_type(self):
        return self.type.irtype

    def eval(self):
        if self.lvalue.get_type().is_reference():
            ptr = self.lvalue.get_pointer().irvalue
        else:
            ptr = self.lvalue.eval()
        bitcast = self.builder.bitcast(ptr, ir.IntType(8).as_pointer())
        self.builder.call(self.module.free, [bitcast])


class MakeSharedExpr(Expr):
    """
    A make expression for creating new variables on the heap with shared ownership.\n
    make shared typeexpr;\n
    make shared typeexpr(args);\n
    make shared typeexpr{init};
    """
    def __init__(self, builder, module, package, spos, typeexpr, args=None, init=None):
        super().__init__(builder, module, package, spos)
        self.typeexpr = typeexpr
        self.mtype = None
        self.type = None
        self.args = args
        self.init = init

    def get_type(self):
        if self.type is None:
            self.mtype = self.typeexpr.get_type()
            self.type = self.mtype.get_reference_to()
        return self.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        int32 = ir.IntType(32)
        self.get_type()
        malloc_fn = self.module.aligned_malloc
        sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
        # asize = (size + 3) & ~3
        aligned_sizeof = self.builder.and_(
            self.builder.add(sizeof, int32(3)),
            int32(~3))
        malloc_args = [aligned_sizeof, int32(4)] if malloc_fn.name.startswith('_') \
            else [int32(4), aligned_sizeof]
        mallocptr = self.builder.call(malloc_fn, malloc_args)
        self.builder.call(self.module.memset, [
            mallocptr,
            ir.Constant(ir.IntType(8), 0),
            aligned_sizeof,
            ir.Constant(ir.IntType(1), 0),
        ])
        bitcast = self.builder.inttoptr(
            self.builder.add(self.builder.ptrtoint(mallocptr, ir.IntType(64)), ir.Constant(ir.IntType(64), 1)),
            self.type.irtype
        )
        #bitcast = self.builder.bitcast(mallocptr, self.type.irtype)
        return bitcast


class PostfixOp(Expr):
    """
    A base class for unary postfix operations.\n
    left OP
    """
    def get_type(self):
        return self.left.get_type()

    def __init__(self, builder, module, package, spos, left, expr):
        super().__init__(builder, module, package, spos)
        self.left = left
        self.expr = expr
        self.is_constexpr = self.left.is_constexpr and self.expr.is_constexpr


class ElementOf(PostfixOp):
    """
    An element of postfix operation.\n
    left[expr]
    """
    def get_type(self):
        return self.left.get_type().get_element_of()

    def get_pointer(self):
        ptr = self.left.get_pointer()
        irvalue = ptr.get_ir_value(self.module) if isinstance(ptr, GlobalValue) else ptr.irvalue
        # print(ptr, self.expr.get_type())
        if self.expr.get_type().is_integer():
            leftty = self.left.get_type()
            if leftty.is_pointer():
                gep = self.builder.gep(self.left.eval(), [
                    self.expr.eval()
                ], True)
                return Value(ptr.name, ptr.type.get_dereference_of(), gep, ptr.qualifiers)
            elif leftty.is_slice():
                left_ir = self.left.get_pointer().irvalue
                expr_ir = self.expr.eval()
                print(left_ir, expr_ir)
                gep = self.builder.gep(left_ir, [
                    ir.Constant(ir.IntType(64), 0),
                    ir.Constant(ir.IntType(32), 0),
                ], True)
                ld = self.builder.load(gep)
                bc = self.builder.bitcast(ld, ld.type.pointee.element.as_pointer())
                gep2 = self.builder.gep(bc, [
                    expr_ir
                ], True)
                return Value(ptr.name, ptr.type.get_dereference_of(), gep2, ptr.qualifiers)
            else:
                gep = self.builder.gep(irvalue, [
                    ir.Constant(ir.IntType(32), 0),
                    self.expr.eval()
                ], True)
                return Value(ptr.name, ptr.type.get_element_of(), gep, ptr.qualifiers)
        lineno = self.expr.getsourcepos().lineno
        colno = self.expr.getsourcepos().colno
        throw_saturn_error(self.builder, self.module, lineno, colno,
                           f"Expression type for index is '{str(self.expr.get_type())}', but expected integer type."
                           )

    def eval(self):
        ptr = self.get_pointer()
        lep = self.builder.load(ptr.irvalue)
        return lep


class TupleElementOf(PostfixOp):
    """
    A tuple element of postfix operation.\n
    left.i
    """
    def get_type(self):
        return self.left.get_type().get_element_type(int(self.expr))

    def get_pointer(self):
        ptr = self.left.get_pointer()
        leftty = self.left.get_type()
        if leftty.is_pointer():
            gep = self.builder.gep(self.left.eval(), [
                ir.Constant(ir.IntType(32), int(self.expr))
            ], True)
            return Value(ptr.name, ptr.type.get_dereference_of(), gep, ptr.qualifiers)
        else:
            gep = self.builder.gep(ptr.irvalue, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), int(self.expr))
            ], True)
            return Value(ptr.name, ptr.type.get_element_of(), gep, ptr.qualifiers)
    
    def eval(self):
        ptr = self.get_pointer()
        lep = self.builder.load(ptr.irvalue)
        return lep


class PrefixOp(Expr):
    """
    A base class for unary prefix operations.\n
    OP right
    """
    def get_type(self):
        return self.right.get_type()

    def __init__(self, builder, module, package, spos, right):
        super().__init__(builder, module, package, spos)
        self.right = right
        self.is_constexpr = False
        self.is_deref = False


class AddressOf(PrefixOp):
    """
    An address of prefix operation.\n
    &right
    """
    def get_type(self):
        return self.right.get_type().get_pointer_to()

    def eval(self):
        cantakeaddr = isinstance(self.right, LValue) or isinstance(self.right, ElementOf)
        if not cantakeaddr:
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot take the address of a non-lvalue."
            )
        ptr = self.right.get_pointer()
        if isinstance(ptr, GlobalValue):
            irvalue = ptr.get_ir_value(self.module)
        else:
            irvalue = ptr.irvalue
        return irvalue


class DerefOf(PrefixOp):
    """
    An dereference of prefix operation.\n
    *right
    """
    def __init__(self, builder, module, package, spos, right):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.right = right
        self.is_constexpr = False
        self.is_deref = True

    def get_name(self):
        return self.right.get_name()

    def get_type(self):
        return self.right.get_type().get_dereference_of()
    
    def get_pointer(self):
        sptr = self.right.get_pointer()
        #print(sptr.name, sptr.qualifiers)
        ql = sptr.qualifiers.copy()
        qualifiers = []
        for q in ql:
            if q == 'immut' or q == 'readonly':
                qualifiers.append(q)
        #print(sptr.name, '=>', qualifiers)
        return Value(sptr.name, self.get_type(), self.builder.load(self.right.get_pointer().irvalue), qualifiers=qualifiers)

    def eval(self):
        if not isinstance(self.right, LValue):
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot dereference a non-lvalue."
            )
        ptr = self.get_pointer()
        #i = Value("", self.get_type(), self.builder.load(ptr.irvalue))
        i = self.builder.load(ptr.irvalue)
        return i


class BinaryNot(PrefixOp):
    """
    Binary not '~' operator.\n
    ~right
    """
    def get_type(self):
        return self.right.get_type()

    def eval(self):
        binnot = self.builder.not_(self.right.eval())
        return binnot

    def consteval(self):
        return ~self.right.consteval()


class Negate(PrefixOp):
    """
    Negate '-' operator.\n
    -right
    """
    def get_type(self):
        return self.right.get_type()

    def consteval(self):
        return -self.right.consteval()

    def eval(self):
        if self.right.is_constexpr:
            return ir.Constant(self.get_type().irtype, self.consteval())
        neg = self.builder.sub(ir.Constant(self.get_type().irtype, 0), self.right.eval())
        return neg


class BoolNot(PrefixOp):
    """
    Boolean not '!' operator.\n
    !right
    """
    def get_type(self):
        return types['bool']

    def eval(self):
        tv = None
        if not self.right.get_type().is_bool():
            tv = CastExpr(self.builder, self.module, self.package, self.spos,
                TypeExpr(self.builder, self.module, self.package, self.spos,
                LValue(self.builder, self.module, self.package, self.spos, 'bool')), self.right).eval()
        else:
            tv = self.right.eval()
        ntv = self.builder.xor(tv, ir.Constant(ir.IntType(1), 1))
        return ntv

    def consteval(self):
        return not self.right.consteval()


class SelectExpr(Expr):
    """
    A ternary selection operation.\n
    if cond then a else b
    """
    def __init__(self, builder, module, package, spos, cond, a, b):
        super().__init__(builder, module, package, spos)
        self.cond = cond
        self.a = a
        self.b = b

    def get_type(self):
        return self.a.get_type()

    def eval(self):
        return self.builder.select(self.cond.eval(), self.a.eval(), self.b.eval())


class BinaryOp(Expr):
    """
    A base class for binary operations.\n
    left OP right
    """
    def get_type(self):
        if self.left.get_type().is_similar(self.right.get_type()):
            return self.left.get_type()
        return types['void']

    def __init__(self, builder, module, package, spos, left, right):
        super().__init__(builder, module, package, spos)
        self.left = left
        self.right = right
        self.is_constexpr = left.is_constexpr and right.is_constexpr


class Sum(BinaryOp):
    """
    An add binary operation.\n
    left + right
    """
    def eval(self):
        ty = self.get_type()
        lty = self.left.get_type()
        rty = self.right.get_type()
        if ty.is_integer():
            i = self.builder.add(self.left.eval(), self.right.eval())
        elif ty.is_float():
            i = self.builder.fadd(self.left.eval(), self.right.eval())
        elif ty.is_hvector():
            ety = ty.get_element_of()
            if ety.is_integer():
                i = self.builder.add(self.left.eval(), self.right.eval())
            elif ety.is_float():
                i = self.builder.fadd(self.left.eval(), self.right.eval())
            else:
                lineno = self.spos.lineno
                colno = self.spos.colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Attempting to perform addition with two vectors of incompatible types "
                                   f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        else:
            lty = lty.get_base_type()
            if lty.is_struct() and lty.has_operator('+'):
                fn = lty.get_operator('+')
                if not fn:
                    lineno = self.spos.lineno
                    colno = self.spos.colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"Cannot perform addition with struct ({lty.name}). Has no operator+.")
                atypes = [lty.get_pointer_to(), rty.get_pointer_to()]
                ovrld = fn.search_overload(atypes)
                if not ovrld:
                    atypes = [lty.get_pointer_to(), rty.get_reference_to()]
                    ovrld = fn.search_overload(atypes)
                    if not ovrld:
                        lineno = self.spos.lineno
                        colno = self.spos.colno
                        throw_saturn_error(self.builder, self.module, lineno, colno,
                                           f"Could not find overload for struct ({str(lty)}) operator+ with argument types: "
                                           f"({str(lty)} and {str(rty)}).")
                o_fn = implicit_define_function(self.module, ovrld.overload.fn)
                i = self.builder.call(o_fn, [self.left.get_pointer().irvalue, self.right.get_pointer().irvalue])
            else:
                lineno = self.spos.lineno
                colno = self.spos.colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Attempting to perform addition with two operands of incompatible types "
                                   f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        return i

    def consteval(self):
        return self.left.consteval() + self.right.consteval()


class Sub(BinaryOp):
    """
    A subtraction binary operation.\n
    left - right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_integer():
            i = self.builder.sub(self.left.eval(), self.right.eval())
        elif ty.is_float():
            i = self.builder.fsub(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Attempting to perform subtraction with two operands of incompatible types (%s and %s)." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
        return i

    def consteval(self):
        return self.left.consteval() - self.right.consteval()


class Mul(BinaryOp):
    """
    A multiply binary operation.\n
    left * right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_float():
            i = self.builder.fmul(self.left.eval(), self.right.eval())
        elif ty.is_integer():
            i = self.builder.mul(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Attempting to perform multiplication with two operands of incompatible types "
                               f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        return i

    def consteval(self):
        return self.left.consteval() * self.right.consteval()


class Div(BinaryOp):
    """
    A division binary operation.\n
    left / right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_unsigned():
            i = self.builder.udiv(self.left.eval(), self.right.eval())
        elif ty.is_integer():
            i = self.builder.sdiv(self.left.eval(), self.right.eval())
        elif ty.is_float():
            i = self.builder.fdiv(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Attempting to perform division with two operands of incompatible types "
                               f"({str(self.left.get_type())} and {str(self.right.get_type())}). "
                               f"Please cast one of the operands.")
        return i

    def consteval(self):
        return self.left.consteval() / self.right.consteval()


class Mod(BinaryOp):
    """
    A modulus binary operation.\n
    left % right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_unsigned():
            i = self.builder.urem(self.left.eval(), self.right.eval())
        elif ty.is_integer():
            i = self.builder.srem(self.left.eval(), self.right.eval())
        elif ty.is_float():
            i = self.builder.frem(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno, "Attempting to perform division with two operands of incompatible types (%s and %s). Please cast one of the operands." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
        return i

    def consteval(self):
        return self.left.consteval() % self.right.consteval()


class ShiftLeft(BinaryOp):
    """
    A bit shift left operation.\n
    left << right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_integer():
            i = self.builder.shl(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                "Attempting to perform a bit shift with two operands of incompatible types (%s and %s). Please cast one of the operands." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
        return i

    def consteval(self):
        return self.left.consteval() << self.right.consteval()


class ShiftRight(BinaryOp):
    """
    A bit shift right operation.\n
    left >> right
    """
    def eval(self):
        i = None
        ty = self.get_type()
        if ty.is_unsigned():
            i = self.builder.lshr(self.left.eval(), self.right.eval())
        elif ty.is_integer():
            i = self.builder.ashr(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                "Attempting to perform a bit shift with two operands of incompatible types (%s and %s). Please cast one of the operands." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
        return i

    def consteval(self):
        return self.left.consteval() >> self.right.consteval()


class And(BinaryOp):
    """
    An and bitwise binary operation.\n
    left & right
    """
    def eval(self):
        ty = self.get_type()
        i = None
        if ty.is_integer():
            i = self.builder.and_(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                               f"Attempting to perform a binary and with at least one operand of a non-integer type "
                               f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        return i

    def consteval(self):
        return self.left.consteval() & self.right.consteval()


class Or(BinaryOp):
    """
    An or bitwise binary operation.\n
    left | right
    """
    def eval(self):
        ty = self.get_type()
        i = None
        if ty.is_integer():
            i = self.builder.or_(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Attempting to perform a binary and with at least one operand of a non-integer type "
                               f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        return i

    def consteval(self):
        return self.left.consteval() | self.right.consteval()


class Xor(BinaryOp):
    """
    An xor bitwise binary operation.\n
    left ^ right
    """
    def eval(self):
        i = self.builder.xor(self.left.eval(), self.right.eval())
        return i

    def consteval(self):
        return self.left.consteval() ^ self.right.consteval()


class BoolAnd(BinaryOp):
    """
    Boolean and '&&' operator.\n
    left && right
    """
    def eval(self):
        begin = self.builder.basic_block
        rhs = self.builder.append_basic_block(self.module.get_unique_name("land.rhs"))
        end = self.builder.append_basic_block(self.module.get_unique_name("land.end"))
        bool1 = self.left.eval()
        self.builder.cbranch(bool1, rhs, end)
        self.builder.goto_block(rhs)
        self.builder.position_at_start(rhs)
        bool2 = self.right.eval()
        self.builder.branch(end)
        self.builder.goto_block(end)
        self.builder.position_at_start(end)
        phi = self.builder.phi(types["bool"].irtype, 'land')
        phi.add_incoming(bool1, begin)
        phi.add_incoming(bool2, rhs)
        return phi

    def consteval(self):
        return self.left.consteval() and self.right.consteval()


class BoolOr(BinaryOp):
    """
    Boolean and '||' operator.\n
    left || right
    """
    def eval(self):
        begin = self.builder.basic_block
        rhs = self.builder.append_basic_block(self.module.get_unique_name("lor.rhs"))
        end = self.builder.append_basic_block(self.module.get_unique_name("lor.end"))
        bool1 = self.left.eval()
        self.builder.cbranch(bool1, end, rhs)
        self.builder.goto_block(rhs)
        self.builder.position_at_start(rhs)
        bool2 = self.right.eval()
        self.builder.branch(end)
        self.builder.goto_block(end)
        self.builder.position_at_start(end)
        phi = self.builder.phi(types["bool"].irtype, 'lor')
        phi.add_incoming(bool1, begin)
        phi.add_incoming(bool2, rhs)
        return phi

    def consteval(self):
        return self.left.consteval() or self.right.consteval()


class BoolCmpOp(BinaryOp):
    """
    Base class for boolean comparison binary operations.
    """
    def getcmptype(self):
        #print(type(self.left), type(self.right))
        #print(self.left.get_type(), self.right.get_type())
        ltype = self.left.get_type()
        rtype = self.right.get_type()
        if ltype.is_pointer() and isinstance(self.right, Null):
            self.lhs = self.left.eval()
            rirtype = ltype.irtype
            self.rhs = ir.Constant(rirtype, rirtype.null)
            return ltype
        if ltype.is_struct() and isinstance(self.right, Null):
            self.lhs = self.left.eval()
            rirtype = ltype.irtype
            self.rhs = rirtype(rirtype.null)
            return ltype
        if ltype.is_similar(rtype):
            self.lhs = self.left.eval()
            self.rhs = self.right.eval()
            return ltype
        if self.right.get_ir_type() == self.left.get_ir_type():
            self.lhs = self.left.eval()
            self.rhs = self.right.eval()
            return ltype
        if isinstance(self.left.get_ir_type(), ir.DoubleType):
            if isinstance(self.right.get_ir_type(), ir.FloatType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.fpext(self.right.eval(), ir.DoubleType())
                return ltype
            if isinstance(self.right.get_ir_type(), ir.IntType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.sitofp(self.right.eval(), ir.DoubleType())
                return ltype
        elif isinstance(self.left.get_ir_type(), ir.IntType):
            if isinstance(self.right.get_ir_type(), ir.FloatType) or isinstance(self.right.get_ir_type(), ir.DoubleType):
                self.lhs = self.builder.sitofp(self.right.eval(), self.left.get_ir_type())
                self.rhs = self.right.eval()
                return rtype
            elif isinstance(self.right.get_ir_type(), ir.IntType):
                if str(self.right.get_ir_type()) == 'i1' or str(self.left.get_ir_type()) == 'i1':
                    raise RuntimeError("Cannot do comparison between booleans and integers. (%s,%s) (At %s)" % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))
                if self.left.get_ir_type().width > self.right.get_ir_type().width:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At line %d, col %d)' % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos.lineno, self.spos.colno))
                    self.lhs = self.left.eval()
                    self.rhs = self.builder.sext(self.right.eval(), self.left.get_ir_type())
                    return ltype
                else:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At %s)' % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))
                    self.rhs = self.right.eval()
                    self.lhs = self.builder.sext(self.left.eval(), self.right.get_ir_type())
                    return rtype
        raise RuntimeError("Ouch. Types for comparison cannot be matched. (%s,%s) (At %s)" % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))

    def get_ir_type(self):
        return types['bool'].irtype


class Spaceship(BoolCmpOp):
    """
    Comparison spaceship '<=>' operator.\n
    left <=> right
    """
    def eval(self):
        ltype = self.left.get_type()
        if ltype.is_struct():
            if ltype.has_operator('<=>'):
                method = ltype.operator['<=>']
                ptr = self.left.get_pointer().irvalue
                value = self.right.eval()
                ovrld = method.get_overload([ltype.get_pointer_to(), self.right.get_type()])
                if not ovrld:
                    pass
                return self.builder.call(ovrld, [ptr, value])
            else:
                lineno = self.spos.lineno
                colno = self.spos.colno
                throw_saturn_error(self.builder, self.module, lineno, colno, 
                    "Comparing structs using operator '<=>', but no matching operator method found. (%s and %s)." % (
                    str(self.left.get_type()),
                    str(self.right.get_type())
                ))
        cmpty = self.getcmptype()
        begin = self.builder.basic_block
        lt = self.builder.append_basic_block(self.module.get_unique_name("ship.less"))
        gt = self.builder.append_basic_block(self.module.get_unique_name("ship.greater"))
        after = self.builder.append_basic_block(self.module.get_unique_name("ship.after"))
        ltv = ir.Constant(ir.IntType(32), -1)
        eqv = ir.Constant(ir.IntType(32), 0)
        gtv = ir.Constant(ir.IntType(32), 1)
        if cmpty.is_pointer():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
            return i
        if cmpty.is_unsigned():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('==', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('==', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        self.builder.cbranch(i, after, lt)
        self.builder.goto_block(lt)
        self.builder.position_at_start(lt)
        if cmpty.is_unsigned():
            j = self.builder.icmp_unsigned('<', self.lhs, self.rhs)
        elif cmpty.is_integer():
            j = self.builder.icmp_signed('<', self.lhs, self.rhs)
        elif cmpty.is_float():
            j = self.builder.fcmp_unordered('<', self.lhs, self.rhs)
        else:
            j = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        self.builder.cbranch(j, after, gt)
        self.builder.goto_block(gt)
        self.builder.position_at_start(gt)
        self.builder.branch(after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)
        phi = self.builder.phi(types["int"].irtype, 'land')
        phi.add_incoming(eqv, begin)
        phi.add_incoming(ltv, lt)
        phi.add_incoming(gtv, gt)
        return phi


class BooleanEq(BoolCmpOp):
    """
    Comparison equal '==' operator.\n
    left == right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_pointer():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
            return i
        if cmpty.is_struct():
            if cmpty.has_operator('<=>'):
                method = cmpty.operator['<=>']
                ptr = self.left.get_pointer().irvalue
                value = self.right.eval()
                ovrld = method.get_overload([cmpty.get_pointer_to(), self.right.get_type()])
                if not ovrld:
                    pass
                call = self.builder.call(ovrld, [ptr, value])
                i = self.builder.icmp_unsigned('==', call, ir.Constant(ovrld.rtype.get_ir_type(), 0))
                return i
            else:
                lineno = self.spos.lineno
                colno = self.spos.colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Comparing structs using operator '<=>', but no matching operator method found. "
                                   f"({str(self.left.get_type())} and {str(self.right.get_type())}).")
        if cmpty.is_unsigned() or cmpty.is_bool():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('==', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('==', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() == self.right.consteval()


class BooleanNeq(BoolCmpOp):
    """
    Comparison not equal '!=' operator.\n
    left != right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_pointer():
            i = self.builder.icmp_unsigned('!=', self.lhs, self.rhs)
            return i
        if cmpty.is_unsigned() or cmpty.is_bool():
            i = self.builder.icmp_unsigned('!=', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('!=', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('!=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('!=', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() != self.right.consteval()


class BooleanGt(BoolCmpOp):
    """
    Comparison greater than '>' operator.\n
    left > right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_unsigned() or cmpty.is_bool():
            i = self.builder.icmp_unsigned('>', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('>', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('>', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_unordered('>', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() > self.right.consteval()


class BooleanLt(BoolCmpOp):
    """
    Comparison less than '<' operator.\n
    left < right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_unsigned() or cmpty.is_bool():
            i = self.builder.icmp_unsigned('<', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('<', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('<', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() < self.right.consteval()


class BooleanGte(BoolCmpOp):
    """
    Comparison greater than or equal '>=' operator.\n
    left >= right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_unsigned():
            i = self.builder.icmp_unsigned('>=', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('>=', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('>=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('>=', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() >= self.right.consteval()


class BooleanLte(BoolCmpOp):
    """
    Comparison greater than or equal '<=' operator.\n
    left <= right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if cmpty.is_unsigned():
            i = self.builder.icmp_unsigned('<=', self.lhs, self.rhs)
        elif cmpty.is_integer():
            i = self.builder.icmp_signed('<=', self.lhs, self.rhs)
        elif cmpty.is_float():
            i = self.builder.fcmp_unordered('<=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('<=', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() <= self.right.consteval()


class Assignment(ASTNode):
    """
    Assignment statement to a defined variable.\n
    lvalue = expr;
    """
    def __init__(self, builder, module, package, spos, lvalue, expr):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.expr = expr

    def getsourcepos(self):
        return self.spos
    
    def eval(self):
        sptr = self.lvalue.get_pointer()
        stype = sptr.type
        ptr = sptr.irvalue
        if stype.is_reference():
            stype = stype.type
            ptr = self.builder.load(ptr)
        if not sptr.is_mut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            msg = ''
            if sptr.is_const():
                msg = 'const'
            if sptr.is_immut():
                msg = 'immut'
            if msg == '':
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Cannot reassign to (default) immut variable, {sptr.name}.")
            else:
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Cannot reassign to {msg} variable, {sptr.name}.")
        if sptr.is_readonly() and self.lvalue.is_deref:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot write to readonly pointer variable, {sptr.name}.")
        if stype.is_struct():
            if stype.has_operator('='):
                method = stype.operator['=']
                value = self.expr.eval()
                ovrld = method.get_overload([stype.get_pointer_to(), self.expr.get_type()])
                if not ovrld:
                    lineno = self.expr.getsourcepos().lineno
                    colno = self.expr.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"No matching overload of = operator for struct, {stype.name}, "
                                       f"for types ({print_types([stype.get_pointer_to(), self.expr.get_type()])}).")
                ovrld = implicit_define_function(self.module, ovrld)
                self.builder.call(ovrld, [ptr, value])
                return
            else:
                lineno = self.expr.getsourcepos().lineno
                colno = self.expr.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Struct, {stype.name}, has no operator= defined.")
        value = self.expr.eval()
        if sptr.is_atomic():
            self.builder.store_atomic(value, ptr, 'seq_cst', 4)
            return
        if isinstance(self.expr, Null):
            self.builder.store(ir.Constant(ptr.type.pointee, 'null'), ptr)
            return
        try:
            self.builder.store(value, ptr)
        except TypeError:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Type error occurred, {self.lvalue.get_type()} <= {self.expr.get_type()}.")


class AddAssignment(Assignment):
    """
    Add assignment statement to a defined variable.\n
    lvalue += expr; (lvalue = lvalue + expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.lvalue.getsourcepos().lineno
            colno = self.lvalue.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            ty = self.expr.get_type()
            if ty.is_float():
                res = self.builder.fadd(value, self.expr.eval())
            elif ty.is_integer():
                res = self.builder.add(value, self.expr.eval())
            else:
                res = None
                lineno = self.expr.getsourcepos().lineno
                colno = self.expr.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Attempting to perform addition with two operands of incompatible types "
                                   f"({str(self.lvalue.get_pointer().type)} and {str(ty)}).")
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('add', ptr.irvalue, self.expr.eval(), 'seq_cst')


class SubAssignment(Assignment):
    """
    Sub assignment statement to a defined variable.\n
    lvalue -= expr; (lvalue = lvalue - expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            ty = self.expr.get_type()
            if ty.is_float():
                res = self.builder.fsub(value, self.expr.eval())
            elif ty.is_integer():
                res = self.builder.sub(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('sub', ptr.irvalue, self.expr.eval(), 'seq_cst')


class PrefixIncrementOp(PrefixOp):
    """
    Prefix increment to a defined variable.\n
    ++right; (right = right + 1, right;)
    """
    def eval(self):
        if not (isinstance(self.right, LValue) or
                isinstance(self.right, ElementOf) or
                isinstance(self.right, TupleElementOf) or
                isinstance(self.right, LValueField)):
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Cannot increment expression which is not an lvalue."
                               )
        ptr = self.right.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}."
                               )
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            ty = self.right.get_type()
            if ty.is_pointer():
                res = self.builder.gep(value, [ir.Constant(ir.IntType(64), 1)])
            elif ty.is_integer():
                res = self.builder.add(value, ir.Constant(ty.get_ir_type(), 1))
            else:
                res = None
                lineno = self.right.getsourcepos().lineno
                colno = self.right.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Attempting to perform addition on operand of incompatible type "
                                   f"({str(ty)}).")
            self.builder.store(res, ptr.irvalue)
            return res
        else:
            ty = self.right.get_type()
            self.builder.atomic_rmw('add', ptr.irvalue, ir.Constant(ty.get_ir_type(), 1), 'seq_cst')
            return self.builder.load_atomic(ptr.irvalue)


class PrefixDecrementOp(PrefixOp):
    """
    Prefix decrement to a defined variable.\n
    --right; (right = right - 1, right;)
    """
    def eval(self):
        if not (isinstance(self.right, LValue) or
                isinstance(self.right, ElementOf) or
                isinstance(self.right, TupleElementOf) or
                isinstance(self.right, LValueField)):
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Cannot decrement expression which is not an lvalue.")
        ptr = self.right.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.right.getsourcepos().lineno
            colno = self.right.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            ty = self.right.get_type()
            if ty.is_integer():
                res = self.builder.sub(value, ir.Constant(ty.get_ir_type(), 1))
            else:
                res = None
                lineno = self.right.getsourcepos().lineno
                colno = self.right.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Attempting to perform subtraction on operand of incompatible type "
                                   f"({str(ty)}).")
            self.builder.store(res, ptr.irvalue)
            return self.builder.load(ptr.irvalue)
        else:
            ty = self.right.get_type()
            self.builder.atomic_rmw('add', ptr.irvalue, ir.Constant(ty.get_ir_type(), 1), 'seq_cst')
            return self.builder.load_atomic(ptr.irvalue)


class MulAssignment(Assignment):
    """
    Multiply assignment statement to a defined variable.\n
    lvalue *= expr; (lvalue = lvalue * expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.mul(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            value = self.builder.load_atomic(ptr.irvalue, 'seq_cst', 4)
            res = self.builder.mul(value, self.expr.eval())
            self.builder.store_atomic(res, ptr.irvalue, 'seq_cst', 4)


class DivAssignment(Assignment):
    """
    Division assignment statement to a defined variable.\n
    lvalue /= expr; (lvalue = lvalue / expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        value = None
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
        else:
            value = self.builder.load_atomic(ptr.irvalue, 'seq_cst', 4)
        res = None
        if self.lvalue.get_type().is_unsigned():
            res = self.builder.udiv(value, self.expr.eval())
        elif self.lvalue.get_type().is_integer():
            res = self.builder.sdiv(value, self.expr.eval())
        elif self.lvalue.get_type().is_float():
            res = self.builder.fdiv(value, self.expr.eval())
        else:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot do division assignment on variable, %s." % ptr.name
            )
        if not ptr.is_atomic():
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.store_atomic(res, ptr.irvalue, 'seq_cst', 4)


class ModAssignment(Assignment):
    """
    Modulo assignment statement to a defined variable.\n
    lvalue %= expr; (lvalue = lvalue % expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        value = None
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
        else:
            value = self.builder.load_atomic(ptr.irvalue, 'seq_cst', 4)
        res = None
        if self.lvalue.get_type().is_unsigned():
            res = self.builder.urem(value, self.expr.eval())
        elif self.lvalue.get_type().is_integer():
            res = self.builder.srem(value, self.expr.eval())
        elif self.lvalue.get_type().is_float():
            res = self.builder.frem(value, self.expr.eval())
        else:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot do modulus assignment on variable, {ptr.name}.")
        if not ptr.is_atomic():
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.store_atomic(res, ptr.irvalue, 'seq_cst', 4)


class AndAssignment(Assignment):
    """
    And assignment statement to a defined variable.\n
    lvalue &= expr; (lvalue = lvalue & expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.and_(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('and', ptr.irvalue, self.expr.eval(), 'seq_cst')


class OrAssignment(Assignment):
    """
    Or assignment statement to a defined variable.\n
    lvalue |= expr; (lvalue = lvalue | expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.or_(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('or', ptr.irvalue, self.expr.eval(), 'seq_cst')


class XorAssignment(Assignment):
    """
    Xor assignment statement to a defined variable.\n
    lvalue ^= expr; (lvalue = lvalue ^ expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if not ptr.is_mut():
            msg = '(default) immut'
            if ptr.is_const():
                msg = 'const'
            elif ptr.is_immut():
                msg = 'immut'
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot reassign to {msg} variable, {ptr.name}.")
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.xor(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('xor', ptr.irvalue, self.expr.eval(), 'seq_cst')


class Program:
    """
    Base node for AST
    """
    def __init__(self, package, stmt=None):
        self.package = package
        self.stmts = []
        if stmt is not None:
            self.stmts.append(stmt)

    def add(self, stmt):
        self.stmts.append(stmt)

    def generate_symbols(self):
        for stmt in self.stmts:
            if hasattr(stmt, 'generate_symbol'):
                stmt.generate_symbol()

    def eval(self):
        for stmt in self.stmts:
            stmt.eval()


class PackageDecl(ASTNode):
    def __init__(self, builder, module, package, spos, lvalue):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.builder.package = self.lvalue.get_name()

    def eval(self):
        pass


class ImportDecl(ASTNode):
    """
    A statement that reads and imports another package.\n
    import lvalue;\n
    import lvalue::{symbols_to_import};
    """
    def __init__(self, builder, module, package, spos, lvalue, symbols_to_import=None, import_all=False):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.import_all = import_all
        if symbols_to_import is None:
            symbols_to_import = []
        self.symbols_to_import = symbols_to_import
        package_paths = self.lvalue.get_name().split('::')
        base_path = self.package.working_directory
        for path in package_paths:
            base_path += '/packages/' + path
        self.new_package = Package(package_paths[-1], working_directory=base_path, target=self.package.target)

    def generate_symbol(self):
        from sparser import parser, ParserState
        from lexer import lexer
        from cachedmodule import CachedModule
        import os.path
        base_path = self.new_package.working_directory
        symbols_path = base_path + f'/symbols.{self.new_package.target.short_name}.json'
        print('Symbols path:', symbols_path)
        package = self.new_package
        if os.path.isfile(symbols_path) and os.path.getmtime(symbols_path) > os.path.getmtime(base_path + '/main.sat'):
            package.load_symbols_from_file(self.module, symbols_path)

            if not self.import_all:
                self.package.import_package(package)
                if len(self.symbols_to_import) > 0:
                    self.package.import_symbols_from_package(package, self.symbols_to_import)
            else:
                self.package.import_package(package)
                self.package.import_all_symbols_from_package(package)
        else:
            path = base_path + '/main.sat'
            if path not in self.package.cachedmods.keys():
                text_input = ""
                with open(path, encoding='utf8') as f:
                    text_input = f.read()

                cmod = CachedModule(path, text_input)
                self.package.cachedmods[path] = cmod

            cmod = self.package.cachedmods[path]

            tokens = lexer.lex(cmod.text_input)

            self.builder.filestack.append(cmod.text_input)
            self.builder.filestack_idx += 1

            self.module.filestack.append(path)
            self.module.filestack_idx += 1

            # if not self.import_all:
            package = self.new_package
            # else:
            #    pg = Parser(self.module, self.builder, package)
            #    pg.parse()

            ast = parser.parse(tokens, state=ParserState(self.builder, self.module, package))
            ast.generate_symbols()
            # package.save_symbols_to_file(symbols_path)
            cmod.add_parsed_ast(ast)

            self.builder.filestack.pop(-1)
            self.builder.filestack_idx -= 1

            self.module.filestack.pop(-1)
            self.module.filestack_idx -= 1

            if not self.import_all:
                self.package.import_package(package)
                if len(self.symbols_to_import) > 0:
                    self.package.import_symbols_from_package(package, self.symbols_to_import)
            else:
                self.package.import_package(package)
                self.package.import_all_symbols_from_package(package)

        # print(self.new_package)

    def eval(self):
        return
        from cachedmodule import CachedModule
        from lexer import lexer
        from sparser import parser, ParserState
        base_path = self.new_package.working_directory
        path = base_path + '/main.sat'
        if path not in self.package.cachedmods:
            text_input = ""
            with open(path, encoding='utf8') as f:
                text_input = f.read()

            cmod = CachedModule(path, text_input)
            self.package.cachedmods[path] = cmod

            tokens = lexer.lex(cmod.text_input)

            self.builder.filestack.append(cmod.text_input)
            self.builder.filestack_idx += 1

            self.module.filestack.append(path)
            self.module.filestack_idx += 1

            package = self.package
            if not self.import_all:
                package = self.new_package

            self.builder.filestack.pop(-1)
            self.builder.filestack_idx -= 1

            self.module.filestack.pop(-1)
            self.module.filestack_idx -= 1

            ast = parser.parse(tokens, state=ParserState(self.builder, self.module, package))
            ast.eval()
        else:
            cmod = self.package.cachedmods[path]
            cmod.ast.eval()


class ImportDeclExtern(ASTNode):
    """
    A statement that reads and imports another package's declarations.
    """
    def __init__(self, builder, module, package, spos, lvalue):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue

    def eval(self):
        pass


class CIncludeDecl(ASTNode):
    """
    A statement that reads and imports a C header file.
    """
    def __init__(self, builder, module, package, spos, string, decl_mode=False):
        super().__init__(builder, module, package, spos)
        self.string = string
        self.decl_mode = decl_mode

    def generate_symbol(self):
        import cparser
        path = self.package.working_directory + '/' + str(self.string.value).strip('"')
        print(f"Including C file \"{path}\"...")
        cparser.parse_c_file(self.builder, self.module, self.package, path)

    def eval(self):
        pass


class BinaryInclude(ASTNode):
    """
    A binary file include.\n
    name := binary_include(path);\n
    name: T = binary_include(path);
    """
    def __init__(self, builder, module, package, spos, path, name, var_type=None,
                 visibility=Visibility.PUBLIC):
        super().__init__(builder, module, package, spos)
        self.path = clean_string_literal(path.value)
        self.name = name.value
        self.type = None
        self.symbol = None
        self.visibility = visibility

    def get_type(self):
        if self.type is None:
            import os
            size = os.path.getsize(self.path)
            self.type = types['byte'].get_array_of(size)
        return self.type

    def generate_symbol(self):
        if self.symbol is None or self.symbol.get_ir_value(self.module) is None:
            global_fmt = ir.GlobalVariable(self.module, self.get_type().get_ir_type(), name=self.name)
            global_fmt.linkage = 'external'
            global_fmt.global_constant = True
            ptr = GlobalValue(self.name, self.get_type(), global_fmt,
                              visibility=self.visibility,
                              qualifiers=[('const',)])
            ptr.add_ir_value(self.module, global_fmt)
            self.symbol = self.package.add_symbol(self.name, ptr)
            # print('Generating symbol ', ptr)

    def eval(self):
        data_type = self.get_type().get_ir_type()
        bin_global = self.package.lookup_symbol(self.name)
        global_fmt = bin_global.get_ir_value(self.module)
        global_fmt.linkage = LinkageType.VALUE[LinkageType.DEFAULT]
        global_fmt.global_constant = True
        with open(self.path, 'rb') as file:
            data = file.read()
        fmt_data = bytearray(data)
        c_data = ir.Constant(ir.ArrayType(ir.IntType(8), len(data)),
                             fmt_data)
        global_fmt.initializer = c_data.bitcast(data_type)
        ptr = Value(self.name, self.get_type(), global_fmt, visibility=self.visibility, qualifiers=[('const',)])
        

class CDeclareDecl(ASTNode):
    """
    Creates a block of C declarations.
    """
    def __init__(self, builder, module, package, spos, cblock):
        super().__init__(builder, module, package, spos)
        self.cblock = cblock

    def eval(self):
        self.builder.c_decl = True 
        for decl in self.cblock:
            decl.eval()
        self.builder.c_decl = False


class Attribute(ASTNode):
    """
    A name that describes a configuration property of a symbol.
    lvalue\n
    lvalue(args...)
    """
    def __init__(self, builder, module, package, spos, lvalue, args=None):
        super().__init__(builder, module, package, spos)
        if args is None:
            self.args = []
        else:
            self.args = args
        self.lvalue = lvalue


class AttributeList(ASTNode):
    """
    A list of attributes to be assigned to the succeeding symbol.
    [[attr1, attr2, ...]]\n
    [[attr1(arg1, arg2, ...), ...]]\n
    """
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.attr_list = {}

    def add_attr(self, attr):
        self.attr_list[attr.lvalue.get_name()] = attr

    def has_attr(self, attr_name):
        return attr_name in self.attr_list

    def get_attr(self, attr_name):
        return self.attr_list[attr_name]


class CodeBlock(ASTNode):
    """
    A block of multiple statements with an enclosing scope.
    { ... }\n
    [capture]{ ... }
    """
    def __init__(self, builder, module, package, spos, stmt, capture=None):
        super().__init__(builder, module, package, spos)
        if stmt is not None:
            self.stmts = [stmt]
        else:
            self.stmts = []
        self.capture = capture

    def add(self, stmt):
        self.stmts.append(stmt)

    def add_capture(self, capture):
        self.capture = capture

    def eval(self, builder=None, continue_dest=None, break_dest=None):
        if builder is not None:
            self.builder = builder
        scope = Scope(self.builder)
        if self.capture is not None:
            scope.is_guarded = True
            pass_capture_to_scope(self.builder, self.module, self.package, self.capture, scope)
        push_existing_scope(scope)
        if continue_dest is not None:
            set_continue_dest(continue_dest)
        if break_dest is not None:
            set_break_dest(break_dest)
        for stmt in self.stmts:
            stmt.eval()
        pop_inner_scope()


def get_type_by_name(builder, module, name):
    """
    Searches the types dictionary and returns the irtype of the semantic type of that name.
    """
    if name in types.keys():
        return types[name].irtype
    return types["int"].irtype


def from_type_get_name(builder, module, t):
    if t == ir.IntType(32):
        return "int"
    if isinstance(t, ir.FloatType):
        return "float32"
    if isinstance(t, ir.DoubleType):
        return "float64"
    if t == ir.IntType(8).as_pointer():
        return "cstring"
    return "bool"


class ValueDecl(ASTNode):
    """
    A definition of a named value.\n
    {qualifiers}* name\n
    {qualifiers}* &name
    """
    def __init__(self, builder, module, package, spos, name, qualifiers=None, is_ref=False):
        super().__init__(builder, module, package, spos)
        if qualifiers is None:
            qualifiers = []
        self.name = name
        self.qualifiers = qualifiers.copy()
        self.is_ref = is_ref


class FuncArg(ASTNode):
    """
    An definition of a function parameter.\n
    name : atype, \n
    name : atype = default_value,\n
    name := default_value,
    """
    def __init__(self, builder, module, package, spos, name, atype, default_value=None, qualifiers=None):
        super().__init__(builder, module, package, spos)
        if qualifiers is None:
            qualifiers = []
        self.name = name
        self.atype = atype
        self.type = None
        self.default_value = default_value
        self.qualifiers = qualifiers.copy()

    def has_default_value(self):
        return self.default_value is not None
    
    def eval(self, func: ir.Function, decl=True):
        if self.atype is None:
            self.type = self.default_value.get_type()
        else:
            self.type = self.atype.get_type()
            self.type.irtype = self.type.get_ir_type()

        arg = ir.Argument(func, self.type.irtype, name=self.name.value)
        if 'sret' in self.qualifiers:
            arg.add_attribute(f'sret({str(self.type.irtype)})')
        if decl:
            val = Value(self.name.value, self.type, arg, qualifiers=self.qualifiers)
            add_new_local(self.name.value, val)
            return val
        else:
            with self.builder.goto_entry_block():
                self.builder.position_at_start(self.builder.block)
                ptr = self.builder.alloca(self.type.irtype, name=self.name.value)
            self.builder.store(arg, ptr)
            argval = Value(self.name.value, self.type, arg, qualifiers=self.qualifiers)
            val = Value(self.name.value, self.type, ptr, qualifiers=self.qualifiers)
            add_new_local(self.name.value, val)
            return argval


class FuncArgList(ASTNode):
    """
    A list of arguments for a function.
    """
    def __init__(self, builder, module, package, spos, arg=None):
        super().__init__(builder, module, package, spos)
        if arg is not None:
            self.args = [arg]
        else:
            self.args = []

    def add(self, arg):
        self.args.append(arg)

    def prepend(self, arg):
        self.args.insert(0, arg)

    def get_arg_list(self, func):
        args = []
        for arg in self.args:
            args.append(arg.eval(func, False).irvalue)
        return args

    def get_decl_arg_list(self, func):
        args = []
        for arg in self.args:
            args.append(arg.eval(func).irvalue)
        return args

    def get_arg_type_list(self):
        atypes = []
        for arg in self.args:
            atypes.append(arg.type.irtype)
        return atypes

    def get_arg_stype_list(self):
        atypes = []
        for arg in self.args:
            atypes.append(arg.type)
        return atypes

    def get_default_args_list(self):
        default_args = []
        for arg in self.args:
            if arg.has_default_value():
                default_args.append(arg)
        return default_args

    def get_arg_decl_type_list(self):
        return [arg.atype for arg in self.args]

    def eval(self, func):
        eargs = []
        for arg in self.args:
            eargs.append(arg.eval(func))
        return eargs


class FuncDecl(ASTNode):
    """
    A declaration and definition of a function.\n
    fn name(decl_args): rtype { block }\n
    visibility fn name(decl_args): rtype { block }\n
    [[attribute_list]] fn name(decl_args): rtype { block }
    """
    def __init__(self, builder, module, package, spos, name, rtype, block, decl_args, var_arg=False,
                 visibility=Visibility.DEFAULT,
                 attribute_list=None):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args
        self.var_arg = var_arg
        self.visibility = visibility
        self.attribute_list = attribute_list

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def generate_symbol(self):
        package = self.package
        if self.package.lookup_symbol(self.name.value) is None:
            rtype = self.rtype.get_type()
            if rtype.is_struct() and rtype.is_value():
                sret = True
            else:
                sret = False
            decltypes = self.decl_args.get_arg_decl_type_list()
            sargtypes = [decltype.get_type() for decltype in decltypes]
            argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]
            default_args = self.decl_args.get_default_args_list()
            if sret:
                argtypes.append(rtype.get_ir_type().as_pointer())
                rirtype = ir.VoidType()
            else:
                rirtype = rtype.get_ir_type()
            fnty = ir.FunctionType(rirtype, argtypes, var_arg=self.var_arg)
            sfnty = FuncType("", fnty, rtype, sargtypes)
            fname = self.name.value
            if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
                fname = mangle_name(self.name.value, sfnty.atypes)

            if self.attribute_list and self.attribute_list.has_attr('link_name'):
                fname = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
            try:
                self.module.get_global(fname)
                text_input = self.builder.filestack[self.builder.filestack_idx]
                lines = text_input.splitlines()
                lineno = self.name.getsourcepos().lineno
                colno = self.name.getsourcepos().colno
                if lineno > 1:
                    line1 = lines[lineno - 2]
                    line2 = lines[lineno - 1]
                    print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
                else:
                    line1 = lines[lineno - 1]
                    print("%s\n%s^" % (line1, "~" * (colno - 1)))
                raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
                    self.module.filestack[self.module.filestack_idx],
                    lineno,
                    colno,
                    self.name.value
                ))
            except KeyError:
                pass
            fn = ir.Function(self.module, fnty, fname)
            if self.name.value not in self.module.sfuncs:
                fn_symbol = package.add_symbol(self.name.value,
                                               Func(self.name.value, sfnty.rtype, visibility=self.visibility))
                overload_symbol = fn_symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype, default_args=default_args)
                if self.attribute_list is not None and self.attribute_list.has_attr('link_name'):
                    link_name = self.attribute_list.get_attr('link_name').args[0]
                    overload_symbol.link_name = link_name
            else:
                symbol = package[self.name.value]
                overload_symbol = symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype, default_args=default_args)
                if self.attribute_list is not None and self.attribute_list.has_attr('link_name'):
                    link_name = self.attribute_list.get_attr('link_name').args[0]
                    overload_symbol.link_name = link_name

    def eval(self):
        push_new_scope(self.builder)
        if self.attribute_list is not None and self.attribute_list.has_attr('message'):
            msg = self.attribute_list.get_attr('message').args[0].value.strip("\"")
            print("message:", msg)

        rtype = self.rtype.get_type()
        if rtype.is_struct() and rtype.is_value():
            sret = True
        else:
            sret = False

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [argtype.get_ir_type() for argtype in sargtypes]
        if sret:
            argtypes.append(rtype.get_ir_type().as_pointer())
            rirtype = ir.VoidType()
        else:
            rirtype = rtype.get_ir_type()

        fnty = ir.FunctionType(rirtype, argtypes, var_arg=self.var_arg)
        #print(f"fn {self.name.value} ({[str(stype) for stype in sargtypes]}): {str(self.rtype.type)};")
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype, sargtypes)
        fname = self.name.value
        if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
            fname = mangle_name(self.name.value, sfnty.atypes)
        if self.attribute_list and self.attribute_list.has_attr('link_name'):
            fname = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
        symbol = self.package.lookup_symbol(self.name.value)
        #print(fname)
        if symbol is not None and symbol.get_overload(sfnty.atypes) is not None:
            fn = symbol.get_overload(sfnty.atypes)
            if not fn.is_declaration:
                text_input = self.builder.filestack[self.builder.filestack_idx]
                lines = text_input.splitlines()
                lineno = self.name.getsourcepos().lineno
                colno = self.name.getsourcepos().colno
                if lineno > 1:
                    line1 = lines[lineno - 2]
                    line2 = lines[lineno - 1]
                    print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
                else:
                    line1 = lines[lineno - 1]
                    print("%s\n%s^" % (line1, "~" * (colno - 1)))
                raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
                    self.module.filestack[self.module.filestack_idx],
                    lineno,
                    colno,
                    self.name.value
                ))
        else:
            fn = ir.Function(self.module, fnty, fname)
            if self.name.value not in self.module.sfuncs:
                self.module.sfuncs[self.name.value] = Func(self.name.value, sfnty.rtype, visibility=self.visibility)
                self.package.add_symbol(self.name.value, self.module.sfuncs[self.name.value])
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
                if self.attribute_list and self.attribute_list.has_attr('link_name'):
                    overload = self.module.sfuncs[self.name.value].get_overload(sfnty.atypes)
                    overload.link_name = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
            else:
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
                if self.attribute_list:
                    overload = self.module.sfuncs[self.name.value].get_overload(sfnty.atypes)
                    overload.link_name = self.attribute_list.get_attr('link_name').args[0]
        #print("New function:", fname)
        sfnty.name = fname
        self.module.sfunctys[fname] = sfnty
        block = fn.append_basic_block("entry")
        self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
            "name": self.name.value,
            "scope": self.module.di_file,
            "file": self.module.di_file,
            "line": self.spos.lineno,
            "unit": self.module.di_compile_unit,
            #"column": self.spos.colno,
            "isDefinition": True
        }, True)
        self.builder.position_at_start(block)
        args = self.decl_args.get_arg_list(fn)
        if sret:
            ty = rtype.get_pointer_to()
            irty = ty.get_ir_type()
            arg = ir.Argument(fn, irty, name='sret')
            arg.add_attribute('sret')
            with self.builder.goto_entry_block():
                self.builder.position_at_start(self.builder.block)
                ptr = self.builder.alloca(irty, name='sret')
            self.builder.store(arg, ptr)
            argval = Value('sret', ty, arg)
            val = Value('sret', ty, ptr)
            add_new_local('sret', val)
            args.append(argval.irvalue)
            self.builder.ret_dest = arg
        fn.args = tuple(args)
        self.block.eval()
        if not self.builder.block.is_terminated:
            if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
        if sret:
            self.builder.ret_dest = None
        pop_inner_scope()


class FuncDeclExtern(ASTNode):
    """
    A declaration of an externally defined function.\n
    fn name(decl_args) : rtype; 
    """
    def __init__(self, builder, module, package, spos, name, rtype, decl_args, var_arg=False):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.decl_args = decl_args
        self.var_arg = var_arg
        self.visibility = Visibility.PUBLIC
        self.attribute_list = None

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def getsourcepos(self):
        return self.spos

    def generate_symbol(self):
        package = self.package
        if self.package.lookup_symbol(self.name.value) is None:
            rtype = self.rtype.get_type()
            # if rtype.is_struct() and rtype.is_value():
            #     self.decl_args.add(FuncArg(
            #         self.builder,
            #         self.module,
            #         self.package,
            #         self.rtype.spos,
            #         Token('IDENT', 'ret', self.spos),
            #         rtype.get_pointer_to(), ['sret']))
            decltypes = self.decl_args.get_arg_decl_type_list()
            sargtypes = [decltype.get_type() for decltype in decltypes]
            argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]
            default_args = self.decl_args.get_default_args_list()
            fnty = ir.FunctionType(rtype.get_ir_type(), argtypes, var_arg=self.var_arg)
            # print(f"fn {self.name.value} ({[str(stype) for stype in sargtypes]}): {str(rtype)};")
            # print("%s (%s)" % (self.name.value, fnty))
            sfnty = FuncType("", fnty, rtype, sargtypes)
            fname = self.name.value
            if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
                fname = mangle_name(self.name.value, sfnty.atypes)
            if self.attribute_list and self.attribute_list.has_attr('link_name'):
                fname = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
            try:
                self.module.get_global(fname)
                text_input = self.builder.filestack[self.builder.filestack_idx]
                lines = text_input.splitlines()
                lineno = self.name.getsourcepos().lineno
                colno = self.name.getsourcepos().colno
                if lineno > 1:
                    line1 = lines[lineno - 2]
                    line2 = lines[lineno - 1]
                    print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
                else:
                    line1 = lines[lineno - 1]
                    print("%s\n%s^" % (line1, "~" * (colno - 1)))
                raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
                    self.module.filestack[self.module.filestack_idx],
                    lineno,
                    colno,
                    self.name.value
                ))
            except KeyError:
                pass
            fn = ir.Function(self.module, fnty, fname)
            symbol = package.lookup_symbol(fname)
            if symbol is None:
                fn_symbol = package.add_symbol(self.name.value,
                                               Func(self.name.value, sfnty.rtype, visibility=self.visibility))
                overload_symbol = fn_symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype, default_args=default_args)

                if self.attribute_list and self.attribute_list.has_attr('link_name'):
                    overload_symbol.link_name = fname
            else:
                overload_symbol = symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype, default_args=default_args)
                if self.attribute_list and self.attribute_list.has_attr('link_name'):
                    overload_symbol.link_name = fname

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()
        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [argtype.get_ir_type() for argtype in sargtypes]
        fnty = ir.FunctionType(rtype.irtype, argtypes, var_arg=self.var_arg)
        sfnty = FuncType("", fnty, rtype, sargtypes)
        fname = self.name.value
        if not self.builder.c_decl:
            fname = mangle_name(self.name.value, sfnty.atypes)
        if self.attribute_list and self.attribute_list.has_attr('link_name'):
            fname = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
        try:
            fn = self.module.get_global(fname)
        except KeyError:
            fn = ir.Function(self.module, fnty, fname)
        fn.args = tuple(self.decl_args.get_decl_arg_list(fn))
        #self.module.sfunctys[self.name.value] = sfnty
        symbol = self.package.lookup_symbol(self.name.value)
        if symbol is None:
            symbol = Func(self.name.value, sfnty.rtype)
            self.package.add_symbol(self.name.value, symbol)
        overload = symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
        if self.attribute_list and self.attribute_list.has_attr('link_name'):
            link_name = self.attribute_list.get_attr('link_name').args[0].value.strip('\"')
            overload.link_name = link_name
        pop_inner_scope()


class CaptureExpr(ASTNode):
    """
    A scope capture expression.\n
    []\n
    [var1, &var2, ...]\n
    [*]\n
    """
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.capture_list = {}
        self.capture_all_by_value = False
        self.capture_all_by_ref = False

    def capture_by_value(self, lvalue: LValue, spec=None):
        """
        [lvalue]\n
        """
        if lvalue.get_name() in self.capture_list:
            lineno = lvalue.spos.lineno
            colno = lvalue.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Can't capture a variable twice.")
        if spec is None:
            spec = []
        self.capture_list[lvalue.get_name()] = (lvalue, spec, 'value')

    def capture_by_ref(self, lvalue: LValue, spec=None):
        """
        [&lvalue]\n
        """
        if lvalue.get_name() in self.capture_list:
            lineno = lvalue.spos.lineno
            colno = lvalue.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Can't capture a variable twice.")
        if spec is None:
            spec = []
        self.capture_list[lvalue.get_name()] = (lvalue, spec, 'ref')

    def capture_all_vars_by_ref(self):
        """
        [&]\n
        """
        self.capture_all_by_ref = True

    def capture_all_vars_by_value(self):
        """
        [*]\n
        """
        self.capture_all_by_value = True


class LambdaExpr(Expr):
    """
    A lambda expression.\n
    fn(decl_args): rtype { block }\n
    fn[capture](decl_args): rtype { block }
    """
    def __init__(self, builder, module, package, spos, rtype, block, decl_args, capture=None):
        super().__init__(builder, module, package, spos)
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args
        self.capture = capture
        self.type = None
        self.irvalue = None

    def has_capture(self):
        return self.capture is not None

    def get_type(self):
        if self.type is None:
            decltypes = self.decl_args.get_arg_decl_type_list()
            sargtypes = [decltype.get_type() for decltype in decltypes]
            argtypes = [argtype.get_ir_type() for argtype in sargtypes]
            self.type = FuncType('',
                                 ir.FunctionType(self.rtype.get_ir_type(), argtypes),
                                 self.rtype.get_type(),
                                 sargtypes).get_pointer_to()
        return self.type

    def eval(self):
        if self.irvalue is None:
            push_new_scope(self.builder)
            fn = ir.Function(self.module,
                             self.get_type().get_dereference_of().get_ir_type(),
                             self.module.get_unique_name(self.builder.function.name + '._unnamed_lambda'))
            fn.linkage = LinkageType.VALUE[LinkageType.PRIVATE]
            block = fn.append_basic_block('entry')
            with self.builder.goto_block(block):
                fn.args = tuple(self.decl_args.get_arg_list(fn))
                self.block.eval()
                if not self.builder.block.is_terminated:
                    if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                        self.builder.ret_void()
                    else:
                        self.builder.ret(ir.Constant(ir.IntType(32), 0))
            self.irvalue = fn
        return self.irvalue


class GlobalVarDecl(ASTNode):
    """
    A global variable declaration statement.\n
    name : vtype;\n
    name : vtype = initval;
    """
    def __init__(self, builder, module, package, spos, name, vtype, initval=None, spec=None,
                 visibility=Visibility.DEFAULT):
        super().__init__(builder, module, package, spos)
        if spec is None:
            spec = []
        self.name = name
        self.vtype = vtype
        self.initval = initval
        self.spec = spec.copy()
        self.visibility = visibility
        self.symbol = None
        self.attribute_list = None

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def getsourcepos(self):
        return self.spos

    def generate_symbol(self):
        if self.symbol is None:
            # self.vtype.eval()
            vartype = self.vtype.get_type()

            quals = [s for s in self.spec.copy()]

            gvar = ir.GlobalVariable(self.module, vartype.get_ir_type(), self.name.value)
            gvar.align = 4
            gvar.linkage = LinkageType.VALUE[LinkageType.EXTERNAL]

            val = GlobalValue(self.name.value, vartype, gvar,
                              visibility=self.visibility, qualifiers=quals)
            if val.is_const():
                gvar.global_constant = True
            val.add_ir_value(self.module, gvar)
            self.symbol = val
            self.package.add_symbol(self.name.value, val)

    def eval(self):
        # self.vtype.eval()
        vartype = self.vtype.type

        quals = [s for s in self.spec.copy()]

        for i in range(len(self.spec)):
            if self.spec[i][0] == 'const':
                if self.initval is None:
                    lineno = self.spec[i][1].lineno
                    colno = self.spec[i][1].colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       "Can't create const global variable with no initial value."
                                       )
            elif self.spec[i][0] == 'immut':
                if self.initval is None:
                    lineno = self.spec[i][1].lineno
                    colno = self.spec[i][1].colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       "Can't create immut global variable with no initial value.")

        gvar = self.symbol.get_ir_value(self.module)
        gvar.align = 4
        gvar.linkage = LinkageType.VALUE[LinkageType.DEFAULT]

        if self.initval:
            if self.initval.is_constexpr:
                gvar.initializer = ir.Constant(vartype.irtype, self.initval.consteval())
            else:
                gvar.initializer = self.initval.eval()
        # add_new_global(self.name.value, ptr)


class MethodDecl(ASTNode):
    """
    A declaration and definition of a method.\n
    fn(*struct) name(decl_args): rtype { block }
    """
    def __init__(self, builder, module, package, spos, name, rtype, block, decl_args, struct,
                 visibility=Visibility.DEFAULT):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args
        self.struct = struct
        thisarg = FuncArg(self.builder, self.module, self.package, self.struct.getsourcepos(),
                          Token('IDENT', 'this'),
                          PointerTypeExpr(self.builder, self.module, self.package, self.struct.getsourcepos(),
                                          TypeExpr(self.builder, self.module, self.package, self.struct.getsourcepos(),
                                                   self.struct))
        )
        self.decl_args.prepend(thisarg)
        self.visibility = visibility
        self.attribute_list = None

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def generate_symbol(self):
        package = self.package
        symbol_path = f"{self.struct.get_name()}::{self.name.value}"
        if self.package.lookup_symbol(symbol_path) is None:
            rtype = self.rtype.get_type()
            decltypes = self.decl_args.get_arg_decl_type_list()
            sargtypes = [decltype.get_type() for decltype in decltypes]
            argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]
            fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
            #print(f"fn {self.name.value} ({[str(stype) for stype in sargtypes]}): {str(rtype)};")
            # print("%s (%s)" % (self.name.value, fnty))
            sfnty = FuncType("", fnty, rtype, sargtypes)
            name = self.name.value

            struct_symbol = package.lookup_symbol(self.struct.get_name())
            fn_symbol = Func(self.name.value, sfnty.rtype, visibility=self.visibility)
            fn_symbol.parent = struct_symbol

            struct_symbol[name] = fn_symbol

            fname = name
            if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
                fname = mangle_symbol(fn_symbol, atypes=sfnty.atypes)
            try:
                self.module.get_global(fname)
                text_input = self.builder.filestack[self.builder.filestack_idx]
                lines = text_input.splitlines()
                lineno = self.name.getsourcepos().lineno
                colno = self.name.getsourcepos().colno
                if lineno > 1:
                    line1 = lines[lineno - 2]
                    line2 = lines[lineno - 1]
                    print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
                else:
                    line1 = lines[lineno - 1]
                    print("%s\n%s^" % (line1, "~" * (colno - 1)))
                raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
                    self.module.filestack[self.module.filestack_idx],
                    lineno,
                    colno,
                    self.name.value
                ))
            except(KeyError):
                pass
            # print(fname)
            fn = ir.Function(self.module, fnty, fname)
            struct_symbol = package.lookup_symbol(self.struct.get_name())
            if package.lookup_symbol(symbol_path) is None:
                fn_symbol = Func(name, sfnty.rtype, visibility=self.visibility)
                fn_symbol.parent = struct_symbol
                struct_symbol[name] = fn_symbol
                if name == 'new':
                    struct_symbol.add_ctor(fn_symbol)
                elif self.name.value == 'delete':
                    struct_symbol.add_dtor(fn_symbol)
                elif self.name.value == 'operator.assign':
                    struct_symbol.add_operator('=', fn_symbol)
                elif self.name.value == 'operator.eq':
                    struct_symbol.add_operator('==', fn_symbol)
                elif self.name.value == 'operator.spaceship':
                    struct_symbol.add_operator('<=>', fn_symbol)
                elif self.name.value == 'operator.add':
                    struct_symbol.add_operator('+', fn_symbol)
                elif self.name.value == 'operator.sub':
                    struct_symbol.add_operator('-', fn_symbol)
                elif self.name.value == 'operator.mul':
                    struct_symbol.add_operator('*', fn_symbol)
                elif self.name.value == 'operator.div':
                    struct_symbol.add_operator('/', fn_symbol)
                elif self.name.value == 'operator.mod':
                    struct_symbol.add_operator('%', fn_symbol)
                elif self.name.value == 'operator.and':
                    struct_symbol.add_operator('&', fn_symbol)
                elif self.name.value == 'operator.or':
                    struct_symbol.add_operator('|', fn_symbol)
                elif self.name.value == 'operator.xor':
                    struct_symbol.add_operator('^', fn_symbol)
                else:
                    struct_symbol.add_method(name, fn_symbol)
                fn_symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
            else:
                fn_symbol = struct_symbol[name]
                fn_symbol.add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]

        fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype, sargtypes)
        name = self.name.value

        struct_type = self.package.lookup_symbol(self.struct.get_name())
        symbol = self.package.lookup_symbol(f"{self.struct.get_name()}::{name}")

        fname = name
        if not self.builder.c_decl:
            fname = mangle_symbol(symbol, atypes=sfnty.atypes)

        if symbol is not None and symbol.get_overload(sfnty.atypes) is not None:
            fn = symbol.get_overload(sfnty.atypes)
            if not fn.is_declaration:
                text_input = self.builder.filestack[self.builder.filestack_idx]
                lines = text_input.splitlines()
                lineno = self.name.getsourcepos().lineno
                colno = self.name.getsourcepos().colno
                if lineno > 1:
                    line1 = lines[lineno - 2]
                    line2 = lines[lineno - 1]
                    print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
                else:
                    line1 = lines[lineno - 1]
                    print("%s\n%s^" % (line1, "~" * (colno - 1)))
                raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
                    self.module.filestack[self.module.filestack_idx],
                    lineno,
                    colno,
                    self.name.value
                ))
        # try:
        #     self.module.get_global(fname)
        #     text_input = self.builder.filestack[self.builder.filestack_idx]
        #     lines = text_input.splitlines()
        #     lineno = self.name.getsourcepos().lineno
        #     colno = self.name.getsourcepos().colno
        #     if lineno > 1:
        #         line1 = lines[lineno - 2]
        #         line2 = lines[lineno - 1]
        #         print("%s\n%s\n%s^" % (line1, line2, "~" * (colno - 1)))
        #     else:
        #         line1 = lines[lineno - 1]
        #         print("%s\n%s^" % (line1, "~" * (colno - 1)))
        #     raise RuntimeError("%s (%d:%d): Redefining global value, %s, as function." % (
        #         self.module.filestack[self.module.filestack_idx],
        #         lineno,
        #         colno,
        #         self.name.value
        #     ))
        # except(KeyError):
        #     pass
        else:
            func = Func(name, sfnty.rtype, visibility=self.visibility)
            func.parent = struct_type
            struct_type[name] = func
            fname = mangle_symbol(func, atypes=sfnty.atypes)

            fn = ir.Function(self.module, fnty, fname)

            if self.name.value not in self.module.sfuncs:
                self.module.sfuncs[self.name.value] = func
                self.package.add_symbol(self.name.value, self.module.sfuncs[self.name.value])
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
            else:
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
            symbol = self.module.sfuncs[self.name.value]
        #print("New method:", fname)
        struct_type = self.package.lookup_symbol(self.struct.get_name())
        if struct_type is None:
            lineno = self.name.lineno
            colno = self.name.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Can't find type {self.struct.get_name()} for method {fname}"
                               )
        if self.name.value == 'new':
            struct_type.add_ctor(symbol)
        elif self.name.value == 'delete':
            struct_type.add_dtor(symbol)
        elif self.name.value == 'operator.assign':
            struct_type.add_operator('=', symbol)
        elif self.name.value == 'operator.eq':
            struct_type.add_operator('==', symbol)
        elif self.name.value == 'operator.spaceship':
            struct_type.add_operator('<=>', symbol)
        elif self.name.value == 'operator.add':
            struct_type.add_operator('+', symbol)
        elif self.name.value == 'operator.sub':
            struct_type.add_operator('-', symbol)
        elif self.name.value == 'operator.mul':
            struct_type.add_operator('*', symbol)
        elif self.name.value == 'operator.div':
            struct_type.add_operator('/', symbol)
        elif self.name.value == 'operator.mod':
            struct_type.add_operator('%', symbol)
        elif self.name.value == 'operator.and':
            struct_type.add_operator('&', symbol)
        elif self.name.value == 'operator.or':
            struct_type.add_operator('|', symbol)
        elif self.name.value == 'operator.xor':
            struct_type.add_operator('^', symbol)
        else:
            struct_type.add_method(name, symbol)
        block = fn.append_basic_block("entry")
        self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
            "name": name, 
            "file": self.module.di_file,
            "line": self.spos.lineno,
            "unit": self.module.di_compile_unit,
            #"column": self.spos.colno,
            "isDefinition": True
        }, True)
        self.builder.position_at_start(block)
        #self.builder.defer = []
        fn.args = tuple(self.decl_args.get_arg_list(fn))
        # print(fn.name, str(fn.args))
        self.block.eval()
        if not self.builder.block.is_terminated:
            eval_dtor_scope()
            eval_defer_scope()
            if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
        pop_inner_scope()


class MethodDeclExtern(ASTNode):
    """
    A declaration of an externally defined method.\n
    fn(*struct) name(decl_args) : rtype; 
    """
    def __init__(self, builder, module, package, spos, name, rtype, decl_args, struct):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.decl_args = decl_args
        self.struct = struct
        thisarg = FuncArg(
            self.builder, self.module, self.package, self.struct.getsourcepos(), Token('IDENT', 'this'),
                TypeExpr(self.builder, self.module, self.package, self.struct.getsourcepos(), self.struct)
        )
        thisarg.atype = thisarg.atype.get_pointer_to()
        self.decl_args.prepend(thisarg)
        self.visibility = Visibility.PUBLIC
        self.attribute_list = None

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()
        rtype.irtype = rtype.get_ir_type()

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]

        fnty = ir.FunctionType(rtype.irtype, argtypes)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype, sargtypes)
        symbol_path = f"{self.struct.get_name()}::{self.name.value}"
        name = self.name.value
        fname = self.struct.get_name() + '.' + name
        if not self.builder.c_decl:
            fname = mangle_name(name, sfnty.atypes)
        fn = ir.Function(self.module, fnty, fname)
        fn.args = tuple(self.decl_args.get_decl_arg_list(fn))
        #self.module.sfunctys[fname] = sfnty
        if name not in self.module.sfuncs:
            self.module.sfuncs[name] = Func(name, sfnty.rtype)
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
        else:
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn, rtype=sfnty.rtype)
        pop_inner_scope()


class VarDecl(ASTNode):
    """
    A local varible declaration statement.\n
    name : vtype;\n
    name : vtype = initval;
    """
    def __init__(self, builder, module, package, spos, name, vtype, initval=None, spec=None):
        super().__init__(builder, module, package, spos)
        if spec is None:
            spec = []
        self.name = name
        self.vtype = vtype
        self.initval = initval
        self.spec = spec.copy()

    def eval(self):
        vartype = self.vtype.get_type()

        quals = []
        for i in range(len(self.spec)):
            if self.spec[i][0] == 'const':
                if self.initval is None:
                    lineno = self.spec[i][1].lineno
                    colno = self.spec[i][1].colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       "Can't create const variable with no initial value."
                                       )
            elif self.spec[i][0] == 'immut':
                if self.initval is None:
                    lineno = self.spec[i][1].lineno
                    colno = self.spec[i][1].colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       "Can't create immut variable with no initial value."
                                       )

        quals = self.spec.copy()

        with self.builder.goto_entry_block():
            self.builder.position_at_start(self.builder.block)
            ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.irtype, name=self.name.value), qualifiers=quals)
        
        add_new_local(self.name.value, ptr)
        dbglv = self.module.add_debug_info("DILocalVariable", {
            "name":self.name.value, 
            #"arg":0, 
            "scope":self.builder.dbgsub
        })
        dbgexpr = self.module.add_debug_info("DIExpression", {})
        self.builder.debug_metadata = self.module.add_debug_info("DILocation", {
            "line": self.spos.lineno,
            "column": self.spos.lineno,
            "scope": self.builder.dbgsub
        })
        self.builder.call(
            self.module.get_global("llvm.dbg.addr"), 
            [ptr.irvalue, dbglv, dbgexpr]
        )
        self.builder.debug_metadata = None
        if vartype.is_optional():
            self.builder.store(ir.Constant(vartype.irtype, None), ptr.irvalue)
        if isinstance(vartype, StructType):
            c = ir.Constant(vartype.irtype, None)
            self.builder.store(c, ptr.irvalue)
            # bcast = self.builder.bitcast(ptr.irvalue, ir.IntType(8).as_pointer())
            # val = ir.Constant(ir.IntType(8), 0)
            # self.builder.call(self.module.memset, [
            #     bcast,
            #     val,
            #     calc_sizeof_struct(self.builder, self.module, ptr.type.irtype),
            #     ir.Constant(ir.IntType(1), 0),
            # ])
            #print(vartype, vartype.has_ctor(), vartype.has_operator('='))
            if self.initval is not None and vartype.has_operator('='):
                method = vartype.operator['=']
                pptr = ptr.irvalue
                value = self.initval.eval()
                ovrld = method.search_overload([vartype.get_pointer_to(), self.initval.get_type()])
                # print(ovrld, str(list(method.overloads.values())[0]))
                if not ovrld:
                    lineno = self.initval.getsourcepos().lineno
                    colno = self.initval.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"Can't find operator= on types {print_types([vartype.get_pointer_to(), self.initval.get_type()])}"
                                       )
                ovrld_fn = implicit_define_function(self.module, ovrld.overload.fn)
                self.builder.call(ovrld_fn, [pptr, value])
                return
            if vartype.has_ctor():
                ctor = implicit_define_function(self.module, vartype.get_ctor())
                self.builder.call(ctor, [ptr.irvalue])
        elif self.initval is not None:
            self.builder.store(self.initval.eval(), ptr.irvalue)
        return ptr


class VarDeclAssign(ASTNode):
    """
    An automatic variable declaration and assignment statement. Uses type inference.\n
    name := initval;
    """
    def __init__(self, builder, module, package, spos, name, initval, spec=None):
        super().__init__(builder, module, package, spos)
        if spec is None:
            spec = []
        self.name = name
        self.initval = initval
        self.spec = spec.copy()

    def eval(self):
        val = self.initval.eval()
        vartype = self.initval.get_type()
        
        #print('New var:', vartype, val, self.initval.get_ir_type())
        quals = self.spec.copy()
        if vartype.is_void():
            #print("%s (%s)" % (str(vartype), str(vartype.irtype)))
            lineno = self.initval.getsourcepos().lineno
            colno = self.initval.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Can't create variable of void type."
            )
        if hasattr(self.initval, 'get_stack_value'):
            ptr = self.initval.get_stack_value(self.name.value)
        else:
            with self.builder.goto_entry_block():
                self.builder.position_at_start(self.builder.block)
                ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.get_ir_type(), name=self.name.value),
                            qualifiers=quals)
            #ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.irtype, name=self.name.value), qualifiers=quals)

        add_new_local(self.name.value, ptr)
        dbglv = self.module.add_debug_info("DILocalVariable", {
            "name":self.name.value, 
            #"arg":1, 
            "file": self.module.di_file,
            "line": self.spos.lineno,
            "scope":self.builder.dbgsub
        })
        dbgexpr = self.module.add_debug_info("DIExpression", {})
        self.builder.debug_metadata = self.module.add_debug_info("DILocation", {
            "line": self.spos.lineno,
            "column": self.spos.lineno,
            "scope": self.builder.dbgsub
        })
        self.builder.call(
            self.module.get_global("llvm.dbg.addr"), 
            [ptr.irvalue, dbglv, dbgexpr]
        )
        self.builder.debug_metadata = None
        if self.initval is not None:
            if ptr.is_atomic():
                self.builder.store_atomic(val, ptr.irvalue, 'seq_cst', 4)
                return ptr
            self.builder.store(val, ptr.irvalue)
        return ptr


class TypeExpr(ASTNode):
    """
    Expression representing a Saturn type.
    """
    def __init__(self, builder, module, package, spos, lvalue, decl_mode=False):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.type = None
        self.base_type = None
        self.quals = []

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def get_base_type(self):
        return self

    def copy(self):
        return TypeExpr(self.builder, self.module, self.package, self.spos, self.lvalue)

    def replace_base_type(self, new_type_expr):
        return new_type_expr.copy()

    def replace_types(self, pairs):
        tuple_types = self.lvalue.type_list.copy()
        for i, ty in enumerate(tuple_types):
            for pair in pairs:
                old, new = pair
                if ty.get_base_type() is old:
                    tuple_types[i] = ty.replace_base_type(new)
                    continue
                if isinstance(ty, TupleTypeExpr):
                    tuple_types[i] = ty.replace_types(pairs)
                    continue
                if ty.get_base_type().lvalue.name == old.name:
                    tuple_types[i] = ty.replace_base_type(new)
        return TypeExpr(self.builder, self.module, self.package, self.spos,
                        LValueGeneric(self.builder, self.module, self.package, self.lvalue.spos,
                                      tuple_types, self.lvalue.lhs))

    def is_generic_type(self):
        return isinstance(self.lvalue, LValueGeneric)

    def get_type(self):
        if self.type is None:
            if isinstance(self.lvalue, LValueGeneric):
                lname = self.lvalue.get_name().rstrip('::' + self.lvalue.name)
                if lname not in types.keys():
                    type_symbol = self.package.lookup_symbol(lname)
                    # print(str(self.package))
                    if type_symbol is None:
                        # print(*types.keys())
                        raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                            self.module.filestack[self.module.filestack_idx],
                            self.spos.lineno,
                            self.spos.colno,
                            lname
                        ))
                else:
                    type_symbol = types[lname]
                type_list = self.lvalue.type_list
                specl = type_symbol.specialize(self.module, type_list)
                self.base_type = specl
                self.type = specl
                return specl
            lname = self.lvalue.get_name()
            if lname not in types.keys():
                type_symbol = self.package.lookup_symbol(lname)
                # print(str(self.package))
                if type_symbol is None:
                    # print(*types.keys())
                    raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                        self.module.filestack[self.module.filestack_idx],
                        self.spos.lineno,
                        self.spos.colno,
                        lname
                    ))
            else:
                type_symbol = types[lname]
            self.base_type = type_symbol
            self.type = type_symbol
            if self.type is None:
                raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                    self.module.filestack[self.module.filestack_idx],
                    self.spos.lineno,
                    self.spos.colno,
                    lname
                ))
        return self.type

    def get_pointer_to(self):
        return PointerTypeExpr(self.builder, self.module, self.package, self.spos, self)


class PointerTypeExpr(TypeExpr):
    """
    Expression representing a pointer to a Saturn type.
    """
    def __init__(self, builder, module, package, spos, pointee, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.pointee = pointee

    def get_base_type(self):
        return self.pointee.get_base_type()

    def copy(self):
        return PointerTypeExpr(self.builder, self.module, self.package, self.spos, self.pointee.copy())

    def replace_base_type(self, new_type_expr):
        return PointerTypeExpr(self.builder, self.module, self.package, self.spos, new_type_expr)

    def get_type(self):
        if self.type is None:
            self.type = self.pointee.get_type().get_pointer_to()
        return self.type

    def eval(self):
        pass


class ReferenceTypeExpr(TypeExpr):
    """
    Expression representing a reference to a Saturn type.
    """
    def __init__(self, builder, module, package, spos, base, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.base = base

    def get_base_type(self):
        return self.base.get_base_type()

    def copy(self):
        return ReferenceTypeExpr(self.builder, self.module, self.package, self.spos, self.base.copy())

    def replace_base_type(self, new_type_expr):
        return ReferenceTypeExpr(self.builder, self.module, self.package, self.spos,
                                 new_type_expr)

    def get_type(self):
        if self.type is None:
            self.type = self.base.get_type().get_reference_to()
            base = self.base.get_type()
            # print(str(base), str(base.irtype), str(self.type), str(self.type.irtype))
        return self.type

    def eval(self):
        pass


class ArrayTypeExpr(TypeExpr):
    """
    Expression representing an array Saturn type.
    """
    def __init__(self, builder, module, package, spos, element, size, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.element = element
        self.size = size

    def get_base_type(self):
        return self.element.get_base_type()

    def copy(self):
        return ArrayTypeExpr(self.builder, self.module, self.package, self.spos, self.element.copy(), self.size)

    def replace_base_type(self, new_type_expr):
        return ArrayTypeExpr(self.builder, self.module, self.package, self.spos,
                             new_type_expr, self.size)

    def get_type(self):
        if not self.size.is_constexpr:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Can't determine array size. Array size must be calculable at compile time."
                               )
        size = self.size.consteval()
        if self.type is None:
            self.type = self.element.get_type().get_array_of(size)
        return self.type

    def eval(self):
        pass


class HVectorTypeExpr(TypeExpr):
    """
    Expression representing a hardware vector Saturn type, suitable for SIMD operations.
    """
    def __init__(self, builder, module, package, spos, element, size, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.element = element
        self.size = size

    def get_base_type(self):
        return self.element.get_base_type()

    def copy(self):
        return HVectorTypeExpr(self.builder, self.module, self.package, self.spos, self.element.copy(), self.size)

    def replace_base_type(self, new_type_expr):
        return HVectorTypeExpr(self.builder, self.module, self.package, self.spos,
                               new_type_expr, self.size)

    def get_type(self):
        if not self.size.is_constexpr:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               "Can't determine vector size. Hardware vector size must be calculable at compile time."
                               )
        size = self.size.consteval()
        if self.type is None:
            self.type = self.element.get_type().get_hvector_of(size)
        return self.type

    def eval(self):
        pass


class SliceTypeExpr(TypeExpr):
    """
    Expression representing a slice Saturn type.
    """
    def __init__(self, builder, module, package, spos, element, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.element = element

    def get_base_type(self):
        return self.element.get_base_type()

    def copy(self):
        return SliceTypeExpr(self.builder, self.module, self.package, self.spos, self.element.copy())

    def replace_base_type(self, new_type_expr):
        return SliceTypeExpr(self.builder, self.module, self.package, self.spos,
                             new_type_expr)

    def get_type(self):
        if self.type is None:
            self.type = self.element.get_type().get_slice_of()
        return self.type

    def eval(self):
        pass


class TupleTypeExpr(TypeExpr):
    """
    Expression representing a Saturn tuple type.\n
    tuple(typeexprs...)
    """
    def __init__(self, builder, module, package, spos, typeexprs):
        super().__init__(builder, module, package, spos, None)
        self.types = typeexprs
        self.type = None
        self.base_type = self.type
        self.quals = []

    def get_type(self):
        if self.type is None:
            self.type = TupleType("", None, self.types)
        return self.type

    def copy(self):
        return TupleTypeExpr(self.builder, self.module, self.package, self.spos, self.types.copy())

    def replace_types(self, pairs):
        tuple_types = self.types.copy()
        for i, ty in enumerate(tuple_types):
            for pair in pairs:
                old, new = pair
                if ty.get_base_type() is old:
                    tuple_types[i] = ty.replace_base_type(new)
                    continue
                if ty.get_base_type().lvalue.name == old.name:
                    tuple_types[i] = ty.replace_base_type(new)
        return TupleTypeExpr(self.builder, self.module, self.package, self.spos, tuple_types)

    def eval(self):
        pass


class OptionalTypeExpr(TypeExpr):
    """
    Expression representing a Saturn optional type.\n
    ?typeexpr
    """
    def __init__(self, builder, module, package, spos, typeexpr):
        super().__init__(builder, module, package, spos, None)
        self.typeexpr = typeexpr
        self.base = None
        self.type = None
        self.base_type = self.type
        self.quals = []

    def get_base_type(self):
        return self.typeexpr.get_base_type()

    def replace_base_type(self, new_type_expr):
        return OptionalTypeExpr(self.builder, self.module, self.package, self.spos,
                                new_type_expr)

    def copy(self):
        return OptionalTypeExpr(self.builder, self.module, self.package, self.spos, self.typeexpr.copy())

    def get_type(self):
        if self.base is None:
            self.base = self.typeexpr.get_type()
        if self.type is None:
            self.type = make_optional_type(self.base)
        return self.type

    def eval(self):
        pass


class FuncTypeExpr(TypeExpr):
    """
    Expression representing a Saturn function type.\n
    fn(argtypeexprs...) rettypeexpr
    """
    def __init__(self, builder, module, package, spos, argtypeexprs, rettypeexpr):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.args = argtypeexprs
        # for ty in self.args:
        #     lname = ty.lvalue.name
        #     if lname not in types.keys():
        #         #print(*types.keys())
        #         raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
        #             self.module.filestack[self.module.filestack_idx],
        #             self.spos.lineno,
        #             self.spos.colno,
        #             lname
        #         ))
        self.rtype = rettypeexpr
        fnty = ir.FunctionType(self.rtype.get_ir_type(), [ty.get_ir_type() for ty in self.args])
        self.type = FuncType("", fnty, self.rtype.get_type(), [ty.get_type() for ty in self.args])
        self.base_type = self.type
        self.quals = []

    def eval(self):
        pass


class TypeDecl(ASTNode):
    """
    A type declaration.\n
    type lvalue : ltype;
    """
    def __init__(self, builder, module, package, spos, lvalue, ltype):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.ltype = ltype
        self.package.add_symbol(self.lvalue.get_name(), self.ltype.get_type())
        self.type = None
        self.visibility = Visibility.DEFAULT
        self.attribute_list = None

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def get_type(self):
        if self.type is None:
            name = self.lvalue.get_name()
            dty: Type = self.ltype.get_type()
            ty = Type(name, dty.tclass, dty.irtype, dty.qualifiers, dty.traits)
            ty.visibility = self.visibility
            self.type = self.package.add_symbol(name, ty)
        return self.type

    def eval(self):
        pass


def calc_sizeof_struct(builder, module, stype):
    int32 = ir.IntType(32)
    stypeptr = stype.get_ir_type().as_pointer()
    null = stypeptr('zeroinitializer')
    size = ir.Constant(int32, null.gep([ir.Constant(ir.IntType(32), 1)]).ptrtoint(int32))
    return size


class StructField(ASTNode):
    def __init__(self, builder, module, package, spos, name, ftype, qualifiers=None, initvalue=None):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.ftype = ftype
        self.type = None
        self.qualifiers = [] if qualifiers is None else qualifiers
        self.initvalue = initvalue

    def get_type(self):
        if self.type is None:
            self.type = self.ftype.get_type()
        return self.type


class StructDeclBody(ASTNode):
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.fields = []

    def get_ir_types(self):
        ir_types = []
        for f in self.fields:
            ir_types.append(f.ftype.get_type().get_ir_type())
        return ir_types

    def get_fields(self):
        return self.fields

    def add(self, field):
        self.fields.append(field)


class StructDecl(ASTNode):
    """
    A struct declaration expression.\n
    type lvalue : struct { body }
    """
    def __init__(self, builder, module, package, spos, lvalue, body, decl_mode,
                 visibility=Visibility.PUBLIC,
                 attribute_list=None):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.body = body
        self.ctor = None
        self.decl_mode = decl_mode
        self.visibility = visibility
        self.attribute_list = attribute_list
        name = self.lvalue.get_name()
        self.symbol = StructType(name, self.module.context.get_identified_type(name), [])
        self.package.add_symbol(name, self.symbol)
        if self.body is not None:
            for fld in self.body.get_fields():
                self.symbol.add_field(fld.name.value, fld.ftype.get_type(), fld.initvalue, fld.qualifiers)

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def generate_symbol(self):
        name = self.lvalue.get_name()
        if self.module.context.get_identified_type(name).is_opaque and self.body is not None:
            idstruct = self.module.context.get_identified_type(name)
            idstruct.set_body(*self.body.get_ir_types())
            self.symbol.irtype = idstruct
            for fld in self.body.get_fields():
                self.symbol.add_field(fld.name.value, fld.get_type(), fld.initvalue, fld.qualifiers)

    def eval(self):
        name = self.lvalue.get_name()
        initfs = self.symbol.get_fields_with_init()
        if len(initfs) > 0:
            push_new_scope(self.builder)
            structty = self.symbol
            structptr = structty.irtype.as_pointer()
            fnty = ir.FunctionType(ir.VoidType(), [structptr])
            fn = ir.Function(self.module, fnty, self.lvalue.get_name() + '.new')
            #fn.attributes.add("alwaysinline")
            self.ctor = fn
            structty.add_ctor(fn)
            #self.module.sfunctys[self.name.value] = sfnty
            if not self.decl_mode:
                fn.args = (ir.Argument(fn, structptr, name='this'),)
                thisptr = fn.args[0]
                block = fn.append_basic_block("entry")
                self.builder.position_at_start(block)
                for fld in initfs:
                    i = structty.get_field_index(fld.name)
                    if i == -1:
                        lineno = self.getsourcepos().lineno
                        colno = self.getsourcepos().colno
                        throw_saturn_error(self.builder, self.module, lineno, colno,
                                           f"Cannot find field '{fld.name}' in struct '{structty.name}'"
                                           )
                    gep = self.builder.gep(thisptr, [
                        ir.Constant(ir.IntType(32), 0),
                        ir.Constant(ir.IntType(32), i)
                    ])
                    if fld.get_ir_value(self.module).constant == 'null':
                        self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
                    else:
                        self.builder.store(fld.irvalue, gep)
                self.builder.ret_void()
            pop_inner_scope()


class StructGenericDecl(ASTNode):
    """
    A generic struct declaration expression.\n
    type<[type_decl_list]> lvalue : struct { body }
    """
    def __init__(self, builder, module, package, spos, lvalue, type_decl_list, body, decl_mode,
                 visibility=Visibility.PUBLIC,
                 attribute_list=None):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.body = body
        self.ctor = None
        self.decl_mode = decl_mode
        self.visibility = visibility
        self.attribute_list = attribute_list
        name = self.lvalue.get_name()
        types[name] = GenericType(name, StructType(self.lvalue.name, None, []), type_decl_list)
        self.package.add_symbol(name, types[name])
        self.symbol = types[name]
        if self.body is not None:
            for fld in self.body.get_fields():
                self.symbol.base.add_field(fld.name.value, fld.ftype, fld.initvalue, fld.qualifiers)

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def generate_symbol(self):
        pass

    def eval(self):
        pass


class EnumBody(ASTNode):
    """
    Enumeration type body.
    """
    def __init__(self, builder, module, package, spos):
        super().__init__(builder, module, package, spos)
        self.values = {}
        self.current_value = 0

    def has_value(self, value=None):
        if value is None:
            val = self.current_value
        else:
            val = value.consteval()
        return val in self.values

    def add_value(self, name, value=None):
        if value is None:
            val = self.current_value
        else:
            if not value.is_constexpr:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Enum value for {name.name} cannot be computed at compile time.")
            val = value.consteval()
        self.values[val] = name.name
        self.current_value = val + 1


class EnumDecl(ASTNode):
    """
    A struct declaration expression.\n
    type lvalue : enum { body }\n
    type lvalue : enum(value_type) { body }
    """
    def __init__(self, builder, module, package, spos, lvalue, body,
                 value_type=None, decl_mode=False,
                 visibility=Visibility.PUBLIC,
                 attribute_list=None):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.body = body
        if value_type is None:
            value_type = TypeExpr(self.builder, self.module, self.package, self.spos,
                                  LValue(self.builder, self.module, self.package, self.spos, 'int'))
        self.value_type = value_type
        self.decl_mode = decl_mode
        self.visibility = visibility
        self.attribute_list = attribute_list
        name = self.lvalue.get_name()
        types[name] = EnumType(name, self.value_type.get_type())
        self.package.add_symbol(name, types[name])
        self.symbol = types[name]
        if self.body is not None:
            for value, el in self.body.values.items():
                types[name].add_value(el, value)

    def add_attribute_list(self, attr_list: AttributeList):
        self.attribute_list = attr_list

    def add_visibility(self, visibility_decl):
        tt = visibility_decl.gettokentype()
        if tt == 'TPRIV':
            visibility = Visibility.PRIVATE
        elif tt == 'TPUB':
            visibility = Visibility.PUBLIC
        else:
            visibility = Visibility.DEFAULT
        self.visibility = visibility

    def generate_symbol(self):
        name = self.lvalue.get_name()

    def eval(self):
        name = self.lvalue.get_name()


class GenericTypeArg(ASTNode):
    """
    Type argument for a generic type/function/value.
    type name\n
    type name = default_lvalue\n
    type name where where_expr\n
    type name where where_expr = lvalue\n
    """
    def __init__(self, builder, module, package, spos, name, default_lvalue=None, where_expr=None):
        super().__init__(builder, module, package, spos)
        self.name = name.value
        self.default_lvalue = default_lvalue
        self.where_expr = where_expr

    def has_default_value(self):
        return self.default_lvalue is not None


class FuncCall(Expr):
    """
    Function call expression.\n
    lvalue(args)
    """
    def __init__(self, builder, module, package, spos, lvalue, args):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.args = args
        self.is_constexpr = False

    def get_type(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            if name not in self.module.sglobals:
                symbol = self.package.lookup_symbol(name)
                if symbol is None:
                    lineno = self.getsourcepos().lineno
                    colno = self.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno,
                                       f"Cannot find lvalue {self.lvalue.get_name()}.")
                if isinstance(symbol, Func):
                    sfn = symbol
                    aargs = []
                    for arg in self.args:
                        if arg.get_type().is_reference():
                            aargs.append(arg.get_type())
                        else:
                            aargs.append(arg.get_type())
                    match = sfn.search_overload(aargs)
                    if not match:
                        lineno = self.getsourcepos().lineno
                        colno = self.getsourcepos().colno
                        throw_saturn_error(self.builder, self.module, lineno, colno,
                                           f"Cannot find overload for function {self.lvalue.get_name()} "
                                           f"with argument types ({print_types(aargs)}).")
                    return match.overload.rtype
                #  return self.module.sfuncs[name].rtype
            return self.module.sglobals[name].rtype
        return ptr.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        sfn = None
        if ptr is None:
            ptr = self.package.lookup_symbol(name)
            if ptr is None:
                lineno = self.getsourcepos().lineno
                colno = self.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno,
                                   f"Cannot find lvalue {self.lvalue.get_name()}.")
            if isinstance(ptr, Func):
                sfn = ptr
                aargs = []
                for arg in self.args:
                    if arg.get_type().is_reference():
                        aargs.append(arg.get_type())
                    else:
                        aargs.append(arg.get_type())
                ovrld = sfn.get_overload(aargs)
                if not ovrld:
                    match = sfn.search_overload(aargs)
                    if not match:
                        lineno = self.getsourcepos().lineno
                        colno = self.getsourcepos().colno
                        throw_saturn_error(self.builder, self.module, lineno, colno,
                                           f"Cannot find overload for function {self.lvalue.get_name()} "
                                           f"with argument types ({print_types(aargs)}).")
                    args = []
                    for arg in enumerate(self.args):
                        if arg[0] in match.implicit_conversions:
                            args.append(cast_to(self.builder, self.module, self.package, arg[1], match.implicit_conversions[arg[0]]))
                        else:
                            args.append(arg[1].eval())
                    if match.overload.default_args:
                        required_count = len(match.overload.atypes) - len(match.overload.default_args)
                        if required_count <= len(args):
                            start = len(args) - required_count
                            for arg in match.overload.default_args[start:]:
                                args.append(arg.default_value.eval())
                    return self.builder.call(match.overload.fn, args, self.lvalue.get_name())
                # print("Overload:", ovrld.module.name, name, self.module.name, (ovrld.module.name == self.module.name))
                try:
                    self.module.get_global(ovrld.name)
                except KeyError:
                    ovrld = ir.Function(self.module,
                                        ir.FunctionType(sfn.rtype.get_ir_type(),
                                                        [aarg.get_ir_type() for aarg in aargs]),
                                        mangle_name(name, aargs))
                    # lineno = self.getsourcepos().lineno
                    # colno = self.getsourcepos().colno
                    # throw_saturn_error(self.builder, self.module, lineno, colno,
                    #                    "Function %s not defined in current module." % (
                    #                    self.lvalue.get_name())
                    #                    )
                args = [arg.eval() for arg in self.args]
                rty = sfn.rtype
                if rty.is_struct() and rty.is_value():
                    irty = rty.get_ir_type()
                    with self.builder.goto_entry_block():
                        self.builder.position_at_start(self.builder.block)
                        ptr = self.builder.alloca(irty, name='sret')
                    args.append(ptr)
                    call = self.builder.call(ovrld, args, self.lvalue.get_name())
                    return self.builder.load(ptr)
                return self.builder.call(ovrld, args, self.lvalue.get_name())
            #ptr = self.module.sglobals[name]
        args = [arg.eval() for arg in self.args]
        fn = self.builder.load(ptr.irvalue)
        return self.builder.call(fn, args)
        #return self.builder.call(self.module.get_global(self.lvalue.get_name()), args, self.lvalue.get_name())


class LambdaCall(Expr):
    """
    Lambda expression call expression.\n
    lambda_expr(args)
    """
    def __init__(self, builder, module, package, spos, lambda_, args):
        super().__init__(builder, module, package, spos)
        self.lambda_ = lambda_
        self.args = args
        self.is_constexpr = False

    def get_type(self):
        return self.lambda_.rtype

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        eval_args = [arg.eval() for arg in self.args]
        return self.builder.call(self.lambda_.eval(), eval_args)


class MethodCall(Expr):
    """
    Method call expression.\n
    callee.lvalue(args)
    """
    def __init__(self, builder, module, package, spos, callee, lvalue, args):
        super().__init__(builder, module, package, spos)
        self.callee = callee
        self.lvalue = lvalue
        self.args = args

    def get_type(self):
        # name = self.callee.get_type().name + '.' + self.lvalue.get_name()
        name = self.callee.get_type().get_base_type().get_full_name() + '::' + self.lvalue.get_name()
        # sfn = self.module.sfuncs[name]
        sfn = self.package.lookup_symbol(name)
        return sfn.rtype

    def get_ir_type(self):
        return self.get_type().get_ir_type()
        #return self.module.get_global(self.callee.get_type().name + '.' + self.lvalue.get_name()).ftype.return_type

    def eval(self):
        name = self.callee.get_type().get_base_type().get_full_name() + '::' + self.lvalue.get_name()
        # sfn = self.module.sfuncs[name]
        sfn = self.package.lookup_symbol(name.strip(f'{self.package.name}::'))
        if not sfn:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot find method {name} in package {self.package.name}."
                               )
        # sfn = self.module.sfuncs[name]
        #print(name, self.module.sfuncs[name], sfn.overloads)
        sargs = [arg for arg in self.args]
        if self.callee.get_type().is_value():
            sargs.insert(0, AddressOf(self.builder, self.module, self.package, self.spos, self.callee))
        else:
            sargs.insert(0, self.callee)
        aargs = [arg.get_type() for arg in sargs]
        ovrld = sfn.search_overload(aargs)
        if not ovrld:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot find overload for function %s with argument types (%s)." % (self.lvalue.get_name(), print_types(aargs))
            )
        args = [arg.eval() for arg in sargs]
        fn = ovrld.overload.fn
        try:
            self.module.get_global(fn.name)
        except KeyError:
            fn = ir.Function(self.module,
                             fn.ftype,
                             fn.name)
        return self.builder.call(fn, args, name)


class Statement(ASTNode):
    def __init__(self, builder, module, package, spos, value):
        super().__init__(builder, module, package, spos)
        self.value = value

    def getsourcepos(self):
        return self.spos

    def eval(self):
        pass


class ReturnStatement(Statement):
    """
    Return statement.\n
    return value;
    """
    def eval(self):
        ret_block = self.builder.append_basic_block('ret')
        with self.builder.goto_block(ret_block):
            eval_dtor_scope()
            eval_defer_scope()
            if self.value is not None:
                if self.builder.ret_dest is not None:
                    self.builder.store(self.value.eval(), self.builder.ret_dest)
                    self.builder.ret_void()
                else:
                    self.builder.ret(self.value.eval())
            else:
                self.builder.ret_void()
        self.builder.branch(ret_block)
        self.builder.goto_block(ret_block)
        self.builder.position_at_start(ret_block)


class FallthroughStatement(Statement):
    """
    Fallthrough statement.\n
    fallthrough;
    """
    def eval(self):
        pass


class BreakStatement(Statement):
    """
    Break statement.\n
    break;
    """
    def eval(self):
        self.builder.branch(get_break_dest())


class ContinueStatement(Statement):
    """
    Continue statement.\n
    continue;
    """
    def eval(self):
        self.builder.branch(get_continue_dest())


class DeferStatement(Statement):
    """
    Defer statement.\n
    defer stmt;\n
    defer { block }
    """
    def __init__(self, builder, module, package, spos, stmt):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.stmt = stmt

    def eval(self):
        """TODO: Actually implement defer in a non intrusive way."""
        push_defer(self.stmt)
        #self.builder.defer.insert(0, self.stmt)
        pass


class IfStatement(ASTNode):
    """
    If statement.\n
    if boolexpr { then }\n
    if boolexpr { then } else if boolexpr { elif } ... else { el }\n
    if boolexpr { then } else { el }
    """
    def __init__(self, builder, module, package, spos, boolexpr, then, elseif=None, el=None):
        """TODO: Implement else-if"""
        super().__init__(builder, module, package, spos)
        if elseif is None:
            elseif = []
        self.boolexpr = boolexpr
        self.then = then
        self.elseif = elseif
        self.el = el

    def add_elseif(self, cond, block):
        self.elseif.append((cond, block))

    def add_else(self, block):
        self.el = block

    def eval_elif(self, _index, _elif):
        boolexpr = _elif[0].eval()
        with self.builder.if_else(boolexpr) as (_then, _otherwise):
            with _then:
                _elif[1].eval()
            with _otherwise:
                if _index + 1 < len(self.elseif):
                    self.eval_elif(_index + 1, self.elseif[_index + 1])
                else:
                    self.el.eval()
                    return

    def eval(self):
        bexpr = self.boolexpr.eval()
        if self.el is None:
            with self.builder.if_then(bexpr):
                self.then.eval()
        else:
            with self.builder.if_else(bexpr) as (then, otherwise):
                with then:
                    self.then.eval()
                with otherwise:
                    if len(self.elseif) == 0:
                        self.el.eval()
                    else:
                        self.eval_elif(0, self.elseif[0])


class WhileStatement(ASTNode):
    """
    While loop statement.\n
    while boolexpr { loop }
    """
    def __init__(self, builder, module, package, spos, boolexpr, loop):
        super().__init__(builder, module, package, spos)
        self.boolexpr = boolexpr
        self.loop = loop

    def getsourcepos(self):
        return self.spos

    def eval(self):
        bexpr = self.boolexpr.eval()
        loop = self.builder.append_basic_block(self.module.get_unique_name("while"))
        after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        self.builder.cbranch(bexpr, loop, after)
        self.builder.goto_block(loop)
        self.builder.position_at_start(loop)
        self.loop.eval(break_dest=after, continue_dest=loop)
        bexpr2 = self.boolexpr.eval()
        self.builder.cbranch(bexpr2, loop, after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)


class DoWhileStatement(ASTNode):
    """
    Do-While loop statement.\n
    do { loop } while boolexpr;
    """
    def __init__(self, builder, module, package, spos, boolexpr, loop):
        super().__init__(builder, module, package, spos)
        self.boolexpr = boolexpr
        self.loop = loop

    def eval(self):
        loop = self.builder.append_basic_block(self.module.get_unique_name("while"))
        after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        self.builder.branch(loop)
        self.builder.goto_block(loop)
        self.builder.position_at_start(loop)
        self.loop.eval(break_dest=after, continue_dest=loop)
        bexpr = self.boolexpr.eval()
        self.builder.cbranch(bexpr, loop, after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)


class IterExpr(ASTNode):
    """
    An expression representing an iteration.\n
    a .. b \n
    a .. b : c \n
    a ... b \n
    a ... b : c
    """
    def __init__(self, builder, module, package, spos, a, b, c=None, inclusive=False):
        super().__init__(builder, module, package, spos)
        self.a = a
        self.b = b
        self.c = c
        self.inclusive = inclusive

    def get_type(self):
        return self.a.get_type()

    def get_ir_type(self):
        return self.a.get_type().irtype

    def eval_init(self):
        return self.a.eval()
    
    def eval_loop_check(self, loopvar):
        tocheck = self.b
        inc = self.get_inc_amount()
        if inc.constant > 0:
            if self.inclusive:
                return BooleanLte(self.builder, self.module, self.package, self.spos, loopvar, tocheck).eval()
            return BooleanLt(self.builder, self.module, self.package, self.spos, loopvar, tocheck).eval()
        else:
            if self.inclusive:
                return BooleanGte(self.builder, self.module, self.package, self.spos, loopvar, tocheck).eval()
            return BooleanGt(self.builder, self.module, self.package, self.spos, loopvar, tocheck).eval()

    def get_inc_amount(self):
        if self.c is None:
            return ir.Constant(self.get_ir_type(), 1)
        return self.c.eval()

    def eval_loop_inc(self, loopvar):
        if self.c is not None:
            AddAssignment(self.builder, self.module, self.package, self.spos, loopvar, self.c).eval()
        else:
            ptr = loopvar.get_pointer()
            add = self.builder.add(self.builder.load(ptr.irvalue), ir.Constant(ir.IntType(32), 1))
            self.builder.store(add, ptr.irvalue)


class LValueIterator(ASTNode):
    def __init__(self, builder, module, package, spos, lvalue):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.start = ElementOf(self.builder, self.module, self.package, self.spos, self.lvalue,
                               Integer(self.builder, self.module, self.package, self.spos, '0'))
        self.end = ElementOf(self.builder, self.module, self.package, self.spos, self.lvalue,
                             Integer(self.builder, self.module, self.package, self.spos,
                                     str(self.lvalue.get_type().get_array_count())))

    def get_type(self):
        ty = self.lvalue.get_type()
        return self.lvalue.get_type().get_element_of().get_pointer_to()

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval_init(self):
        return self.start.get_pointer().irvalue

    def eval_loop_check(self, loopvar):
        tocheck = AddressOf(self.builder, self.module, self.package, self.spos, self.end)
        return BooleanLt(self.builder, self.module, self.package, self.spos, loopvar, tocheck).eval()

    def get_inc_amount(self):
        return ir.Constant(self.get_ir_type(), 1)

    def eval_loop_inc(self, loopvar, valuevar):
        ptr = loopvar.get_pointer()
        ld = self.builder.load(ptr.irvalue)
        gep = self.builder.gep(ld, [ir.Constant(ir.IntType(32), 1)])
        self.builder.store(gep, ptr.irvalue)
        ptr = valuevar.get_pointer()
        self.builder.store(self.builder.load(gep), ptr.irvalue)


class ForStatement(ASTNode):
    """
    For loop statement.\n
    for it in itexpr { loop }\n
    """
    def __init__(self, builder, module, package, spos, it, itexpr, loop):
        super().__init__(builder, module, package, spos)
        self.it = it
        self.itexpr = itexpr
        self.loop = loop

    def eval(self):
        if not isinstance(self.itexpr, IterExpr):
            self.itexpr = LValueIterator(self.builder, self.module, self.package, self.itexpr.spos, self.itexpr)
        init = self.builder.append_basic_block(self.module.get_unique_name("for.init"))
        self.builder.branch(init)
        self.builder.goto_block(init)
        self.builder.position_at_start(init)
        push_new_scope(self.builder)
        if not isinstance(self.itexpr, IterExpr):
            name = self.it.get_name() + '.ptr'
            ty = self.itexpr.get_type()
            ptr = Value(name, ty, self.builder.alloca(ty.get_ir_type(), name=name))
            add_new_local(name, ptr)
            name = self.it.get_name()
            value_ty = self.itexpr.get_type().get_dereference_of()
            val_ptr = Value(name, value_ty, self.builder.alloca(value_ty.get_ir_type(), name=name))
            add_new_local(name, val_ptr)
        else:
            name = self.it.get_name()
            ty = self.itexpr.get_type()
            ptr = Value(name, ty, self.builder.alloca(ty.get_ir_type(), name=name), qualifiers=['mut'])
            add_new_local(name, ptr)
        init_val = self.itexpr.eval_init()
        self.builder.store(init_val, ptr.irvalue)
        if not isinstance(self.itexpr, IterExpr):
            self.builder.store(self.builder.load(init_val), val_ptr.irvalue)
        check = self.builder.append_basic_block(self.module.get_unique_name("for.check"))
        loop = self.builder.append_basic_block(self.module.get_unique_name("for.loop"))
        inc = self.builder.append_basic_block(self.module.get_unique_name("for.inc"))
        after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        self.builder.branch(check)
        self.builder.goto_block(check)
        self.builder.position_at_start(check)
        if isinstance(self.itexpr, IterExpr):
            checkval = self.itexpr.eval_loop_check(self.it)
        else:
            checkval = self.itexpr.eval_loop_check(LValue(self.builder, self.module, self.package, self.itexpr.spos,
                                                          self.it.get_name() + '.ptr'))
        self.builder.cbranch(checkval, loop, after)
        self.builder.goto_block(loop)
        self.builder.position_at_start(loop)
        self.loop.eval(continue_dest=inc, break_dest=after)
        self.builder.branch(inc)
        self.builder.goto_block(inc)
        self.builder.position_at_start(inc)
        if isinstance(self.itexpr, IterExpr):
            self.itexpr.eval_loop_inc(self.it)
        else:
            self.itexpr.eval_loop_inc(LValue(self.builder, self.module, self.package, self.itexpr.spos,
                                             self.it.get_name() + '.ptr'), self.it)
        self.builder.branch(check)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)
        pop_inner_scope()


class SwitchCase(ASTNode):
    """
    Switch statement case
    case expr: stmts
    """
    def __init__(self, builder, module, package, spos, expr, stmts=None):
        super().__init__(builder, module, package, spos)
        if stmts is None:
            stmts = []
        self.expr = expr
        self.stmts = stmts

    def add_stmt(self, stmt):
        self.stmts.append(stmt)

    def eval(self):
        for stmt in self.stmts:
            stmt.eval()


class SwitchDefaultCase(SwitchCase):
    """
    Switch statement case
    default: stmts
    """
    def __init__(self, builder, module, package, spos, stmts=None):
        if stmts is None:
            stmts = []
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.stmts = stmts


class SwitchBody(ASTNode):
    def __init__(self, builder, module, package, spos, cases=None, default_case=None):
        super().__init__(builder, module, package, spos)
        if cases is None:
            cases = []
        self.cases = cases
        self.default_case = default_case

    def add_case(self, case):
        self.cases.append(case)

    def set_default(self, case):
        self.default_case = case


class SwitchStatement(ASTNode):
    """
    While loop statement.\n
    switch expr { case_stmt ... default_case_stmt }
    """
    def __init__(self, builder, module, package, spos, expr, body=None):
        super().__init__(builder, module, package, spos)
        self.expr = expr
        self.body = body

    def eval(self):
        sexpr = self.expr.eval()
        after = None
        switch = None
        default = None
        if self.body.default_case is not None:
            default = self.builder.append_basic_block(self.module.get_unique_name("switch.default"))
            after = self.builder.append_basic_block(self.module.get_unique_name("switch.after"))
            switch = self.builder.switch(sexpr, default)
        else:
            after = self.builder.append_basic_block(self.module.get_unique_name("switch.after"))
            switch = self.builder.switch(sexpr, after)
        prev_block = None
        prev_case = None
        set_break_dest(after)
        for case in self.body.cases:
            case_expr = case.expr.eval()
            case_block = self.builder.append_basic_block(self.module.get_unique_name("switch.case"))
            switch.add_case(case_expr, case_block)
            if prev_block is not None and not prev_block.is_terminated:
                if len(prev_case.stmts) > 0 and isinstance(prev_case.stmts[-1], FallthroughStatement):
                    self.builder.branch(case_block)
                else:
                    self.builder.branch(after)
            self.builder.goto_block(case_block)
            self.builder.position_at_start(case_block)
            case.eval()
            prev_block = case_block
            prev_case = case
        if prev_block is not None and not prev_block.is_terminated:
            if len(prev_case.stmts) > 0 and isinstance(prev_case.stmts[-1], FallthroughStatement):
                if default is not None:
                    self.builder.branch(default)
                else:
                    self.builder.branch(after)
            else:
                self.builder.branch(after)
        if default is not None:
            self.builder.goto_block(default)
            self.builder.position_at_start(default)
            self.body.default_case.eval()
            if not default.is_terminated:
                self.builder.branch(after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)


class Print(ASTNode):
    def __init__(self, builder, module, package, spos, value):
        super().__init__(builder, module, package, spos)
        self.value = value

    def eval(self):
        # Call Print Function
        args = [value.eval() for value in self.value]
        self.builder.call(self.module.get_global("printf"), args)


def pass_var_by_ref(package, lvalue, spec, scope: Scope):
    var = check_name_in_scope(lvalue.get_name())
    if not var:
        var = package.lookup_symbol(lvalue.get_name())
        if not var:
            pass
    if isinstance(var, Value):
        # TODO: Add check to make sure immutable variables aren't passed as mutable.
        scope[lvalue.get_name()] = Value(var.name, var.type, var.irvalue, spec, var.objtype)


def pass_var_by_value(builder, module, lvalue, spec, scope: Scope):
    name = Token('IDENT', lvalue.get_name())
    spos = lvalue.getsourcepos()
    initval = lvalue
    val = initval.eval()
    vartype = initval.get_type()

    if spec is not None:
        quals = spec.copy()
    else:
        quals = initval.get_pointer().qualifiers

    if vartype.is_void():
        lineno = initval.getsourcepos().lineno
        colno = initval.getsourcepos().colno
        throw_saturn_error(builder, module, lineno, colno,
                           "Can't create variable of void type.")
    if hasattr(initval, 'get_stack_value'):
        ptr = initval.get_stack_value(name.value)
    else:
        with builder.goto_entry_block():
            builder.position_at_start(builder.block)
            ptr = Value(name.value, vartype, builder.alloca(vartype.get_ir_type(), name=name.value),
                        qualifiers=quals)

    scope[name.value] = ptr
    dbglv = module.add_debug_info("DILocalVariable", {
        "name": name.value,
        "file": module.di_file,
        "line": spos.lineno,
        "scope": builder.dbgsub
    })
    dbgexpr = module.add_debug_info("DIExpression", {})
    builder.debug_metadata = module.add_debug_info("DILocation", {
        "line": spos.lineno,
        "column": spos.lineno,
        "scope": builder.dbgsub
    })
    builder.call(
        module.get_global("llvm.dbg.addr"),
        [ptr.irvalue, dbglv, dbgexpr]
    )
    builder.debug_metadata = None
    if initval is not None:
        if ptr.is_atomic():
            builder.store_atomic(val, ptr.irvalue, 'seq_cst', 4)
            return ptr
        builder.store(val, ptr.irvalue)
    return ptr


def pass_capture_to_scope(builder, module, package, capture: CaptureExpr, scope: Scope):
    global SCOPE
    if capture.capture_all_by_value:
        for i in range(len(SCOPE)):
            cscope = SCOPE[-1 - i]
            for name, ptr in cscope.vars.items():
                lvalue = LValue(builder, module, package, capture.spos, name)
                pass_var_by_value(builder, module, lvalue, None, scope)
            if cscope.is_guarded:
                break
    elif capture.capture_all_by_ref:
        for i in range(len(SCOPE)):
            cscope = SCOPE[-1 - i]
            for name, ptr in cscope.vars.items():
                lvalue = LValue(builder, module, package, capture.spos, name)
                pass_var_by_ref(package, lvalue, lvalue.get_pointer().qualifiers, scope)
            if cscope.is_guarded:
                break
    for lvalue, spec, pass_ty in capture.capture_list.values():
        if pass_ty == 'ref':
            pass_var_by_ref(package, lvalue, spec, scope)
        else:
            pass_var_by_value(builder, module, lvalue, spec, scope)
    return scope
