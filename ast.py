from llvmlite import ir
from rply import Token
from typesys import Type, types

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
    def __init__(self, builder, module, spos):
        self.builder = builder
        self.module = module
        self.spos = spos

    def getsourcepos(self):
        return self.spos

    def _get_type(self):
        return types['void'].irtype

class Number(Expr):
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value
        self.type = self._get_type()
    
    def _get_type(self):
        return types['int'].irtype


class Integer(Number):
    def _get_type(self):
        return types['int'].irtype

    def eval(self):
        i = ir.Constant(self.type, int(self.value))
        return i


class Integer64(Number):
    def _get_type(self):
        return types['int64'].irtype

    def eval(self):
        val = self.value.strip('L')
        i = ir.Constant(self.type, int(val))
        return i


class Byte(Number):
    def _get_type(self):
        return types['int8'].irtype
    
    def eval(self):
        i = ir.Constant(self.type, int(self.value))
        return i


class Float(Number):
    def _get_type(self):
        return types['float32'].irtype

    def eval(self):
        i = ir.Constant(self.type, float(self.value))
        return i


class Double(Number):
    def _get_type(self):
        return types['float64'].irtype

    def eval(self):
        i = ir.Constant(self.type, float(self.value))
        return i


class StringLiteral(Expr):
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value
        self.type = ir.IntType(8).as_pointer()

    def _get_type(self):
        return types['cstring'].irtype

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
        self.value = self.builder.bitcast(global_fmt, self.type)
        return self.value


class Boolean(Expr):
    def __init__(self, builder, module, spos, value: bool):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value

    def _get_type(self):
        return types['bool'].irtype

    def eval(self):
        i = ir.Constant(ir.IntType(1), self.value)
        return i


class BinaryOp(Expr):
    def _get_type(self):
        if self.left._get_type() == self.right._get_type():
            return self.left._get_type()
        return types['int'].irtype

    def __init__(self, builder, module, spos, left, right):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.left = left
        self.right = right


class Sum(BinaryOp):
    def eval(self):
        i = self.builder.add(self.left.eval(), self.right.eval())
        return i


class Sub(BinaryOp):
    def eval(self):
        i = self.builder.sub(self.left.eval(), self.right.eval())
        return i


class Mul(BinaryOp):
    def eval(self):
        i = self.builder.mul(self.left.eval(), self.right.eval())
        return i


class Div(BinaryOp):
    def eval(self):
        i = self.builder.sdiv(self.left.eval(), self.right.eval())
        return i


class And(BinaryOp):
    def eval(self):
        i = self.builder.and_(self.left.eval(), self.right.eval())
        return i


class Or(BinaryOp):
    def eval(self):
        i = self.builder.or_(self.left.eval(), self.right.eval())
        return i


class Xor(BinaryOp):
    def eval(self):
        i = self.builder.xor(self.left.eval(), self.right.eval())
        return i


class BoolCmpOp(BinaryOp):
    def getcmptype(self):
        if self.right._get_type() == self.left._get_type():
            self.lhs = self.left.eval()
            self.rhs = self.right.eval()
            return self.left._get_type()
        if isinstance(self.left._get_type(), ir.DoubleType):
            if isinstance(self.right._get_type(), ir.FloatType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.fpext(self.right.eval(), ir.DoubleType())
                return self.left._get_type()
            if isinstance(self.right._get_type(), ir.IntType):
                self.lhs = self.left.eval()
                self.rhs = self.builder.sitofp(self.right.eval(), ir.DoubleType())
                return self.left._get_type()
        elif isinstance(self.left._get_type(), ir.IntType):
            if isinstance(self.right._get_type(), ir.FloatType) or isinstance(self.right._get_type(), ir.DoubleType):
                self.lhs = self.builder.sitofp(self.right.eval(), self.left._get_type())
                self.rhs = self.right.eval()
                return self.right._get_type()
            elif isinstance(self.right._get_type(), ir.IntType):
                if str(self.right._get_type()) == 'i1' or str(self.left._get_type()) == 'i1':
                    raise RuntimeError("Cannot do comparison between booleans and integers. (%s,%s) (At %s)" % (self.left._get_type(), self.right._get_type(), self.spos))
                if self.left._get_type().width > self.right._get_type().width:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At line %d, col %d)' % (self.left._get_type(), self.right._get_type(), self.spos.lineno, self.spos.colno))
                    self.lhs = self.left.eval()
                    self.rhs = self.builder.sext(self.right.eval(), self.left._get_type())
                    return self.left._get_type()
                else:
                    print('Warning: Automatic integer promotion for comparison (%s,%s) (At %s)' % (self.left._get_type(), self.right._get_type(), self.spos))
                    self.rhs = self.right.eval()
                    self.lhs = self.builder.sext(self.left.eval(), self.right._get_type())
                    return self.right._get_type()
        raise RuntimeError("Ouch. Types for comparison cannot be matched. (%s,%s) (At %s)" % (self.left._get_type(), self.right._get_type(), self.spos))

    def _get_type(self):
        return types['bool'].irtype


class BooleanEq(BoolCmpOp):
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
    def __init__(self, builder, module, spos, lvalue, expr):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue
        self.expr = expr

    def getsourcepos(self):
        return self.spos
    
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        self.builder.store(self.expr.eval(), ptr)


class AddAssignment(Assignment):
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        value = self.builder.load(ptr)
        res = self.builder.add(value, self.expr.eval())
        self.builder.store(res, ptr)


class SubAssignment(Assignment):
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        value = self.builder.load(ptr)
        res = self.builder.sub(value, self.expr.eval())
        self.builder.store(res, ptr)


class MulAssignment(Assignment):
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        value = self.builder.load(ptr)
        res = self.builder.mul(value, self.expr.eval())
        self.builder.store(res, ptr)


class Program():
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
        pass


class ImportDecl():
    def __init__(self, builder, module, spos, lvalue):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue

    def eval(self):
        from sparser import Parser
        from lexer import Lexer
        text_input = ""
        with open('./packages/' + self.lvalue.get_name() + '/main.sat') as f:
            text_input = f.read()

        lexer = Lexer().get_lexer()
        tokens = lexer.lex(text_input)
        pg = Parser(self.module, self.builder)
        pg.parse()
        parser = pg.get_parser()
        parser.parse(tokens).eval()



class CodeBlock():
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
    def __init__(self, builder, module, spos, name, atype):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.name = name
        self.atype = get_type_by_name(builder, module, str(atype.value))

    def getsourcepos(self):
        return self.spos
    
    def eval(self, func: ir.Function):
        arg = ir.Argument(func, self.atype, name=self.name.value)
        scope = get_inner_scope()
        scope[self.name.value] = arg
        return arg


class FuncArgList():
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
            args.append(arg.eval(func))
        return args

    def get_arg_type_list(self):
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
        rtype = get_type_by_name(self.builder, self.module, self.rtype.value)
        argtypes = self.decl_args.get_arg_type_list()
        fnty = ir.FunctionType(rtype, argtypes)
        fn = ir.Function(self.module, fnty, self.name.value)
        fn.args = tuple(self.decl_args.get_arg_list(fn))
        block = fn.append_basic_block("entry")
        # self.builder.dbgsub = self.module.add_debug_info("DISubprogram", {
        #     "name":self.name.value, 
        #     "file": self.module.di_file,
        #     "line": self.spos.lineno,
        #     #"column": self.spos.colno,
        #     "isDefinition":True
        # }, True)
        self.builder.position_at_start(block)
        self.block.eval()
        if not self.builder.block.is_terminated:
            if isinstance(self.builder.function.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
        pop_inner_scope()


class FuncDeclExtern():
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
        rtype = get_type_by_name(self.builder, self.module, self.rtype.value)
        argtypes = self.decl_args.get_arg_type_list()
        fnty = ir.FunctionType(rtype, argtypes)
        fn = ir.Function(self.module, fnty, self.name.value)
        fn.args = tuple(self.decl_args.get_arg_list(fn))
        pop_inner_scope()


class GlobalVarDecl():
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
        vartype = get_type_by_name(self.builder, self.module, str(self.vtype.value))
        ptr = self.builder.alloca(vartype, name=self.name.value)
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
            self.builder.store(self.initval.eval(), ptr)
        return ptr


class VarDeclAssign():
    def __init__(self, builder, module, spos, name, initval):
        self.name = name
        self.builder = builder
        self.module = module
        self.spos = spos
        self.initval = initval

    def getsourcepos(self):
        return self.spos

    def eval(self):
        vartype = self.initval._get_type()
        ptr = self.builder.alloca(vartype, name=self.name.value)
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
            self.builder.store(self.initval.eval(), ptr)
        return ptr


class LValue(Expr):
    def __init__(self, builder, module, spos, name, lhs=None):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lhs = lhs
        self.name = name
        self.value = None

    def _get_type(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
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
    
    def eval(self):
        name = self.get_name()
        ptr = check_name_in_scope(name)
        if ptr is None:
            ptr = self.module.get_global(name)
        if ptr.type.is_pointer:
            self.value = self.builder.load(ptr)
        else:
            self.value = ptr
        return self.value
            


class FuncCall(Expr):
    def __init__(self, builder, module, spos, lvalue, args):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.lvalue = lvalue
        self.args = args

    def _get_type(self):
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
    def eval(self):
        if self.value is not None:
            self.builder.ret(self.value.eval())
        else:
            self.builder.ret_void()


class IfStatement():
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