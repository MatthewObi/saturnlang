import ctypes

from llvmlite import ir, binding
from irutil import TokenType

char = ir.IntType(8)
int1 = ir.IntType(1)
int8 = char
int8ptr = char.as_pointer()
int32 = ir.IntType(32)
int64 = ir.IntType(64)
double = ir.DoubleType()
void = ir.VoidType()


class CodeGen:
    def __init__(self, filename, opt_level, compile_target):
        self.binding = binding
        self.filename = filename
        self.opt_level = opt_level
        self.compile_target = compile_target
        self.binding.initialize()
        self.binding.initialize_native_target()
        self.binding.initialize_native_asmprinter()
        self._config_llvm()
        self._create_execution_engine()
        self._declare_print_function()

    def _config_llvm(self):
        # Config LLVM
        self.module = ir.Module(name=self.filename)
        if self.compile_target == 'wasm':
            self.module.triple = "wasm32-unknown-wasi"
        elif self.compile_target == 'windows-x64':
            self.module.triple = "x86_64-pc-windows-msvc"
        elif self.compile_target == 'linux-x64':
            self.module.triple = "x86_64-pc-linux-gcc"
        self.module.di_file = self.module.add_debug_info("DIFile", {
            "filename": "main.sat",
            "directory": "saturn",
        })
        is_optimized = False
        flags = ""
        if self.opt_level > 0:
            is_optimized = True
            flags += f"O{self.opt_level}"
        self.module.di_compile_unit = self.module.add_debug_info("DICompileUnit", {
            "language": ir.DIToken("DW_LANG_C99"),
            "file": self.module.di_file,
            "producer": "llvmlite x.y",
            "runtimeVersion": 2,
            "isOptimized": is_optimized,
            "flags": flags
        }, is_distinct=True)

        self.module.di_types = dict()
        self.module.di_types["int"] = self.module.add_debug_info("DIBasicType", {
            "name": "int",
            "size": 32,
            "encoding": ir.DIToken("DW_ATE_signed")
        })
        self.module.di_types["float32"] = self.module.add_debug_info("DIBasicType", {
            "name": "float32",
            "size": 32,
            "encoding": ir.DIToken("DW_ATE_float")
        })
        self.module.di_types["float64"] = self.module.add_debug_info("DIBasicType", {
            "name": "float64",
            "size": 64,
            "encoding": ir.DIToken("DW_ATE_float")
        })
        self.module.di_types["cstring"] = self.module.add_debug_info("DIBasicType", {
            "name": "cstring",
            "size": 64,
            "encoding": ir.DIToken("DW_ATE_address")
        })
        self.module.di_types["bool"] = self.module.add_debug_info("DIBasicType", {
            "name": "bool",
            "size": 8,
            "encoding": ir.DIToken("DW_ATE_boolean")
        })
        self.module.sfunctys = {}
        self.module.sfuncs = {}
        self.module.sglobals = {}
        self.module.add_named_metadata("llvm.dbg.cu", self.module.di_compile_unit)
        self.module.add_named_metadata("llvm.ident", ["llvmlite/1.0"])
        self.module.add_named_metadata("llvm.module.flags", [
            int32(2), 'Dwarf Version', int32(2)
        ])
        self.module.add_named_metadata("llvm.module.flags", [
            int32(2), 'Debug Info Version', int32(3)
        ])
        self.module.add_named_metadata("llvm.module.flags", [
            int32(1), 'PIC Level', int32(2)
        ])
        self.module.memset = self.module.declare_intrinsic('llvm.memset', [int8ptr, int32])
        self.module.memcpy = self.module.declare_intrinsic('llvm.memcpy', [int8ptr, int8ptr, int32])
        self.module.memmove = self.module.declare_intrinsic('llvm.memmove', [int8ptr, int8ptr, int32])
        self.builder = ir.IRBuilder()
        self.builder.c_decl = False
        self.builder.compile_target = self.compile_target

    def _create_execution_engine(self):
        """
        Create an ExecutionEngine suitable for JIT code generation on
        the host CPU.  The engine is reusable for an arbitrary number of
        modules.
        """
        target = self.binding.Target.from_default_triple()
        target_machine = target.create_target_machine()
        self.target_machine = target_machine
        # And an execution engine with an empty backing module
        backing_mod = binding.parse_assembly("")
        engine = binding.create_mcjit_compiler(backing_mod, target_machine)
        self.engine = engine

    def _declare_coroutine_functions(self):
        token_t = TokenType()

        co_destroy_ty = ir.FunctionType(void, [int8ptr])
        co_destroy = ir.Function(self.module, co_destroy_ty, 'llvm.coro.destroy')
        self.module.co_destroy = co_destroy

        co_size_ty = ir.FunctionType(int64, [])
        co_size = ir.Function(self.module, co_size_ty, 'llvm.coro.size.i64')
        self.module.co_size = co_size

        co_begin_ty = ir.FunctionType(int8ptr, [token_t, int8ptr])
        co_begin = ir.Function(self.module, co_begin_ty, 'llvm.coro.begin')
        self.module.co_begin = co_begin

        co_end_ty = ir.FunctionType(int1, [int8ptr, int1])
        co_end = ir.Function(self.module, co_end_ty, 'llvm.coro.end')
        self.module.co_end = co_end

        co_free_ty = ir.FunctionType(int8ptr, [token_t, int8ptr])
        co_free = ir.Function(self.module, co_free_ty, 'llvm.coro.free')
        self.module.co_free = co_free

        co_id_ty = ir.FunctionType(token_t, [int32, int8ptr, int8ptr, int8ptr])
        co_id = ir.Function(self.module, co_id_ty, 'llvm.coro.id')
        self.module.co_id = co_id

        co_id_retcon_ty = ir.FunctionType(token_t, [int32, int32, int8ptr, int8ptr, int8ptr, int8ptr])
        co_id_retcon = ir.Function(self.module, co_id_retcon_ty, 'llvm.coro.id.retcon')
        self.module.co_id_retcon = co_id_retcon

        co_suspend_ty = ir.FunctionType(int8, [token_t, int1])
        co_suspend = ir.Function(self.module, co_suspend_ty, 'llvm.coro.suspend')
        self.module.co_suspend = co_suspend

        # co_id_async_ty = ir.FunctionType(token_t, [int32, int32, int8ptr, int8ptr])
        # co_id_async = ir.Function(self.module, co_id_async_ty, 'llvm.coro.id.async')
        # self.module.co_id_async = co_id_async

    def _define_ref_load(self):
        # define i8* @saturn.ref.load(i8* %ref) {
        ref_load_ty = ir.FunctionType(int8ptr, [int8ptr])
        ref_load = ir.Function(self.module, ref_load_ty, 'saturn.ref.load')

        # entry:
        block = ref_load.append_basic_block("entry")
        self.builder.position_at_start(block)
        _args = [
            ir.Argument(ref_load, int8ptr),
        ]
        ref_load.args = tuple(_args)

        #   %0 = ptrtoint i8* %ref to 164
        _0 = self.builder.ptrtoint(_args[0], int64)

        #   %1 = and i64 %0, -4
        _1 = self.builder.and_(_0, int64(-4))

        #   %2 = inttoptr i64 %1 to i8*
        _2 = self.builder.inttoptr(_1, int8ptr)

        #   ret i8* %2
        self.builder.ret(_2)
        # }

        self.module.ref_load = ref_load

    def _define_ref_delete(self):
        int8ptrptr = int8ptr.as_pointer()
        # define void @saturn.ref.delete(i8** %arg0) {
        ref_delete_ty = ir.FunctionType(void, [int8ptrptr])
        ref_delete = ir.Function(self.module, ref_delete_ty, 'saturn.ref.delete')

        # entry:
        block = ref_delete.append_basic_block("entry")
        self.builder.position_at_start(block)

        #   %ref = alloca i8**
        _entry_args = [
            ir.Argument(ref_delete, int8ptrptr),
        ]
        ref_delete.args = tuple(_entry_args)
        ref = self.builder.alloca(int8ptrptr)

        #   store i8** %arg0, i8*** %ref
        self.builder.store(_entry_args[0], ref)

        #   %ld = load i8**, i8*** %ref
        ld = self.builder.load(ref)

        #   store i8* null, i8** %ld
        self.builder.store(int8ptr(int8ptr.null), ld)

        #   ret void
        self.builder.ret_void()
        # }

    def _declare_print_function(self):
        # Declare Printf function
        voidptr_ty = ir.IntType(8).as_pointer()
        printf_ty = ir.FunctionType(ir.IntType(32), [voidptr_ty], var_arg=True)
        printf = ir.Function(self.module, printf_ty, name="printf")
        self.printf = printf

        llvm_dbg_ty = ir.FunctionType(void, [ir.MetaDataType(), ir.MetaDataType(), ir.MetaDataType()])
        llvm_dbg_val = ir.Function(self.module, llvm_dbg_ty, "llvm.dbg.value")
        self.module.llvm_dbg_value = llvm_dbg_val

        llvm_dbg_decl_ty = ir.FunctionType(void, [ir.MetaDataType(), ir.MetaDataType(), ir.MetaDataType()])
        llvm_dbg_decl = ir.Function(self.module, llvm_dbg_decl_ty, "llvm.dbg.addr")
        self.module.llvm_dbg_decl = llvm_dbg_decl

        aligned_malloc_name = 'aligned_alloc'
        if self.compile_target == 'windows-x64':
            aligned_malloc_name = '_aligned_malloc'
        aligned_malloc_ty = ir.FunctionType(int8ptr, [int32, int32])
        aligned_malloc = ir.Function(self.module, aligned_malloc_ty, name=aligned_malloc_name)
        self.module.aligned_malloc = aligned_malloc

        free_name = 'free'
        free_ty = ir.FunctionType(void, [int8ptr])
        if self.compile_target == 'windows-x64':
            free_name = '_aligned_free'
        free = ir.Function(self.module, free_ty, name=free_name)
        self.module.free = free
        
        # Declare strlen
        # strlen_ty = ir.FunctionType(ir.IntType(32), [voidptr_ty])
        # strlen = ir.Function(self.module, strlen_ty, name="strlen")
        # self.strlen = strlen

    def _compile_ir(self):
        """
        Compile the LLVM IR string with the given engine.
        The compiled module object is returned.
        """
        # Create a LLVM module object from the IR
        llvm_ir = str(self.module)
        with open('out.ll', 'w') as output_file:
            output_file.write(llvm_ir)
        mod = self.binding.parse_assembly(llvm_ir.replace('target triple = ', 'source_filename = "%s"\ntarget triple = ' % self.filename))
        mod.name = self.module.name
        mod.verify()
        if self.opt_level > 0:
            # Opt module
            pmb = self.binding.PassManagerBuilder()
            pmb.opt_level = self.opt_level
            if pmb.opt_level < 2:
                pmb.disable_unroll_loops = True
            if pmb.opt_level > 1:
                pmb.inlining_threshold = 2
            mpm = self.binding.ModulePassManager()
            pmb.populate(mpm)
            if mpm.run(mod):
                pass  # print('opt ', self.module.name)

            # Opt functions
            fpm = self.binding.FunctionPassManager(mod)
            pmb.populate(fpm)
            fpm.initialize()
            for f in mod.functions:
                if not fpm.run(f):
                    pass  # print('noopt ', f.name)
                else:
                    pass  # print('opt ', f.name)
            fpm.finalize()

        # Now add the module and make sure it is ready for execution
        self.engine.add_module(mod)
        self.engine.finalize_object()
        self.engine.run_static_constructors()
        return mod

    def create_ir(self):
        return self._compile_ir()

    def create_entry(self):
        i32 = int32
        i8_ptr_ptr = ir.IntType(8).as_pointer().as_pointer()
        _entry_ty = ir.FunctionType(i32, [i32, i8_ptr_ptr])
        _entry = ir.Function(self.module, _entry_ty, name="_entry")
        block = _entry.append_basic_block("entry")
        self.builder.position_at_start(block)
        _entry_args = [
            ir.Argument(_entry, i32),
            ir.Argument(_entry, i8_ptr_ptr)
        ]
        _entry.args = tuple(_entry_args)
        argc = self.builder.alloca(i32)
        self.builder.store(_entry_args[0], argc)
        argv = self.builder.alloca(i8_ptr_ptr)
        self.builder.store(_entry_args[1], argv)
        ret_code = self.builder.call(self.module.get_global("main"), 
            [self.builder.load(argc), self.builder.load(argv)])
        self.builder.ret(ret_code)

    def ir_to_c_type(self, irtype: ir.Type):
        from ctypes import Structure, POINTER, CFUNCTYPE, \
            c_int8, c_int16, c_int, c_int32, c_int64, c_float, c_double, c_char_p, c_bool, c_char
        if irtype.is_pointer:
            if isinstance(irtype.pointee, ir.IntType) and not irtype.pointee.is_pointer and \
                    irtype.pointee.get_abi_size(self.engine.target_data) == 1:
                return c_char_p
            return POINTER(self.ir_to_c_type(irtype.pointee))
        if isinstance(irtype, ir.IntType):
            isize = irtype.get_abi_size(self.engine.target_data)
            if isize == 1:
                return c_char_p if irtype.is_pointer else c_char
            if isize == 2:
                return c_int16
            if isize == 4:
                return c_int32
            if isize == 8:
                return c_int64
            return c_int
        elif isinstance(irtype, ir.FloatType):
            return c_float
        elif isinstance(irtype, ir.DoubleType):
            return c_double
        elif isinstance(irtype, ir.LiteralStructType):
            fields = [('f' + str(i), self.ir_to_c_type(element)) for (i, element) in enumerate(irtype.elements)]

            class T(Structure):
                _fields_ = fields

            return T
        elif isinstance(irtype, ir.IdentifiedStructType):
            fields = [('f' + str(i), self.ir_to_c_type(element)) for (i, element) in enumerate(irtype.elements)]

            class T(Structure):
                _fields_ = fields

            return T
        elif isinstance(irtype, ir.FunctionType):
            retty = self.ir_to_c_type(irtype.return_type)
            argtys = [self.ir_to_c_type(argty) for argty in irtype.args]
            print(retty, argtys)
            return CFUNCTYPE(retty, *argtys)
        return None

    def jit_execute(self, fn: ir.Function, *params):
        from ctypes import CFUNCTYPE, c_int
        func_ptr = self.engine.get_function_address(fn.name)
        # print(f"Function at 0x{func_ptr:X}")
        retty = self.ir_to_c_type(fn.ftype.return_type)
        argtys = [self.ir_to_c_type(argty) for argty in fn.ftype.args]
        # print(retty, *argtys, *params)
        cparams = [param for param in params]
        func = CFUNCTYPE(retty, *argtys)(func_ptr)
        # print(func, *cparams)
        return func(*cparams)

    def save_ir(self, filename, ir):
        with open(filename, 'w') as output_file:
            output_file.write(str(ir))

    def save_obj(self, filename, ir):
        obj = self.target_machine.emit_object(ir)
        with open(filename, 'wb') as output_file:
            output_file.write(obj)