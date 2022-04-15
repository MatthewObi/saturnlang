from rply import ParserGenerator, Token

from ast import (
    Program, CodeBlock, Statement, ReturnStatement, BreakStatement, ContinueStatement, FallthroughStatement,
    DeferStatement,
    PackageDecl, ImportDecl, ImportDeclExtern, CIncludeDecl, CDeclareDecl, BinaryInclude,
    Attribute, AttributeList, ValueDecl,
    TypeDecl, StructField, StructDeclBody, StructDecl, StructGenericDecl, EnumDecl, EnumBody,
    Sum, Sub, Mul, Div, Mod, ShiftLeft, ShiftRight, And, Or, Xor, BinaryNot, BoolAnd, BoolOr, BoolNot, Negate, Print,
    AddressOf, DerefOf, ElementOf, TupleElementOf,
    Integer, UInteger, Integer64, UInteger64, Integer16, UInteger16, SByte,
    Float, Double, HalfFloat, Quad, Byte, StringLiteral, MultilineStringLiteral,
    StructLiteralElement, StructLiteralBody, StructLiteral, Null,
    ArrayLiteralElement, ArrayLiteralBody, ArrayLiteral, TypeExpr, TupleTypeExpr, OptionalTypeExpr, FuncTypeExpr,
    TupleLiteralElement, TupleLiteralBody, TupleLiteral,
    GenericTypeArg, CaptureExpr,
    FuncDecl, FuncDeclExtern, FuncArgList, FuncArg, GlobalVarDecl, VarDecl, VarDeclAssign, LambdaExpr,
    MethodDecl, MethodDeclExtern,
    LValue, LValueField, LValueGeneric, FuncCall, LambdaCall, MethodCall, CastExpr, SelectExpr,
    MakeExpr, MakeSharedExpr, MakeUnsafeExpr, MakeUnsafeArrayExpr, DestroyExpr,
    Assignment, AddAssignment, SubAssignment, MulAssignment, ModAssignment, AndAssignment, OrAssignment, XorAssignment,
    PrefixIncrementOp, PrefixDecrementOp,
    Boolean, Spaceship, BooleanEq, BooleanNeq, BooleanGte, BooleanGt, BooleanLte, BooleanLt,
    IfStatement, WhileStatement, DoWhileStatement, SwitchCase, SwitchDefaultCase, SwitchBody, SwitchStatement,
    ForStatement, IterExpr, PointerTypeExpr, ReferenceTypeExpr, ArrayTypeExpr, HVectorTypeExpr, SliceTypeExpr,
)
from serror import throw_saturn_error


class ParserState:
    def __init__(self, builder, module, package, decl_mode=False):
        self.module = module
        self.builder = builder
        self.package = package
        self.decl_mode = decl_mode


class Parser:
    def __init__(self):
        self.pg = ParserGenerator(
            # A list of all token names accepted by the parser.
            ['TPACKAGE', 'TIMPORT', 'TCINCLUDE', 'TCDECLARE', 'TBININCLUDE',
             'INT', 'UINT', 'LONGINT', 'ULONGINT', 'SBYTE', 'BYTE', 'SHORTINT', 'USHORTINT',
             'HALF', 'FLOAT', 'DOUBLE', 'QUAD', 'STRING', 'MLSTRING',
             'HEXINT', 'HEXUINT', 'HEXLINT', 'HEXULINT', 'HEXSINT', 'HEXUSINT', 'HEXBINT', 'HEXSBINT',
             'IDENT', 'TPRINT', 'DOT', 'RARROW', 'TRETURN', 'LVEC', 'RVEC',
             'LPAREN', 'RPAREN', 'LBRACKET', 'RBRACKET', 'LDBRACKET', 'RDBRACKET', 'LANGLE', 'RANGLE',
             'SEMICOLON', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'LSHFT', 'RSHFT',
             'AND', 'OR', 'XOR', 'BOOLAND', 'BOOLOR', 'BINNOT', 'QMARK', 'INC', 'DEC',
             'TFN', 'TPUB', 'TPRIV', 'COLON', 'LBRACE', 'RBRACE', 'COMMA', 'CC',
             'EQ', 'CEQ', 'ADDEQ', 'SUBEQ', 'MULEQ', 'MODEQ', 'ANDEQ', 'OREQ', 'XOREQ',
             'TIF', 'TELSE', 'TWHILE', 'TTHEN', 'TDO', 'TBREAK', 'TCONTINUE', 'TFALLTHROUGH', 'TDEFER',
             'TSWITCH', 'TCASE', 'TDEFAULT', 'TFOR', 'TIN', 'DOTDOT', 'ELIPSES',
             'TCONST', 'TIMMUT', 'TMUT', 'TREADONLY', 'TNOCAPTURE', 'TATOMIC', 
             'TTYPE', 'TSTRUCT', 'TENUM', 'TTUPLE', 'TCAST', 'TOPERATOR',
             'TMAKE', 'TDESTROY', 'TSHARED', 'TOWNED', 'TUNSAFE', 'TNEW',
             'BOOLEQ', 'BOOLNEQ', 'BOOLGT', 'BOOLLT', 'BOOLGTE', 'BOOLLTE', 'SPACESHIP', 'BOOLNOT',
             'TTRUE', 'TFALSE', 'TNULL'],

             precedence=[
                ('left', ['TIF', 'TELSE']),
                ('left', ['DOTDOT']),
                ('left', ['BOOLOR']),
                ('left', ['BOOLAND']),
                ('left', ['OR']),
                ('left', ['XOR']),
                ('left', ['AND']),
                ('left', ['BOOLEQ', 'BOOLNEQ', 'BOOLGT', 'BOOLLT', 'BOOLGTE', 'BOOLLTE', 'SPACESHIP']),
                ('left', ['LSHFT', 'RSHFT']),
                ('left', ['ADD', 'SUB']),
                ('left', ['MUL', 'DIV', 'MOD']),
                ('right', ['INC', 'DEC']),
                ('right', ['BOOLNOT', 'BINNOT']),
                ('left', ['LBRACKET', 'RBRACKET', 'DOT']),
            ]
        )

    def parse(self):
        @self.pg.production('program : gstmt_list')
        @self.pg.production('program : ')
        def program(state, p):
            if len(p) == 0:
                return Program(state.package)
            else:
                prog = Program(state.package, p[0][0])
                for gstmt in p[0][1:]:
                    prog.add(gstmt)
                return prog

        @self.pg.production('gstmt_list : gstmt_decl')
        @self.pg.production('gstmt_list : gstmt_list gstmt_decl')
        def gstmt_list(state, p):
            if len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[1])
                return p[0]

        @self.pg.production('gstmt_decl : attribute_decl gstmt_item')
        @self.pg.production('gstmt_decl : gstmt_item')
        def gstmt_decl_attr(state, p):
            if len(p) == 1:
                return p[0]
            else:
                p[1].add_attribute_list(p[0])
                return p[1]

        @self.pg.production('gstmt_item : visibility_decl gstmt')
        @self.pg.production('gstmt_item : gstmt')
        def gstmt_decl(state, p):
            if len(p) == 2:
                p[1].add_visibility(p[0])
                return p[1]
            else:
                return p[0]

        @self.pg.production('gstmt : func_decl')
        @self.pg.production('gstmt : func_decl_extern')
        @self.pg.production('gstmt : gvar_decl')
        @self.pg.production('gstmt : method_decl')
        @self.pg.production('gstmt : pack_decl')
        @self.pg.production('gstmt : import_decl')
        @self.pg.production('gstmt : binary_include_decl')
        @self.pg.production('gstmt : c_include_decl')
        @self.pg.production('gstmt : c_declare_decl')
        @self.pg.production('gstmt : type_decl')
        @self.pg.production('gstmt : struct_decl')
        @self.pg.production('gstmt : enum_decl')
        def gstmt(state, p):
            return p[0]

        @self.pg.production('visibility_decl : TPUB | TPRIV')
        def visibility_decl(state, p):
            return p[0]

        @self.pg.production('attribute_decl : LDBRACKET attribute_param_list RDBRACKET')
        def attribute_decl(state, p):
            return p[1]

        @self.pg.production('attribute_param_list : attribute_param_list COMMA attribute_param')
        @self.pg.production('attribute_param_list : attribute_param_list COMMA')
        @self.pg.production('attribute_param_list : attribute_param')
        def attribute_param_list(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                attr_list = AttributeList(state.builder, state.module, state.package, spos)
                attr_list.add_attr(p[0])
                return attr_list
            elif len(p) == 2:
                return p[0]
            else:
                attr_list = p[0]
                attr_list.add_attr(p[2])
                return attr_list

        @self.pg.production('attribute_param : lvalue LPAREN args RPAREN')
        @self.pg.production('attribute_param : lvalue LPAREN RPAREN')
        @self.pg.production('attribute_param : lvalue')
        def attribute_param(state, p):
            name = p[0]
            if len(p) > 3:
                args = p[2]
            else:
                args = None
            spos = p[0].getsourcepos()
            return Attribute(state.builder, state.module, state.package, spos, name, args)

        @self.pg.production('value_decl : storage_spec_list IDENT')
        @self.pg.production('value_decl : IDENT')
        def value_decl(state, p):
            if len(p) == 1:
                spos = p[0].getsourcepos()
                return ValueDecl(state.builder, state.module, state.package, spos, p[0])
            else:
                spos = p[1].getsourcepos()
                return ValueDecl(state.builder, state.module, state.package, spos, p[1], [s[0] for s in p[0]])

        @self.pg.production('value_decl : storage_spec_list AND IDENT')
        @self.pg.production('value_decl : AND IDENT')
        def value_decl_ref(state, p):
            if len(p) == 2:
                spos = p[0].getsourcepos()
                return ValueDecl(state.builder, state.module, state.package, spos, p[1], is_ref=True)
            else:
                spos = p[1].getsourcepos()
                return ValueDecl(state.builder, state.module, state.package, spos, p[2], [s[0] for s in p[0]],
                                 is_ref=True)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN COLON typeexpr block')
        def func_decl(state, p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            block = p[7]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return FuncDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args RPAREN block')
        def func_decl_retvoid(state, p):
            name = p[1]
            declargs = p[3]
            spostexpr = p[5].getsourcepos()
            rtype = TypeExpr(state.builder, state.module, state.package,
                             spostexpr,
                             LValue(state.builder, state.module, state.package, spostexpr, "void")
                             )
            block = p[5]
            spos = p[0].getsourcepos()
            return FuncDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl_extern : TFN IDENT LPAREN decl_args RPAREN COLON typeexpr SEMICOLON')
        def func_decl_extern(state, p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            spos = p[0].getsourcepos()
            return FuncDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args COMMA ELIPSES IDENT RPAREN COLON typeexpr block')
        def func_decl_varargs(state, p):
            name = p[1]
            declargs = p[3]
            rtype = p[6]
            block = p[7]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return FuncDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl : TFN IDENT LPAREN decl_args COMMA ELIPSES IDENT RPAREN block')
        def func_decl_retvoid_varargs(state, p):
            name = p[1]
            declargs = p[3]
            spostexpr = p[5].getsourcepos()
            rtype = TypeExpr(state.builder, state.module, state.package,
                             spostexpr,
                             LValue(state.builder, state.module, state.package, spostexpr, "void")
                             )
            block = p[5]
            spos = p[0].getsourcepos()
            return FuncDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs)

        @self.pg.production('func_decl_extern : TFN IDENT LPAREN decl_args COMMA ELIPSES RPAREN COLON typeexpr SEMICOLON')
        def func_decl_extern_varargs(state, p):
            name = p[1]
            declargs = p[3]
            rtype = p[8]
            spos = p[0].getsourcepos()
            return FuncDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, var_arg=True)

        @self.pg.production('decl_args : decl_args COMMA decl_arg')
        @self.pg.production('decl_args : decl_arg')
        @self.pg.production('decl_args : ')
        def decl_args(state, p):
            if len(p) == 0:
                return FuncArgList(state.builder, state.module, state.package, None)
            if len(p) == 1:
                spos = p[0].getsourcepos()
                return FuncArgList(state.builder, state.module, state.package, spos, p[0])
            else:
                p[0].add(p[2])
                return p[0]

        @self.pg.production('decl_arg : value_decl COLON typeexpr')
        def decl_arg(state, p):
            name = p[0].name
            vtype = p[2]
            quals = None if not p[0].qualifiers else p[0].qualifiers
            spos = p[0].getsourcepos()
            return FuncArg(state.builder, state.module, state.package, spos, name, vtype, qualifiers=quals)

        @self.pg.production('decl_arg : value_decl COLON typeexpr EQ expr')
        def decl_arg_default(state, p):
            name = p[0].name
            vtype = p[2]
            quals = None if not p[0].qualifiers else p[0].qualifiers
            spos = p[0].getsourcepos()
            default_value = p[4]
            return FuncArg(state.builder, state.module, state.package, spos, name, vtype, qualifiers=quals,
                           default_value=default_value)

        @self.pg.production('gvar_decl : value_decl COLON typeexpr SEMICOLON')
        def gvar_decl(state, p):
            name = p[0].name
            vtype = p[2]
            quals = None if not p[0].qualifiers else p[0].qualifiers
            spos = p[0].getsourcepos()
            return GlobalVarDecl(state.builder, state.module, state.package, spos, name, vtype, spec=quals)

        @self.pg.production('gvar_decl : value_decl COLON typeexpr EQ expr SEMICOLON')
        def gvar_decl_init(state, p):
            name = p[0].name
            vtype = p[2]
            quals = None if not p[0].qualifiers else p[0].qualifiers
            initval = p[4]
            spos = p[0].getsourcepos()
            return GlobalVarDecl(state.builder, state.module, state.package, spos, name, vtype, initval, spec=quals)

        @self.pg.production('binary_include_decl : value_decl CEQ TBININCLUDE LPAREN STRING RPAREN SEMICOLON')
        def binary_include_decl(state, p):
            spos = p[0].getsourcepos()
            return BinaryInclude(state.builder, state.module, state.package, spos, p[4], p[0].name)

        @self.pg.production('method_decl : TFN LPAREN MUL lvalue RPAREN IDENT LPAREN decl_args RPAREN COLON typeexpr block')
        def method_decl(state, p):
            struct = p[3]
            name = p[5]
            declargs = p[7]
            rtype = p[10]
            block = p[11]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return MethodDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs, struct)
            return MethodDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, struct)

        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TNEW LPAREN decl_args RPAREN COLON typeexpr block')
        def method_decl_ctor(state, p):
            struct = p[3]
            name = Token('IDENT', 'new')
            declargs = p[7]
            rtype = p[10]
            block = p[11]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return MethodDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs,
                                  struct)
            return MethodDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, struct)

        @self.pg.production('method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR EQ LPAREN decl_args RPAREN COLON typeexpr block')
        def method_decl_assign(state, p):
            struct = p[3]
            name = Token('IDENT', 'operator.assign')
            declargs = p[8]
            rtype = p[11]
            block = p[12]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return MethodDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs, struct)
            return MethodDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, struct)

        @self.pg.production('method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR SPACESHIP LPAREN decl_args RPAREN COLON typeexpr block')
        def method_decl_spaceship(state, p):
            struct = p[3]
            name = Token('IDENT', 'operator.spaceship')
            declargs = p[8]
            rtype = p[11]
            block = p[12]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return MethodDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs, struct)
            return MethodDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, struct)

        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR ADD LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR SUB LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR MUL LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR DIV LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR MOD LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR AND LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR OR LPAREN decl_args RPAREN COLON typeexpr block')
        @self.pg.production(
            'method_decl : TFN LPAREN MUL lvalue RPAREN TOPERATOR XOR LPAREN decl_args RPAREN COLON typeexpr block')
        def method_decl_bin(state, p):
            struct = p[3]
            if p[6].gettokentype() == 'ADD':
                name = Token('IDENT', 'operator.add')
            elif p[6].gettokentype() == 'SUB':
                name = Token('IDENT', 'operator.sub')
            elif p[6].gettokentype() == 'MUL':
                name = Token('IDENT', 'operator.mul')
            elif p[6].gettokentype() == 'DIV':
                name = Token('IDENT', 'operator.div')
            elif p[6].gettokentype() == 'MOD':
                name = Token('IDENT', 'operator.mod')
            elif p[6].gettokentype() == 'AND':
                name = Token('IDENT', 'operator.and')
            elif p[6].gettokentype() == 'OR':
                name = Token('IDENT', 'operator.or')
            elif p[6].gettokentype() == 'XOR':
                name = Token('IDENT', 'operator.xor')
            else:
                name = Token('IDENT', 'operator.undefined')
            declargs = p[8]
            rtype = p[11]
            block = p[12]
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return MethodDecl(state.builder, state.module, state.package, spos, name, rtype, block, declargs,
                                  struct)
            return MethodDeclExtern(state.builder, state.module, state.package, spos, name, rtype, declargs, struct)

        @self.pg.production('pack_decl : TPACKAGE lvalue SEMICOLON')
        def pack_decl(state, p):
            spos = p[0].getsourcepos()
            return PackageDecl(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('import_decl : TIMPORT lvalue SEMICOLON')
        def import_decl(state, p):
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return ImportDecl(state.builder, state.module, state.package, spos, p[1])
            return ImportDeclExtern(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('import_decl : TIMPORT lvalue CC MUL SEMICOLON')
        def import_decl_all(state, p):
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return ImportDecl(state.builder, state.module, state.package, spos, p[1], import_all=True)
            return ImportDeclExtern(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('import_decl : TIMPORT lvalue CC LBRACE symbols_list RBRACE SEMICOLON')
        def import_decl_symbols(state, p):
            spos = p[0].getsourcepos()
            if not state.decl_mode:
                return ImportDecl(state.builder, state.module, state.package, spos, p[1], symbols_to_import=p[4])
            return ImportDeclExtern(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('symbols_list : lvalue')
        @self.pg.production('symbols_list : symbols_list COMMA lvalue')
        @self.pg.production('symbols_list : symbols_list COMMA')
        def symbols_list(state, p):
            if len(p) == 1:
                return [p[0]]
            elif len(p) == 2:
                p[0].append(p[1])
                return p[0]
            else:
                return p[0]

        @self.pg.production('c_include_decl : TCINCLUDE STRING SEMICOLON')
        def c_include_decl(state, p):
            spos = p[0].getsourcepos()
            return CIncludeDecl(state.builder, state.module, state.package, spos, p[1], decl_mode=state.decl_mode)

        @self.pg.production('c_declare_decl : TCDECLARE gstmt_list_body')
        def c_declare_decl(state, p):
            spos = p[0].getsourcepos()
            return CDeclareDecl(state.builder, state.module, state.package, spos, p[2])

        @self.pg.production('type_decl : TTYPE lvalue COLON typeexpr SEMICOLON')
        def type_decl(state, p):
            spos = p[0].getsourcepos()
            return TypeDecl(state.builder, state.module, state.package, spos, p[1], p[3])

        @self.pg.production('struct_decl : TTYPE lvalue COLON TSTRUCT struct_decl_body')
        def struct_decl(state, p):
            spos = p[0].getsourcepos()
            return StructDecl(state.builder, state.module, state.package, spos, p[1], p[4], state.decl_mode)

        @self.pg.production('struct_decl : TTYPE lvalue COLON TSTRUCT SEMICOLON')
        def struct_decl_opaque(state, p):
            spos = p[0].getsourcepos()
            return StructDecl(state.builder, state.module, state.package, spos, p[1], None, state.decl_mode)

        @self.pg.production('struct_decl : TTYPE generic_type_decl lvalue COLON TSTRUCT struct_decl_body')
        def struct_decl_generic(state, p):
            spos = p[0].getsourcepos()
            return StructGenericDecl(state.builder, state.module, state.package, spos, p[2], p[1], p[5], state.decl_mode)

        @self.pg.production('struct_decl_body : LBRACE struct_decl_list RBRACE')
        @self.pg.production('struct_decl_body : LBRACE RBRACE')
        def struct_decl_body(state, p):
            if len(p) == 2:
                spos = p[1].getsourcepos()
                return StructDeclBody(state.builder, state.module, state.package, spos)
            else:
                return p[1]

        @self.pg.production('struct_decl_list : struct_decl_list struct_decl_field')
        @self.pg.production('struct_decl_list : struct_decl_field')
        def struct_decl_list(state, p):
            if len(p) == 2:
                spos = p[0].getsourcepos()
                p[0].add(p[1])
                return p[0]
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                sdb = StructDeclBody(state.builder, state.module, state.package, spos)
                sdb.add(p[0])
                return sdb
            else:
                spos = None
                return StructDeclBody(state.builder, state.module, state.package, spos)

        @self.pg.production('struct_decl_field : value_decl COLON typeexpr SEMICOLON')
        def struct_decl_field(state, p):
            spos = p[0].getsourcepos()
            spec = None if not p[0].qualifiers else p[0].qualifiers
            return StructField(state.builder, state.module, state.package, spos,
                               p[0].name, p[2], p[0].qualifiers)

        @self.pg.production('struct_decl_field : value_decl COLON typeexpr EQ expr SEMICOLON')
        def struct_decl_field_init(state, p):
            spos = p[0].getsourcepos()
            spec = None if not p[0].qualifiers else p[0].qualifiers
            return StructField(state.builder, state.module, state.package, spos,
                               p[0].name, p[2], spec, p[4])

        @self.pg.production('generic_type_decl : LANGLE generic_type_list RANGLE')
        def generic_type_decl(state, p):
            return p[1]

        @self.pg.production('generic_type_list : generic_type_list COMMA generic_type_element')
        @self.pg.production('generic_type_list : generic_type_list COMMA')
        @self.pg.production('generic_type_list : generic_type_element')
        def generic_type_list(state, p):
            if len(p) == 1:
                return [p[0]]
            elif len(p) == 2:
                return p[0]
            else:
                p[0].append(p[2])
                return p[0]

        @self.pg.production('generic_type_element : TTYPE IDENT')
        @self.pg.production('generic_type_element : TTYPE IDENT EQ lvalue')
        def generic_type_element(state, p):
            spos = p[0].getsourcepos()
            return GenericTypeArg(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('enum_decl : TTYPE lvalue COLON TENUM enum_decl_body')
        def enum_decl(state, p):
            spos = p[0].getsourcepos()
            return EnumDecl(state.builder, state.module, state.package, spos, p[1], p[5], None, state.decl_mode)

        @self.pg.production('enum_decl : TTYPE lvalue COLON TENUM LPAREN typeexpr RPAREN enum_decl_body')
        def enum_decl_custom_type(state, p):
            spos = p[0].getsourcepos()
            return EnumDecl(state.builder, state.module, state.package, spos, p[1], p[7], p[5], state.decl_mode)

        @self.pg.production('enum_decl_body : LBRACE enum_decl_list RBRACE')
        @self.pg.production('enum_decl_body : LBRACE RBRACE')
        def enum_decl_body(state, p):
            if len(p) == 2:
                spos = p[1].getsourcepos()
                return EnumBody(state.builder, state.module, state.package, spos)
            else:
                return p[1]

        @self.pg.production('enum_decl_list : lvalue')
        @self.pg.production('enum_decl_list : lvalue EQ expr')
        @self.pg.production('enum_decl_list : enum_decl_list COMMA lvalue')
        @self.pg.production('enum_decl_list : enum_decl_list COMMA lvalue EQ expr')
        @self.pg.production('enum_decl_list : enum_decl_list COMMA')
        def enum_decl_body(state, p):
            spos = p[0].getsourcepos()
            if isinstance(p[0], EnumBody):
                if len(p) == 2:
                    return p[0]
                elif len(p) == 3:
                    p[0].add_value(p[2])
                    return p[0]
                else:
                    p[0].add_value(p[2], p[4])
                    return p[0]
            else:
                enum_body = EnumBody(state.builder, state.module, state.package, spos)
                if len(p) == 1:
                    enum_body.add_value(p[0])
                else:
                    enum_body.add_value(p[0], p[2])
                return enum_body

        @self.pg.production('gstmt_list_body : LBRACE RBRACE')
        @self.pg.production('gstmt_list_body : LBRACE gstmt_list RBRACE')
        def gstmt_list_body(state, p):
            if len(p) == 2:
                return []
            else:
                return p[1]

        @self.pg.production('stmt_list : stmt_list stmt_or_block')
        @self.pg.production('stmt_list : stmt_or_block')
        def stmt_list(state, p):
            if len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[1])
                return p[0]

        @self.pg.production('block : LBRACE stmt_list RBRACE')
        @self.pg.production('block : LBRACE RBRACE')
        def block(state, p):
            if len(p) == 2:
                spos = p[1].getsourcepos()
                return CodeBlock(state.builder, state.module, state.package, spos,
                                 Statement(state.builder, state.module, state.package, spos, None))
            else:
                stmt_list = p[1]
                spos = p[1][0].getsourcepos()
                code_block = CodeBlock(state.builder, state.module, state.package, spos, stmt_list[0])
                for stmt in stmt_list[1:]:
                    code_block.add(stmt)
                return code_block

        @self.pg.production('block : capture_expr LBRACE stmt_list RBRACE')
        @self.pg.production('block : capture_expr LBRACE RBRACE')
        def block_capture(state, p):
            if len(p) == 3:
                spos = p[2].getsourcepos()
                return CodeBlock(state.builder, state.module, state.package, spos,
                                 Statement(state.builder, state.module, state.package, spos, None),
                                 capture=p[0])
            else:
                stmt_list = p[2]
                spos = p[2][0].getsourcepos()
                code_block = CodeBlock(state.builder, state.module, state.package, spos, stmt_list[0], capture=p[0])
                for stmt in stmt_list[1:]:
                    code_block.add(stmt)
                return code_block

        @self.pg.production('stmt : SEMICOLON')
        def stmt_empty(state, p):
            spos = p[0].getsourcepos()
            return Statement(state.builder, state.module, state.package, spos, None)

        @self.pg.production('stmt : expr SEMICOLON')
        @self.pg.production('stmt : TRETURN expr SEMICOLON')
        def stmt(state, p):
            if len(p) == 3:
                spos = p[0].getsourcepos()
                return ReturnStatement(state.builder, state.module, state.package, spos, p[1])
            else:
                return p[0]
        
        @self.pg.production('stmt : TRETURN SEMICOLON')
        def stmt_retvoid(state, p):
            spos = p[0].getsourcepos()
            return ReturnStatement(state.builder, state.module, state.package, spos, None)

        @self.pg.production('stmt : TBREAK SEMICOLON')
        def stmt_break(state, p):
            spos = p[0].getsourcepos()
            return BreakStatement(state.builder, state.module, state.package, spos, None)

        @self.pg.production('stmt : TCONTINUE SEMICOLON')
        def stmt_continue(state, p):
            spos = p[0].getsourcepos()
            return ContinueStatement(state.builder, state.module, state.package, spos, None)

        @self.pg.production('stmt : TFALLTHROUGH SEMICOLON')
        def stmt_fallthrough(state, p):
            spos = p[0].getsourcepos()
            return FallthroughStatement(state.builder, state.module, state.package, spos, None)

        @self.pg.production('stmt : TDEFER stmt_or_block')
        def stmt_defer(state, p):
            spos = p[0].getsourcepos()
            if not isinstance(p[1], CodeBlock):
                _block = CodeBlock(state.builder, state.module, state.package, p[1].getsourcepos(), p[1])
            else:
                _block = p[0]
            return DeferStatement(state.builder, state.module, state.package, spos, _block)

        @self.pg.production('stmt : value_decl COLON typeexpr SEMICOLON')
        def stmt_var_decl(state, p):
            spos = p[0].getsourcepos()
            spec = None if not p[0].qualifiers else p[0].qualifiers
            return VarDecl(state.builder, state.module, state.package, spos, p[0].name, p[2], spec=spec)

        @self.pg.production('stmt : value_decl COLON typeexpr EQ expr SEMICOLON')
        def stmt_var_decl_eq(state, p):
            spos = p[0].getsourcepos()
            spec = None if not p[0].qualifiers else p[0].qualifiers
            return VarDecl(state.builder, state.module, state.package, spos, p[0].name, p[2], p[4], spec=spec)

        @self.pg.production('storage_spec_list : storage_spec_list storage_spec')
        @self.pg.production('storage_spec_list : storage_spec')
        def storage_spec_list(state, p):
            if len(p) == 0:
                return []
            elif len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[1])
                return p[0]

        @self.pg.production('storage_spec : TCONST')
        @self.pg.production('storage_spec : TIMMUT')
        @self.pg.production('storage_spec : TMUT')
        @self.pg.production('storage_spec : TREADONLY')
        @self.pg.production('storage_spec : TNOCAPTURE')
        @self.pg.production('storage_spec : TATOMIC')
        def storage_spec(state, p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'TCONST':
                return 'const', spos
            elif p[0].gettokentype() == 'TIMMUT':
                return 'immut', spos
            elif p[0].gettokentype() == 'TMUT':
                return 'mut', spos
            elif p[0].gettokentype() == 'TREADONLY':
                return 'readonly', spos
            elif p[0].gettokentype() == 'TNOCAPTURE':
                return 'nocapture', spos
            elif p[0].gettokentype() == 'TATOMIC':
                return 'atomic', spos

        @self.pg.production('stmt : value_decl CEQ expr SEMICOLON')
        def stmt_var_decl_ceq(state, p):
            spos = p[0].getsourcepos()
            spec = None if not p[0].qualifiers else p[0].qualifiers
            return VarDeclAssign(state.builder, state.module, state.package, spos, p[0].name, p[2], spec=spec)

        @self.pg.production('stmt : lvalue_expr EQ expr SEMICOLON')
        def stmt_assign(state, p):
            spos = p[0].getsourcepos()
            return Assignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr ADDEQ expr SEMICOLON')
        def stmt_assign_add(state, p):
            spos = p[0].getsourcepos()
            return AddAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr SUBEQ expr SEMICOLON')
        def stmt_assign_sub(state, p):
            spos = p[0].getsourcepos()
            return SubAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr MULEQ expr SEMICOLON')
        def stmt_assign_mul(state, p):
            spos = p[0].getsourcepos()
            return MulAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr MODEQ expr SEMICOLON')
        def stmt_assign_mod(state, p):
            spos = p[0].getsourcepos()
            return ModAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr ANDEQ expr SEMICOLON')
        def stmt_assign_and(state, p):
            spos = p[0].getsourcepos()
            return AndAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr OREQ expr SEMICOLON')
        def stmt_assign_or(state, p):
            spos = p[0].getsourcepos()
            return OrAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('stmt : lvalue_expr XOREQ expr SEMICOLON')
        def stmt_assign_xor(state, p):
            spos = p[0].getsourcepos()
            return XorAssignment(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('typeexpr : lvalue')
        @self.pg.production('typeexpr : MUL typeexpr')
        @self.pg.production('typeexpr : AND typeexpr')
        @self.pg.production('typeexpr : LBRACKET expr RBRACKET typeexpr')
        def typeexpr(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return TypeExpr(state.builder, state.module, state.package, spos, p[0], state.decl_mode)
            else:
                if p[0].gettokentype() == 'MUL':
                    return PointerTypeExpr(state.builder, state.module, state.package, spos, p[1])
                elif p[0].gettokentype() == 'AND':
                    return ReferenceTypeExpr(state.builder, state.module, state.package, spos, p[1])
                else:
                    size = p[1]
                    return ArrayTypeExpr(state.builder, state.module, state.package, spos, p[3], size)

        @self.pg.production('typeexpr : LBRACKET RBRACKET typeexpr')
        def typeexpr_slice(state, p):
            spos = p[0].getsourcepos()
            return SliceTypeExpr(state.builder, state.module, state.package, spos, p[2])

        @self.pg.production('typeexpr : LVEC expr RVEC typeexpr')
        def typeexpr_hvector(state, p):
            spos = p[0].getsourcepos()
            size = p[1]
            return HVectorTypeExpr(state.builder, state.module, state.package, spos, p[3], size)

        @self.pg.production('typeexpr : TTUPLE LPAREN tuple_type_list RPAREN')
        def typeexpr_tuple(state, p):
            spos = p[0].getsourcepos()
            return TupleTypeExpr(state.builder, state.module, state.package, spos, p[2])

        @self.pg.production('typeexpr : QMARK typeexpr')
        def typeexpr_optional(state, p):
            spos = p[0].getsourcepos()
            return OptionalTypeExpr(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('tuple_type_list : typeexpr')
        @self.pg.production('tuple_type_list : tuple_type_list COMMA typeexpr')
        def tuple_type_list(state, p):
            if len(p) == 0:
                return []
            elif len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[2])
                return p[0]

        @self.pg.production('typeexpr : TFN LPAREN func_arg_type_list RPAREN RARROW typeexpr')
        def typeexpr_func(state, p):
            spos = p[0].getsourcepos()
            return FuncTypeExpr(state.builder, state.module, state.package, spos, p[2], p[5])

        @self.pg.production('typeexpr : TFN LPAREN RPAREN RARROW typeexpr')
        def typeexpr_func_empty(state, p):
            spos = p[0].getsourcepos()
            return FuncTypeExpr(state.builder, state.module, state.package, spos, [], p[5])

        @self.pg.production('func_arg_type_list : typeexpr')
        @self.pg.production('func_arg_type_list : func_arg_type_list COMMA typeexpr')
        def func_arg_type_list(state, p):
            if len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[2])
                return p[0]

        @self.pg.production('stmt : if_else_stmt')
        def stmt_if_else(state, p):
            return p[0]

        @self.pg.production('stmt : if_then_stmt')
        def stmt_if_else(state, p):
            return p[0]

        @self.pg.production('stmt : switch_stmt')
        def stmt_switch(state, p):
            return p[0]

        @self.pg.production('stmt : TWHILE expr block')
        def stmt_while(state, p):
            spos = p[0].getsourcepos()
            return WhileStatement(state.builder, state.module, state.package, spos, p[1], p[2])

        @self.pg.production('stmt : TWHILE expr TDO stmt')
        def stmt_while_do(state, p):
            spos = p[0].getsourcepos()
            block = CodeBlock(state.builder, state.module, state.package, p[3].getsourcepos(), p[3])
            return WhileStatement(state.builder, state.module, state.package, spos, p[1], block)

        @self.pg.production('stmt : TDO LBRACE block RBRACE TWHILE expr SEMICOLON')
        def stmt_dowhile(state, p):
            spos = p[0].getsourcepos()
            return DoWhileStatement(state.builder, state.module, state.package, spos, p[5], p[2])
        
        @self.pg.production('stmt : TDO expr TWHILE expr SEMICOLON')
        def stmt_dowhile_expr(state, p):
            spos = p[0].getsourcepos()
            block = CodeBlock(state.builder, state.module, state.package, p[1].getsourcepos(), p[1])
            return DoWhileStatement(state.builder, state.module, state.package, spos, p[3], block)

        @self.pg.production('stmt : for_stmt')
        def stmt_for(state, p):
            return p[0]

        @self.pg.production('if_stmt : TIF expr block')
        def if_stmt(state, p):
            spos = p[0].getsourcepos()
            return IfStatement(state.builder, state.module, state.package, spos, p[1], p[2])

        # @self.pg.production('if_stmt : if_stmt TELSE if_stmt')
        # def if_stmt_elseif(state, p):
        #     p[0].add_elseif(p[3], p[5])
        #     return p[0]

        @self.pg.production('if_else_stmt : if_stmt')
        def if_else_stmt_if(state, p):
            return p[0]

        @self.pg.production('if_else_stmt : if_else_stmt TELSE if_stmt')
        def if_stmt_elseif(state, p):
            p[0].add_elseif(p[2].boolexpr, p[2].then)
            return p[0]

        @self.pg.production('stmt : if_else_stmt TELSE block')
        def if_stmt_else(state, p):
            p[0].add_else(p[2])
            return p[0]

        @self.pg.production('if_then_stmt : TIF expr TTHEN stmt')
        def if_stmt_then(state, p):
            spos = p[0].getsourcepos()
            block = CodeBlock(state.module, state.builder, state.package, p[3].getsourcepos(), p[3])
            return IfStatement(state.builder, state.module, state.package, spos, p[1], block)

        @self.pg.production('stmt : if_then_stmt TELSE stmt')
        def if_stmt_then_else(state, p):
            elblock = CodeBlock(state.module, state.builder, state.package, p[1].getsourcepos(), p[2])
            p[0].add_else(elblock)
            return p[0]

        @self.pg.production('switch_stmt : TSWITCH lvalue_expr LBRACE switch_body RBRACE')
        @self.pg.production('switch_stmt : TSWITCH lvalue_expr LBRACE RBRACE')
        def switch_stmt(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 5:
                return SwitchStatement(state.builder, state.module, state.package, spos, p[1], p[3])
            else:
                return SwitchStatement(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('switch_body : switch_body case_expr')
        @self.pg.production('switch_body : switch_body default_case_expr')
        @self.pg.production('switch_body : case_expr')
        @self.pg.production('switch_body : default_case_expr')
        def switch_body(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 2:
                if isinstance(p[1], SwitchDefaultCase):
                    if p[0].default_case is not None:
                        throw_saturn_error(state.builder, state.module, spos.lineno, spos.colno,
                            "Cannot have more than one default case in a switch statement."
                        )
                    p[0].set_default(p[1])
                    return p[0]
                else:
                    p[0].add_case(p[1])
                    return p[0]
            else:
                if isinstance(p[0], SwitchDefaultCase):
                    return SwitchBody(state.builder, state.module, state.package, spos, [], p[0])
                else:
                    return SwitchBody(state.builder, state.module, state.package, spos, [p[0]])

        @self.pg.production('case_expr : TCASE expr COLON')
        def case_expr(state, p):
            spos = p[0].getsourcepos()
            return SwitchCase(state.builder, state.module, state.package, spos, p[1], [])
        
        @self.pg.production('case_expr : case_expr stmt')
        def case_expr_stmt(state, p):
            p[0].add_stmt(p[1])
            return p[0]

        @self.pg.production('default_case_expr : default_case_expr stmt')
        @self.pg.production('default_case_expr : TDEFAULT COLON')
        def default_case_expr(state, p):
            if not isinstance(p[0], SwitchDefaultCase):
                spos = p[0].getsourcepos()
                return SwitchDefaultCase(state.builder, state.module, state.package, spos, [])
            else:
                p[0].add_stmt(p[1])
                return p[0]

        @self.pg.production('for_stmt : TFOR lvalue TIN iter_expr block')
        def for_stmt(state, p):
            spos = p[0].getsourcepos()
            return ForStatement(state.builder, state.module, state.package, spos, p[1], p[3], p[4])

        @self.pg.production('for_stmt : TFOR lvalue TIN iter_expr TDO stmt')
        def for_stmt_do(state, p):
            spos = p[0].getsourcepos()
            block = CodeBlock(state.builder, state.module, state.package, p[5].getsourcepos(), p[5])
            return ForStatement(state.builder, state.module, state.package, spos, p[1], p[3], block)

        @self.pg.production('for_stmt : TFOR lvalue TIN lvalue_expr block')
        def for_stmt_lvalue(state, p):
            spos = p[0].getsourcepos()
            return ForStatement(state.builder, state.module, state.package, spos, p[1], p[3], p[4])

        @self.pg.production('for_stmt : TFOR lvalue TIN lvalue_expr TDO stmt')
        def for_stmt_do_lvalue(state, p):
            spos = p[0].getsourcepos()
            block = CodeBlock(state.builder, state.module, state.package, p[5].getsourcepos(), p[5])
            return ForStatement(state.builder, state.module, state.package, spos, p[1], p[3], block)

        @self.pg.production('stmt_or_block : stmt | block')
        def block_stmt(state, p):
            return p[0]

        @self.pg.production('iter_expr : expr DOTDOT expr')
        @self.pg.production('iter_expr : expr DOTDOT expr COLON expr')
        def iter_expr_const(state, p):
            if len(p) == 3:
                spos = p[0].getsourcepos()
                return IterExpr(state.builder, state.module, state.package, spos, p[0], p[2])
            else:
                spos = p[0].getsourcepos()
                return IterExpr(state.builder, state.module, state.package, spos, p[0], p[2], p[4])

        @self.pg.production('iter_expr : expr ELIPSES expr')
        @self.pg.production('iter_expr : expr ELIPSES expr COLON expr')
        def iter_expr_const_inclusive(state, p):
            if len(p) == 3:
                spos = p[0].getsourcepos()
                return IterExpr(state.builder, state.module, state.package, spos, p[0], p[2], inclusive=True)
            else:
                spos = p[0].getsourcepos()
                return IterExpr(state.builder, state.module, state.package, spos, p[0], p[2], p[4], inclusive=True)

        @self.pg.production('expr : AND expr')
        @self.pg.production('expr : BOOLNOT expr')
        @self.pg.production('expr : BINNOT expr')
        @self.pg.production('expr : SUB expr')
        @self.pg.production('expr : INC lvalue_expr')
        @self.pg.production('expr : DEC lvalue_expr')
        def expr_unary(state, p):
            right = p[1]
            operator = p[0]
            spos = p[0].getsourcepos()
            if operator.gettokentype() == 'AND':
                return AddressOf(state.builder, state.module, state.package, spos, right)
            elif operator.gettokentype() == 'BOOLNOT':
                return BoolNot(state.builder, state.module, state.package, spos, right)
            elif operator.gettokentype() == 'BINNOT':
                return BinaryNot(state.builder, state.module, state.package, spos, right)
            elif operator.gettokentype() == 'SUB':
                return Negate(state.builder, state.module, state.package, spos, right)
            elif operator.gettokentype() == 'INC':
                return PrefixIncrementOp(state.builder, state.module, state.package, spos, right)
            elif operator.gettokentype() == 'DEC':
                return PrefixDecrementOp(state.builder, state.module, state.package, spos, right)

        @self.pg.production('expr : expr ADD expr')
        @self.pg.production('expr : expr SUB expr')
        @self.pg.production('expr : expr MUL expr')
        @self.pg.production('expr : expr DIV expr')
        @self.pg.production('expr : expr MOD expr')
        @self.pg.production('expr : expr LSHFT expr')
        @self.pg.production('expr : expr RSHFT expr')
        @self.pg.production('expr : expr AND expr')
        @self.pg.production('expr : expr OR expr')
        @self.pg.production('expr : expr XOR expr')
        @self.pg.production('expr : expr SPACESHIP expr')
        @self.pg.production('expr : expr BOOLAND expr')
        @self.pg.production('expr : expr BOOLOR expr')
        @self.pg.production('expr : expr BOOLEQ expr')
        @self.pg.production('expr : expr BOOLNEQ expr')
        @self.pg.production('expr : expr BOOLGTE expr')
        @self.pg.production('expr : expr BOOLGT expr')
        @self.pg.production('expr : expr BOOLLTE expr')
        @self.pg.production('expr : expr BOOLLT expr')
        def expr(state, p):
            left = p[0]
            right = p[2]
            operator = p[1]
            spos = p[0].getsourcepos()
            if operator.gettokentype() == 'ADD':
                return Sum(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'SUB':
                return Sub(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'MUL':
                return Mul(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'DIV':
                return Div(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'MOD':
                return Mod(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'LSHFT':
                return ShiftLeft(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'RSHFT':
                return ShiftRight(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'AND':
                return And(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'OR':
                return Or(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'XOR':
                return Xor(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'SPACESHIP':
                return Spaceship(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLEQ':
                return BooleanEq(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLNEQ':
                return BooleanNeq(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLGTE':
                return BooleanGte(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLGT':
                return BooleanGt(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLLTE':
                return BooleanLte(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLLT':
                return BooleanLt(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLAND':
                return BoolAnd(state.builder, state.module, state.package, spos, left, right)
            elif operator.gettokentype() == 'BOOLOR':
                return BoolOr(state.builder, state.module, state.package, spos, left, right)

        @self.pg.production('expr : TCAST LANGLE typeexpr RANGLE LPAREN expr RPAREN')
        def expr_cast(state, p):
            spos = p[0].getsourcepos()
            ctype = p[2]
            cexpr = p[5]
            return CastExpr(state.builder, state.module, state.package, spos, ctype, cexpr)

        @self.pg.production('expr : expr TIF expr TELSE expr')
        def expr_select(state, p):
            spos = p[0].getsourcepos()
            a = p[0]
            cond = p[2]
            b = p[4]
            return SelectExpr(state.builder, state.module, state.package, spos, cond, a, b)

        @self.pg.production('lambda_expr : TFN LPAREN decl_args RPAREN COLON typeexpr block')
        def lambda_expr(state, p):
            spos = p[0].getsourcepos()
            args = p[2]
            rtype = p[5]
            block = p[6]
            return LambdaExpr(state.builder, state.module, state.package, spos, rtype, block, args)
        #
        # @self.pg.production('lambda_expr : TFN capture_expr LPAREN decl_args RPAREN COLON typeexpr LBRACE block RBRACE')
        # def lambda_expr(state, p):
        #     spos = p[0].getsourcepos()
        #     args = p[3]
        #     rtype = p[6]
        #     block = p[8]
        #     capture = p[1]
        #     return LambdaExpr(state.builder, state.module, state.package, spos, rtype, block, args, capture)

        @self.pg.production('capture_expr : LBRACKET RBRACKET')
        def capture_expr_empty(state, p):
            capture = CaptureExpr(state.builder, state.module, state.package, p[1].getsourcepos())
            return capture

        @self.pg.production('capture_expr : LBRACKET capture_args_list RBRACKET')
        def capture_expr(state, p):
            capture = CaptureExpr(state.builder, state.module, state.package, p[1][0][0].getsourcepos())
            for arg in p[1]:
                if arg[0].name == '&':
                    capture.capture_all_by_ref = True
                elif arg[0].name == '*':
                    capture.capture_all_by_value = True
                else:
                    if arg[2]:
                        capture.capture_by_ref(arg[0], arg[1])
                    else:
                        capture.capture_by_value(arg[0], arg[1])
            return capture

        @self.pg.production('capture_args_list : AND')
        def capture_args_list_all_by_ref(state, p):
            return [(LValue(state.builder, state.module, state.package, p[0].getsourcepos(), '&'),
                     [],
                     True)]

        @self.pg.production('capture_args_list : MUL')
        def capture_args_list_all_by_value(state, p):
            return [(LValue(state.builder, state.module, state.package, p[0].getsourcepos(), '*'),
                     [],
                     False)]

        @self.pg.production('capture_args_list : capture_arg')
        @self.pg.production('capture_args_list : capture_args_list COMMA capture_arg')
        @self.pg.production('capture_args_list : capture_args_list COMMA')
        def capture_args_list(state, p):
            if len(p) == 1:
                return [p[0]]
            elif len(p) == 3:
                p[0].append(p[2])
            return p[0]

        @self.pg.production('capture_arg : value_decl')
        def capture_arg(state, p):
            return LValue(state.builder, state.module, state.package, p[0].spos, p[0].name.value), \
                   p[0].qualifiers, \
                   p[0].is_ref

        @self.pg.production('func_call : lvalue LPAREN args RPAREN')
        def func_call(state, p):
            name = p[0]
            spos = p[0].getsourcepos()
            return FuncCall(state.builder, state.module, state.package, spos, name, p[2])

        @self.pg.production('func_call : lvalue LPAREN RPAREN')
        def func_call_empty(state, p):
            name = p[0]
            spos = p[0].getsourcepos()
            return FuncCall(state.builder, state.module, state.package, spos, name, [])

        @self.pg.production('expr : func_call')
        def expr_func_call(state, p):
            return p[0]

        @self.pg.production('func_call : lambda_expr LPAREN args RPAREN')
        def lambda_call(state, p):
            lambda_ = p[0]
            spos = p[0].getsourcepos()
            return LambdaCall(state.builder, state.module, state.package, spos, lambda_, p[2])

        @self.pg.production('func_call : lambda_expr LPAREN RPAREN')
        def lambda_call_empty(state, p):
            lambda_ = p[0]
            spos = p[0].getsourcepos()
            return LambdaCall(state.builder, state.module, state.package, spos, lambda_, [])

        @self.pg.production('expr : TPRINT LPAREN args RPAREN')
        def expr_print_call(state, p):
            spos = p[0].getsourcepos()
            return Print(state.builder, state.module, state.package, spos, p[2])

        @self.pg.production('expr : LPAREN expr RPAREN')
        def expr_parens(state, p):
            return p[1]
        
        @self.pg.production('args : args COMMA expr')
        @self.pg.production('args : expr')
        def args(state, p):
            if len(p) == 1:
                return [p[0]]
            else:
                p[0].append(p[2])
                return p[0]

        @self.pg.production('lvalue : IDENT')
        @self.pg.production('lvalue : lvalue CC IDENT')
        def lvalue(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return LValue(state.builder, state.module, state.package, spos, p[0].value)
            else:
                return LValue(state.builder, state.module, state.package, spos, p[2].value, p[0])

        @self.pg.production('lvalue : lvalue LANGLE tuple_type_list RANGLE')
        @self.pg.production('lvalue : lvalue LANGLE RANGLE')
        def lvalue_generic(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 4:
                return LValueGeneric(state.builder, state.module, state.package, spos, p[2], p[0])
            else:
                return LValue(state.builder, state.module, state.package, spos, p[2].value, p[0])

        @self.pg.production('lvalue_expr : LPAREN lvalue_expr RPAREN')
        def lvalue_expr_self(state, p):
            return p[1]

        @self.pg.production('lvalue_expr : lvalue_expr DOT IDENT')
        def lvalue_dot(state, p):
            spos = p[0].getsourcepos()
            return LValueField(state.builder, state.module, state.package, spos, p[0], p[2].value)

        @self.pg.production('lvalue_expr : lvalue')
        @self.pg.production('lvalue_expr : MUL lvalue_expr')
        @self.pg.production('lvalue_expr : lvalue_expr LBRACKET expr RBRACKET')
        def lvalue_expr(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return p[0]
            elif len(p) == 4:
                return ElementOf(state.builder, state.module, state.package, spos, p[0], p[2])
            else:
                if p[0].gettokentype() == 'MUL':
                    return DerefOf(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('lvalue_expr : lvalue_expr DOT func_call')
        def lvalue_expr_method(state, p):
            spos = p[0].getsourcepos()
            return MethodCall(state.builder, state.module, state.package, spos, p[0], p[2].lvalue, p[2].args)

        @self.pg.production('lvalue_expr : lvalue_expr DOT INT')
        def lvalue_expr_tuple_element(state, p):
            spos = p[0].getsourcepos()
            return TupleElementOf(state.builder, state.module, state.package, spos, p[0], p[2].value)

        @self.pg.production('expr : lambda_expr')
        def expr_lambda(state, p):
            return p[0]

        @self.pg.production('expr : lvalue_expr')
        def expr_lvalue(state, p):
            return p[0]

        @self.pg.production('expr : struct_literal')
        def expr_struct_literal(state, p):
            return p[0]

        @self.pg.production('expr : array_literal')
        def expr_array_literal(state, p):
            return p[0]

        @self.pg.production('expr : tuple_literal')
        def expr_tuple_literal(state, p):
            return p[0]

        @self.pg.production('expr : make_expr')
        def expr_make_expr(state, p):
            return p[0]

        @self.pg.production('struct_literal : LPAREN lvalue RPAREN struct_literal_body')
        def struct_literal(state, p):
            spos = p[1].getsourcepos()
            stype = TypeExpr(state.builder, state.module, state.package, spos, p[1])
            return StructLiteral(state.builder, state.module, state.package, spos, stype, p[3])

        @self.pg.production('struct_literal_body : LBRACE struct_literal_element_list RBRACE')
        @self.pg.production('struct_literal_body : LBRACE RBRACE')
        def struct_literal_body(state, p):
            if len(p) == 2:
                return StructLiteralBody(state.builder, state.module, state.package, None)
            else:
                return p[1]

        @self.pg.production('struct_literal_element_list : struct_literal_element_list COMMA struct_literal_element')
        @self.pg.production('struct_literal_element_list : struct_literal_element_list COMMA')
        @self.pg.production('struct_literal_element_list : struct_literal_element')
        def struct_literal_element_list(state, p):
            if len(p) == 1:
                spos = p[0].getsourcepos()
                body = StructLiteralBody(state.builder, state.module, state.package, spos)
                body.add_field(p[0].name, p[0].expr)
                return body
            elif len(p) == 2:
                return p[0]
            else:
                p[0].add_field(p[2].name, p[2].expr)
                return p[0]

        @self.pg.production('struct_literal_element : IDENT COLON expr')
        def struct_literal_element(state, p):
            spos = p[0].getsourcepos()
            return StructLiteralElement(state.builder, state.module, state.package, spos, p[0], p[2])

        @self.pg.production('array_literal : LBRACKET RBRACKET lvalue LBRACE array_literal_body RBRACE')
        def array_literal(state, p):
            spos = p[1].getsourcepos()
            elty = TypeExpr(state.builder, state.module, state.package, spos, p[2])
            return ArrayLiteral(state.builder, state.module, state.package, spos, elty, p[4])

        @self.pg.production(
            'array_literal : LBRACKET RBRACKET LBRACKET typeexpr RBRACKET LBRACE array_literal_body RBRACE')
        def array_literal_elty(state, p):
            spos = p[1].getsourcepos()
            return ArrayLiteral(state.builder, state.module, state.package, spos, p[3], p[6])

        @self.pg.production('array_literal_body : array_literal_body COMMA array_literal_element')
        @self.pg.production('array_literal_body : array_literal_body COMMA')
        @self.pg.production('array_literal_body : array_literal_element')
        @self.pg.production('array_literal_body : ')
        def array_literal_body(state, p):
            if len(p) == 0:
                return ArrayLiteralBody(state.builder, state.module, state.package, None)
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                body = ArrayLiteralBody(state.builder, state.module, state.package, spos)
                body.add_element(p[0])
                return body
            elif len(p) == 2:
                return p[0]
            else:
                p[0].add_element(p[2])
                return p[0]

        @self.pg.production('array_literal_element : expr')
        @self.pg.production('array_literal_element : number COLON expr')
        def array_literal_element(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 1:
                return ArrayLiteralElement(state.builder, state.module, state.package, spos, p[0])
            else:
                return ArrayLiteralElement(state.builder, state.module, state.package, spos, p[2], int(p[0].value))

        @self.pg.production('tuple_literal : TTUPLE LBRACE tuple_literal_body RBRACE')
        def tuple_literal(state, p):
            spos = p[1].getsourcepos()
            return TupleLiteral(state.builder, state.module, state.package, spos, p[2])

        @self.pg.production('tuple_literal_body : tuple_literal_body COMMA tuple_literal_element')
        @self.pg.production('tuple_literal_body : tuple_literal_body COMMA')
        @self.pg.production('tuple_literal_body : tuple_literal_element')
        @self.pg.production('tuple_literal_body : ')
        def tuple_literal_body(state, p):
            if len(p) == 0:
                return TupleLiteralBody(state.builder, state.module, state.package, None)
            elif len(p) == 1:
                spos = p[0].getsourcepos()
                body = TupleLiteralBody(state.builder, state.module, state.package, spos)
                body.add_element(p[0].expr)
                return body
            elif len(p) == 2:
                return p[0]
            else:
                p[0].add_element(p[2].expr)
                return p[0]

        @self.pg.production('tuple_literal_element : expr')
        def tuple_literal_element(state, p):
            spos = p[0].getsourcepos()
            return TupleLiteralElement(state.builder, state.module, state.package, spos, p[0])

        @self.pg.production('make_expr : TMAKE lvalue')
        def make_expr(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[1].getsourcepos(), p[1])
            return MakeExpr(state.builder, state.module, state.package, spos, ty)

        @self.pg.production('make_expr : TMAKE LBRACKET expr RBRACKET lvalue')
        def make_expr_array(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[4].getsourcepos(), p[4])
            size = p[2]
            raise RuntimeError('Unimplemented make_expr with array')

        @self.pg.production('make_expr : TMAKE TNEW lvalue LPAREN args RPAREN')
        def make_expr_new(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[2].getsourcepos(), p[2])
            return MakeExpr(state.builder, state.module, state.package, spos, ty, args=p[4])

        @self.pg.production('make_expr : TMAKE struct_literal')
        @self.pg.production('make_expr : TMAKE array_literal')
        def make_expr_literal(state, p):
            spos = p[0].getsourcepos()
            raise RuntimeError('Unimplemented make_expr with struct/array literal')

        @self.pg.production('make_expr : TMAKE TOWNED lvalue')
        @self.pg.production('make_expr : TMAKE TOWNED LBRACKET expr RBRACKET lvalue')
        @self.pg.production('make_expr : TMAKE TOWNED TNEW lvalue LPAREN args RPAREN')
        @self.pg.production('make_expr : TMAKE TOWNED struct_literal')
        @self.pg.production('make_expr : TMAKE TOWNED array_literal')
        def make_expr_owned(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 3:
                return MakeExpr(state.builder, state.module, state.package, spos, p[2])
            else:
                if p[3].gettokentype() == 'LPAREN':
                    return MakeExpr(state.builder, state.module, state.package, spos, p[2], args=p[4])
                if p[3].gettokentype() == 'LPAREN':
                    return MakeExpr(state.builder, state.module, state.package, spos, p[2], init=p[4])

        @self.pg.production('make_expr : TMAKE TSHARED lvalue')
        @self.pg.production('make_expr : TMAKE TSHARED LBRACKET expr RBRACKET lvalue')
        @self.pg.production('make_expr : TMAKE TSHARED TNEW lvalue LPAREN args RPAREN')
        @self.pg.production('make_expr : TMAKE TSHARED struct_literal')
        @self.pg.production('make_expr : TMAKE TSHARED array_literal')
        def make_expr_shared(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 3:
                return MakeSharedExpr(state.builder, state.module, state.package, spos, p[2])
            else:
                if   p[3].gettokentype() == 'LPAREN':
                    return MakeSharedExpr(state.builder, state.module, state.package, spos, p[2], args=p[4])
                elif p[3].gettokentype() == 'LBRACE':
                    return MakeSharedExpr(state.builder, state.module, state.package, spos, p[2], init=p[4])

        @self.pg.production('make_expr : TMAKE TUNSAFE lvalue')
        def make_expr_unsafe(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[2].getsourcepos(), p[2])
            return MakeUnsafeExpr(state.builder, state.module, state.package, spos, ty)

        @self.pg.production('make_expr : TMAKE TUNSAFE LBRACKET expr RBRACKET lvalue')
        def make_expr_unsafe_array(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[5].getsourcepos(), p[5])
            return MakeUnsafeArrayExpr(state.builder, state.module, state.package, spos, ty, p[3])

        @self.pg.production('make_expr : TMAKE TUNSAFE TNEW lvalue LPAREN args RPAREN')
        def make_expr_unsafe_new(state, p):
            spos = p[0].getsourcepos()
            ty = TypeExpr(state.builder, state.module, state.package, p[3].getsourcepos(), p[3])
            return MakeUnsafeExpr(state.builder, state.module, state.package, spos, ty, args=p[5])

        @self.pg.production('make_expr : TMAKE TUNSAFE struct_literal')
        @self.pg.production('make_expr : TMAKE TUNSAFE array_literal')
        def make_expr_unsafe(state, p):
            spos = p[0].getsourcepos()
            if len(p) == 3:
                return MakeUnsafeExpr(state.builder, state.module, state.package, spos, p[2])
            else:
                if p[3].gettokentype() == 'LPAREN':
                    return MakeUnsafeExpr(state.builder, state.module, state.package, spos, p[2], args=p[4])
                elif p[3].gettokentype() == 'LBRACE':
                    return MakeUnsafeExpr(state.builder, state.module, state.package, spos, p[2], init=p[4])

        @self.pg.production('stmt : TDESTROY lvalue_expr SEMICOLON')
        def destroy_stmt(state, p):
            spos = p[0].getsourcepos()
            return DestroyExpr(state.builder, state.module, state.package, spos, p[1])

        @self.pg.production('expr : number')
        def expr_number(state, p):
            return p[0]

        @self.pg.production('number : INT')
        @self.pg.production('number : UINT')
        @self.pg.production('number : LONGINT')
        @self.pg.production('number : ULONGINT')
        @self.pg.production('number : SBYTE')
        @self.pg.production('number : BYTE')
        @self.pg.production('number : SHORTINT')
        @self.pg.production('number : USHORTINT')
        @self.pg.production('number : HALF')
        @self.pg.production('number : FLOAT')
        @self.pg.production('number : DOUBLE')
        @self.pg.production('number : QUAD')
        def number(state, p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'INT':
                return Integer(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'UINT':
                return UInteger(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'LONGINT':
                return Integer64(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'ULONGINT':
                return UInteger64(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'SBYTE':
                return SByte(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'BYTE':
                return Byte(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'SHORTINT':
                return Integer16(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'USHORTINT':
                return UInteger16(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'HALF':
                return HalfFloat(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'FLOAT':
                return Float(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'DOUBLE':
                return Double(state.builder, state.module, state.package, spos, p[0].value)
            elif p[0].gettokentype() == 'QUAD':
                return Quad(state.builder, state.module, state.package, spos, p[0].value)

        @self.pg.production('number : HEXINT')
        @self.pg.production('number : HEXUINT')
        @self.pg.production('number : HEXLINT')
        @self.pg.production('number : HEXULINT')
        @self.pg.production('number : HEXSINT')
        @self.pg.production('number : HEXUSINT')
        @self.pg.production('number : HEXBINT')
        @self.pg.production('number : HEXSBINT')
        def expr_hex(state, p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'HEXINT':
                return Integer(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXUINT':
                return UInteger(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXLINT':
                return Integer64(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXULINT':
                return UInteger64(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXSINT':
                return Integer16(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXUSINT':
                return UInteger16(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXBINT':
                return Byte(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)
            elif p[0].gettokentype() == 'HEXSBINT':
                return SByte(state.builder, state.module, state.package, spos, p[0].value.strip('0x'), base=16)

        @self.pg.production('expr : string_expr')
        def expr_string_expr(state, p):
            spos = p[0].getsourcepos()
            return StringLiteral(state.builder, state.module, state.package, spos, p[0].value)
        
        @self.pg.production('string_expr : STRING')
        def string_expr(state, p):
            spos = p[0].getsourcepos()
            return StringLiteral(state.builder, state.module, state.package, spos, p[0].value)

        @self.pg.production('string_expr : MLSTRING')
        def string_expr_mlstring(state, p):
            spos = p[0].getsourcepos()
            return MultilineStringLiteral(state.builder, state.module, state.package, spos, p[0].value)

        @self.pg.production('expr : boolexpr')
        def expr_bool(state, p):
            return p[0]

        @self.pg.production('boolexpr : TTRUE')
        @self.pg.production('boolexpr : TFALSE')
        def expr_bool_literal(state, p):
            spos = p[0].getsourcepos()
            if p[0].gettokentype() == 'TTRUE':
                return Boolean(state.builder, state.module, state.package, spos, True)
            else:
                return Boolean(state.builder, state.module, state.package, spos, False)

        @self.pg.production('expr : TNULL')
        def expr_null(state, p):
            spos = p[0].getsourcepos()
            return Null(state.builder, state.module, state.package, spos)

        @self.pg.error
        def error_handle(state, token):
            text_input = state.builder.filestack[state.builder.filestack_idx]
            lines = text_input.splitlines()
            if token.getsourcepos() is None:
                raise RuntimeError("%s (?:?) Ran into a(n) %s where it wasn't expected." % (
                    state.module.filestack[state.module.filestack_idx],
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
                state.module.filestack[state.module.filestack_idx],
                token.getsourcepos().lineno,
                token.getsourcepos().colno,
                token.gettokentype(), 
            ))

    def get_parser(self):
        _pg = self.pg.build()
        # exit(0)
        return _pg


pg = Parser()
pg.parse()
parser = pg.get_parser()
