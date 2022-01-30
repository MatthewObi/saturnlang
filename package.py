import json
from llvmlite import ir
from compilerutil import targets


class Visibility:
    """
    The visibility of a symbol can be one of three different values:\n
    private: The symbol is only viewable by other symbols in the same module (file).\n
    (default): The symbol is viewable by other symbols in the same package.\n
    public: The symbol is viewable by other symbols in other packages that import the containing package.
    """
    PRIVATE = 0
    DEFAULT = 1
    PUBLIC  = 2

    VALUE = [
        'priv',
        'default',
        'pub'
    ]

    INDEX = {
        'priv': 0,
        'default': 1,
        'pub': 2
    }


class LinkageType:
    PRIVATE = 0
    INTERNAL = 1
    LINK_ONCE = 2
    LINK_ONCE_ODR = 3
    WEAK = 4
    WEAK_ODR = 5
    COMMON = 6
    APPENDING = 7
    AVAILABLE_EXTERNALLY = 8
    EXTERNAL = 9
    EXTERN_WEAK = 10
    DEFAULT = 11

    VALUE = [
        'private',
        'internal',
        'linkonce',
        'linkonce_odr',
        'weak',
        'weak_odr',
        'common',
        'appending',
        'available_externally',
        'external',
        'extern_weak',
        ''
    ]

    INDEX = {
        'private': 0,
        'internal': 1,
        'linkonce': 2,
        'linkonce_odr': 3,
        'weak': 4,
        'weak_odr': 5,
        'common': 6,
        'appending': 7,
        'available_externally': 8,
        'external': 9,
        'extern_weak': 10,
        '': 11,
        'default': 11
    }


class SymbolType:
    DECLARATION = 0
    DEFINITION = 1


class Symbol:
    """
    A single symbol.\n
    name: The name of the symbol.\n
    parent: The parent symbol of the symbol (default is None)\n
    visibility: The visibility of the symbol (default is default)\n
    link_type: The linkage type of the symbol (default is external)
    """
    def __init__(self, name, parent=None, visibility=Visibility.DEFAULT, link_type=LinkageType.DEFAULT, c_decl=False):
        self.name = name
        self.visibility = visibility
        self.link_type = link_type
        self.link_name = self.name
        self.parent = parent
        self.irvalue = {}
        self.symbols = {}
        self.c_decl = c_decl

    def __getitem__(self, item):
        return self.symbols[item]

    def __setitem__(self, key, value):
        self.symbols[key] = value

    def get_ir_value(self, module: ir.Module):
        key = hash(module)
        if key not in self.irvalue:
            return None
        return self.irvalue[key]

    def lookup_symbol(self, key):
        parts = key.split("::")
        sym = self
        for part in parts:
            if part not in sym.symbols:
                if self.parent is not None:
                    self.parent.lookup_symbol(key)
                return None
            sym = sym[part]
        return sym

    def add_ir_value(self, module, ir_value):
        key = hash(module)
        self.irvalue[key] = ir_value

    def get_full_name(self):
        if self.parent is not None:
            return self.parent.get_full_name() + '::' + self.name
        return self.name

    def is_private(self):
        return self.visibility == Visibility.PRIVATE

    def is_public(self):
        return self.visibility == Visibility.PUBLIC

    def is_default_viewable(self):
        return self.visibility == Visibility.DEFAULT

    def is_viewable_to_same_package(self):
        return self.visibility > Visibility.PRIVATE

    def is_private_linkage(self):
        return self.link_type == LinkageType.PRIVATE

    def is_external_linkage(self):
        return self.link_type == LinkageType.EXTERNAL or self.link_type == LinkageType.DEFAULT

    def to_dict(self):
        d = {'visible': Visibility.VALUE[self.visibility],
             'link_type': 'default' if LinkageType.VALUE[self.link_type] == '' else LinkageType.VALUE[self.link_type],
             'name': self.name,
             'symbol_type': 'symbol'}
        if self.c_decl:
            d['c_decl'] = True
        if self.link_name != self.name:
            d['link_name'] = self.link_name
        return d

    def from_dict(self, d):
        self.visibility = Visibility.INDEX[d['visible']]
        self.link_type = Visibility.INDEX[d['link_type']]
        self.c_decl = d['c_decl'] if 'c_decl' in d else False
        self.name = d['name']
        self.link_name = d['link_name'] if 'link_name' in d else self.name

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} symbol {self.get_full_name()} " \
            f"({'default' if LinkageType.VALUE[self.link_type] == '' else LinkageType.VALUE[self.link_type]})"
        return s


class Module(Symbol):
    def __init__(self, package, name):
        from llvmlite import ir
        super().__init__(name)
        self.package = package
        self.symbols = self.package.symbols
        self.codegen = None
        self.ir_module = None
        self.ast = None

    def initialize_module(self):
        pass

    def add_ast(self, ast):
        self.ast = ast

    def get_available_symbols(self):
        return {k: v for k, v in self.symbols.items() if v.is_viewable_to_same_package()}


class Package(Symbol):
    _cache = {}

    def __init__(self, name, working_directory='.', out_file='', target=None):
        super().__init__(name)
        self.modules = {}
        self.current_module = None
        self.c_package = None
        self.imported_packages = {}
        self.working_directory = working_directory
        self.out_file = out_file
        if target is None:
            self.target = targets['native']
        else:
            self.target = target

    @classmethod
    def get_or_create(cls, name, working_directory='.', out_file='', target=targets['native']):
        if name not in cls._cache:
            cls._cache[name] = Package(name, working_directory, out_file, target)
        return cls._cache[name]

    def get_or_create_c_package(self):
        if self.c_package is None:
            self.c_package = Package("C", working_directory=self.working_directory)
        return self.c_package

    def load_symbols_from_file(self, module, file):
        with open(file) as f:
            d = json.load(f)
            self.current_module = module
            self.from_dict(d)

    def save_symbols_to_file(self, file):
        with open(self.working_directory + '/' + file, 'w') as f:
            json.dump(self.to_dict(), f, indent=1)

    def add_module(self, name):
        self.modules[name] = Module(self, name)

    def add_or_get_module(self, name):
        if name not in self.modules:
            self.modules[name] = Module(self, name)
        return self.modules[name]

    def get_module(self, name):
        return self.modules[name]

    def add_symbol(self, lvalue, value):
        value.parent = self
        self.symbols[lvalue] = value
        return self.symbols[lvalue]

    def add_symbol_extern(self, lvalue, value):
        self.symbols[lvalue] = value
        return self.symbols[lvalue]

    def get_or_add_symbol(self, lvalue, value):
        if lvalue not in self.symbols:
            self.add_symbol(lvalue, value)
        return self.symbols[lvalue]

    def add_symbol_weak(self, lvalue, value):
        if lvalue not in self.symbols:
            self.add_symbol(lvalue, value)

    def add_symbol_odr(self, lvalue, value):
        if lvalue not in self.symbols:
            self.add_symbol(lvalue, value)
        else:
            raise RuntimeError(f"Can't add symbol '{lvalue}' to package '{self.name}'. Symbol already declared.")

    def import_package(self, package):
        if package is self:
            return
        self.imported_packages[package.name] = package
        self[package.name] = package

    def import_symbols_from_package(self, package, symbols):
        if package is self:
            return
        self.imported_packages[package.name] = package
        for symbol in symbols:
            name = symbol.get_name()
            sym = package.lookup_symbol(name)
            if sym is None:
                raise RuntimeError(f"Cannot import symbol '{name}' from package '{package.name}'")
            self.add_symbol_extern(symbol.name, sym)

    def import_all_symbols_from_package(self, package):
        if package is self:
            return
        self.imported_packages[package.name] = package
        for symbol in package.symbols.values():
            self.add_symbol_weak(symbol.name, symbol)
        self[package.name] = package

    def __getitem__(self, item):
        if item not in self.symbols:
            return None
        return self.symbols[item]

    def __setitem__(self, key, value):
        self.symbols[key] = value

    def to_dict(self):
        d = super().to_dict()
        d['type'] = 'package'
        d['children'] = {k: v.to_dict() for (k, v) in self.symbols.items() if v.is_viewable_to_same_package()}
        return d

    def from_dict(self, d):
        super().from_dict(d)
        from typesys import symbol_from_dict
        for k, v in d['children'].items():
            self.add_symbol(k, symbol_from_dict(self, self.current_module, v))

    def __str__(self):
        s = f"package {self.name}\n"
        for symbol in self.symbols.values():
            nxt = str(symbol)
            if nxt is None:
                nxt = "?????"
            s += '\t' + f"{nxt}\n"
        return s
