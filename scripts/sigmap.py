# Shared layout constants + hash function for M64.BIN signing/verification.
#
# Educational description of the official updater's scheme (Route B / SD-OTA):
# SHA-256 over the ENTIRE file with only the 64-byte r||s field zeroed,
# then ECDSA P-256 (secp256r1). The 33-byte compressed public key embedded
# in the image (TEX+6) IS covered by the hash; only r||s are excluded.
#
# This module does not contain, and must not be used to forge, any vendor
# signing key. sign.py signs with a key YOU generate, which the official
# updater will accept only when the device's dev-mode is enabled. The
# USB-DFU path (Route A) does not use this signature check at all.
import hashlib
TEX_OFF   = 0x30
PUB_OFF   = TEX_OFF + 0x06   # 0x36  compressed P-256 point, 33 bytes
PUB_LEN   = 33
R_OFF     = TEX_OFF + 0x28   # 0x58  ECDSA r, 32 bytes
S_OFF     = TEX_OFF + 0x48   # 0x78  ECDSA s, 32 bytes
RS_START  = R_OFF            # 0x58
RS_END    = S_OFF + 0x20     # 0x98  (r||s contiguous, 0x40 bytes)

def signing_digest(image: bytes) -> bytes:
    """SHA-256 over the whole image with r||s (0x58..0x98) zeroed in place."""
    b = bytearray(image)
    b[RS_START:RS_END] = b'\x00' * (RS_END - RS_START)
    return hashlib.sha256(bytes(b)).digest()

def get_pub(image: bytes) -> bytes:
    return image[PUB_OFF:PUB_OFF+PUB_LEN]
def get_rs(image: bytes):
    return image[R_OFF:R_OFF+32], image[S_OFF:S_OFF+32]
