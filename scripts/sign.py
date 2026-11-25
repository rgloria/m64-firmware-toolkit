#!/usr/bin/env python3
"""Self-sign an M64 image with our own P-256 key (dev-mode path).
   Usage: sign.py <in.BIN> <out.BIN> <privkey.pem>
   Steps: embed our compressed pubkey at TEX+6, zero r||s, SHA-256 the whole
   file, ECDSA-P256 sign, write r @0x58 and s @0x78."""
import sys, hashlib
from ecdsa import SigningKey, NIST256p
from ecdsa.util import sigencode_string
import sigmap

def compress_point(vk):
    # 0x02/0x03 || X ; vk.to_string() is X(32)||Y(32)
    xy = vk.to_string()
    x, y = xy[:32], xy[32:]
    prefix = b'\x03' if (y[-1] & 1) else b'\x02'
    return prefix + x

def sign(inp, outp, pem):
    sk = SigningKey.from_pem(open(pem).read())
    assert sk.curve == NIST256p, "key must be NIST P-256 / secp256r1"
    pub = compress_point(sk.get_verifying_key())
    assert len(pub)==33
    b = bytearray(open(inp,'rb').read())
    # 1) embed our compressed pubkey
    b[sigmap.PUB_OFF:sigmap.PUB_OFF+33] = pub
    # 2) zero r||s then hash whole file
    digest = sigmap.signing_digest(bytes(b))
    # 3) sign the digest (fixed 32||32 r||s)
    sig = sk.sign_digest_deterministic(digest, hashfunc=hashlib.sha256,
                                       sigencode=sigencode_string)
    r, s = sig[:32], sig[32:]
    # 4) write r,s
    b[sigmap.R_OFF:sigmap.R_OFF+32] = r
    b[sigmap.S_OFF:sigmap.S_OFF+32] = s
    open(outp,'wb').write(bytes(b))
    print(f"signed {inp} -> {outp}")
    print(f"  embedded pubkey: {pub.hex()}")
    print(f"  digest         : {digest.hex()}")
    print(f"  r              : {r.hex()}")
    print(f"  s              : {s.hex()}")

if __name__=='__main__':
    sign(sys.argv[1], sys.argv[2], sys.argv[3])
