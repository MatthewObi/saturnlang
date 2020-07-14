from lexer import Lexer
from sparser import Parser
from codegen import CodeGen

import sys
import os
import glob

opt_level = 0

files = []
llfiles = []

for f in glob.glob("*.sat"):
    files.append(f)

for ff in files:
    evalfiles = files.copy()
    evalfiles.remove(ff)

    text_input = ""
    with open(ff) as f:
        text_input = f.read()

    lexer = Lexer().get_lexer()
    tokens = lexer.lex(text_input)

    codegen = CodeGen(ff, opt_level=opt_level)

    module = codegen.module
    builder = codegen.builder

    builder.filestack = [text_input]
    builder.filestack_idx = 0

    module.filestack = [ff]
    module.filestack_idx = 0

    pg = Parser(module, builder)
    pg.parse()

    for evalf in evalfiles:
        ev_text_input = ""
        with open(evalf) as f:
            ev_text_input = f.read()

        ev_lexer = Lexer().get_lexer()
        ev_tokens = ev_lexer.lex(ev_text_input)

        builder.filestack.append(ev_text_input)
        builder.filestack_idx += 1

        module.filestack.append(evalf)
        module.filestack_idx += 1

        ev_pg = Parser(module, builder, True)
        ev_pg.parse()
        ev_parser = ev_pg.get_parser()
        ev_parser.parse(ev_tokens).eval()

        builder.filestack.pop(-1)
        builder.filestack_idx -= 1

        module.filestack.pop(-1)
        module.filestack_idx -= 1

    parser = pg.get_parser()
    parser.parse(tokens).eval()

    ir = codegen.create_ir()
    dest = ff.rstrip('.sat')
    codegen.save_ir(dest + '.ll', ir)
    llfiles.append(dest)

for llf in llfiles:
    ll = llf + '.ll'
    os.system('llc -O2 -o %s %s' % (llf + '.s', ll))
    print('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))
    os.system('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))

linkcmd = 'lld-link -out:main.exe -defaultlib:libcmt -libpath:"C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.26.28801/lib/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/ucrt/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/um/x64" -nologo '
for llf in llfiles:
    lls = llf + '.o'
    linkcmd += '"%s" ' % lls
print(linkcmd)
os.system(linkcmd)