from lexer import Lexer
from sparser import Parser
from codegen import CodeGen

import sys
import os

text_input = ""
with open('main.sat') as f:
    text_input = f.read()

lexer = Lexer().get_lexer()
tokens = lexer.lex(text_input)

codegen = CodeGen('main.sat', opt_level=1)

module = codegen.module
builder = codegen.builder

pg = Parser(module, builder)
pg.parse()
parser = pg.get_parser()
parser.parse(tokens).eval()

ir = codegen.create_ir()
codegen.save_ir("output.ll", ir)

os.system('llc -O2 -o main.s output.ll')
print('llc -filetype=obj -O2 -o main.o output.ll')
os.system('llc -filetype=obj -O2 -o main.o output.ll')
print('lld-link -out:main.exe -defaultlib:libcmt -libpath:"C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.26.28801/lib/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/ucrt/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/um/x64" -nologo "main.o"')
os.system('lld-link -out:main.exe -defaultlib:libcmt -libpath:"C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.26.28801/lib/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/ucrt/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/um/x64" -nologo "main.o"')