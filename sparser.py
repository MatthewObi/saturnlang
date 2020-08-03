from rply import ParserGenerator, Token
from ast import ( 
    Program, CodeBlock, Statement, ReturnStatement, 
    PackageDecl, ImportDecl, CIncludeDecl, TypeDecl, StructField, StructDeclBody, StructDecl,
    Sum, Sub, Mul, Div, Mod, And, Or, Xor, BoolAnd, BoolOr, Print, 
    AddressOf, DerefOf, ElementOf,
    Number, Integer, UInteger, Integer64, UInteger64, Float, Double, Byte, StringLiteral, MultilineStringLiteral,
    StructLiteralElement, StructLiteralBody, StructLiteral, 
    ArrayLiteralElement, ArrayLiteralBody, ArrayLiteral, TypeExpr,
    FuncDecl, FuncDeclExtern, FuncArgList, FuncArg, GlobalVarDecl, VarDecl, VarDeclAssign, 
    MethodDecl, MethodDeclExtern,
    LValue, LValueField, FuncCall, MethodCall, CastExpr, Assignment, AddAssignment, SubAssignment, MulAssignment, 
    Boolean, BooleanEq, BooleanNeq, BooleanGte, BooleanGt, BooleanLte, BooleanLt, 
    IfStatement, WhileStatement, SwitchCase, SwitchDefaultCase, SwitchBody, SwitchStatement
)
from serror import throw_saturn_error


class Parser():
    def __init__(self, module, builder, decl_mode=False):
        self.pg = ParserGenerator(
            # A list of all token names accepted by the parser.
            ['TPACKAGE', 'TIMPORT', 'TCINCLUDE',
             'INT', 'UINT', 'LONGINT', 'ULONGINT', 'BYTE', 'FLOAT', 'DOUBLE', 'STRING', 'MLSTRING',
             'IDENT', 'TPRINT', 'DOT', 'TRETURN', 'LPAREN', 'RPAREN', 'LBRACKET', 'RBRACKET',
             'SEMICOLON', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'AND', 'OR', 'XOR', 'BOOLAND', 'BOOLOR',
             'TFN', 'COLON', 'LBRACE', 'RBRACE', 'COMMA', 'CC', 'EQ', 'CEQ', 'ADDEQ', 'SUBEQ', 'MULEQ',
             'TIF', 'TELSE', 'TWHILE', 'TSWITCH', 'TCASE', 'TDEFAULT', 
             'TCONST', 'TIMMUT', 'TTYPE', 'TSTRUCT', 'TCAST',
             'BOOLEQ', 'BOOLNEQ', 'BOOLGT', 'BOOLLT', 'BOOLGTE', 'BOOLLTE', 'TTRUE', 'TFALSE'],

             precedence=[
                ('left', ['BOOLOR']),
                ('left', ['BOOLAND']),
                ('left', ['BOOLEQ', 'BOOLNEQ', 'BOOLGT', 'BOOLLT', 'BOOLGTE', 'BOOLLTE']),
                ('left', ['ADD', 'SUB']),
                ('left', ['MUL', 'DIV', 'MOD'])
            ]
        )
        self.module = module
        self.builder = builder
        self.decl_mode = decl_mode

    def parse(self):
        @self.pg.production('program : program gstmt')
        @self.pg.production('program : gstmt')
        def program(p):
            if(len(p) == 1):
                return Program(p[0])
            else:
                p[0].add(p[1])
                return p[0]

        @self.pg.production('gstmt : func_decl')
        @self.pg.production('gstmt : func_decl_extern')
        @self.pg.production('gstmt : gvar_decl')
        @self.pg.production('gstmt : method_decl')
        @self.pg.production('gstmt : pack_decl')
        @self.pg.production('gstmt : import_decl')
        @self.pg.production('gstmt : c_include_decl')
        @self.pg.production('gstmt : type_decl')
        @self.pg.production('gstmt : struct_decl')
        def gstmt(p):
           return p[0]

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN COLON typeexpr LBRACE block RBRACE')
        def func_decl(p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            block = p[8]
            spos = p[0].getsourcepos()
            if not self.decl_mode:
                return FuncDecl(self.builder, self.module, spos, name, rtype, block, declargs)
            return FuncDeclExtern(self.builder, self.module, spos, name, rtype, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN LBRACE block RBRACE')
        def func_decl_retvoid(p):
            name = p[1]
            declargs = p[3]
            spostexpr = p[5].getsourcepos()
            rtype = TypeExpr(self.builder, self.module, 
                spostexpr, 
                LValue(self.builder, self.module, spostexpr, "void")
            )
            block = p[6]
            spos = p[0].getsourcepos()
            if not self.decl_mode:
                return FuncDecl(self.builder, self.module, spos, name, rtype, block, declargs)
            return FuncDeclExtern(self.builder, self.module, spos, name, rtype, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN LBRACE RBRACE')
        def func_decl_retvoid_empty(p):
            name = p[1]
            declargs = p[3]
            spostexpr = p[5].getsourcepos()
            rtype = TypeExpr(self.builder, self.module, 
                spostexpr, 
                LValue(self.builder, self.module, spostexpr, "void")
            )
            spos = p[0].getsourcepos()
            block = CodeBlock(self.builder, self.module, spos, None)
            return FuncDecl(self.builder, self.module, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl_extern : TFN IDENT LPAREN decl_args RPAREN COLON typeexpr SEMICOLON')
        def func_decl_extern(p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            spos = p[0].getsourcepos()
            return FuncDeclExtern(self.builder, self.module, spos, name, rtype, declargs)

        @self.pg.production('decl_args : decl_args COMMA decl_arg')
        @self.pg.production('decl_args : decl_arg')
        @self.pg.production('decl_args : ')
        def decl_args(p):
            if len(p) == 0:
                return FuncArgList(self.builder, self.module, None)
            if len(p) == 1:
                spos = p[0].getsourcepos()
                return FuncArgList(self.builder, self.module, spos, p[0])
            else:
                p[0].add(p[2])
                return p[0]

        @self.pg.production('decl_arg : IDENT COLON typeexpr')
        def decl_arg(p):
            name = p[0]
            vtype = p[2]
            spos = p[0].getsourcepos()
            return FuncArg(self.builder, self.module, spos, name, vtype)

        @self.pg.production('gvar_decl : IDENT COLON typeexpr SEMICOLON')
        def gvar_decl(p):
            name = p[0]
            vtype = p[2]
            spos = p[0].getsourcepos()
            return GlobalVarDecl(self.builder, self.module, spos, name, vtype)

        @self.pg.production('gvar_decl : IDENT COLON typeexpr EQ expr SEMICOLON')
        def gvar_decl_init(p):
            name = p[0]
            vtype = p[2]
            initval = p[4]
            spos = p[0].getsourcepos()
            return GlobalVarDecl(self.builder, self.module, spos, name, vtype, initval)

        @self.pg.production('method_decl : TFN LPAREN MUL lvalue RPAREN IDENT LPAREN decl_args RPAREN COLON typeexpr LBRACE block RBRACE')
        def method_decl(p):
            struct = p[3]
            name = p[5]
            declargs = p[7]
            rtype = p[10]
            block = p[12]
            spos = p[0].getsourcepos()
            if not self.decl_mode:
                return MethodDecl(self.builder, self.module, spos, name, rtype, block, declargs, struct)
            return MethodDeclExtern(self.builder, self.module, spos, name, rtype, declargs, struct)

        @self.pg.production('pack_decl : TPACKAGE lvalue SEMICOLON')
        def pack_decl(p):
            spos = p[0].getsourcepos()
            return PackageDecl(self.builder, self.module, spos, p[1])

        @self.pg.production('import_decl : TIMPORT lvalue SEMICOLON')
        def import_decl(p):
            spos = p[0].getsourcepos()
            return ImportDecl(self.builder, self.module, spos, p[1])

        @self.pg.production('c_include_decl : TCINCLUDE STRING SEMICOLON')
        def c_include_decl(p):
            spos = p[0].getsourcepos()
            return CIncludeDecl(self.builder, self.module, spos, p[1])

        @self.pg.production('type_decl : TTYPE lvalue COLON typeexpr SEMICOLON')
        def type_decl(p):
            spos = p[0].getsourcepos()
            return TypeDecl(self.builder, self.module, spos, p[1], p[3])

        @self.pg.production('struct_decl : TTYPE lvalue COLON TSTRUCT LBRACE struct_decl_body RBRACE')
        def struct_decl(p):
            spos = p[0].getsourcepos()
            return StructDecl(self.builder, self.module, spos, p[1], p[5], self.decl_mode)

        @self.pg.production('struct_decl_body : struct_decl_body struct_decl_field')
        @self.pg.production('struct_decl_body : struct_decl_field')
        @self.pg.production('struct_decl_body : ')
        def struct_decl_body(p):
            if len(p) == 2:
                spos = p[0].getsourcepos()
                p[0].add(p[1])
                return p[0]
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                sdb = StructDeclBody(self.builder, self.module, spos)
                sdb.add(p[0])
                return sdb
            else:
                spos = None
                return StructDeclBody(self.builder, self.module, spos)

        @self.pg.production('struct_decl_field : IDENT COLON typeexpr SEMICOLON')
        def struct_decl_field(p):
            spos = p[0].getsourcepos()
            return StructField(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('struct_decl_field : IDENT COLON typeexpr EQ expr SEMICOLON')
        def struct_decl_field_init(p):
            spos = p[0].getsourcepos()
            return StructField(self.builder, self.module, spos, p[0], p[2], p[4])

        @self.pg.production('block : block stmt')
        @self.pg.production('block : stmt')
        def block(p):
            if(len(p) == 1):
                spos = p[0].getsourcepos()
                return CodeBlock(self.module, self.builder, spos, p[0])
            else:
                p[0].add(p[1])
                return p[0]

        @self.pg.production('stmt : expr SEMICOLON')
        @self.pg.production('stmt : TRETURN expr SEMICOLON')
        def stmt(p):
            if len(p) == 3:
                spos = p[0].getsourcepos()
                return ReturnStatement(self.builder, self.module, spos, p[1])
            else:
                return p[0]

        
        @self.pg.production('stmt : TRETURN SEMICOLON')
        def stmt_retvoid(p):
            spos = p[0].getsourcepos()
            return ReturnStatement(self.builder, self.module, spos, None)

        @self.pg.production('stmt : IDENT COLON typeexpr SEMICOLON')
        def stmt_var_decl(p):
            spos = p[0].getsourcepos()
            return VarDecl(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : IDENT COLON typeexpr EQ expr SEMICOLON')
        def stmt_var_decl_eq(p):
            spos = p[0].getsourcepos()
            return VarDecl(self.builder, self.module, spos, p[0], p[2], p[4])

        @self.pg.production('stmt : IDENT CEQ expr SEMICOLON')
        def stmt_var_decl_ceq(p):
            spos = p[0].getsourcepos()
            return VarDeclAssign(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : TCONST IDENT CEQ expr SEMICOLON')
        @self.pg.production('stmt : TIMMUT IDENT CEQ expr SEMICOLON')
        def stmt_var_decl_ceq_spec(p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'TCONST':
                return VarDeclAssign(self.builder, self.module, spos, p[1], p[3], 'const')
            elif p[0].gettokentype() == 'TIMMUT':
                return VarDeclAssign(self.builder, self.module, spos, p[1], p[3], 'immut')

        @self.pg.production('stmt : lvalue_expr EQ expr SEMICOLON')
        def stmt_assign(p):
            spos = p[0].getsourcepos()
            return Assignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr ADDEQ expr SEMICOLON')
        def stmt_assign_add(p):
            spos = p[0].getsourcepos()
            return AddAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr SUBEQ expr SEMICOLON')
        def stmt_assign_sub(p):
            spos = p[0].getsourcepos()
            return SubAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr MULEQ expr SEMICOLON')
        def stmt_assign_mul(p):
            spos = p[0].getsourcepos()
            return MulAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('typeexpr : lvalue')
        @self.pg.production('typeexpr : MUL typeexpr')
        @self.pg.production('typeexpr : LBRACKET INT RBRACKET typeexpr')
        def typeexpr(p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return TypeExpr(self.builder, self.module, spos, p[0])
            else:
                if p[0].gettokentype() == 'MUL':
                    p[1].add_pointer_qualifier()
                    return p[1]
                else:
                    size = p[1]
                    p[3].add_array_qualifier(size)
                    return p[3]


        @self.pg.production('stmt : if_stmt')
        def stmt_if(p):
            return p[0]

        @self.pg.production('stmt : switch_stmt')
        def stmt_switch(p):
            return p[0]

        @self.pg.production('stmt : TWHILE expr LBRACE block RBRACE')
        def stmt_while(p):
            spos = p[0].getsourcepos()
            return WhileStatement(self.builder, self.module, spos, p[1], p[3])

        @self.pg.production('if_stmt : TIF expr LBRACE block RBRACE')
        def if_stmt(p):
            spos = p[0].getsourcepos()
            return IfStatement(self.builder, self.module, spos, p[1], p[3])

        @self.pg.production('if_stmt : TIF expr LBRACE block RBRACE TELSE LBRACE block RBRACE')
        def if_stmt_else(p):
            spos = p[0].getsourcepos()
            return IfStatement(self.builder, self.module, spos, p[1], p[3], el=p[7])

        @self.pg.production('switch_stmt : TSWITCH lvalue_expr LBRACE switch_body RBRACE')
        @self.pg.production('switch_stmt : TSWITCH lvalue_expr LBRACE RBRACE')
        def switch_stmt(p):
            spos = p[0].getsourcepos()
            if len(p) == 5:
                return SwitchStatement(self.builder, self.module, spos, p[1], p[3])
            else:
                return SwitchStatement(self.builder, self.module, spos, p[1])

        @self.pg.production('switch_body : switch_body case_expr')
        @self.pg.production('switch_body : switch_body default_case_expr')
        @self.pg.production('switch_body : case_expr')
        @self.pg.production('switch_body : default_case_expr')
        def switch_body(p):
            spos = p[0].getsourcepos()
            if len(p) == 2:
                if isinstance(p[1], SwitchDefaultCase):
                    if p[0].default_case is not None:
                        throw_saturn_error(self.builder, self.module, spos.lineno, spos.colno, 
                            "Cannot have more than one default case in a switch statement."
                        )
                    p[0].set_default(p[1])
                    return p[0]
                else:
                    p[0].add_case(p[1])
                    return p[0]
            else:
                if isinstance(p[0], SwitchDefaultCase):
                    return SwitchBody(self.builder, self.module, spos, [], p[0])
                else:
                    return SwitchBody(self.builder, self.module, spos, [p[0]])

        @self.pg.production('case_expr : case_expr stmt')
        @self.pg.production('case_expr : TCASE expr COLON')
        def case_expr(p):
            if len(p) == 3:
                spos = p[0].getsourcepos()
                return SwitchCase(self.builder, self.module, spos, p[1])
            else:
                p[0].add_stmt(p[1])
                return p[0]

        @self.pg.production('default_case_expr : default_case_expr stmt')
        @self.pg.production('default_case_expr : TDEFAULT COLON')
        def default_case_expr(p):
            if not isinstance(p[0], SwitchDefaultCase):
                spos = p[0].getsourcepos()
                return SwitchDefaultCase(self.builder, self.module, spos)
            else:
                p[0].add_stmt(p[1])
                return p[0]


        @self.pg.production('expr : AND expr')
        def expr_unary(p):
            right = p[1]
            operator = p[0]
            spos = p[0].getsourcepos()
            if operator.gettokentype() == 'AND':
                return AddressOf(self.builder, self.module, spos, right)

        @self.pg.production('expr : expr ADD expr')
        @self.pg.production('expr : expr SUB expr')
        @self.pg.production('expr : expr MUL expr')
        @self.pg.production('expr : expr DIV expr')
        @self.pg.production('expr : expr MOD expr')
        @self.pg.production('expr : expr AND expr')
        @self.pg.production('expr : expr OR expr')
        @self.pg.production('expr : expr XOR expr')
        @self.pg.production('expr : expr BOOLAND expr')
        @self.pg.production('expr : expr BOOLOR expr')
        @self.pg.production('expr : expr BOOLEQ expr')
        @self.pg.production('expr : expr BOOLNEQ expr')
        @self.pg.production('expr : expr BOOLGTE expr')
        @self.pg.production('expr : expr BOOLGT expr')
        @self.pg.production('expr : expr BOOLLTE expr')
        @self.pg.production('expr : expr BOOLLT expr')
        def expr(p):
            left = p[0]
            right = p[2]
            operator = p[1]
            spos = p[0].getsourcepos()
            if operator.gettokentype() == 'ADD':
                return Sum(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'SUB':
                return Sub(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'MUL':
                return Mul(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'DIV':
                return Div(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'MOD':
                return Mod(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'AND':
                return And(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'OR':
                return Or(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'XOR':
                return Xor(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLEQ':
                return BooleanEq(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLNEQ':
                return BooleanNeq(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLGTE':
                return BooleanGte(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLGT':
                return BooleanGt(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLLTE':
                return BooleanLte(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLLT':
                return BooleanLt(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLAND':
                return BoolAnd(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLOR':
                return BoolOr(self.builder, self.module, spos, left, right)

        @self.pg.production('expr : TCAST BOOLLT typeexpr BOOLGT LPAREN expr RPAREN')
        def expr_cast(p):
            spos = p[0].getsourcepos()
            ctype = p[2]
            cexpr = p[5]
            return CastExpr(self.builder, self.module, spos, ctype, cexpr)

        @self.pg.production('func_call : lvalue LPAREN args RPAREN')
        def func_call(p):
            name = p[0]
            spos = p[0].getsourcepos()
            return FuncCall(self.builder, self.module, spos, name, p[2])

        @self.pg.production('func_call : lvalue LPAREN RPAREN')
        def func_call_empty(p):
            name = p[0]
            spos = p[0].getsourcepos()
            return FuncCall(self.builder, self.module, spos, name, [])

        @self.pg.production('expr : func_call')
        def expr_func_call(p):
            return p[0]

        @self.pg.production('expr : TPRINT LPAREN args RPAREN')
        def expr_print_call(p):
            spos = p[0].getsourcepos()
            return Print(self.builder, self.module, spos, p[2])

        @self.pg.production('expr : LPAREN expr RPAREN')
        def expr_parens(p):
            return p[1]
        
        @self.pg.production('args : args COMMA expr')
        @self.pg.production('args : expr')
        def args(p):
            if(len(p)==1):
                return [p[0]]
            else:
                p[0].append(p[2])
                return p[0]

        @self.pg.production('lvalue : IDENT')
        @self.pg.production('lvalue : lvalue CC IDENT')
        def lvalue(p):
            spos = p[0].getsourcepos()
            if(len(p) == 1):
                return LValue(self.builder, self.module, spos, p[0].value)
            else:
                return LValue(self.builder, self.module, spos, p[2].value, p[0])

        @self.pg.production('lvalue : lvalue DOT IDENT')
        def lvalue_dot(p):
            spos = p[0].getsourcepos()
            return LValueField(self.builder, self.module, spos, p[0], p[2].value)

        @self.pg.production('lvalue_expr : lvalue')
        @self.pg.production('lvalue_expr : MUL lvalue')
        @self.pg.production('lvalue_expr : lvalue LBRACKET expr RBRACKET')
        def lvalue_expr(p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return p[0]
            elif len(p) == 4:
                return ElementOf(self.builder, self.module, spos, p[0], p[2])
            else:
                if p[0].gettokentype() == 'MUL':
                    return DerefOf(self.builder, self.module, spos, p[1])

        
        @self.pg.production('lvalue_expr : lvalue DOT func_call')
        def lvalue_expr_method(p):
            spos = p[0].getsourcepos()
            return MethodCall(self.builder, self.module, spos, p[0], p[2].lvalue, p[2].args)

        @self.pg.production('expr : lvalue_expr')
        def expr_lvalue(p):
            return p[0]

        @self.pg.production('expr : struct_literal')
        def expr_struct_literal(p):
            return p[0]

        @self.pg.production('expr : array_literal')
        def expr_array_literal(p):
            return p[0]

        @self.pg.production('struct_literal : typeexpr LBRACE struct_literal_body RBRACE')
        def struct_literal(p):
            spos = p[1].getsourcepos()
            return StructLiteral(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('struct_literal_body : struct_literal_body COMMA struct_literal_element')
        @self.pg.production('struct_literal_body : struct_literal_body COMMA')
        @self.pg.production('struct_literal_body : struct_literal_element')
        @self.pg.production('struct_literal_body : ')
        def struct_literal_body(p):
            if len(p) == 0:
                return StructLiteralBody(self.builder, self.module, None)
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                body = StructLiteralBody(self.builder, self.module, spos)
                body.add_field(p[0].name, p[0].expr)
                return body
            elif len(p) == 2:
                return p[0]
            else:
                p[0].add_field(p[2].name, p[2].expr)
                return p[0]

        @self.pg.production('struct_literal_element : IDENT COLON expr')
        def struct_literal_element(p):
            spos = p[0].getsourcepos()
            return StructLiteralElement(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('array_literal : LBRACKET RBRACKET typeexpr LBRACE array_literal_body RBRACE')
        def array_literal(p):
            spos = p[1].getsourcepos()
            return ArrayLiteral(self.builder, self.module, spos, p[2], p[4])

        @self.pg.production('array_literal_body : array_literal_body COMMA array_literal_element')
        @self.pg.production('array_literal_body : array_literal_body COMMA')
        @self.pg.production('array_literal_body : array_literal_element')
        @self.pg.production('array_literal_body : ')
        def array_literal_body(p):
            if len(p) == 0:
                return ArrayLiteralBody(self.builder, self.module, None)
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                body = ArrayLiteralBody(self.builder, self.module, spos)
                body.add_element(p[0].expr)
                return body
            elif len(p) == 2:
                return p[0]
            else:
                p[0].add_element(p[2].expr)
                return p[0]

        @self.pg.production('array_literal_element : expr')
        def array_literal_element(p):
            spos = p[0].getsourcepos()
            return ArrayLiteralElement(self.builder, self.module, spos, p[0])

        @self.pg.production('expr : number')
        def expr_number(p):
            return p[0]

        @self.pg.production('number : INT')
        @self.pg.production('number : UINT')
        @self.pg.production('number : LONGINT')
        @self.pg.production('number : ULONGINT')
        @self.pg.production('number : BYTE')
        @self.pg.production('number : FLOAT')
        @self.pg.production('number : DOUBLE')
        def number(p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'INT':
                return Integer(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'UINT':
                return UInteger(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'LONGINT':
                return Integer64(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'ULONGINT':
                return UInteger64(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'BYTE':
                return Byte(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'FLOAT':
                return Float(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'DOUBLE':
                return Double(self.builder, self.module, spos, p[0].value)
        
        @self.pg.production('expr : STRING')
        def expr_string(p):
            spos = p[0].getsourcepos()
            return StringLiteral(self.builder, self.module, spos, p[0].value)

        @self.pg.production('expr : MLSTRING')
        def expr_mlstring(p):
            spos = p[0].getsourcepos()
            return MultilineStringLiteral(self.builder, self.module, spos, p[0].value)

        @self.pg.production('expr : boolexpr')
        def expr_bool(p):
            return p[0]

        @self.pg.production('boolexpr : TTRUE')
        @self.pg.production('boolexpr : TFALSE')
        def expr_bool_literal(p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'TTRUE':
                return Boolean(self.builder, self.module, spos, True)
            else:
                return Boolean(self.builder, self.module, spos, False)

        @self.pg.error
        def error_handle(token):
            text_input = self.builder.filestack[self.builder.filestack_idx]
            lines = text_input.splitlines()
            if token.getsourcepos() is None:
                raise RuntimeError("%s (?:?) Ran into a(n) %s where it wasn't expected." % (
                    self.module.filestack[self.module.filestack_idx],
                    token.gettokentype(), 
                ))
            lineno = token.getsourcepos().lineno
            if lineno > 1:
                line1 = lines[lineno - 2]
                line2 = lines[lineno - 1]
                print("%s\n%s\n%s^" % (line1, line2, "~" * (token.getsourcepos().colno - 1)))
            else:
                line1 = lines[lineno - 1]
                print("%s\n%s^" % (line1, "~" * (token.getsourcepos().colno - 1)))
            raise RuntimeError("%s (%d:%d) Ran into a(n) %s where it wasn't expected." % (
                self.module.filestack[self.module.filestack_idx],
                token.getsourcepos().lineno,
                token.getsourcepos().colno,
                token.gettokentype(), 
            ))

    def get_parser(self):
        return self.pg.build()