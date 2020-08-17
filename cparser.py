from pycparser import c_parser, c_ast

def parse_c_file(builder, module, path):
    parser = c_parser.CParser()
    text = ""
    with open(path) as f:
        text = f.read()
        
    ast = parser.parse(text, filename=path)

    for ext in ast.ext:
        if isinstance(ext, c_ast.FuncDef):
            create_c_funcdecl(builder, module, ext)
            continue

def get_type_str(node):
    if isinstance(node, c_ast.IdentifierType):
        return node.names[0]
    if isinstance(node, c_ast.PtrDecl):
        return "*" + get_type_str(node.type)
    else:
        return get_type_str(node.type)

def create_c_funcdecl(builder, module, node):
    decl = node.decl
    name = decl.name
    rtype = get_type_str(decl.type)
    pstring = 'fn %s(' % name
    for param_decl in decl.type.args.params:
        pstring += '%s : %s, ' % (param_decl.name, get_type_str(param_decl.type))
    pstring = pstring.rstrip(', ')
    pstring += '): %s;' % rtype
    print(pstring)