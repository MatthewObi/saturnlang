import rply.token
from pycparser import c_parser, c_ast, parse_file
from typesys import types, FuncType, Func, StructType, Value
from ast import LValue, StringLiteral
from llvmlite import ir
from package import Package, Visibility
import sys

sys.path.extend(['.', '..'])


def parse_c_file(builder, module, package, path):
    ast = parse_file(filename=path,
                     use_cpp=True,
                     cpp_path='clang',
                     cpp_args=['-nobuiltininc',
                               '-D__cdecl=',
                               '-D__fastcall=',
                               '-D__inline=inline',
                               '-D__restrict=',
                               '-D__declspec(x)=',
                               '-D__attribute__(x)=',
                               '-D__asm__(x)=',
                               '-D__extension__=',
                               '-D__int64=long',
                               '-E', r'-Iutils/fake_libc_include']
                     )

    # ast.show()
    c_package = package.get_or_create_c_package()

    for ext in ast.ext:
        if isinstance(ext, c_ast.Decl):
            # ext.show()
            if isinstance(ext.type, c_ast.FuncDecl):
                # ext.type.show()
                create_c_funcdecl(builder, module, c_package, ext.name, ext.type)
                continue
            if isinstance(ext.type, c_ast.TypeDecl):
                # ext.type.show()
                # print(*ext.storage, ext.type.declname, ':', str(get_type(ext.type.type, module, c_package)))
                if 'static' in ext.storage:
                    continue
                create_c_global_var(builder, module, c_package, ext.type.declname, ext.type)
                continue
            if isinstance(ext.type, c_ast.PtrDecl):
                if isinstance(ext.type.type, c_ast.FuncDecl):
                    funcdecl = ext.type.type
                    # print(funcdecl.type.declname, ':', str(get_type(ext.type, module, c_package)))
                    create_c_global_var(builder, module, c_package, funcdecl.type.declname, ext)
                    continue
                # print(*ext.storage, ext.type.declname, ':', str(get_type(ext.type.type)))
                if 'static' in ext.storage:
                    continue
                create_c_global_var(builder, module, c_package, ext.type.declname, ext.type)
                continue
            if isinstance(ext.type, c_ast.Struct):
                cstruct = ext.type
                create_c_struct(builder, module, c_package, cstruct)
        if isinstance(ext, c_ast.Typedef):
            if isinstance(ext.type.type, c_ast.Struct) and ext.type.type.decls is not None:
                cstruct = ext.type.type
                create_typedef_c_struct(builder, module, c_package, cstruct, ext.type.declname)
            else:
                dtype = get_type(ext.type, module, c_package)
                tname = "C::" + ext.name
                types[tname] = dtype
                # print(f"type {tname}: {dtype};")
        if isinstance(ext, c_ast.FuncDef):
            create_c_funcdecl_from_def(builder, module, c_package, ext)
            continue

    package.import_all_symbols_from_package(c_package)


def get_type(node, module: ir.Module, package: Package):
    if isinstance(node, c_ast.IdentifierType):
        pname = ""
        for name in node.names:
            pname += name + "."
        base = types["C::" + pname[:-1]]
        return base
    if isinstance(node, c_ast.PtrDecl):
        ty = get_type(node.type, module, package)
        if isinstance(ty.get_ir_type(), ir.VoidType):
            return types["C::char"].get_pointer_to()
        else:
            return ty.get_pointer_to()
    if isinstance(node, c_ast.Struct):
        if node.name is None:
            sname = module.get_unique_name("C::_unnamed_struct")
        else:
            sname = "C::" + node.name
        stype = StructType(node.name, module.context.get_identified_type(node.name), [])
        types[sname] = stype
        package.add_symbol(node.name, stype)
        return types[sname]
    if isinstance(node, c_ast.Union):
        if node.name is None:
            name = module.get_unique_name("_unnamed_union")
        else:
            name = node.name
        sname = "C::" + name
        stype = StructType(name, module.context.get_identified_type(name), [])
        types[sname] = stype
        package.add_symbol(name, stype)
        return types[sname]
    if isinstance(node, c_ast.FuncDecl):
        rtype = get_type(node.type, module, package)
        args = []
        for param_decl in node.args.params:
            args.append((param_decl.name, get_type(param_decl.type, module, package)))
        sargtypes = [arg[1] for arg in args]
        argtypes = [arg.get_ir_type() for arg in sargtypes]
        fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
        sfnty = FuncType("", fnty, rtype, sargtypes)
        return sfnty
    return get_type(node.type, module, package)


def create_typedef_c_struct(builder, module, package, node, name):
    fields = [(decl.name, get_type(decl.type, module, package)) for decl in node.decls]
    stype = StructType(name, module.context.get_identified_type(name), [])
    sname = "C::" + name
    types[sname] = stype
    package.add_symbol(name, stype)
    s_str = f"type {str(types[sname])}: struct"
    if len(fields) > 0:
        s_str += ' {'
        for fld in fields:
            s_str += f" {fld[0]}: {fld[1]},"
            types[sname].add_field(fld[0], fld[1], None)
        s_str = s_str.rstrip(",") + " }"
    else:
        s_str += ';'
    # print(s_str)
    if module.context.get_identified_type(name).is_opaque and len(fields) > 0:
        idstruct = module.context.get_identified_type(name)
        idstruct.set_body(*[field[1].get_ir_type() for field in fields])


def create_c_struct(builder, module, package, node):
    name = "C::" + node.name
    if node.decls is not None:
        fields = [(decl.name, get_type(decl.type, module, package)) for decl in node.decls]
    else:
        fields = []
    stype = StructType(node.name, module.context.get_identified_type(node.name), [])
    types[name] = stype
    package.add_symbol(node.name, stype)
    if len(fields) > 0:
        for fld in fields:
            types[name].add_field(fld[0], fld[1], None)
    if module.context.get_identified_type(node.name).is_opaque and len(fields) > 0:
        idstruct = module.context.get_identified_type(node.name)
        idstruct.set_body(*[field[1].irtype for field in fields])


def create_c_funcdecl_from_def(builder, module, package, node):
    decl = node.decl
    name = decl.name
    typedecl: c_ast.FuncDecl = decl.type
    rtype = get_type(typedecl.type, module, package)
    args = []
    for param_decl in decl.type.args.params:
        args.append((param_decl.name, get_type(param_decl.type, module, package)))
    # print(f"fn {name}({[str(arg[1]) for arg in args]}): {rtype};")
    sargtypes = [arg[1] for arg in args]
    argtypes = [arg.get_ir_type() for arg in sargtypes]
    fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
    # print("%s (%s)" % (self.name.value, fnty))
    sfnty = FuncType("", fnty, rtype, sargtypes)
    fname = "C::" + name
    fn = ir.Function(module, fnty, name)
    fn.args = tuple([ir.Argument(fn, arg[1].get_ir_type(), arg[0]) for arg in args])

    arg_str = ""
    for sarg in sargtypes:
        arg_str += f"{str(sarg)}, "
    arg_str = arg_str.rstrip(", ")
    # print(f"fn {fname}({arg_str}): {str(rtype)}")

    # self.module.sfunctys[self.name.value] = sfnty
    if fname not in module.sfuncs:
        module.sfuncs[fname] = Func(fname, sfnty.rtype, c_decl=True, visibility=Visibility.PRIVATE)
        package.add_symbol(name, module.sfuncs[fname])
        module.sfuncs[fname].add_overload(sfnty.atypes, fn)
    else:
        module.sfuncs[fname].add_overload(sfnty.atypes, fn)


def create_c_funcdecl(builder, module: ir.Module, package, name, decl):
    rtype = get_type(decl.type, module, package)
    args = []
    for param_decl in decl.args.params:
        args.append((param_decl.name, get_type(param_decl.type, module, package)))
    # print(f"fn {name}({[str(arg[1]) for arg in args]}): {rtype};")
    sargtypes = [arg[1] for arg in args]
    argtypes = [arg.get_ir_type() for arg in sargtypes]
    fnty = ir.FunctionType(rtype.get_ir_type(), argtypes)
    # print("%s (%s)" % (self.name.value, fnty))
    sfnty = FuncType("", fnty, rtype, sargtypes)
    fname = "C::" + name
    try:
        fn = module.get_global(name)
    except KeyError:
        fn = ir.Function(module, fnty, name)
    if len(args) > 0 and not isinstance(args[0][1].get_ir_type(), ir.VoidType):
        fn.args = tuple([ir.Argument(fn, arg[1].get_ir_type(), arg[0]) if arg[0] is not None
                         else ir.Argument(fn, arg[1].get_ir_type()) for arg in args])
    else:
        fn.args = tuple()
    arg_str = ""
    for sarg in sargtypes:
        arg_str += f"{str(sarg)}, "
    arg_str = arg_str.rstrip(", ")
    # print(f"fn {fname}({arg_str}): {str(rtype)}")
    # self.module.sfunctys[self.name.value] = sfnty
    if fname not in module.sfuncs:
        module.sfuncs[fname] = Func(name, sfnty.rtype, c_decl=True, visibility=Visibility.PRIVATE)
        package.add_symbol(name, module.sfuncs[fname])
        module.sfuncs[fname].add_overload(sfnty.atypes, fn)
    else:
        module.sfuncs[fname].add_overload(sfnty.atypes, fn)


def create_c_global_var(builder, module, package, name, node):
    ty = get_type(node.type, module, package)
    try:
        var = module.get_global(name)
    except KeyError:
        var = ir.GlobalVariable(module, ty.get_ir_type(), name)
    val = Value(name, ty, var, objtype='global')
    package.add_symbol(name, val)
