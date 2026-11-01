ObjC.import('Foundation');
ObjC.import('Metal');
ObjC.bindFunction('sel_registerName', ['void *', ['char *']]);
ObjC.bindFunction('objc_msgSend', ['void', ['id', 'void *', 'id', 'unsigned long', 'unsigned long']]);
function run() {
  var device = $.MTLCreateSystemDefaultDevice();
  if (!device) throw new Error('No Metal device');
  var name = ObjC.unwrap(device.name);
  console.log('DEVICE=' + name);
  console.log('MAX_THREADS_STRUCT=' + JSON.stringify(device.maxThreadsPerThreadgroup));
  var err = Ref();
  var source = '#include <metal_stdlib>\nusing namespace metal;\nkernel void verify_gpu(device uint *out [[buffer(0)]], uint tid [[thread_position_in_grid]]) { out[tid] = tid * tid + 17u; }';
  var options = $.MTLCompileOptions.alloc.init;
  var library = device.newLibraryWithSourceOptionsError($(source), options, err);
  if (!library || library.isNil()) throw new Error('Shader compile failed: ' + ObjC.unwrap(err[0].localizedDescription));
  console.log('SHADER_COMPILED');
  var fn = library.newFunctionWithName('verify_gpu');
  var pipeline = device.newComputePipelineStateWithFunctionError(fn, err);
  if (!pipeline || pipeline.isNil()) throw new Error('Pipeline failed: ' + ObjC.unwrap(err[0].localizedDescription));
  var count = 4096;
  var buffer = device.newBufferWithLengthOptions(count * 4, 0);
  var queue = device.newCommandQueue;
  var command = queue.commandBuffer;
  var encoder = command.computeCommandEncoder;
  encoder.setComputePipelineState(pipeline);
  // JXA otherwise confuses setBuffer:offset:atIndex: with setBufferOffset:atIndex:.
  $.objc_msgSend(encoder, $.sel_registerName('setBuffer:offset:atIndex:'), buffer, 0, 0);
  // This runtime exposes anonymous MTLSize fields; pass packed 3xuint64 via NSInvocation.
  var dispatchSelector=$.NSSelectorFromString('dispatchThreadgroups:threadsPerThreadgroup:');
  var invocation=$.NSInvocation.invocationWithMethodSignature(encoder.methodSignatureForSelector(dispatchSelector));
  invocation.target=encoder;
  invocation.selector=dispatchSelector;
  var groupBytes=$.NSData.alloc.initWithBase64EncodedStringOptions('EAAAAAAAAAABAAAAAAAAAAEAAAAAAAAA',0);
  var threadBytes=$.NSData.alloc.initWithBase64EncodedStringOptions('AAEAAAAAAAABAAAAAAAAAAEAAAAAAAAA',0);
  invocation.setArgumentAtIndex(groupBytes.bytes,2);
  invocation.setArgumentAtIndex(threadBytes.bytes,3);
  invocation.invoke;
  encoder.endEncoding;
  var started=Date.now();
  command.commit;
  command.waitUntilCompleted;
  var status=Number(command.status);
  console.log('COMMAND_STATUS=' + status);
  if (status!==4) throw new Error('GPU command did not complete successfully');
  var data=$.NSData.dataWithBytesLength(buffer.contents,count*4);
  var b64=ObjC.unwrap(data.base64EncodedStringWithOptions(0));
  console.log('OUTPUT_BYTES=' + data.length + ' BASE64_PREFIX=' + b64.slice(0,64));
  var alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var bytes=[],acc=0,bits=0;
  for(var i=0;i<b64.length;i++) {
    var v=alphabet.indexOf(b64[i]);
    if(v<0) continue;
    acc=(acc<<6)|v; bits+=6;
    if(bits>=8) {bits-=8;bytes.push((acc>>bits)&255);}
  }
  if (bytes.length !== count * 4) throw new Error('Incomplete GPU buffer readback');
  var mismatches=0,firstValues=[];
  for(var n=0;n<count;n++) {
    var offset=n*4;
    var actual=(bytes[offset]|(bytes[offset+1]<<8)|(bytes[offset+2]<<16)|(bytes[offset+3]<<24))>>>0;
    if(n<8) firstValues.push(actual);
    if(actual!==n*n+17) mismatches++;
  }
  console.log('FIRST_VALUES=' + JSON.stringify(firstValues));
  if(mismatches) throw new Error('GPU output mismatch count=' + mismatches);
  return JSON.stringify({result:'METAL_COMPUTE_PASS',device:name,values_checked:count,mismatches:mismatches,command_status:status,submit_readback_ms:Date.now()-started});
}
