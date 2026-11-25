import struct
from capstone import *
data=open('M64.BIN','rb').read()
SEC_FILE_START=0x118
SEC_FILE_END=0xBE0A8
BASE=0x08000000
def f2a(off): return BASE+(off-SEC_FILE_START)
def a2f(addr): return addr-BASE+SEC_FILE_START
def in_sec_file(off): return SEC_FILE_START<=off<SEC_FILE_END
def in_sec_va(addr): return BASE<=addr<f2a(SEC_FILE_END)

md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
md.detail=True

def find_bytes(needle, start=0):
    out=[]; i=data.find(needle,start)
    while i!=-1:
        out.append(i); i=data.find(needle,i+1)
    return out

def cstr(off, maxlen=120):
    e=data.find(b'\x00',off)
    return data[off:e].decode('latin1',errors='replace')

# find literal-pool words (4-byte LE) in section that equal a given VA
def xrefs_to_va(va):
    out=[]
    tgt=struct.pack('<I',va)
    i=data.find(tgt,SEC_FILE_START)
    while i!=-1 and i<SEC_FILE_END:
        out.append(i); i=data.find(tgt,i+1)
    return out

def disasm(file_off, nbytes, label=""):
    va=f2a(file_off)
    print(f"--- disasm @ file 0x{file_off:x} (VA 0x{va:08x}) {label} ---")
    for ins in md.disasm(data[file_off:file_off+nbytes], va):
        print(f"0x{ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}")

if __name__=='__main__':
    import sys
    cmd=sys.argv[1]
    if cmd=='str':
        needle=sys.argv[2].encode()
        for o in find_bytes(needle):
            print(f"file 0x{o:x}  VA 0x{f2a(o):08x}  {data[o-1]==0 and '[NUL-pre]' or ''}  {cstr(o)!r}")
    elif cmd=='xref':
        va=int(sys.argv[2],16)
        for o in xrefs_to_va(va):
            print(f"literal word @ file 0x{o:x} (VA 0x{f2a(o):08x}) -> points to 0x{va:08x}")
    elif cmd=='d':
        disasm(int(sys.argv[2],16), int(sys.argv[3]))
