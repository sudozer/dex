import struct


def returnBitstring(field):

    fieldType = field['type']
    value = field['value']
    bitLength = field['bitLength']
    if fieldType == 'char':
        bitstring = format(ord(value), '08b')
    elif fieldType in ('float', 'double'):
        format_ = '>f' if fieldType == 'float' else '>d'
        bitstring = ''.join(
            format(byte, '08b')
            for byte in struct.pack(format_, float(value))
        )
    else:
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
