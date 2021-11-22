import json


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
    def __init__(self, name, parent=None, visibility=Visibility.DEFAULT, link_type=LinkageType.DEFAULT):
        self.name = name
        self.visibility = visibility
        self.link_type = link_type
        self.parent = parent
        self.irvalue = None
        self.symbols = {}

    def __getitem__(self, item):
        return self.symbols[item]

    def __setitem__(self, key, value):
        self.symbols[key] = value

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

    def get_ir_value(self):
        if self.irvalue is None:
            pass
        return self.irvalue

    def add_ir_value(self, ir_value):
        self.irvalue = ir_value

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
             'type': 'symbol'}
        return d

    def from_dict(self, d):
        self.visibility = Visibility.INDEX[d['visible']]
        self.link_type = Visibility.INDEX[d['link_type']]
        self.name = d['name']

    def __str__(self):
        s = f"{Visibility.VALUE[self.visibility]} symbol {self.get_full_name()} " \
            f"({'default' if LinkageType.VALUE[self.link_type] == '' else LinkageType.VALUE[self.link_type]})"
        return s


class Module(Symbol):
    def __init__(self, package, name):
        super().__init__(name)
        self.package = package
        self.symbols = self.package.symbols
        self.codegen = None
        self.ir_module = None


class Package(Symbol):
    def __init__(self, name):
        super().__init__(name)
        self.modules = {}
        self.current_module = None
        self.imported_packages = {}

    def load_symbols_from_file(self, module, file):
        with open(file) as f:
            d = json.load(f)
            self.current_module = module
            self.from_dict(d)

    def save_symbols_to_file(self, file):
        with open(file, 'w') as f:
            json.dump(self.to_dict(), f)
            #json.dump({k: str(v) for (k, v) in self.symbols.items()}, f)

    def add_module(self, name):
        self.modules[name] = Module(self, name)

    def get_module(self, name):
        return self.modules[name]

    def add_symbol(self, lvalue, value):
        value.parent = self
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
        raise RuntimeError(f"Can't add symbol '{lvalue}' to package '{self.name}'. Symbol already declared.")

    def import_package(self, package):
        self.imported_packages[package.name] = package
        self[package.name] = package

    def import_symbols_from_package(self, package, symbols):
        self.imported_packages[package.name] = package
        for symbol in symbols:
            name = symbol.get_name()
            # print(*[str(sym) for sym in package.symbols.values()])
            sym = package.lookup_symbol(name)
            if sym is None:
                raise RuntimeError(f"Cannot import symbol '{name}' from package '{package.name}'")
            self.add_symbol(symbol.name, sym)

    def import_all_symbols_from_package(self, package):
        self.imported_packages[package.name] = package
        for symbol in package.symbols:
            self.add_symbol_weak(symbol.name, symbol)

    def __getitem__(self, item):
        if item not in self.symbols:
            return None
        return self.symbols[item]

    def __setitem__(self, key, value):
        self.symbols[key] = value

    def to_dict(self):
        d = super().to_dict()
        d['type'] = 'package'
        d['children'] = {k: v.to_dict() for (k, v) in self.symbols.items()}
        return d

    def from_dict(self, d):
        super().from_dict(d)
        from typesys import symbol_from_dict
        for k, v in d['children'].items():
            self.add_symbol(k, symbol_from_dict(self.current_module, d['children']))

    def __str__(self):
        s = f"package {self.name}\n"
        for symbol in self.symbols.values():
            s += '\t' + f"{str(symbol)}\n"
        return s
