from llvmlite import ir
from rply import Token
from typesys import Type, types, FuncType, Value
from serror import throw_saturn_error

SCOPE = []

def get_inner_scope():
    global SCOPE
    return SCOPE[-1]

def check_name_in_scope(name):
    global SCOPE
    for i in range(len(SCOPE)):
        s = SCOPE[len(SCOPE)-1-i]
        if name in s.keys():
            return s[name]
    return None

def push_new_scope():
    global SCOPE
    SCOPE.append({})

def pop_inner_scope():
    global SCOPE
    SCOPE.pop(-1)

class Expr():
    """
    An expression. Base class for integer and float constants.
    """
    def __init__(self, builder, module, spos):
        self.builder = builder
        self.module = module
        self.spos = spos

    def getsourcepos(self):
        return self.spos

    def get_type(self):
        return types['void']

    def get_ir_type(self):
        return self.get_type().irtype

class Number(Expr):
    """
    A number constant. Base class for integer and float constants.
    """
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value
        self.type = self.get_type()

    def get_type(self):
        return types['int']


class Integer(Number):
    """
    A 32-bit integer constant. (int)
    """
    def get_type(self):
        return types['int']

    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value))
        return i


class Integer64(Number):
    """
    A 64-bit integer constant. (int64)
    """
    def get_type(self):
        return types['int64']

    def eval(self):
        val = self.value.strip('L')
        i = ir.Constant(self.type.irtype, int(val))
        return i


class Byte(Number):
    """
    An 8-bit unsigned integer constant. (byte)
    """
    def get_type(self):
        return types['byte']
    
    def eval(self):
        i = ir.Constant(self.type.irtype, int(self.value))
        return i


class Float(Number):
    """
    A single-precision float constant. (float32)
    """
    def get_type(self):
        return types['float32']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value))
        return i


class Double(Number):
    """
    A double-precision float constant. (float64)
    """
    def get_type(self):
        return types['float64']

    def eval(self):
        i = ir.Constant(self.type.irtype, float(self.value))
        return i


class StringLiteral(Expr):
    """
    A null terminated string literal. (cstring)
    """
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value
        self.type = self.get_type()

    def get_type(self):
        return types['cstring']

    def get_reference(self):
        return self.value

    def eval(self):
        fmt = str(self.value).strip("\"") + '\0'
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
    def __init__(self, builder, module, spos, value: bool):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value

    def get_type(self):
        return types['bool']

    def eval(self):
        i = ir.Constant(self.get_type().irtype, self.value)
        return i

        
class LValue(Expr):
    """
    Expression representing a named value in memory.
    """
    def __init__(self, builder, module, spos, name, lhs=None):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lhs = lhs
        self.name = name
        self.value = None

    def get_type(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.sglobals[name]
        if ptr.type.is_pointer():
            return ptr.type.get_deference_of()
        return ptr.type

    def get_ir_type(self):
        name = self.get_name()
        ptr = check_name_in_scope(name).irvalue
        if ptr is None:
            ptr = self.module.get_global(name)
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
                s += "."
                i = i + 1
        return s

    def get_pointer(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.sglobals[name]
        return ptr
    
    def eval(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.sglobals[name]
        return self.builder.load(ptr.irvalue)


class PostfixOp(Expr):
    """
    A base class for unary postfix operations.\n
    left OP
    """
    def get_type(self):
        return self.left.get_type()

    def __init__(self, builder, module, spos, left, expr):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.left = left
        self.expr = expr


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
                return Value("", ptr.type.get_deference_of(), gep)
            else:
                gep = self.builder.gep(ptr.irvalue, [
                    ir.Constant(ir.IntType(32), 0),
                    self.expr.eval()
                ], True)
                return Value("", ptr.type.get_element_of(), gep)
            

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

    def __init__(self, builder, module, spos, right):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.right = right


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
    def get_name(self):
        return self.right.get_name()

    def get_type(self):
        return self.right.get_type()
    
    def get_pointer(self):
        return Value("", self.get_type(), self.builder.load(self.right.get_pointer().irvalue))

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


class BinaryOp(Expr):
    """
    A base class for binary operations.\n
    left OP right
    """
    def get_type(self):
        if self.left.get_type().is_similar(self.right.get_type()):
            return self.left.get_type()
        return types['void']

    def __init__(self, builder, module, spos, left, right):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.left = left
        self.right = right


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


class Xor(BinaryOp):
    """
    An xor bitwise binary operation.\n
    left ^ right
    """
    def eval(self):
        i = self.builder.xor(self.left.eval(), self.right.eval())
        return i


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


class BoolCmpOp(BinaryOp):
    """
    Base class for boolean comparison binary operations.
    """
    def getcmptype(self):
        if self.right.get_ir_type() == self.left.get_ir_type():
            self.lhs = self.left.eval()
            self.rhs = self.right.eval()
            return self.left.get_ir_type()
        if isinstance(self.left.get_ir_type(), ir.DoubleType):
            if isinstance(self.right.get_ir_type(), ir.FloatType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.fpext(self.right.eval(), ir.DoubleType())
                return self.left.get_ir_type()
            if isinstance(self.right.get_ir_type(), ir.IntType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.sitofp(self.right.eval(), ir.DoubleType())
                return self.left.get_ir_type()
        elif isinstance(self.left.get_ir_type(), ir.IntType):
            if isinstance(self.right.get_ir_type(), ir.FloatType) or isinstance(self.right.get_ir_type(), ir.DoubleType):
                self.lhs = self.builder.sitofp(self.right.eval(), self.left.get_ir_type())
                self.rhs = self.right.eval()
                return self.right.get_ir_type()
            elif isinstance(self.right.get_ir_type(), ir.IntType):
                if str(self.right.get_ir_type()) == 'i1' or str(self.left.get_ir_type()) == 'i1':
                    raise RuntimeError("Cannot do comparison between booleans and integers. (%s,%s) (At %s)" % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))
                if self.left.get_ir_type().width > self.right.get_ir_type().width:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At line %d, col %d)' % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos.lineno, self.spos.colno))
                    self.lhs = self.left.eval()
                    self.rhs = self.builder.sext(self.right.eval(), self.left.get_ir_type())
                    return self.left.get_ir_type()
                else:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At %s)' % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))
                    self.rhs = self.right.eval()
                    self.lhs = self.builder.sext(self.left.eval(), self.right.get_ir_type())
                    return self.right.get_ir_type()
        raise RuntimeError("Ouch. Types for comparison cannot be matched. (%s,%s) (At %s)" % (self.left.get_ir_type(), self.right.get_ir_type(), self.spos))

    def get_ir_type(self):
        return types['bool'].irtype


class BooleanEq(BoolCmpOp):
    """
    Comparison equal '==' operator.\n
    left == right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('==', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('==', self.lhs, self.rhs)
        return i


class BooleanNeq(BoolCmpOp):
    """
    Comparison not equal '!=' operator.\n
    left != right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('!=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('!=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('!=', self.lhs, self.rhs)
        return i


class BooleanGt(BoolCmpOp):
    """
    Comparison greater than '>' operator.\n
    left > right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('>', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('>', self.lhs, self.rhs)
        return i


class BooleanLt(BoolCmpOp):
    """
    Comparison less than '<' operator.\n
    left < right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('<', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('<', self.lhs, self.rhs)
        return i


class BooleanGte(BoolCmpOp):
    """
    Comparison greater than or equal '>=' operator.\n
    left >= right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('>=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('>=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('>=', self.lhs, self.rhs)
        return i


class BooleanLte(BoolCmpOp):
    """
    Comparison greater than or equal '<=' operator.\n
    left <= right
    """
    def eval(self):
        cmpty = self.getcmptype()
        if isinstance(cmpty, ir.IntType):
            i = self.builder.icmp_signed('<=', self.lhs, self.rhs)
        elif isinstance(cmpty, ir.FloatType) or isinstance(cmpty, ir.DoubleType):
            i = self.builder.fcmp_ordered('<=', self.lhs, self.rhs)
        else:
            i = self.builder.fcmp_ordered('<=', self.lhs, self.rhs)
        return i


class Assignment():
    """
    Assignment statement to a defined variable.\n
    lvalue = expr;
    """
    def __init__(self, builder, module, spos, lvalue, expr):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue
        self.expr = expr

    def getsourcepos(self):
        return self.spos
    
    def eval(self):
        sptr = self.lvalue.get_pointer()
        if sptr.type.is_const() or sptr.type.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % sptr.name
            )
        ptr = sptr.irvalue
        value = self.expr.eval()
        #print("(%s) => (%s)" % (value, ptr))
        self.builder.store(value, ptr)


class AddAssignment(Assignment):
    """
    Add assignment statement to a defined variable.\n
    lvalue += expr; (lvalue = lvalue + expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.type.is_const() or ptr.type.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        value = self.builder.load(ptr.irvalue)
        res = self.builder.add(value, self.expr.eval())
        self.builder.store(res, ptr.irvalue)


class SubAssignment(Assignment):
    """
    Sub assignment statement to a defined variable.\n
    lvalue -= expr; (lvalue = lvalue - expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.type.is_const() or ptr.type.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        value = self.builder.load(ptr.irvalue)
        res = self.builder.sub(value, self.expr.eval())
        self.builder.store(res, ptr.irvalue)


class MulAssignment(Assignment):
    """
    Multiply assignment statement to a defined variable.\n
    lvalue *= expr; (lvalue = lvalue * expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.type.is_const() or ptr.type.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        value = self.builder.load(ptr.irvalue)
        res = self.builder.mul(value, self.expr.eval())
        self.builder.store(res, ptr.irvalue)


class DivAssignment(Assignment):
    """
    Division assignment statement to a defined variable.\n
    lvalue /= expr; (lvalue = lvalue / expr;)
    """
    def eval(self):
        ptr = self.lvalue.get_pointer()
        if ptr.type.is_const() or ptr.type.is_immut():
            lineno = self.expr.getsourcepos().lineno
            colno = self.expr.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Cannot reassign to const variable, %s." % ptr.name
            )
        value = self.builder.load(ptr.irvalue)
        res = self.builder.sdiv(value, self.expr.eval())
        self.builder.store(res, ptr.irvalue)


class Program():
    """
    Base node for AST
    """
    def __init__(self, stmt):
        self.stmts = [stmt]

    def add(self, stmt):
        self.stmts.append(stmt)

    def eval(self):
        for stmt in self.stmts:
            stmt.eval()


class PackageDecl():
    def __init__(self, builder, module, spos, lvalue):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue

    def eval(self):
        self.builder.package = self.lvalue.get_name()


class ImportDecl():
    """
    A statement that reads and imports another package.
    """
    def __init__(self, builder, module, spos, lvalue):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue

    def eval(self):
        from sparser import Parser
        from lexer import Lexer
        from cachedmodule import CachedModule, cachedmods

        path = './packages/' + self.lvalue.get_name() + '/main.sat'
        if path not in cachedmods.keys():
            text_input = ""
            with open(path) as f:
                text_input = f.read()
            
            cmod = CachedModule(path, text_input)
            cachedmods[path] = cmod
            
        cmod = cachedmods[path]

        lexer = Lexer().get_lexer()
        tokens = lexer.lex(cmod.text_input)

        self.builder.filestack.append(cmod.text_input)
        self.builder.filestack_idx += 1

        self.module.filestack.append(path)
        self.module.filestack_idx += 1

        pg = Parser(self.module, self.builder)
        pg.parse()

        self.builder.filestack.pop(-1)
        self.builder.filestack_idx -= 1

        self.module.filestack.pop(-1)
        self.module.filestack_idx -= 1

        parser = pg.get_parser()
        parser.parse(tokens).eval()



class CodeBlock():
    """
    A block of multiple statements with an enclosing scope.
    """
    def __init__(self, builder, module, spos, stmt):
        self.builder = builder
        self.module = module
        self.spos = spos
        if stmt is not None:
            self.stmts = [stmt]
        else:
            self.stmts = []

    def getsourcepos(self):
        return self.spos

    def add(self, stmt):
        self.stmts.append(stmt)

    def eval(self, builder=None):
        push_new_scope()
        if builder is not None:
            self.builder = builder
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


class FuncArg():
    """
    An definition of a function parameter.\n
    name : rtype, 
    """
    def __init__(self, builder, module, spos, name, atype):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.name = name
        self.atype = atype.type

    def getsourcepos(self):
        return self.spos
    
    def eval(self, func: ir.Function, decl=True):
        arg = ir.Argument(func, self.atype.irtype, name=self.name.value)
        if decl:
            val = Value(self.name.value, self.atype, arg)
            scope = get_inner_scope()
            scope[self.name.value] = val
            return val
        else:
            ptr = self.builder.alloca(self.atype.irtype, name=self.name.value)
            self.builder.store(arg, ptr)
            argval = Value(self.name.value, self.atype, arg)
            val = Value(self.name.value, self.atype, ptr)
            scope = get_inner_scope()
            scope[self.name.value] = val
            return argval



class FuncArgList():
    """
    A list of arguments for a function.
    """
    def __init__(self, builder, module, spos, arg=None):
        if arg is not None:
            self.args = [arg]
        else:
            self.args = []

    def add(self, arg):
        self.args.append(arg)

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
            atypes.append(arg.atype.irtype)
        return atypes

    def get_arg_stype_list(self):
        atypes = []
        for arg in self.args:
            atypes.append(arg.atype)
        return atypes

    def eval(self, func):
        eargs = []
        for arg in self.args:
            eargs.append(arg.eval(func))
        return eargs



class FuncDecl():
    """
    A declaration and definition of a function.\n
    fn name(decl_args): rtype { block }
    """
    def __init__(self, builder, module, spos, name, rtype, block, decl_args):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.name = name
        self.rtype = rtype
        self.block = block
        self.decl_args = decl_args

    def getsourcepos(self):
        return self.spos

    def eval(self):
        push_new_scope()
        rtype = self.rtype
        argtypes = self.decl_args.get_arg_type_list()
        fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", rtype.type, self.decl_args.get_arg_stype_list())
        try:
            self.module.get_global(self.name.value)
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
        fn = ir.Function(self.module, fnty, self.name.value)
        self.module.sfunctys[self.name.value] = sfnty
        block = fn.append_basic_block("entry")
        # self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
        #     "name":self.name.value, 
        #     "file": self.module.di_file,
        #     "line": self.spos.lineno,
        #     #"column": self.spos.colno,
        #     "isDefinition":True
        # }, True)
        self.builder.position_at_start(block)
        fn.args = tuple(self.decl_args.get_arg_list(fn))
        self.block.eval()
        if not self.builder.block.is_terminated:
            if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
        pop_inner_scope()


class FuncDeclExtern():
    """
    A declaration of an externally defined function.\n
    fn name(decl_args) : rtype; 
    """
    def __init__(self, builder, module, spos, name, rtype, decl_args):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.name = name
        self.rtype = rtype
        self.decl_args = decl_args

    def getsourcepos(self):
        return self.spos

    def eval(self):
        push_new_scope()
        rtype = self.rtype.type
        argtypes = self.decl_args.get_arg_type_list()
        fnty = ir.FunctionType(rtype.irtype, argtypes)
        #print("%s (%s)" % (self.name.value, fnty))
        sfnty = FuncType("", rtype, self.decl_args.get_arg_stype_list())
        fn = ir.Function(self.module, fnty, self.name.value)
        fn.args = tuple(self.decl_args.get_decl_arg_list(fn))
        self.module.sfunctys[self.name.value] = sfnty
        pop_inner_scope()


class GlobalVarDecl():
    """
    A global variable declaration statement.\n
    name : vtype;\n
    name : vtype = initval;
    """
    def __init__(self, builder, module, spos, name, vtype, initval=None):
        self.name = name
        self.vtype = vtype
        self.builder = builder
        self.module = module
        self.spos = spos
        self.initval = initval

    def getsourcepos(self):
        return self.spos

    def eval(self):
        vartype = get_type_by_name(self.builder, self.module, str(self.vtype))
        gvar = ir.GlobalVariable(self.module, vartype, self.name.value)

        if self.initval:
            gvar.initializer = self.initval.eval()
        else:
            gvar.initializer = ir.Constant(vartype, 0)
        return gvar


class VarDecl():
    """
    A local varible declaration statement.\n
    name : vtype;\n
    name : vtype = initval;
    """
    def __init__(self, builder, module, spos, name, vtype, initval=None):
        self.name = name
        self.vtype = vtype
        self.builder = builder
        self.module = module
        self.spos = spos
        self.initval = initval

    def getsourcepos(self):
        return self.spos

    def eval(self):
        vartype = self.vtype.type
        ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.irtype, name=self.name.value))
        scope = get_inner_scope()
        scope[self.name.value] = ptr
        # dbglv = self.module.add_debug_info("DILocalVariable", {
        #     "name":self.name.value, 
        #     "arg":0, 
        #     "scope":self.builder.dbgsub
        # })
        # dbgexpr = self.module.add_debug_info("DIExpression", {})
        # self.builder.call(
        #     self.module.get_global("llvm.dbg.addr"), 
        #     [ptr, dbglv, dbgexpr]
        # )
        if self.initval is not None:
            self.builder.store(self.initval.eval(), ptr.irvalue)
        return ptr


class VarDeclAssign():
    """
    An automatic variable declaration and assignment statement. Uses type inference.\n
    name := initval;
    """
    def __init__(self, builder, module, spos, name, initval, spec='none'):
        self.name = name
        self.builder = builder
        self.module = module
        self.spos = spos
        self.initval = initval
        self.spec = spec

    def getsourcepos(self):
        return self.spos

    def eval(self):
        val = self.initval.eval()
        vartype = self.initval.get_type()
        if self.spec == 'const':
            vartype = vartype.get_const_of()
        elif self.spec == 'immut':
            vartype = vartype.get_immut_of()
        if str(vartype.irtype) == 'void':
            #print("%s (%s)" % (str(vartype), str(vartype.irtype)))
            lineno = self.initval.getsourcepos().lineno
            colno = self.initval.getsourcepos().colno
            throw_saturn_error(self.builder, self.module, lineno, colno, 
                "Can't create variable of void type."
            )
        ptr = Value(self.name.value, vartype, self.builder.alloca(vartype.irtype, name=self.name.value))

        scope = get_inner_scope()
        scope[self.name.value] = ptr
        # dbglv = self.module.add_debug_info("DILocalVariable", {
        #     "name":self.name.value, 
        #     #"arg":1, 
        #     "file": self.module.di_file,
        #     "line": self.spos.lineno,
        #     "scope":self.builder.dbgsub,
        #     "type": self.module.di_types[from_type_get_name(self.builder, self.module, vartype)]
        # })
        # dbgexpr = self.module.add_debug_info("DIExpression", {})
        # self.builder.call(
        #     self.module.get_global("llvm.dbg.addr"), 
        #     [ptr, dbglv, dbgexpr]
        # )
        if self.initval is not None:
            self.builder.store(val, ptr.irvalue)
        return ptr


class TypeExpr():
    """
    Expression representing a Saturn type.
    """
    def __init__(self, builder, module, spos, lvalue):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue
        lname = self.lvalue.get_name()
        if lname not in types.keys():
            raise RuntimeError("%s (%d:%d): Undefined type, %s, used in typeexpr." % (
                self.module.filestack[self.module.filestack_idx],
                self.spos.lineno,
                self.spos.colno,
                lname
            ))
        self.type = types[lvalue.get_name()]
        self.base_type = types[lvalue.get_name()]

    def get_ir_type(self):
        return self.type.irtype

    def add_pointer_qualifier(self):
        self.type = self.type.get_pointer_to()

    def add_array_qualifier(self, size):
        self.type = self.type.get_array_of(int(size.value))

    def is_pointer(self):
        return self.type.is_pointer()     


class FuncCall(Expr):
    """
    Function call expression.\n
    lvalue(args)
    """
    def __init__(self, builder, module, spos, lvalue, args):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue
        self.args = args

    def get_type(self):
        return self.module.sfunctys[self.lvalue.get_name()].rtype

    def get_ir_type(self):
        return self.module.get_global(self.lvalue.get_name()).ftype.return_type

    def eval(self):
        args = []
        for arg in self.args:
            args.append(arg.eval())
        return self.builder.call(self.module.get_global(self.lvalue.get_name()), args, self.lvalue.get_name())


class Statement():
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value

    def getsourcepos(self):
        return self.spos


class ReturnStatement(Statement):
    """
    Return statement.\n
    return value;
    """
    def eval(self):
        if self.value is not None:
            self.builder.ret(self.value.eval())
        else:
            self.builder.ret_void()


class IfStatement():
    """
    If statement.\n
    if boolexpr { then }\n
    if boolexpr { then } else { el }
    """
    def __init__(self, builder, module, spos, boolexpr, then, elseif=[], el=None):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.boolexpr = boolexpr
        self.then = then
        self.el = el

    def getsourcepos(self):
        return self.spos

    def eval(self):
        bexpr = self.boolexpr.eval()
        then = self.builder.append_basic_block(self.module.get_unique_name("then"))
        el = None
        if self.el is not None:
            el = self.builder.append_basic_block(self.module.get_unique_name("else"))
        after = self.builder.append_basic_block(self.module.get_unique_name("after"))
        if self.el is not None:
            self.builder.cbranch(bexpr, then, el)
        else:
            self.builder.cbranch(bexpr, then, after)
        self.builder.goto_block(then)
        self.builder.position_at_start(then)
        self.then.eval()
        if not then.is_terminated:
            self.builder.branch(after)
        if self.el is not None:
            self.builder.goto_block(el)
            self.builder.position_at_start(el)
            self.el.eval()
            self.builder.branch(after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)


class WhileStatement():
    """
    While loop statement.\n
    while boolexpr { loop }
    """
    def __init__(self, builder, module, spos, boolexpr, loop):
        self.builder = builder
        self.module = module
        self.spos = spos
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
        self.loop.eval()
        bexpr2 = self.boolexpr.eval()
        self.builder.cbranch(bexpr2, loop, after)
        self.builder.goto_block(after)
        self.builder.position_at_start(after)


class Print():
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value

    def getsourcepos(self):
        return self.spos

    def eval(self):
        # Call Print Function
        args = []
        for value in self.value:
            args.append(value.eval())
        self.builder.call(self.module.get_global("printf"), args)