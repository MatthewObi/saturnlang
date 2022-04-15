import pstats
import time

import llvmlite

from lexer import lexer
from sparser import parser, ParserState
from codegen import CodeGen, test_jit
from package import Package
from cachedmodule import CachedModule
from ctypes import create_string_buffer, c_char_p, pointer, byref
from compilerutil import CompileTarget, targets

import sys
import os
import glob

cachedmods = {}
packages = {}


class CommandArgs:
    def __init__(self):
        self.args = {}

    def add_arg(self, arg, value: str = ''):
        self.args[arg] = value

    def has_arg(self, arg):
        if arg not in self.args:
            return False
        return True

    def __getitem__(self, item):
        return self.args[item]


def parse_command_line_args() -> CommandArgs:
    command_args = CommandArgs()

    argv = sys.argv[1:]
    for value in argv:
        if value.startswith('-O'):
            opt_value = value.strip('-O')
            command_args.add_arg('O', opt_value)
            continue
        if value.startswith('-o'):
            value = next(value)
            command_args.add_arg('o', value)
            continue
        if value.startswith('--'):
            long_arg = value.strip('--')
            if '=' not in long_arg:
                command_args.add_arg(long_arg)
            else:
                k, v = long_arg.split('=', maxsplit=1)
                command_args.add_arg(k, v)
            continue

    return command_args


class PackageType:
    PROGRAM = 0
    LIBRARY = 1
    DYNAMIC = 2


def compile_package(name, working_directory='.',
                    opt_level=-1,
                    package_type=PackageType.LIBRARY) -> Package:
    from typesys import types
    global lexer
    global parser

    n1 = time.perf_counter()

    args = parse_command_line_args()
    compile_target = args['target'] if args.has_arg('target') else 'native'
    if opt_level == -1:
        opt_level = int(args['O']) if args.has_arg('O') else 0
    use_emscripten = True if args.has_arg('use-emscripten') else False
    clean = True if args.has_arg('clean') else False

    target = targets[compile_target]

    # Define output file using package type and compilation target.
    if package_type == PackageType.LIBRARY:
        out_file = f'{working_directory}/{name}.{target.short_name}.a' if not target.platform == 'windows' \
            else f'{working_directory}/{name}.{target.short_name}.lib'
    elif package_type == PackageType.PROGRAM:
        out_file = f'{working_directory}/{name}' if not target.platform == 'windows' \
            else f'{working_directory}/{name}.exe'
    elif package_type == PackageType.DYNAMIC:
        out_file = f'{working_directory}/{name}.{target.short_name}.so' if not target.platform == 'windows' \
            else f'{working_directory}/{name}.{target.short_name}.dll'
    else:
        out_file = f''

    # Clean files.
    if clean:
        for f in glob.glob(f"{working_directory}/*.o"):
            os.remove(f)
        for f in glob.glob(f"{working_directory}/symbols.{target.short_name}.json"):
            os.remove(f)
        for f in glob.glob(f"{out_file}"):
            os.remove(f)

    files = []
    eval_files = []
    llfiles = []
    linkfiles = []

    package = Package.get_or_create(name, working_directory=working_directory, out_file=out_file, target=target)
    # Add primitive type symbols to package.
    for ty in types.values():
        if not ty.name.startswith('C::'):
            from package import Visibility
            ty.visibility = Visibility.PRIVATE
            package.add_symbol_extern(ty.name, ty)
    print(f'Compiling package {name} in directory {working_directory} with target {target.name}...')

    # Get all .sat files in the current working directory.
    for f in glob.glob(f"{working_directory}/*.sat"):
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

    # Compile all .c files in current working directory.
    for f in glob.glob(f"{working_directory}/*.c"):
        if compile_target == 'wasm':
            if use_emscripten:
                print(f"emcc -c {f}")
                os.system(f"emcc -c {f}")
            else:
                target_triple = "wasm32-unknown-wasi"
                os.system(f'clang -c -target {target_triple} -I./wasm/sysroot/include {f}')
        else:
            if compile_target == 'windows-x64':
                target_triple = 'x86_64-pc-windows-msvc'
            elif compile_target == 'linux-x64':
                target_triple = 'x86_64-pc-linux-gcc'
            else:
                target_triple = 'x86_64-pc-windows-msvc'
            print(f"clang -S -target {target_triple} -emit-llvm {f}")
            os.system(f"clang -S -target {target_triple} -emit-llvm {f}")
            llfiles.append(f[:-2])

    for file in files:
        package.add_module(file.rstrip('.sat'))
        mod = package.get_module(file.rstrip('.sat'))
        mod.codegen = CodeGen(file, opt_level=opt_level, compile_target=target)
        mod.ir_module = mod.codegen.module

    for ff in files:
        print(f"Parsing {ff}...")
        if ff not in cachedmods.keys():
            with open(ff, encoding='utf8') as f:
                ev_text_input = f.read()

            cff = CachedModule(ff, ev_text_input)
            cachedmods[ff] = cff

        ev_mod = cachedmods[ff]
        package.cachedmods = cachedmods

        evtokens = lexer.lex(ev_mod.text_input)

        ffmod = package.get_module(ff.rstrip('.sat'))
        builder = ffmod.codegen.builder
        module = ffmod.codegen.module

        builder.filestack = [ev_mod.text_input]
        builder.filestack_idx = 0
        builder.cachedmods = cachedmods

        module.filestack = [ff]
        module.filestack_idx = 0

        ast = parser.parse(evtokens, state=ParserState(builder, module, package))
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
            with open(ff) as f:
                text_input = f.read()

            cff = CachedModule(ff, text_input)
            cachedmods[ff] = cff

        cmod = cachedmods[ff]
        codegen = package.get_module(ff.rstrip('.sat')).codegen
        package.cachedmods = cachedmods

        if cmod.ast is None:

            tokens = lexer.lex(cmod.text_input)

            module = codegen.module
            builder = codegen.builder

            builder.filestack = [cmod.text_input]
            builder.filestack_idx = 0
            builder.cachedmods = cachedmods

            module.filestack = [ff]
            module.filestack_idx = 0

            parser.parse(tokens, state=ParserState(module, builder, package, False)).eval()
        else:
            builder = codegen.builder
            module = codegen.module

            builder.filestack = [cmod.text_input]
            builder.filestack_idx = 0
            builder.cachedmods = cachedmods

            module.filestack = [ff]
            module.filestack_idx = 0

            cmod.ast.eval()

        if target.platform == 'wasm':
            if ff == 'main.sat':
                codegen.create_entry()

        ir = codegen.create_ir()
        dest = ff[:-4]
        codegen.save_ir(dest + '.ll', ir)

        llfiles.append(dest)
        f2 = time.perf_counter()
        print(f"Compiled file in {f2-f1} seconds.")

    package.save_symbols_to_file(f'symbols.{target.short_name}.json')

    for llf in llfiles:
        ll = llf + '.ll'
        os.system('llc -O2 -o %s %s' % (llf + '.s', ll))
        print('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))
        os.system('llc -filetype=obj -O2 -o %s %s' % (llf + '.o', ll))

    modifiedobjs = []
    if os.path.isfile(out_file):
        exe_t = os.path.getmtime(out_file)
        for f in glob.glob(f"{working_directory}/*.o"):
            obj_t = os.path.getmtime(f)
            linkfiles.append(f)
            if obj_t > exe_t:
                modifiedobjs.append(f)
    else:
        for f in glob.glob(f"{working_directory}/*.o"):
            linkfiles.append(f)
            modifiedobjs.append(f)
    if len(modifiedobjs) == 0:
        print('Package up to date. Nothing to do.')
        return package

    if package_type == PackageType.LIBRARY:
        linkcmd = f'llvm-ar -r {out_file} '
    elif package_type == PackageType.PROGRAM:
        if target.platform == 'wasm':
            linkcmd = 'emcc -o ./wasm/emscripten/index.html ' if use_emscripten \
                else 'wasm-ld -o ./wasm/static/main.wasm ' \
                     '-L./wasm/sysroot/lib/wasm32-wasi -lc -lrt ' \
                     '"./wasm/sysroot/lib/wasm32-wasi/crt1.o" '
        elif target.platform == 'windows':
            linkcmd = f'clang -m64 -Wall -Xlinker /subsystem:console -lShell32 -o {out_file} '
        elif target.platform == 'linux':
            linkcmd = f'clang -lc -lrt -lm -Wall -o {out_file} '
        else:
            raise RuntimeError('Cannot proceed. Target has undefined link command.')

    for link_package in package.imported_packages.values():
        if link_package.name == 'C':
            break
        lib_file = f'{link_package.working_directory}/{link_package.name}.{target.short_name}.a' \
            if not target.platform == 'windows' \
            else f'{link_package.working_directory}/{link_package.name}.{target.short_name}.lib'
        linkcmd += f'"{lib_file}" '
    for llf in linkfiles:
        linkcmd += f'"{llf}" '
    print(linkcmd)
    os.system(linkcmd)
    n2 = time.perf_counter()
    print(f"Compiled package in {n2-n1} seconds.")
    return package


def get_relative_directory_for_package(package_symbol):
    symbols = package_symbol.split('::')
    rel_dir = '.'
    for symbol in symbols:
        rel_dir += f'/packages/{symbol}'
    return rel_dir


def main():
    n1 = time.perf_counter()
    std_lang_package = compile_package('lang', working_directory=get_relative_directory_for_package('std::lang'),
                                       opt_level=2)
    std_math_package = compile_package('math', working_directory=get_relative_directory_for_package('std::math'),
                                       opt_level=2)
    main_package = compile_package('main', '.', package_type=PackageType.PROGRAM)

    n2 = time.perf_counter()
    print(f"Compiled program in {n2-n1} seconds.")

    # Uncomment the following line to test JIT-compilation (make sure you're building for your native system first!)
    # test_jit()


if __name__ == "__main__":
    main()
    # Uncomment the lines below and comment the line above to run the compiler with profiling.
    # import cProfile
    # cProfile.run('main()', "profile")
    # import pstats
    # from pstats import SortKey
    # p = pstats.Stats('profile')
    # p.strip_dirs().sort_stats(2).print_stats()
