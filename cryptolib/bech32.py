# -*- coding: utf8 -*-
#
# Copyright (c) 2017 Pieter Wuille
# Copyright (c) 2021 BitLogiK
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

XOR_CONSTANT = 1
XOR_CONSTANT_M = 0x2BC830A3  # BIP350
GENERATOR = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]


def bech32_polymod(values):
    """Internal function that computes the Bech32 checksum."""
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= GENERATOR[i]
    return chk


def bech32_hrp_expand(hrp):
    """Expand the HRP into values for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_verify_checksum(hrp, data, xor_const=XOR_CONSTANT):
    """Verify a checksum given HRP and converted data characters."""
    return bech32_polymod(bech32_hrp_expand(hrp) + data) == xor_const


def bech32_create_checksum(hrp, data, xor_const=XOR_CONSTANT):
    """Compute the checksum values given HRP and data."""
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ xor_const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp, data, cs_value=XOR_CONSTANT):
    """Compute a Bech32 string given HRP and data values."""
    combined = data + bech32_create_checksum(hrp, data, cs_value)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])


def bech32_decode(bech, check_target=XOR_CONSTANT):
    """Validate a Bech32 string, and determine HRP and data."""
    if (any(ord(x) < 33 or ord(x) > 126 for x in bech)) or (
        bech.lower() != bech and bech.upper() != bech
    ):
        return (None, None)
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 90:
        return (None, None)
    if not all(x in CHARSET for x in bech[pos + 1 :]):
        return (None, None)
    hrp = bech[:pos]
    data = [CHARSET.find(x) for x in bech[pos + 1 :]]
    if not bech32_verify_checksum(hrp, data, check_target):
        return (None, None)
    return (hrp, data[:-6])


def convertbits(data, frombits, tobits, pad=True):
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def decode(hrp, addr):
    """Decode a segwit address :(witver, data)"""
    explen = len(hrp) + 1
    if len(addr) < explen + 1:
        return (None, None)
    checksum_val = XOR_CONSTANT_M
    # Witness v0 uses the old XOR checksum
    if addr[explen].lower() == CHARSET[0]:
        checksum_val = XOR_CONSTANT
    hrpgot, data = bech32_decode(addr, checksum_val)
    if hrpgot != hrp:
        return (None, None)
    if data is None:
        return (None, None)
    decoded = convertbits(data[1:], 5, 8, False)
    if decoded is None or len(decoded) < 2 or len(decoded) > 40:
        return (None, None)
    if data[0] > 16:
        return (None, None)
    if data[0] == 0 and len(decoded) != 20 and len(decoded) != 32:
        return (None, None)
    if data[0] == 1 and len(decoded) != 32:
        return (None, None)
    return (data[0], decoded)


def test_bech32(addr_str):
    """Test the validity of a bech32 address"""
    # Before testing here check header is correct
    header_length = 2
    # "ltc" or "tltc" -> LTC address
    if addr_str.startswith("ltc"):
        header_length = 3
    if addr_str.startswith("tltc"):
        header_length = 4
    if len(addr_str) < header_length:
        return False
    return decode(addr_str[:header_length].lower(), addr_str) != (None, None)


def bech32_address(hrp, datahash):
    """Encode a segwit address without witver, for altcoins"""
    return bech32_encode(hrp, convertbits(datahash, 8, 5))


def bech32_address_btc(datahash, hrp="bc", witver=0):
    """Encode a segwit address"""
    checksum = XOR_CONSTANT_M
    if witver == 0:
        checksum = XOR_CONSTANT
    return bech32_encode(hrp, [witver] + convertbits(datahash, 8, 5), checksum)
