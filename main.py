from lexer import Lexer
from sparser import Parser
from codegen import CodeGen, compile_target
from cachedmodule import CachedModule, cachedmods

import sys
import os
import glob

opt_level = 0

files = []
eval_files = []
llfiles = []
linkfiles = []

if len(sys.argv) > 1:
    if sys.argv[1] == '--clean':
        for f in glob.glob("*.o"):
            os.remove(f)

    if '-O1' in sys.argv:
        opt_level = 1
    if '-O2' in sys.argv:
        opt_level = 2

for f in glob.glob("*.sat"):
    mod_t = os.path.getmtime(f)
    objf = f.replace('.sat', '.o')
    if not os.path.exists(objf):
        files.append(f)
        eval_files.append(f)
        continue
    obj_t = os.path.getmtime(objf)
    if mod_t > obj_t:
        files.append(f)
    eval_files.append(f)

for ff in files:
    ffll = ff[:-4]
    print("satc -o %s.ll %s" % (ffll, ff))
    evalfiles = eval_files.copy()
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
    dest = ff[:-4]
    codegen.save_ir(dest + '.ll', ir)
    llfiles.append(dest)

for llf in llfiles:
    ll = llf + '.ll'
    os.system('llc -O2 -o %s %s' % (llf + '.s', ll))
    print('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))
    os.system('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))


modifiedobjs = []
exe_t = os.path.getmtime('main.exe')
for f in glob.glob("*.o"):
    obj_t = os.path.getmtime(f)
    linkfiles.append(f)
    if obj_t > exe_t:
        modifiedobjs.append(f)
if len(modifiedobjs) == 0:
    print('Project up to date. Nothing to do.')
    exit(0)

linkcmd = ''
if compile_target == 'wasm':
    linkcmd = 'wasm-ld -o main.wasm -entry main --export-all -L./test/sysroot/lib/wasm32-wasi -lc '
elif compile_target == 'windows-x64':
    linkcmd = 'lld-link -out:main.exe -defaultlib:libcmt -libpath:"C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.26.28801/lib/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/ucrt/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/um/x64" -nologo '

for llf in linkfiles:
    linkcmd += '"%s" ' % llf
print(linkcmd)
os.system(linkcmd)