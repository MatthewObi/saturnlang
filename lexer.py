from rply import LexerGenerator


class Lexer():
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
        self.lexer.add('TPRINT', r'\bprintf\b')
        self.lexer.add('TPACKAGE', r'\bpackage\b')
        self.lexer.add('TIMPORT', r'\bimport\b')
        self.lexer.add('TFN', r'\bfn\b')
        self.lexer.add('TIF', r'\bif\b')
        self.lexer.add('TELSE', r'\belse\b')
        self.lexer.add('TWHILE', r'\bwhile\b')
        self.lexer.add('TFOR', r'\bfor\b')
        self.lexer.add('TTHEN', r'\bthen\b')
        self.lexer.add('TDO', r'\bdo\b')
        self.lexer.add('TSWITCH', r'\bswitch\b')
        self.lexer.add('TCASE', r'\bcase\b')
        self.lexer.add('TDEFAULT', r'\bdefault\b')
        self.lexer.add('TFALLTHROUGH', r'\bfallthrough\b')
        self.lexer.add('TBREAK', r'\bbreak\b')
        self.lexer.add('TCONTINUE', r'\bcontinue\b')
        self.lexer.add('TRETURN', r'\breturn\b')
        self.lexer.add('TMATCH', r'\bmatch\b')
        self.lexer.add('TEXTERN', r'\bextern\b')
        self.lexer.add('TTYPE', r'\btype\b')
        self.lexer.add('TSTRUCT', r'\bstruct\b')
        self.lexer.add('TOPERATOR', r'\boperator\b')
        self.lexer.add('TNULL', r'\bnull\b')
        self.lexer.add('TCAST', r'\bcast\b')
        self.lexer.add('TCONST', r'\bconst\b')
        self.lexer.add('TIMMUT', r'\bimmut\b')
        self.lexer.add('TATOMIC', r'\batomic\b')
        self.lexer.add('TMUT', r'\bmut\b')
        self.lexer.add('TIN', r'\bin\b')
        self.lexer.add('TCINCLUDE', r'\bc_include\b')

        self.lexer.add('TTRUE', r'\btrue\b')
        self.lexer.add('TFALSE', r'\bfalse\b')
        # Parenthesis
        self.lexer.add('LPAREN', r'\(')
        self.lexer.add('RPAREN', r'\)')
        # Bracket
        self.lexer.add('LBRACKET', r'\[')
        self.lexer.add('RBRACKET', r'\]')

        # Braces
        self.lexer.add('LBRACE', r'\{')
        self.lexer.add('RBRACE', r'\}')

        self.lexer.add('CEQ', r'\:=')

        # Semi Colon
        self.lexer.add('SEMICOLON', r'\;')
        self.lexer.add('CC', r'\:\:')
        self.lexer.add('COLON', r'\:')
        self.lexer.add('COMMA', r',')
        # Mod Operators
        self.lexer.add('ADDEQ', r'\+=')
        self.lexer.add('SUBEQ', r'\-=')
        self.lexer.add('MULEQ', r'\*=')
        self.lexer.add('DIVEQ', r'\/=')
        # Operators
        self.lexer.add('MUL', r'\*')
        self.lexer.add('DIV', r'\/')
        
        self.lexer.add('LANGLE', r'!<')

        self.lexer.add('BOOLAND', r'\&\&')
        self.lexer.add('BOOLOR', r'\|\|')
        self.lexer.add('BOOLEQ', r'==')
        self.lexer.add('BOOLNEQ', r'!=')
        self.lexer.add('SPACESHIP', r'<=>')
        self.lexer.add('BOOLGTE', r'>=')
        self.lexer.add('BOOLLTE', r'<=')
        self.lexer.add('BOOLGT', r'>')
        self.lexer.add('BOOLLT', r'<')

        self.lexer.add('ANDEQ', r'\&=')
        self.lexer.add('OREQ', r'\|=')
        self.lexer.add('XOREQ', r'\^=')

        self.lexer.add('EQ', r'=')
        
        self.lexer.add('AND', r'\&')
        self.lexer.add('OR', r'\|')
        self.lexer.add('XOR', r'\^')
        self.lexer.add('BINNOT', r'\~')
        
        self.lexer.add('ELIPSES', r'\.\.\.')
        self.lexer.add('DOTDOT', r'\.\.')

        # Identifier
        self.lexer.add('IDENT', r'[_A-Za-z]\w*')
        
        # Number
        self.lexer.add('FLOAT', r'[+-]?([0-9]+\.[0-9]+)f')
        self.lexer.add('DOUBLE', r'[+-]?([0-9]+\.[0-9]+)')
        self.lexer.add('LONGINT', r'[+-]?\d+l')
        self.lexer.add('ULONGINT', r'[+-]?\d+ul')
        self.lexer.add('BYTE', r'[+-]?\d+b')
        self.lexer.add('UINT', r'[+-]?\d+u')
        self.lexer.add('INT', r'[+-]?\d+')

        self.lexer.add('DOT', r'\.')
        self.lexer.add('ADD', r'\+')
        self.lexer.add('SUB', r'\-')
        self.lexer.add('MOD', r'\%')

        # String literal
        self.lexer.add('CSTRING', r'c\"(([^\"\\]|\\.)*)\"')
        self.lexer.add('STRING', r'\"(([^\"\\]|\\.)*)\"')

        # Ignore spaces
        self.lexer.ignore(r'\s+')

    def get_lexer(self):
        self._add_tokens()
        return self.lexer.build()