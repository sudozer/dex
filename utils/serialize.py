import struct


def returnBitstring(field):

    fieldType = field['type']
    value = field['value']
    bitLength = field['bitLength']
    if fieldType == 'char':
        if bitLength <= 0 or bitLength % 8:
            raise ValueError("char fields must have a positive bitLength divisible by 8")
        encodedValue = value.encode('utf-8')
        byteLength = bitLength // 8
        if len(encodedValue) > byteLength:
            raise ValueError(
                f"char value requires {len(encodedValue)} bytes, but bitLength allows {byteLength}"
            )
        encodedValue = encodedValue.ljust(byteLength, b'\0')
        bitstring = ''.join(format(byte, '08b') for byte in encodedValue)
    elif fieldType in ('float', 'double'):
        #decimal
        format_ = '>f' if fieldType == 'float' else '>d'
        bitstring = ''.join(
            format(byte, '08b')
            for byte in struct.pack(format_, float(value))
        )
    else:
        #int
        convertedValue = int(value)
        if bitLength:
            bitstring = format(
                convertedValue & ((1 << bitLength) - 1),
                f'0{bitLength}b'
            )
        else:
            bitstring = format(convertedValue, 'b')

    if len(bitstring) % 8 == 0:
        rawbytes_ = int(bitstring, 2).to_bytes(len(bitstring)//8, byteorder="big")
    else:
        rawbytes_ = None
    return bitstring,rawbytes_
