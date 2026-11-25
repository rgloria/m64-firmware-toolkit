#!/usr/bin/env python3
"""Offline re-verification of an M64.BIN signature, replicating the firmware's
   hash+ECDSA-P256 verify. Usage: verify_sig.py <image.BIN>"""
import sys, hashlib
from ecdsa import VerifyingKey, NIST256p
from ecdsa.util import sigdecode_string
from ecdsa.keys import BadSignatureError
import sigmap

def verify(path):
    img = open(path,'rb').read()
    digest = sigmap.signing_digest(img)
    pub = sigmap.get_pub(img)
    r,s = sigmap.get_rs(img)
    print(f"image           : {path} ({len(img)} bytes)")
    print(f"embedded pubkey : {pub.hex()}")
    print(f"signing digest  : {digest.hex()}")
    print(f"r               : {r.hex()}")
    print(f"s               : {s.hex()}")
    vk = VerifyingKey.from_string(pub, curve=NIST256p)
    try:
        vk.verify_digest(r+s, digest, sigdecode=sigdecode_string)
        print("RESULT          : VERIFY = OK  (signature valid for embedded key)")
        return True
    except BadSignatureError:
        print("RESULT          : VERIFY = FAIL (bad signature)")
        return False

if __name__=='__main__':
    ok = verify(sys.argv[1] if len(sys.argv)>1 else 'M64.BIN')
    sys.exit(0 if ok else 1)
