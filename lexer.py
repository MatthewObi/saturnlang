import re

from rply import LexerGenerator


class Lexer:
    def __init__(self):
        self.lexer = LexerGenerator()

    def _add_tokens(self):
        # C-style comments (multi-line)
        self.lexer.ignore(r'\/\*(\*(?!\/)|[^*])*\*\/')

        # C++-style comments (single-line)
        self.lexer.ignore(r'\/\/[^\n]*')

        # Multiline String literal
        self.lexer.add('MLSTRING', r'R\(\"([\S\s]*)\"\)R')

        # Words
        self.lexer.add('TPRINT',       r'\bprintf\b')
        self.lexer.add('TPACKAGE',     r'\bpackage\b')
        self.lexer.add('TIMPORT',      r'\bimport\b')
        self.lexer.add('TFN',          r'\bfn\b')
        self.lexer.add('TIF',          r'\bif\b')
        self.lexer.add('TELSE',        r'\belse\b')
        self.lexer.add('TWHILE',       r'\bwhile\b')
        self.lexer.add('TFOR',         r'\bfor\b')
        self.lexer.add('TTHEN',        r'\bthen\b')
        self.lexer.add('TDO',          r'\bdo\b')
        self.lexer.add('TSWITCH',      r'\bswitch\b')
        self.lexer.add('TCASE',        r'\bcase\b')
        self.lexer.add('TDEFAULT',     r'\bdefault\b')
        self.lexer.add('TFALLTHROUGH', r'\bfallthrough\b')
        self.lexer.add('TBREAK',       r'\bbreak\b')
        self.lexer.add('TCONTINUE',    r'\bcontinue\b')
        self.lexer.add('TRETURN',      r'\breturn\b')
        self.lexer.add('TDEFER',       r'\bdefer\b')
        self.lexer.add('TMATCH',       r'\bmatch\b')
        self.lexer.add('TEXTERN',      r'\bextern\b')
        self.lexer.add('TTYPE',        r'\btype\b')
        self.lexer.add('TSTRUCT',      r'\bstruct\b')
        self.lexer.add('TENUM',        r'\benum\b')
        self.lexer.add('TOPERATOR',    r'\boperator\b')
        self.lexer.add('TPUB',         r'\bpub\b')
        self.lexer.add('TPRIV',        r'\bpriv\b')
        self.lexer.add('TNULL',        r'\bnull\b')
        self.lexer.add('TMAKE',        r'\bmake\b')
        self.lexer.add('TDESTROY',     r'\bdestroy\b')
        self.lexer.add('TSHARED',      r'\bshared\b')
        self.lexer.add('TOWNED',       r'\bowned\b')
        self.lexer.add('TCAST',        r'\bcast\b')
        self.lexer.add('TCONST',       r'\bconst\b')
        self.lexer.add('TIMMUT',       r'\bimmut\b')
        self.lexer.add('TMUT',         r'\bmut\b')
        self.lexer.add('TREADONLY',    r'\breadonly\b')
        self.lexer.add('TNOCAPTURE',   r'\bnocapture\b')
        self.lexer.add('TATOMIC',      r'\batomic\b')
        self.lexer.add('TUNSAFE',      r'\bunsafe\b')
        self.lexer.add('TIN',          r'\bin\b')
        self.lexer.add('TCINCLUDE',    r'\bc_include\b')
        self.lexer.add('TCDECLARE',    r'\bc_declare\b')
        self.lexer.add('TBININCLUDE',  r'\bbin_include\b')
        self.lexer.add('TNEW',         r'\bnew\b')
        self.lexer.add('TTUPLE',       r'\btuple\b')

        self.lexer.add('TTRUE',        r'\btrue\b')
        self.lexer.add('TFALSE',       r'\bfalse\b')
        # Parenthesis
        self.lexer.add('LPAREN',    r'\(')
        self.lexer.add('RPAREN',    r'\)')
        # Angle Bracket
        self.lexer.add('LANGLE', r'<\[')
        self.lexer.add('RANGLE', r'\]>')
        self.lexer.add('LVEC', r'\[<')
        self.lexer.add('RVEC', r'>\]')
        # Bracket
        self.lexer.add('LDBRACKET', r'\[\[')
        self.lexer.add('RDBRACKET', r'\]\]')
        self.lexer.add('LBRACKET',  r'\[')
        self.lexer.add('RBRACKET',  r'\]')

        # Braces
        self.lexer.add('LBRACE',    r'\{')
        self.lexer.add('RBRACE',    r'\}')

        self.lexer.add('CEQ',       r'\:=')

        # Semi Colon
        self.lexer.add('SEMICOLON', r'\;')
        self.lexer.add('CC',        r'\:\:')
        self.lexer.add('COLON',     r'\:')
        self.lexer.add('COMMA',     r',')
        # Mod Operators
        self.lexer.add('ADDEQ',     r'\+=')
        self.lexer.add('SUBEQ',     r'\-=')
        self.lexer.add('MULEQ',     r'\*=')
        self.lexer.add('DIVEQ',     r'\/=')
        self.lexer.add('MODEQ',     r'\%=')
        # Operators
        self.lexer.add('MUL',       r'\*')
        self.lexer.add('DIV',       r'\/')

        self.lexer.add('LSHFTEQ',   r'<<=')
        self.lexer.add('RSHFTEQ',   r'>>=')

        self.lexer.add('LSHFT',     r'<<')
        self.lexer.add('RSHFT',     r'>>')

        self.lexer.add('RARROW',    r'->')

        self.lexer.add('BOOLAND',   r'\&\&')
        self.lexer.add('BOOLOR',    r'\|\|')
        self.lexer.add('BOOLEQ',    r'==')
        self.lexer.add('BOOLNEQ',   r'!=')
        self.lexer.add('SPACESHIP', r'<=>')
        self.lexer.add('BOOLGTE',   r'>=')
        self.lexer.add('BOOLLTE',   r'<=')
        self.lexer.add('BOOLGT',    r'>')
        self.lexer.add('BOOLLT',    r'<')

        self.lexer.add('ANDEQ',     r'\&=')
        self.lexer.add('OREQ',      r'\|=')
        self.lexer.add('XOREQ',     r'\^=')

        self.lexer.add('EQ',      r'=')
        
        self.lexer.add('AND',     r'\&')
        self.lexer.add('OR',      r'\|')
        self.lexer.add('XOR',     r'\^')
        self.lexer.add('BINNOT',  r'\~')
        self.lexer.add('BOOLNOT', r'!')

        self.lexer.add('QMARK',   r'\?')
        
        self.lexer.add('ELIPSES', r'\.\.\.')
        self.lexer.add('DOTDOT',  r'\.\.')

        # Identifier
        self.lexer.add('IDENT',   r'[_A-Za-z]\w*')
        
        # Number
        self.lexer.add('HEXULINT',  r'\b0x[0-9A-Fa-f]+ul\b')
        self.lexer.add('HEXLINT',   r'\b0x[0-9A-Fa-f]+l\b')
        self.lexer.add('HEXUSINT',  r'\b0x[0-9A-Fa-f]+us\b')
        self.lexer.add('HEXSBINT',  r'\b0x[0-9A-Fa-f]+sb\b')
        self.lexer.add('HEXSINT',   r'\b0x[0-9A-Fa-f]+s\b')
        self.lexer.add('HEXBINT',   r'\b0x[0-9A-Fa-f]+b\b')
        self.lexer.add('HEXUINT',   r'\b0x[0-9A-Fa-f]+u\b')
        self.lexer.add('HEXINT',    r'\b0x[0-9A-Fa-f]+\b')
        self.lexer.add('BININT',    r'0b[0-1]+')
        self.lexer.add('BINLINT',   r'0b[0-1]+l')
        self.lexer.add('BINBYTE',   r'0b[0-1]+b')
        self.lexer.add('FLOAT',     r'[0-9]+\.[0-9]*f')
        self.lexer.add('HALF',      r'[0-9]+\.[0-9]*h')
        self.lexer.add('QUAD',      r'[0-9]+\.[0-9]*q')
        self.lexer.add('DOUBLE',    r'[0-9]+\.[0-9]+')
        self.lexer.add('LONGINT',   r'\d+l')
        self.lexer.add('ULONGINT',  r'\d+ul')
        self.lexer.add('SBYTE',     r'\d+sb')
        self.lexer.add('BYTE',      r'\d+b')
        self.lexer.add('USHORTINT', r'\d+us')
        self.lexer.add('SHORTINT',  r'\d+s')
        self.lexer.add('UINT',      r'\d+u')
        self.lexer.add('INT',       r'\d+')

        self.lexer.add('INC', r'\+\+')
        self.lexer.add('DEC', r'\-\-')

        self.lexer.add('DOT', r'\.')
        self.lexer.add('ADD', r'\+')
        self.lexer.add('SUB', r'\-')
        self.lexer.add('MOD', r'\%')

        # String literal
        self.lexer.add('CSTRING', r'c\"(([^\"\\]|\\.)*)\"')
        self.lexer.add('STRING',  r'(?u)\"(([^\"\\]|\\.)*)\"', flags=re.UNICODE)

        # Ignore spaces
        self.lexer.ignore(r'\s+')

    def get_lexer(self):
        self._add_tokens()
        return self.lexer.build()


lexer = Lexer().get_lexer()
