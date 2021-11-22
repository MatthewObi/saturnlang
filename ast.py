from llvmlite import ir
from rply import Token
from typesys import TupleType, Type, make_tuple_type, types, FuncType, StructType, Value, mangle_name, print_types, \
    Func, make_optional_type
from serror import throw_saturn_error
from package import Visibility, LinkageType, Package

SCOPE = []
DECL_SCOPE = []
GLOBALS = {}


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
                if var.type.has_dtor():
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


def check_name_in_scope(name):
    global SCOPE
    global GLOBALS
    for i in range(len(SCOPE)):
        s = SCOPE[-1-i]
        if name in s.keys():
            return s[name]
    if name in GLOBALS.keys():
        return GLOBALS[name]
    return None


def add_new_local(name, ptr):
    global SCOPE
    SCOPE[-1][name] = ptr


def push_new_scope(builder):
    global SCOPE
    SCOPE.append(Scope(builder))


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
    def __init__(self, builder, module, package, spos, value):
        super().__init__(builder, module, package, spos)
        self.value = value
        self.type = self.get_type()
        self.is_constexpr = True


class Integer(Number):
    """
    A 32-bit integer constant. (int)
    """
    def get_type(self):
        return types['int']

    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value))
        return i

    def consteval(self):
        return int(self.value)


class UInteger(Number):
    """
    A 32-bit unsigned integer constant. (uint)
    """
    def get_type(self):
        return types['uint']

    def eval(self):
        val = self.value.strip('u')
        i = ir.Constant(self.type.irtype, int(val))
        return i

    def consteval(self):
        return int(self.value.strip('u'))


class Integer64(Number):
    """
    A 64-bit integer constant. (int64)
    """
    def get_type(self):
        return types['int64']

    def eval(self):
        val = self.value.strip('l')
        i = ir.Constant(self.type.irtype, int(val))
        return i

    def consteval(self):
        return int(self.value.strip('l'))


class UInteger64(Number):
    """
    A 64-bit unsigned integer constant. (uint64)
    """
    def get_type(self):
        return types['uint64']

    def eval(self):
        val = self.value.strip('ul')
        i = ir.Constant(self.type.irtype, int(val))
        return i
    
    def consteval(self):
        return int(self.value.strip('ul'))


class Byte(Number):
    """
    An 8-bit unsigned integer constant. (byte)
    """
    def get_type(self):
        return types['byte']
    
    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value))
        return i

    def consteval(self):
        return int(self.value.strip('ul'))


class Float(Number):
    """
    A single-precision float constant. (float32)
    """
    def get_type(self):
        return types['float32']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value))
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
        self.value = value
        self.raw_value = str(value).strip("\"") + '\0'
        self.type = self.get_type()

    def get_type(self):
        return types['cstring']

    def get_reference(self):
        return self.value

    def eval(self):
        fmt = self.raw_value
        fmt = fmt.replace('\\n', '\n')
        c_fmt = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)),
                            bytearray(fmt.encode("utf8")))
        global_fmt = ir.GlobalVariable(self.module, c_fmt.type, name=self.module.get_unique_name("str"))
        global_fmt.linkage = 'internal'
        global_fmt.global_constant = True
        global_fmt.initializer = c_fmt
        self.value = self.builder.bitcast(global_fmt, self.type.irtype)
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


class ArrayLiteralBody:
    def __init__(self, builder, module, package, spos):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.values = []

    def add_element(self, expr):
        self.values.append( expr )


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
        for val in self.body.values:
            vals.append(val.eval())
        c = ir.Constant(self.get_type().irtype, vals)
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
        self.type = self.get_type()

    def get_type(self):
        return self.stype.get_type()

    def eval(self):
        name = self.module.get_unique_name("_unnamed_struct_literal")
        with self.builder.goto_entry_block():
            self.builder.position_at_start(self.builder.block)
            ptr = self.builder.alloca(self.type.irtype, name=name)
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
                fnty = self.module.sfunctys[key]
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
                key = list(ptr.overloads.keys())[0]
                fn = ptr.overloads[key].fn
                begin = '_Z%d' % len(name)
                key = begin + name + key[3:]
                fnty = self.module.sfunctys[key]
                return Value('', fnty.get_pointer_to(), fn)
            # else:
            #    ptr = self.module.sglobals[name]
        if ptr.type.is_reference():
            i64 = ir.IntType(64)
            deref = self.builder.load(ptr.irvalue)
            v0 = self.builder.ptrtoint(deref, i64)
            v1 = self.builder.and_(v0, i64(-2))
            actualptr = self.builder.inttoptr(v1, self.get_ir_type())
            print(f"Reference: {actualptr}\nType:{ptr.type.type}")
            return Value(ptr.name, ptr.type.type, actualptr)
        return ptr
    
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
        if ptr.is_atomic():
            return self.builder.load_atomic(ptr.irvalue, 'seq_cst', 4)
        if self.get_type().is_reference():
            i64 = ir.IntType(64)
            deref = self.builder.load(ptr.irvalue)
            v0 = self.builder.ptrtoint(deref, i64)
            v1 = self.builder.and_(v0, i64(-2))
            actualptr = self.builder.inttoptr(v1, self.get_ir_type())
            return self.builder.load(actualptr)
        return self.builder.load(ptr.irvalue)


class LValueField(Expr):
    def __init__(self, builder, module, package, spos, lvalue, fname):
        super().__init__(builder, module, package, spos)
        self.fname = fname
        self.lvalue = lvalue
        self.is_constexpr = False
        self.is_deref = False

    def get_type(self):
        #print(type(self.lvalue.get_type()))
        stype = self.lvalue.get_type()
        return stype.get_field_type(stype.get_field_index(self.fname))

    def get_ir_type(self):
        irtype = self.lvalue.get_ir_type()
        stype = self.lvalue.get_type()
        findex = stype.get_field_index(self.fname)
        return irtype.gep(ir.Constant(ir.IntType(32), findex))

    def get_name(self):
        return self.lvalue.get_name()

    def get_pointer(self):
        stype = self.lvalue.get_type()
        ptr = self.lvalue.get_pointer()
        findex = stype.get_field_index(self.fname)
        if findex == -1:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot find field {self.fname} in struct {stype.name}."
                               )
        #print('%s: %d' % (self.fname, findex))
        gep = None
        if ptr.type.is_pointer():
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
        elif ptr.type.is_reference():
            ld = self.builder.load(ptr.irvalue)
            gep = self.builder.gep(ld, [
                ir.Constant(ir.IntType(32), findex)
            ])
        else:
            gep = self.builder.gep(ptr.irvalue, [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), findex)
            ])
        return Value(self.fname, stype.get_field_type(findex), gep, ptr.qualifiers)

    def eval(self):
        stype = self.lvalue.get_type()
        # if not stype.is_struct() or not stype.is_pointer():
        #     lineno = self.lvalue.getsourcepos().lineno
        #     colno = self.lvalue.getsourcepos().colno
        #     throw_saturn_error(self.builder, self.module, lineno, colno, 
        #         "Cannot use field operator on a non-struct type."
        #     )
        ptr = self.lvalue.get_pointer()
        findex = stype.get_field_index(self.fname)
        if findex == -1:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno,
                               f"Cannot find field {self.fname} in struct {stype.name}."
                               )
        if not ptr.type.is_pointer():
            gep = self.builder.gep(ptr.irvalue, [
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

    def get_type(self):
        return self.ctype.get_type()

    def eval(self):
        cast = None
        val = self.expr.eval()
        exprt = self.expr.get_type()
        if exprt.is_reference():
            exprt = exprt.type
        castt = self.get_type()
        if exprt.is_pointer():
            if castt.is_pointer():
                cast = self.builder.bitcast(val, castt.irtype)
            elif castt.is_integer():
                cast = self.builder.ptrtoint(val, castt.irtype)
            elif castt.is_bool():
                #lhs = self.builder.ptrtoint(val, ir.IntType(64))
                #rhs = self.builder.ptrtoint(ir.Constant(exprt.irtype, exprt.irtype.null), ir.IntType(64))
                cast = self.builder.icmp_unsigned('!=', val, ir.Constant(exprt.irtype, exprt.irtype.null))
        elif exprt.is_array():
            if castt.is_pointer():
                cast = self.builder.bitcast(val, castt.irtype)
        elif exprt.is_integer():
            if castt.is_pointer():
                cast = self.builder.inttoptr(val, castt.irtype)
            elif castt.is_integer():
                if castt.get_integer_bits() < exprt.get_integer_bits():
                    cast = self.builder.trunc(val, castt.irtype)
                elif castt.get_integer_bits() > exprt.get_integer_bits():
                    if castt.is_unsigned():
                        cast = self.builder.zext(val, castt.irtype)
                    else:
                        cast = self.builder.sext(val, castt.irtype)
                else:
                    cast = val
            elif castt.is_float():
                if exprt.is_unsigned():
                    cast = self.builder.uitofp(val, castt.irtype)
                else:
                    cast = self.builder.sitofp(val, castt.irtype)
            elif castt.is_bool():
                if exprt.is_unsigned():
                    cast = self.builder.icmp_unsigned('!=', val, ir.Constant(exprt.irtype, 0))
                elif exprt.is_integer():
                    cast = self.builder.icmp_signed('!=', val, ir.Constant(exprt.irtype, 0))
                elif exprt.is_float():
                    cast = self.builder.fcmp_ordered('!=', val, ir.Constant(exprt.irtype, 0.0))
                elif exprt.is_pointer():
                    null = exprt.irtype.null
                    cast = self.builder.icmp_signed('!=', val, null)
            else:
                lineno = self.expr.getsourcepos().lineno
                colno = self.expr.getsourcepos().colno
                throw_saturn_error(self.builder, self.module, lineno, colno, 
                    "Cannot cast from integer type to '%s'." % str(self.get_type())
                )
        else:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot cast expression of type '%s' to '%s'." % (str(exprt), str(castt))
            )
        return cast


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

    def get_type(self):
        if self.type is None:
            self.mtype = self.typeexpr.get_type()
            self.type = self.mtype.get_pointer_to()
        return self.type

    def get_ir_type(self):
        return self.get_type().get_ir_type()

    def eval(self):
        self.get_type()
        malloc_fn = self.module.aligned_malloc
        sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
        aligned_sizeof = self.builder.add(self.builder.and_(sizeof, ir.Constant(ir.IntType(32), 1)), sizeof)
        mallocptr = self.builder.call(malloc_fn, [ir.Constant(ir.IntType(32), 2), aligned_sizeof])
        self.builder.call(self.module.memset, [
            mallocptr,
            ir.Constant(ir.IntType(8), 0),
            aligned_sizeof,
            ir.Constant(ir.IntType(1), 0),
        ])
        bitcast = self.builder.bitcast(mallocptr, self.type.irtype)
        push_defer(DestroyExpr(self.builder, self.module, self.package, self.spos, bitcast, self.type))
        return bitcast


class DestroyExpr(Expr):
    """
    An expression for freeing memory from the heap.
    destroy lvalue;
    """
    def __init__(self, builder, module, package, spos, ptr, stype):
        super().__init__(builder, module, package, spos)
        self.type = stype
        self.ptr = ptr

    def get_type(self):
        return self.type

    def get_ir_type(self):
        return self.type.irtype

    def eval(self):
        bitcast = self.builder.bitcast(self.ptr, ir.IntType(8).as_pointer())
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
        self.get_type()
        malloc_fn = self.module.aligned_malloc
        sizeof = calc_sizeof_struct(self.builder, self.module, self.mtype)
        aligned_sizeof = self.builder.add(self.builder.and_(sizeof, ir.Constant(ir.IntType(32), 1)), sizeof)
        mallocptr = self.builder.call(malloc_fn, [ir.Constant(ir.IntType(32), 2), aligned_sizeof])
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
        if self.expr.get_type().is_integer():
            leftty = self.left.get_type()
            if leftty.is_pointer():
                gep = self.builder.gep(self.left.eval(), [
                    self.expr.eval()
                ], True)
                return Value(ptr.name, ptr.type.get_dereference_of(), gep, ptr.qualifiers)
            else:
                gep = self.builder.gep(ptr.irvalue, [
                    ir.Constant(ir.IntType(32), 0),
                    self.expr.eval()
                ], True)
                return Value(ptr.name, ptr.type.get_element_of(), gep, ptr.qualifiers)
            

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
        return ptr.irvalue


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
        if ty.is_integer():
            i = self.builder.add(self.left.eval(), self.right.eval())
        elif ty.is_float():
            i = self.builder.fadd(self.left.eval(), self.right.eval())
        else:
            lineno = self.spos.lineno
            colno = self.spos.colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Attempting to perform addition with two operands of incompatible types (%s and %s)." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
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
                "Attempting to perform multiplication with two operands of incompatible types (%s and %s)." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
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
            throw_saturn_error(self.builder, self.module, lineno, colno, "Attempting to perform division with two operands of incompatible types (%s and %s). Please cast one of the operands." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
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
            "Attempting to perform a binary and with at least one operand of a non-integer type (%s and %s)." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
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
            "Attempting to perform a binary or with at least one operand of a non-integer type (%s and %s)." % (
                str(self.left.get_type()),
                str(self.right.get_type())
            ))
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
        cmptysat = self.getcmptype()
        begin = self.builder.basic_block
        lt = self.builder.append_basic_block(self.module.get_unique_name("ship.less"))
        gt = self.builder.append_basic_block(self.module.get_unique_name("ship.greater"))
        after = self.builder.append_basic_block(self.module.get_unique_name("ship.after"))
        ltv = ir.Constant(ir.IntType(32), -1)
        eqv = ir.Constant(ir.IntType(32), 0)
        gtv = ir.Constant(ir.IntType(32), 1)
        if cmptysat.is_pointer():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
            return i
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('==', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        self.builder.cbranch(i, after, lt)
        self.builder.goto_block(lt)
        self.builder.position_at_start(lt)
        if isinstance(cmpty, ir.IntType):
            j = self.builder.icmp_signed('<', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            j = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        else:
            j = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        self.builder.cbranch(j, after, gt)
        self.builder.goto_block(gt)
        self.builder.position_at_start(gt)
        if isinstance(cmpty, ir.IntType):
            k = self.builder.icmp_signed('>', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            k = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
        else:
            k = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
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
        cmptysat = self.getcmptype()
        if cmptysat.is_pointer():
            i = self.builder.icmp_unsigned('==', self.lhs, self.rhs)
            return i
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('==', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
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
        cmptysat = self.getcmptype()
        if cmptysat.is_pointer():
            i = self.builder.icmp_unsigned('!=', self.lhs, self.rhs)
            return i
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('!=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('!=', self.lhs, self.rhs)
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
        cmptysat = self.getcmptype()
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('>', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
        return i

    def consteval(self):
        return self.left.consteval() > self.right.consteval()


class BooleanLt(BoolCmpOp):
    """
    Comparison less than '<' operator.\n
    left < right
    """
    def eval(self):
        cmptysat = self.getcmptype()
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('<', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
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
        cmptysat = self.getcmptype()
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('>=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('>=', self.lhs, self.rhs)
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
        cmptysat = self.getcmptype()
        cmpty = cmptysat.irtype
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('<=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('<=', self.lhs, self.rhs)
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
        if sptr.is_const() or sptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            if sptr.is_const():
                msg = 'const'
            if sptr.is_immut():
                msg = 'immut'
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to %s variable, %s." % (msg, sptr.name)
            )
        if sptr.is_readonly() and self.lvalue.is_deref:
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot write to readonly pointer variable, %s." % (sptr.name)
            )
        if stype.is_struct():
            if stype.has_operator('='):
                method = stype.operator['=']
                value = self.expr.eval()
                ovrld = method.get_overload([stype.get_pointer_to(), self.expr.get_type()])
                if not ovrld:
                    pass
                self.builder.call(ovrld, [ptr, value])
                return
        value = self.expr.eval()
        #print("(%s) => (%s)" % (value, ptr))
        if sptr.is_atomic():
            self.builder.store_atomic(value, ptr, 'seq_cst', 4)
            return
        if isinstance(self.expr, Null):
            self.builder.store(ir.Constant(ptr.type.pointee, 'null'), ptr)
            return
        # print(value, ptr)
        self.builder.store(value, ptr)


class AddAssignment(Assignment):
    """
    Add assignment statement to a defined variable.\n
    lvalue += expr; (lvalue = lvalue + expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.add(value, self.expr.eval())
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder.sub(value, self.expr.eval())
            self.builder.store(res, ptr.irvalue)
        else:
            self.builder.atomic_rmw('sub', ptr.irvalue, self.expr.eval(), 'seq_cst')


class MulAssignment(Assignment):
    """
    Multiply assignment statement to a defined variable.\n
    lvalue *= expr; (lvalue = lvalue * expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
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
                "Cannot do modulus assignment on variable, %s." % ptr.name
            )
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder._and(value, self.expr.eval())
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        if not ptr.is_atomic():
            value = self.builder.load(ptr.irvalue)
            res = self.builder._or(value, self.expr.eval())
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
        if ptr.is_const() or ptr.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
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
                stmt.generate_symbol(self.package)

    def eval(self):
        for stmt in self.stmts:
            stmt.eval()


class PackageDecl(ASTNode):
    def __init__(self, builder, module, package, spos, lvalue):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue

    def eval(self):
        self.builder.package = self.lvalue.get_name()


class ImportDecl(ASTNode):
    """
    A statement that reads and imports another package.
    """
    def __init__(self, builder, module, package, spos, lvalue, symbols_to_import=None, import_all=False):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.import_all = import_all
        if symbols_to_import is None:
            symbols_to_import = []
        self.symbols_to_import = symbols_to_import

    def eval(self):
        from sparser import Parser
        from lexer import Lexer
        from cachedmodule import CachedModule
        import os.path

        base_path = './packages/' + self.lvalue.get_name()
        symbols_path = base_path + '/symbols.json'
        if os.path.isfile(symbols_path):
            package = Package(self.lvalue.get_name())
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
                with open(path) as f:
                    text_input = f.read()

                cmod = CachedModule(path, text_input)
                self.package.cachedmods[path] = cmod

            cmod = self.package.cachedmods[path]

            lexer = Lexer().get_lexer()
            tokens = lexer.lex(cmod.text_input)

            self.builder.filestack.append(cmod.text_input)
            self.builder.filestack_idx += 1

            self.module.filestack.append(path)
            self.module.filestack_idx += 1

            package = self.package
            if not self.import_all:
                package = Package(self.lvalue.get_name())
                pg = Parser(self.module, self.builder, package)
                pg.parse()
            else:
                pg = Parser(self.module, self.builder, package)
                pg.parse()

            self.builder.filestack.pop(-1)
            self.builder.filestack_idx -= 1

            self.module.filestack.pop(-1)
            self.module.filestack_idx -= 1

            parser = pg.get_parser()
            parser.parse(tokens).eval()

            if not self.import_all:
                self.package.import_package(package)
                if len(self.symbols_to_import) > 0:
                    self.package.import_symbols_from_package(package, self.symbols_to_import)


class ImportDeclExtern(ASTNode):
    """
    A statement that reads and imports another package's declarations.
    """
    def __init__(self, builder, module, package, spos, lvalue):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        return

        from sparser import Parser
        from lexer import Lexer
        from cachedmodule import CachedModule

        path = './packages/' + self.lvalue.get_name() + '/main.sat'
        if path not in self.builder.cachedmods.keys():
            text_input = ""
            with open(path) as f:
                text_input = f.read()
            
            cmod = CachedModule(path, text_input)
            self.builder.cachedmods[path] = cmod
            
        cmod = self.builder.cachedmods[path]

        lexer = Lexer().get_lexer()
        tokens = lexer.lex(cmod.text_input)

        self.builder.filestack.append(cmod.text_input)
        self.builder.filestack_idx += 1

        self.module.filestack.append(path)
        self.module.filestack_idx += 1

        pg = Parser(self.module, self.builder, self.package, True)
        pg.parse()

        self.builder.filestack.pop(-1)
        self.builder.filestack_idx -= 1

        self.module.filestack.pop(-1)
        self.module.filestack_idx -= 1

        parser = pg.get_parser()
        parser.parse(tokens).eval()

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
        print("Including C file...")
        import cparser
        path = str(self.string.value).strip('"')
        cparser.parse_c_file(self.builder, self.module, self.package, path)

    def eval(self):
        """
        TODO: Add C parsing functionality.
        """
        pass
        

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


class CodeBlock(ASTNode):
    """
    A block of multiple statements with an enclosing scope.
    """
    def __init__(self, builder, module, package, spos, stmt):
        super().__init__(builder, module, package, spos)
        if stmt is not None:
            self.stmts = [stmt]
        else:
            self.stmts = []

    def add(self, stmt):
        self.stmts.append(stmt)

    def eval(self, builder=None):
        if builder is not None:
            self.builder = builder
        push_new_scope(self.builder)
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


class FuncArg(ASTNode):
    """
    An definition of a function parameter.\n
    name : rtype, 
    """
    def __init__(self, builder, module, package, spos, name, atype, qualifiers=None):
        super().__init__(builder, module, package, spos)
        if qualifiers is None:
            qualifiers = []
        self.name = name
        self.atype = atype
        self.type = None
        self.qualifiers = qualifiers.copy()
    
    def eval(self, func: ir.Function, decl=True):
        self.type = self.atype.get_type()
        self.type.irtype = self.type.get_ir_type()

        arg = ir.Argument(func, self.type.irtype, name=self.name.value)
        if 'sret' in self.qualifiers:
            arg.add_attribute('sret')
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
    fn name(decl_args): rtype { block }
    """
    def __init__(self, builder, module, package, spos, name, rtype, block, decl_args, var_arg=False,
                 visibility=Visibility.DEFAULT):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args
        self.var_arg = var_arg
        self.visibility = visibility

    def generate_symbol(self, package):
        if package.lookup_symbol(self.name.value) is None:
            rtype = self.rtype.get_type()
            if rtype.is_struct() and rtype.is_value():
                self.decl_args.add(FuncArg(
                    self.builder,
                    self.module,
                    self.package,
                    self.rtype.spos,
                    Token('IDENT', 'ret', self.spos),
                    rtype.get_pointer_to(), ['sret']))
            decltypes = self.decl_args.get_arg_decl_type_list()
            sargtypes = [decltype.get_type() for decltype in decltypes]
            argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]
            fnty = ir.FunctionType(rtype.get_ir_type(), argtypes, var_arg=self.var_arg)
            #print(f"fn {self.name.value} ({[str(stype) for stype in sargtypes]}): {str(rtype)};")
            # print("%s (%s)" % (self.name.value, fnty))
            sfnty = FuncType("", fnty, rtype, sargtypes)
            fname = self.name.value
            if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
                fname = mangle_name(self.name.value, sfnty.atypes)
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
            fn = ir.Function(self.module, fnty, fname)
            if self.name.value not in self.module.sfuncs:
                fn_symbol = package.add_symbol(self.name.value, Func(self.name.value, sfnty.rtype, visibility=self.visibility))
                fn_symbol.add_overload(sfnty.atypes, fn)
            else:
                symbol = package[self.name.value]
                symbol.add_overload(sfnty.atypes, fn)

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()

        if rtype.is_struct() and rtype.is_value():
            self.decl_args.add(FuncArg(
                self.builder,
                self.module,
                self.package,
                self.rtype.spos,
                Token('IDENT', 'ret', self.spos),
                PointerTypeExpr(self.builder,
                                self.module,
                                self.package,
                                self.rtype.spos,
                                self.rtype), ['sret']))
        rtype = self.rtype

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [argtype.get_ir_type() for argtype in sargtypes]

        fnty = ir.FunctionType(rtype.get_ir_type(), argtypes, var_arg=self.var_arg)
        #print(f"fn {self.name.value} ({[str(stype) for stype in sargtypes]}): {str(self.rtype.type)};")
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype.type, sargtypes)
        fname = self.name.value
        if not self.builder.c_decl and not (self.name.value == 'main' or self.name.value == '_entry'):
            fname = mangle_name(self.name.value, sfnty.atypes)
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
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn)
            else:
                self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn)
        #print("New function:", fname)
        sfnty.name = fname
        self.module.sfunctys[fname] = sfnty
        block = fn.append_basic_block("entry")
        self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
            "name":self.name.value, 
            "scope": self.module.di_file,
            "file": self.module.di_file,
            "line": self.spos.lineno,
            "unit": self.module.di_compile_unit,
            #"column": self.spos.colno,
            "isDefinition":True
        }, True)
        self.builder.position_at_start(block)
        fn.args = tuple(self.decl_args.get_arg_list(fn))
        self.block.eval()
        if not self.builder.block.is_terminated:
            #for stmt in self.builder.defer:
            #    stmt.eval()
            if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
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

    def getsourcepos(self):
        return self.spos

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [argtype.get_ir_type() for argtype in sargtypes]
        #print(self.name, rtype, *argtypes)

        fnty = ir.FunctionType(rtype.irtype, argtypes, var_arg=self.var_arg)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype, sargtypes)
        fname = self.name.value
        if not self.builder.c_decl:
            fname = mangle_name(self.name.value, sfnty.atypes)
        fn = ir.Function(self.module, fnty, fname)
        fn.args = tuple(self.decl_args.get_decl_arg_list(fn))
        #self.module.sfunctys[self.name.value] = sfnty
        if self.name.value not in self.module.sfuncs:
            self.module.sfuncs[self.name.value] = Func(self.name.value, sfnty.rtype)
            self.package.add_symbol(self.name.value, self.module.sfuncs[self.name.value])
            self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn)
        else:
            self.module.sfuncs[self.name.value].add_overload(sfnty.atypes, fn)
        pop_inner_scope()


class GlobalVarDecl(ASTNode):
    """
    A global variable declaration statement.\n
    name : vtype;\n
    name : vtype = initval;
    """
    def __init__(self, builder, module, package, spos, name, vtype, initval=None, spec='none',
                 visibility=Visibility.DEFAULT):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.vtype = vtype
        self.initval = initval
        self.spec = spec
        self.visibility = visibility

    def getsourcepos(self):
        return self.spos

    def generate_symbol(self):
        self.vtype.eval()
        vartype = self.vtype.get_type()
        return Value(self.name.value, vartype, None, objtype='global', visibility=self.visibility)

    def eval(self):
        self.vtype.eval()
        vartype = self.vtype.type
        #vartype = get_type_by_name(self.builder, self.module, str(self.vtype))
        gvar = ir.GlobalVariable(self.module, vartype.irtype, self.name.value)
        gvar.align = 4
        gvar.linkage = LinkageType.VALUE[self.visibility]

        if self.initval:
            gvar.initializer = self.initval.eval()
        
        ptr = Value(self.name.value, vartype, gvar, visibility=self.visibility)
        self.package.add_symbol(self.name.value, ptr)
        # add_new_global(self.name.value, ptr)
        return ptr


class MethodDecl(ASTNode):
    """
    A declaration and definition of a method.\n
    fn(*struct) name(decl_args): rtype { block }
    """
    def __init__(self, builder, module, package, spos, name, rtype, block, decl_args, struct):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args
        self.struct = struct
        thisarg = FuncArg(
            self.builder, self.module, self.package, self.struct.getsourcepos(), Token('IDENT', 'this'),
                TypeExpr(self.builder, self.module, self.package, self.struct.getsourcepos(), self.struct)
        )
        thisarg.atype = thisarg.atype.get_pointer_to()
        self.decl_args.prepend(thisarg)

    def eval(self):
        push_new_scope(self.builder)
        rtype = self.rtype.get_type()

        decltypes = self.decl_args.get_arg_decl_type_list()
        sargtypes = [decltype.get_type() for decltype in decltypes]
        argtypes = [sargtype.get_ir_type() for sargtype in sargtypes]

        fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", fnty, rtype, sargtypes)
        name = self.struct.get_name() + '.' + self.name.value
        fname = name
        if not self.builder.c_decl:
            fname = mangle_name(name, sfnty.atypes)
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
        fn = ir.Function(self.module, fnty, fname)
        #self.module.sfunctys[name] = sfnty
        if name not in self.module.sfuncs:
            self.module.sfuncs[name] = Func(name, sfnty.rtype)
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn)
        else:
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn)
        #print("New method:", fname)
        if self.name.value == 'new':
            types[self.struct.get_name()].add_ctor(self.module.sfuncs[name])
        elif self.name.value == 'delete':
            types[self.struct.get_name()].add_dtor(self.module.sfuncs[name])
        elif self.name.value == 'operator.assign':
            types[self.struct.get_name()].add_operator('=', self.module.sfuncs[name])
        elif self.name.value == 'operator.eq':
            types[self.struct.get_name()].add_operator('==', self.module.sfuncs[name])
        elif self.name.value == 'operator.spaceship':
            types[self.struct.get_name()].add_operator('<=>', self.module.sfuncs[name])
        block = fn.append_basic_block("entry")
        self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
            "name": name, 
            "file": self.module.di_file,
            "line": self.spos.lineno,
            "unit": self.module.di_compile_unit,
            #"column": self.spos.colno,
            "isDefinition":True
        }, True)
        self.builder.position_at_start(block)
        #self.builder.defer = []
        fn.args = tuple(self.decl_args.get_arg_list(fn))
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
        name = self.struct.get_name() + '.' + self.name.value
        fname = name
        if not self.builder.c_decl:
            fname = mangle_name(name, sfnty.atypes)
        fn = ir.Function(self.module, fnty, fname)
        fn.args = tuple(self.decl_args.get_decl_arg_list(fn))
        #self.module.sfunctys[fname] = sfnty
        if name not in self.module.sfuncs:
            self.module.sfuncs[name] = Func(name, sfnty.rtype)
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn)
        else:
            self.module.sfuncs[name].add_overload(sfnty.atypes, fn)
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
        if vartype.is_struct():
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
                ovrld = method.get_overload([vartype.get_pointer_to(), self.initval.get_type()])
                if not ovrld:
                    pass
                self.builder.call(ovrld, [pptr, value])
                return
            if vartype.has_ctor():
                self.builder.call(vartype.get_ctor(), [ptr.irvalue])
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
        quals = [s[0] for s in self.spec.copy()]
        if str(vartype.irtype) == 'void':
            #print("%s (%s)" % (str(vartype), str(vartype.irtype)))
            lineno = self.initval.getsourcepos().lineno
            colno = self.initval.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Can't create variable of void type."
            )
        with self.builder.goto_entry_block():
            self.builder.position_at_start(self.builder.block)
            ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.irtype, name=self.name.value), qualifiers=quals)
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

    def get_type(self):
        if self.type is None:
            lname = self.lvalue.get_name()
            if lname not in types.keys():
                type_symbol = self.package.lookup_symbol(lname)
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

    def is_pointer(self):
        return self.get_type().is_pointer()

    def get_pointer_to(self):
        return PointerTypeExpr(self.builder, self.module, self.package, self.spos, self)

    def eval(self):
        self.type = types[self.lvalue.get_name()]
        for qual in self.quals:
            if qual[0] == '*':
                self.type = self.type.get_pointer_to()
            elif qual[0] == '[]':
                self.type = self.type.get_array_of(qual[1])


class PointerTypeExpr(TypeExpr):
    """
    Expression representing a pointer to a Saturn type.
    """
    def __init__(self, builder, module, package, spos, pointee, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.pointee = pointee

    def get_type(self):
        if self.type is None:
            self.type = self.pointee.get_type().get_pointer_to()
        return self.type

    def eval(self):
        pass


class ArrayTypeExpr(TypeExpr):
    """
    Expression representing an array a Saturn type.
    """
    def __init__(self, builder, module, package, spos, element, size, decl_mode=False):
        super().__init__(builder, module, package, spos, None)
        self.element = element
        self.size = size

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


class TupleTypeExpr(TypeExpr):
    """
    Expression representing a Saturn tuple type.\n
    tuple(typeexprs...)
    """
    def __init__(self, builder, module, package, spos, typeexprs):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.types = typeexprs
        for ty in self.types:
            lname = ty.lvalue.name
            if lname not in types.keys():
                #print(*types.keys())
                raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                    self.module.filestack[self.module.filestack_idx],
                    self.spos.lineno,
                    self.spos.colno,
                    lname
                ))
        self.type = TupleType("", ir.LiteralStructType([ty.get_ir_type() for ty in self.types]))
        self.base_type = self.type
        self.quals = []

    def eval(self):
        pass


class OptionalTypeExpr(TypeExpr):
    """
    Expression representing a Saturn optional type.\n
    optional(typeexpr)
    """
    def __init__(self, builder, module, package, spos, typeexpr):
        self.builder = builder
        self.module = module
        self.package = package
        self.spos = spos
        self.base = typeexpr.get_type()
        self.type = make_optional_type(self.base_type)
        self.base_type = self.type
        self.quals = []

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
        for ty in self.args:
            lname = ty.lvalue.name
            if lname not in types.keys():
                #print(*types.keys())
                raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                    self.module.filestack[self.module.filestack_idx],
                    self.spos.lineno,
                    self.spos.colno,
                    lname
                ))
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

    def get_type(self):
        if self.type is None:
            name = self.lvalue.get_name()
            types[name] = self.ltype.get_type()
            self.package[name] = self.ltype.get_type()
            self.type = types[name]
        return self.type

    def eval(self):
        pass


def calc_sizeof_struct(builder, module, stype):
    stypeptr = stype.irtype.as_pointer()
    null = stypeptr('zeroinitializer')
    gep = null.gep([ir.Constant(ir.IntType(32), 1)])
    size = builder.ptrtoint(gep, ir.IntType(32))
    return size


class StructField(ASTNode):
    def __init__(self, builder, module, package, spos, name, ftype, initvalue=None):
        super().__init__(builder, module, package, spos)
        self.name = name
        self.ftype = ftype
        self.type = None
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
    def __init__(self, builder, module, package, spos, lvalue, body, decl_mode):
        super().__init__(builder, module, package, spos)
        self.lvalue = lvalue
        self.body = body
        self.ctor = None
        self.decl_mode = decl_mode
        name = self.lvalue.get_name()
        types[name] = StructType(name, self.module.context.get_identified_type(name), [])
        self.package.add_symbol(name, types[name])
        if self.body is not None:
            for fld in self.body.get_fields():
                types[name].add_field(fld.name, fld.ftype.get_type(), fld.initvalue)

    def eval(self):
        name = self.lvalue.get_name()
        if self.module.context.get_identified_type(name).is_opaque and self.body is not None:
            idstruct = self.module.context.get_identified_type(name)
            idstruct.set_body(*self.body.get_ir_types())
            types[name].irtype = idstruct
            for fld in self.body.get_fields():
                types[name].add_field(fld.name, fld.get_type(), fld.initvalue)
        initfs = types[name].get_fields_with_init()
        if len(initfs) > 0:
            push_new_scope(self.builder)
            structty = types[name]
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
                    if fld.irvalue.constant == 'null':
                        self.builder.store(ir.Constant(gep.type.pointee, gep.type.pointee.null), gep)
                    else:
                        self.builder.store(fld.irvalue, gep)
                self.builder.ret_void()
            pop_inner_scope()


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
                return symbol.rtype
                #  return self.module.sfuncs[name].rtype
            return self.module.sglobals[name].rtype
        return ptr.type

    def get_ir_type(self):
        return self.get_type().irtype
        #return self.module.sfuncs[self.lvalue.get_name()].rtype.irtype

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
                #sfn = self.module.sfuncs[self.lvalue.get_name()]
                sfn = ptr
                aargs = []
                for arg in self.args:
                    if arg.get_type().is_reference():
                        aargs.append(arg.get_type().type)
                    else:
                        aargs.append(arg.get_type())
                ovrld = sfn.get_overload(aargs)
                if not ovrld:
                    lineno = self.getsourcepos().lineno
                    colno = self.getsourcepos().colno
                    throw_saturn_error(self.builder, self.module, lineno, colno, 
                        "Cannot find overload for function %s with argument types (%s)." % (self.lvalue.get_name(), print_types(aargs))
                    )
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
                return self.builder.call(ovrld, args, self.lvalue.get_name())
            #ptr = self.module.sglobals[name]
        args = [arg.eval() for arg in self.args]
        fn = self.builder.load(ptr.irvalue)
        return self.builder.call(fn, args)
        #return self.builder.call(self.module.get_global(self.lvalue.get_name()), args, self.lvalue.get_name())


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
        name = self.callee.get_type().name + '.' + self.lvalue.get_name()
        return self.module.sfuncs[name].rtype

    def get_ir_type(self):
        return self.get_type().irtype
        #return self.module.get_global(self.callee.get_type().name + '.' + self.lvalue.get_name()).ftype.return_type

    def eval(self):
        name = self.callee.get_type().name + '.' + self.lvalue.get_name()
        sfn = self.module.sfuncs[name]
        #print(name, self.module.sfuncs[name], sfn.overloads)
        sargs = [arg for arg in self.args]
        sargs.insert(0, AddressOf(self.builder, self.module, self.package, self.spos, self.callee))
        aargs = [arg.get_type() for arg in sargs]
        ovrld = sfn.get_overload(aargs)
        if not ovrld:
            lineno = self.getsourcepos().lineno
            colno = self.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot find overload for function %s with argument types (%s)." % (self.lvalue.get_name(), print_types(aargs))
            )
        args = [arg.eval() for arg in sargs]
        return self.builder.call(ovrld, args, name)


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
        self.builder.branch(self.builder.break_dest)


class ContinueStatement(Statement):
    """
    Continue statement.\n
    continue;
    """
    def eval(self):
        self.builder.branch(self.builder.continue_dest)


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
    if boolexpr { then } else { el }
    """
    def __init__(self, builder, module, package, spos, boolexpr, then, elseif=[], el=None):
        super().__init__(builder, module, package, spos)
        self.boolexpr = boolexpr
        self.then = then
        self.elseif = elseif
        self.el = el

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
                    self.el.eval()
        # return
        # then = self.builder.append_basic_block(self.module.get_unique_name("then"))
        # el = None
        # if self.el is not None:
        #     el = self.builder.append_basic_block(self.module.get_unique_name("else"))
        # after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        # if self.el is not None:
        #     self.builder.cbranch(bexpr, then, el)
        # else:
        #     self.builder.cbranch(bexpr, then, after)
        # self.builder.goto_block(then)
        # self.builder.position_at_start(then)
        # self.then.eval()
        # if not self.builder.block.is_terminated:
        #     self.builder.branch(after)
        # if self.el is not None:
        #     self.builder.goto_block(el)
        #     self.builder.position_at_start(el)
        #     self.el.eval()
        #     self.builder.branch(after)
        # self.builder.goto_block(after)
        # self.builder.position_at_start(after)


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
        self.builder.break_dest = after
        self.builder.continue_dest = loop
        self.loop.eval()
        self.builder.break_dest = None
        self.builder.continue_dest = None
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
        self.builder.break_dest = after
        self.builder.continue_dest = loop
        self.loop.eval()
        self.builder.break_dest = None
        self.builder.continue_dest = None
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


class ForStatement(ASTNode):
    """
    For loop statement.\n
    for it in itexpr { loop }
    """
    def __init__(self, builder, module, package, spos, it, itexpr, loop):
        super().__init__(builder, module, package, spos)
        self.it = it
        self.itexpr = itexpr
        self.loop = loop

    def eval(self):
        init = self.builder.append_basic_block(self.module.get_unique_name("for.init"))
        self.builder.branch(init)
        self.builder.goto_block(init)
        self.builder.position_at_start(init)
        push_new_scope(self.builder)
        name = self.it.get_name()
        ty = self.itexpr.get_type()
        ptr = Value(name, ty, self.builder.alloca(ty.irtype, name=name))
        add_new_local(name, ptr)
        self.builder.store(self.itexpr.eval_init(), ptr.irvalue)
        check = self.builder.append_basic_block(self.module.get_unique_name("for.check"))
        loop = self.builder.append_basic_block(self.module.get_unique_name("for.loop"))
        inc = self.builder.append_basic_block(self.module.get_unique_name("for.inc"))
        after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        self.builder.branch(check)
        self.builder.goto_block(check)
        self.builder.position_at_start(check)
        self.builder.break_dest = after
        self.builder.continue_dest = inc
        checkval = self.itexpr.eval_loop_check(self.it)
        self.builder.cbranch(checkval, loop, after)
        self.builder.goto_block(loop)
        self.builder.position_at_start(loop)
        self.loop.eval()
        self.builder.branch(inc)
        self.builder.goto_block(inc)
        self.builder.position_at_start(inc)
        self.itexpr.eval_loop_inc(self.it)
        self.builder.break_dest = None
        self.builder.continue_dest = None
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
    case expr: stmts
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
        self.builder.break_dest = after
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
