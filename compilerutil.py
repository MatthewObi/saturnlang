from llvmlite import ir, binding as llvm

llvm.initialize_all_targets()


class CompileTarget:
    def __init__(self, name, short_name, triple):
        self.name = name
        self.short_name = short_name
        self.triple = triple
        self.target = llvm.Target.from_triple(self.triple)
        self.machine = self.target.create_target_machine()
        if self.name.startswith('win'):
            self.platform = 'windows'
        elif self.name.startswith('wasm'):
            self.platform = 'wasm'
        elif self.name.startswith('linux'):
            self.platform = 'linux'
        elif self.name == 'native':
            import platform
            plat = platform.platform()
            if plat.startswith('Win'):
                self.platform = 'windows'
            elif plat.startswith('Lin'):
                self.platform = 'linux'
            else:
                self.platform = 'linux'
        else:
            self.platform = 'unknown'

    def get_abi_size(self, ty: ir.Type):
        return ty.get_abi_size(self.machine.target_data, llvm.get_global_context())


targets = {
    # Supported
    'native':           CompileTarget('native', 'sys', llvm.get_default_triple()),
    'wasm':             CompileTarget('wasm-wasi', 'wasm', 'wasm32-unknown-wasi'),
    'wasm-emscripten':  CompileTarget('wasm-emscripten', 'em', 'wasm32-unknown-emscripten'),
    'windows-x64':      CompileTarget('windows-x64', 'win64', 'x86_64-pc-windows-msvc'),
    'windows-x86':      CompileTarget('windows-x86', 'win32', 'i686-pc-windows-msvc'),
    'linux-x64':        CompileTarget('linux-x64', 'gnu64', 'x86_64-pc-linux-gnu'),
    'linux-x86':        CompileTarget('linux-x86', 'gnu32', 'i386-pc-linux-gnu'),
    # Future support
    'mingw32-x64':      CompileTarget('mingw32-x64', 'mingw64', 'x86_64-pc-windows-gnu'),
    'mingw32-x86':      CompileTarget('mingw32-x86', 'mingw32', 'i686-pc-windows-gnu'),
    'mac-x64':          CompileTarget('mac-x64', 'mac64', 'x86_64-apple-darwin10'),
    'mac-arm':          CompileTarget('mac-arm', 'macarm', 'arm-apple-darwin'),
    'arm':              CompileTarget('arm', 'arm', 'arm-none-eabi'),
    'armv7a':           CompileTarget('armv7a', 'armv7a', 'armv7a-none-eabi')
}
