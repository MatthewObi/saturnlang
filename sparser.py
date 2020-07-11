from rply import ParserGenerator, Token
from ast import ( 
    Program, CodeBlock, Statement, ReturnStatement, 
    Sum, Sub, Mul, Div, And, Or, Print, 
    Number, Integer, Integer64, Byte, StringLiteral, 
    FuncDecl, FuncDeclExtern, FuncArgList, FuncArg, GlobalVarDecl, VarDecl, VarDeclAssign, 
    LValue, FuncCall, Assignment, AddAssignment, SubAssignment, MulAssignment, 
    Boolean, BooleanEq, BooleanNeq, BooleanGt, IfStatement, WhileStatement
)


class Parser():
    def __init__(self, module, builder):
        self.pg = ParserGenerator(
            # A list of all token names accepted by the parser.
            ['INT', 'LONGINT', 'BYTE', 'STRING', 'IDENT', 'TPRINT', 'DOT', 'TRETURN', 'LPAREN', 'RPAREN',
             'SEMICOLON', 'ADD', 'SUB', 'MUL', 'DIV', 'AND', 'OR',
             'TFN', 'COLON', 'LBRACE', 'RBRACE', 'COMMA', 'EQ', 'CEQ', 'ADDEQ', 'SUBEQ', 'MULEQ',
             'TIF', 'TELSE', 'TWHILE',
             'BOOLEQ', 'BOOLNEQ', 'BOOLGT', 'TTRUE', 'TFALSE'],

             precedence=[
                ('left', ['ADD', 'SUB']),
                ('left', ['MUL', 'DIV'])
            ]
        )
        self.module = module
        self.builder = builder

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
        def gstmt(p):
           return p[0]

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN COLON typeexpr LBRACE block RBRACE')
        def func_decl(p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            block = p[8]
            spos = p[0].getsourcepos()
            return FuncDecl(self.builder, self.module, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN LBRACE block RBRACE')
        def func_decl_retvoid(p):
            name = p[1]
            declargs = p[3]
            rtype = Token('IDENT', 'void')
            block = p[6]
            spos = p[0].getsourcepos()
            return FuncDecl(self.builder, self.module, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN LBRACE RBRACE')
        def func_decl_retvoid_empty(p):
            name = p[1]
            declargs = p[3]
            rtype = Token('IDENT', 'void')
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

        @self.pg.production('stmt : lvalue EQ expr SEMICOLON')
        def stmt_assign(p):
            spos = p[0].getsourcepos()
            return Assignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue ADDEQ expr SEMICOLON')
        def stmt_assign_add(p):
            spos = p[0].getsourcepos()
            return AddAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue SUBEQ expr SEMICOLON')
        def stmt_assign_sub(p):
            spos = p[0].getsourcepos()
            return SubAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue MULEQ expr SEMICOLON')
        def stmt_assign_mul(p):
            spos = p[0].getsourcepos()
            return MulAssignment(self.builder, self.module, spos, p[0], p[2])

        @self.pg.production('typeexpr : IDENT')
        def typeexpr(p):
            return p[0]

        @self.pg.production('stmt : if_stmt')
        def stmt_if(p):
            return p[0]

        @self.pg.production('stmt : TWHILE LPAREN expr RPAREN LBRACE block RBRACE')
        def stmt_while(p):
            spos = p[0].getsourcepos()
            return WhileStatement(self.builder, self.module, spos, p[2], p[5])

        @self.pg.production('if_stmt : TIF LPAREN expr RPAREN LBRACE block RBRACE')
        def if_stmt(p):
            spos = p[0].getsourcepos()
            return IfStatement(self.builder, self.module, spos, p[2], p[5])

        @self.pg.production('if_stmt : TIF LPAREN expr RPAREN LBRACE block RBRACE TELSE LBRACE block RBRACE')
        def if_stmt_else(p):
            spos = p[0].getsourcepos()
            return IfStatement(self.builder, self.module, spos, p[2], p[5], el=p[9])

        @self.pg.production('expr : expr ADD expr')
        @self.pg.production('expr : expr SUB expr')
        @self.pg.production('expr : expr MUL expr')
        @self.pg.production('expr : expr DIV expr')
        @self.pg.production('expr : expr AND expr')
        @self.pg.production('expr : expr OR expr')
        @self.pg.production('expr : expr BOOLEQ expr')
        @self.pg.production('expr : expr BOOLNEQ expr')
        @self.pg.production('expr : expr BOOLGT expr')
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
            elif operator.gettokentype() == 'AND':
                return And(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'OR':
                return Or(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLEQ':
                return BooleanEq(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLNEQ':
                return BooleanNeq(self.builder, self.module, spos, left, right)
            elif operator.gettokentype() == 'BOOLGT':
                return BooleanGt(self.builder, self.module, spos, left, right)

        @self.pg.production('expr : lvalue LPAREN args RPAREN')
        def expr_func_call(p):
            name = p[0]
            spos = p[0].getsourcepos()
            return FuncCall(self.builder, self.module, spos, name, p[2])

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
        @self.pg.production('lvalue : lvalue DOT IDENT')
        def lvalue(p):
            spos = p[0].getsourcepos()
            if(len(p) == 1):
                return LValue(self.builder, self.module, spos, p[0].value)
            else:
                return LValue(self.builder, self.module, spos, p[2], p[0].value)

        @self.pg.production('expr : lvalue')
        def expr_lvalue(p):
            return p[0]

        @self.pg.production('expr : number')
        def expr_number(p):
            return p[0]

        @self.pg.production('number : INT')
        @self.pg.production('number : LONGINT')
        @self.pg.production('number : BYTE')
        def number(p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'INT':
                return Integer(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'LONGINT':
                return Integer64(self.builder, self.module, spos, p[0].value)
            elif p[0].gettokentype() == 'BYTE':
                return Byte(self.builder, self.module, spos, p[0].value)
        
        @self.pg.production('expr : STRING')
        def expr_string(p):
            spos = p[0].getsourcepos()
            return StringLiteral(self.builder, self.module, spos, p[0].value)

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

        # @self.pg.error
        # def error_handle(token):
        #     raise ValueError("Ran into a %s where it wasn't expected. (%s)" % (token.gettokentype(), token.getsourcepos()))

    def get_parser(self):
        return self.pg.build()