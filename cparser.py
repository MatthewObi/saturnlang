import rply.token
from pycparser import c_parser, c_ast, parse_file
from typesys import types, FuncType, Func, StructType
from ast import LValue, StringLiteral
from llvmlite import ir
import sys

sys.path.extend(['.', '..'])


def parse_c_file(builder, module, package, path):
    ast = parse_file(filename=path,
                     use_cpp=True,
                     cpp_path='clang',
                     cpp_args=['-E', r'-Iutils/fake_libc_include'])

    # ast.show()

    for ext in ast.ext:
        if isinstance(ext, c_ast.Decl):
            if isinstance(ext.type, c_ast.Struct):
                cstruct = ext.type
                create_c_struct(builder, module, package, cstruct)
                # print(f"type {cstruct.name}: c_struct", "{")
                # for decl in cstruct.decls:
                #     print(f"    {decl.name}: {str(get_type(decl.type))}")
                # print("}")
        if isinstance(ext, c_ast.Typedef):
            if isinstance(ext.type.type, c_ast.Struct) and ext.type.type.decls is not None:
                cstruct = ext.type.type
                create_typedef_c_struct(builder, module, package, cstruct, ext.type.declname)
                # print(f"type {ext.type.declname}: c_struct", "{")
                # for decl in cstruct.decls:
                #    print(f"    {decl.name}: {str(get_type(decl.type))}")
                # print("}")
            else:
                pass  # print(f"type {ext.type.declname}: c_struct {ext.type.type.name};")
        if isinstance(ext, c_ast.FuncDef):
            create_c_funcdecl(builder, module, package, ext)
            continue


def get_type(node):
    if isinstance(node, c_ast.IdentifierType):
        base = types["C::" + node.names[0]]
        return base
    if isinstance(node, c_ast.PtrDecl):
        return get_type(node.type).get_pointer_to()
    else:
        return get_type(node.type)


def create_typedef_c_struct(builder, module, package, node, name):
    node.show()
    fields = [(decl.name, get_type(decl.type)) for decl in node.decls]
    types["C::" + name] = StructType(name, module.context.get_identified_type(name), [])
    if len(fields) > 0:
        for fld in fields:
            types["C::" + name].add_field(StringLiteral(builder, module, package, None, fld[0]), fld[1], None)
    if module.context.get_identified_type(name).is_opaque and len(fields) > 0:
        idstruct = module.context.get_identified_type(name)
        idstruct.set_body(*[field[1].irtype for field in fields])


def create_c_struct(builder, module, package, node):
    name = node.name
    fields = [(decl.name, get_type(decl.type)) for decl in node.decls]
    types["C::" + name] = StructType(name, module.context.get_identified_type(name), [])
    if len(fields) > 0:
        for fld in fields:
            types["C::" + name].add_field(StringLiteral(builder, module, package, None, fld[0]), fld[1], None)
    if module.context.get_identified_type(name).is_opaque and len(fields) > 0:
        idstruct = module.context.get_identified_type(name)
        idstruct.set_body(*[field[1].irtype for field in fields])


def create_c_funcdecl(builder, module, package, node):
    decl = node.decl
    name = decl.name
    rtype = get_type(decl.type)
    args = []
    for param_decl in decl.type.args.params:
        args.append((param_decl.name, get_type(param_decl.type)))
    # print(f"fn {name}({[str(arg[1]) for arg in args]}): {rtype};")
    sargtypes = [arg[1] for arg in args]
    argtypes = [arg.irtype for arg in sargtypes]
    fnty = ir.FunctionType(rtype.irtype, argtypes)
    # print("%s (%s)" % (self.name.value, fnty))
    sfnty = FuncType("", fnty, rtype, sargtypes)
    fname = name
    fn = ir.Function(module, fnty, fname)
    fn.args = tuple([ir.Argument(fn, arg[1].irtype, arg[0]) for arg in args])
    # self.module.sfunctys[self.name.value] = sfnty
    if name not in module.sfuncs:
        module.sfuncs[name] = Func(name, sfnty.rtype)
        module.sfuncs[name].add_overload(sfnty.atypes, fn)
    else:
        module.sfuncs[name].add_overload(sfnty.atypes, fn)
