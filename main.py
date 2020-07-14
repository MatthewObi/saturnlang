from lexer import Lexer
from sparser import Parser
from codegen import CodeGen
from cachedmodule import CachedModule, cachedmods

import sys
import os
import glob

opt_level = 0

files = []
llfiles = []

for f in glob.glob("*.sat"):
    files.append(f)

for ff in files:
    print("Building %s..." % ff)
    evalfiles = files.copy()
    evalfiles.remove(ff)

    if ff not in cachedmods.keys():
        text_input = ""
        with open(ff) as f:
            text_input = f.read()
        
        cff = CachedModule(ff, text_input)
        cachedmods[ff] = cff

    cmod = cachedmods[ff]

    lexer = Lexer().get_lexer()
    tokens = lexer.lex(cmod.text_input)

    codegen = CodeGen(ff, opt_level=opt_level)

    module = codegen.module
    builder = codegen.builder

    builder.filestack = [cmod.text_input]
    builder.filestack_idx = 0

    module.filestack = [ff]
    module.filestack_idx = 0

    pg = Parser(module, builder, False)
    pg.parse()

    for evalf in evalfiles:
        if evalf not in cachedmods.keys():
            ev_text_input = ""
            with open(evalf) as f:
                ev_text_input = f.read()
            
            cff = CachedModule(ff, ev_text_input)
            cachedmods[evalf] = cff

        ev_mod = cachedmods[evalf]

        evlexer = Lexer().get_lexer()
        evtokens = evlexer.lex(ev_mod.text_input)

        builder.filestack.append(ev_mod.text_input)
        builder.filestack_idx += 1

        module.filestack.append(evalf)
        module.filestack_idx += 1

        ev_pg = Parser(module, builder, True)
        ev_pg.parse()
        ev_parser = ev_pg.get_parser()
        ev_parser.parse(evtokens).eval()

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