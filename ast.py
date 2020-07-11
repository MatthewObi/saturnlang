from llvmlite import ir
from rply import Token

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
        return ir.VoidType()

class Number(Expr):
    def __init__(self, builder, module, spos, value):
        self.builder = builder
        self.module = module
        self.spos = spos
        self.value = value
        self.type = self._get_type()
    
    def _get_type(self):
        return ir.FloatType()


class Integer(Number):
    def _get_type(self):
        return ir.IntType(32)

    def eval(self):
        i = ir.Constant(self.type, int(self.value))
        return i


class Integer64(Number):
    def _get_type(self):
        return ir.IntType(64)

    def eval(self):
        val = self.value.strip('L')
        i = ir.Constant(self.type, int(val))
        return i


class Byte(Number):
    def _get_type(self):
        return ir.IntType(8)
    
    def eval(self):
        i = ir.Constant(self.type, int(self.value))
        return i


class Float(Number):
    def _get_type(self):
        return ir.FloatType()

    def eval(self):
        i = ir.Constant(self.type, float(self.value))
        return i


class Double(Number):
    def _get_type(self):
        return ir.DoubleType()

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
        return ir.IntType(8).as_pointer()

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
        return ir.IntType(1)

    def eval(self):
        i = ir.Constant(ir.IntType(1), self.value)
        return i


class BinaryOp(Expr):
    def _get_type(self):
        if self.left._get_type() == self.right._get_type():
            return self.left._get_type()
        return ir.IntType(32)

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


class BooleanEq(BinaryOp):
    def eval(self):
        if isinstance(self._get_type(), ir.IntType):
            i = self.builder.icmp_signed('==', self.left.eval(), self.right.eval())
        elif isinstance(self._get_type(), ir.FloatType) or isinstance(self._get_type(), ir.DoubleType):
            i = self.builder.fcmp_ordered('==', self.left.eval(), self.right.eval())
        else:
            i = self.builder.fcmp_ordered('==', self.left.eval(), self.right.eval())
        return i

    def _get_type(self):
        return ir.IntType(1)


class BooleanNeq(BinaryOp):
    def eval(self):
        if isinstance(self._get_type(), ir.IntType):
            i = self.builder.icmp_signed('!=', self.left.eval(), self.right.eval())
        elif isinstance(self._get_type(), ir.FloatType) or isinstance(self._get_type(), ir.DoubleType):
            i = self.builder.fcmp_ordered('!=', self.left.eval(), self.right.eval())
        else:
            i = self.builder.fcmp_ordered('!=', self.left.eval(), self.right.eval())
        return i

    def _get_type(self):
        return ir.IntType(1)


class BooleanGt(BinaryOp):
    def eval(self):
        if isinstance(self._get_type(), ir.IntType):
            i = self.builder.icmp_signed('>', self.left.eval(), self.right.eval())
        elif isinstance(self._get_type(), ir.FloatType) or isinstance(self._get_type(), ir.DoubleType):
            i = self.builder.fcmp_ordered('>', self.left.eval(), self.right.eval())
        else:
            i = self.builder.fcmp_ordered('>', self.left.eval(), self.right.eval())
        return i

    def _get_type(self):
        return ir.IntType(1)


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
        if name is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        value = self.builder.load(ptr)
        res = self.builder.add(value, self.expr.eval())
        self.builder.store(res, ptr)


class SubAssignment(Assignment):
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if name is None:
            ptr = self.module.get_global(self.lvalue.get_name())
        value = self.builder.load(ptr)
        res = self.builder.sub(value, self.expr.eval())
        self.builder.store(res, ptr)


class MulAssignment(Assignment):
    def eval(self):
        name = self.lvalue.get_name()
        ptr = check_name_in_scope(name)
        if name is None:
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
    if name == "void":
        return ir.VoidType()
    if name == "int32":
        return ir.IntType(32)
    if name == "int64":
        return ir.IntType(64)
    if name == "int":
        return ir.IntType(32)
    if name == "bool":
        return ir.IntType(1)
    if name == "float32":
        return ir.FloatType()
    if name == "float64":
        return ir.DoubleType()
    if name == "float16":
        return ir.HalfType()
    if name == "cstring":
        return ir.IntType(8).as_pointer()
    return ir.IntType(32)

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
        dbglv = self.module.add_debug_info("DILocalVariable", {
            "name":self.name.value, 
            "arg":0, 
            "scope":self.builder.dbgsub
        })
        dbgexpr = self.module.add_debug_info("DIExpression", {})
        self.builder.call(
            self.module.get_global("llvm.dbg.addr"), 
            [ptr, dbglv, dbgexpr]
        )
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