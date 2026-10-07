import struct


def returnBitstring(field):
    #this is ai code cuz i couldn't be assed
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

    return bitstring
