from typesys import Func, FuncOverload, FuncType, types, mangle_symbol, demangle_symbol, demangle_name, \
    demangle_name_as_function, demangle_name_as_variable, Value
from package import Symbol, Package
from llvmlite import ir

i32 = ir.IntType(32)
i8 = ir.IntType(8)

int32 = types['int32']
uint8 = types['uint8']


def test_mangling():
    test_package: Package = Package.get_or_create('User')
    irtype = ir.FunctionType(i32, [i8.as_pointer()])
    fn = Func('ATest', int32)
    ovrld = FuncOverload('', None, int32, [uint8.get_pointer_to()])
    fn.add_existing_overload(ovrld)
    test_package.add_symbol(fn.name, fn)
    name = mangle_symbol(fn, atypes=[uint8.get_pointer_to()])
    fn_value = Value('Co', int32, None)
    fn[fn_value.name] = fn_value
    fn_value.parent = fn
    print(ovrld, name, demangle_name_as_function(name), irtype)


def test_demangling():
    print(demangle_name_as_function('_ZN3std4math3sinEdd'))
    print(demangle_name_as_function('_ZN3std4math3sinEiRSN3std3str'))
    print(demangle_name_as_function('_ZN3std3alg4sortERMSN3std6vectorT1d'))
    print(demangle_name_as_function('_ZN3std3alg4sortT1SN3std6vectorT1dERM_0'))
    print(demangle_name_as_variable('_ZN3std4math2piT1fE'))
    print(demangle_name_as_variable('_ZN3std4math2piT1dE'))
    print(demangle_name_as_function('_ZN3std3alg4sortT1SN3std6vectorT1dERM_0PFi2R_0R_0'))
    print(demangle_name_as_function('_ZN3std3alg4sortERMSN3std6vectorT1dPFi2RSN3std6vectorT1dRSN3std6vectorT1d'))


if __name__ == '__main__':
    test_mangling()
