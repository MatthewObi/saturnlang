import time

from lexer import Lexer
from sparser import Parser
from codegen import CodeGen
from package import Package, Module
from cachedmodule import CachedModule

import sys
import os
import glob

opt_level = 0
use_emscripten = False

files = []
eval_files = []
llfiles = []
linkfiles = []

cachedmods = {}

compile_target = 'windows-x64'


if __name__ == "__main__":
    n1 = time.perf_counter()
    if len(sys.argv) > 1:
        if sys.argv[1] == '--clean':
            for f in glob.glob("*.o"):
                os.remove(f)

        if '-O1' in sys.argv:
            opt_level = 1
        if '-O2' in sys.argv:
            opt_level = 2
        if '--target=wasm' in sys.argv:
            compile_target = 'wasm'

        if '--use-emscripten' in sys.argv:
            use_emscripten = True

    package = Package('main')

    for f in glob.glob("*.sat"):
        mod_t = os.path.getmtime(f)
        objf = f.replace('.sat', '.o')
        if not os.path.exists(objf):
            files.append(f)
            eval_files.append(f)
            continue
        obj_t = os.path.getmtime(objf)
        print(f"{f}: {mod_t}, {objf}: {obj_t}")
        if mod_t > obj_t:
            files.append(f)
        eval_files.append(f)

    for file in files:
        package.add_module(file.rstrip('.sat'))
        mod = package.get_module(file.rstrip('.sat'))
        mod.codegen = CodeGen(file, opt_level=opt_level, compile_target=compile_target)
        mod.ir_module = mod.codegen.module

    for ff in files:
        print(f"Parsing {ff}...")
        if ff not in cachedmods.keys():
            ev_text_input = ""
            with open(ff) as f:
                ev_text_input = f.read()

            cff = CachedModule(ff, ev_text_input)
            cachedmods[ff] = cff

        ev_mod = cachedmods[ff]

        evlexer = Lexer().get_lexer()
        evtokens = evlexer.lex(ev_mod.text_input)

        ffmod = package.get_module(ff.rstrip('.sat'))
        builder = ffmod.codegen.builder
        module = ffmod.codegen.module

        ev_pg = Parser(module, builder, package, False)
        ev_pg.parse()
        ev_parser = ev_pg.get_parser()
        ast = ev_parser.parse(evtokens)
        ast.generate_symbols()
        ev_mod.add_parsed_ast(ast)

        # builder.filestack.pop(-1)
        # builder.filestack_idx -= 1
        #
        # module.filestack.pop(-1)
        # module.filestack_idx -= 1
        #
        # builder.filestack.append(ev_mod.text_input)
        # builder.filestack_idx += 1
        #
        # module.filestack.append(ff)
        # module.filestack_idx += 1

    for ff in files:
        f1 = time.perf_counter()
        ffll = ff[:-4]
        print(f"satc -o {ffll}.ll {ff}")
        evalfiles = eval_files.copy()
        evalfiles.remove(ff)

        if ff not in cachedmods.keys():
            text_input = ""
            with open(ff) as f:
                text_input = f.read()

            cff = CachedModule(ff, text_input)
            cachedmods[ff] = cff

        cmod = cachedmods[ff]
        codegen = package.get_module(ff.rstrip('.sat')).codegen
        package.cachedmods = cachedmods

        if cmod.ast is None:

            lexer = Lexer().get_lexer()
            tokens = lexer.lex(cmod.text_input)

            module = codegen.module
            builder = codegen.builder

            builder.filestack = [cmod.text_input]
            builder.filestack_idx = 0
            builder.cachedmods = cachedmods

            module.filestack = [ff]
            module.filestack_idx = 0

            pg = Parser(module, builder, package, False)
            pg.parse()

            parser = pg.get_parser()
            parser.parse(tokens).eval()
        else:
            builder = codegen.builder
            module = codegen.module

            builder.filestack = [cmod.text_input]
            builder.filestack_idx = 0
            builder.cachedmods = cachedmods

            module.filestack = [ff]
            module.filestack_idx = 0

            cmod.ast.eval()

        if compile_target == 'wasm':
            if ff == 'main.sat':
                codegen.create_entry()

        ir = codegen.create_ir()
        dest = ff[:-4]
        codegen.save_ir(dest + '.ll', ir)
        llfiles.append(dest)
        f2 = time.perf_counter()
        print(f"Compiled file in {f2-f1} seconds.")

    package.save_symbols_to_file('symbols.json')

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
        linkcmd = 'emcc -o ./wasm/index.html ' if use_emscripten \
            else 'wasm-ld -o ./wasm/static/main.wasm -L./wasm/sysroot/lib/wasm32-wasi -lc -lrt "./wasm/sysroot/lib/wasm32-wasi/crt1.o" '
    elif compile_target == 'windows-x64':
        linkcmd = 'lld-link -subsystem:console -out:main.exe -defaultlib:libcmt -libpath:"C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.26.28801/lib/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/ucrt/x64" -libpath:"C:/Program Files (x86)/Windows Kits/10/Lib/10.0.18362.0/um/x64" -nologo '

    for llf in linkfiles:
        linkcmd += f'"{llf}" '
    print(linkcmd)
    os.system(linkcmd)
    n2 = time.perf_counter()
    print(f"Compiled program in {n2-n1} seconds.")

