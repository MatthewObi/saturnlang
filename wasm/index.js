//import { WASI } from '@wasmer/wasi/lib'
import { WASI } from './node_modules/@wasmer/wasi';
import browserBindings from './node_modules/@wasmer/wasi/lib/bindings/browser';
import { WasmFs } from './node_modules/@wasmer/wasmfs';

const wasmFilePath = '/main.wasm'  // Path to our WASI module

// - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
// Everything starts here
document.getElementById('btnExecute').addEventListener("click", function(){
  console.log(document.getElementById('input').value);
  iargs = document.getElementById('input').value.split(' ');

  // Instantiate new WASI and WasmFs Instances
  // IMPORTANT:
  // Instantiating WasmFs is only needed when running in a browser.
  // When running on the server, NodeJS's native FS module is assigned by default
  const wasmFs = new WasmFs();
  let wasi = new WASI({
    // Arguments passed to the Wasm Module
    // The first argument is usually the filepath to the executable WASI module
    // we want to run.
    args: [wasmFilePath, ...iargs],
  
    // Environment variables that are accesible to the WASI module
    env: {},
  
    // Bindings that are used by the WASI Instance (fs, path, etc...)
    bindings: {
      ...browserBindings,
      fs: wasmFs.fs
    }
  })
  // - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  // Async function to run our WASI module/instance
  const startWasiTask =
  async pathToWasmFile => {
    // Fetch our Wasm File
    let response  = await fetch(pathToWasmFile)
    let wasmBytes = new Uint8Array(await response.arrayBuffer())

    // IMPORTANT:
    // Some WASI module interfaces use datatypes that cannot yet be transferred
    // between environments (for example, you can't yet send a JavaScript BigInt
    // to a WebAssembly i64).  Therefore, the interface to such modules has to
    // be transformed using `@wasmer/wasm-transformer`, which we will cover in
    // a later example

    // Instantiate the WebAssembly file
    let wasmModule = await WebAssembly.compile(wasmBytes);
    let instance = await WebAssembly.instantiate(wasmModule, {
      ...wasi.getImports(wasmModule)
    });

    wasi.start(instance)                      // Start the WASI instance
    let stdout = await wasmFs.getStdOut()     // Get the contents of stdout
    console.log(stdout);
    document.getElementById('output').value += stdout + '\n';
    //document.write(`Standard Output: ${stdout}`) // Write stdout data to the DOM
  }
  startWasiTask(wasmFilePath);
})