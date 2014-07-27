# coding=utf-8
import hashlib
from struct import *
from pyelliptic import arithmetic


#There is another copy of this function in Bitmessagemain.py
def convert_int_to_string(n):
    a = __builtins__.hex(n)
    if a[-1:] == 'L':
        a = a[:-1]
    if (len(a) % 2) == 0:
        return a[2:].decode('hex')
    else:
        return ('0'+a[2:]).decode('hex')

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def encode_base58(num, alphabet=ALPHABET):
    """Encode a number in Base X

    `num`: The number to encode
    `alphabet`: The alphabet to use for encoding
    """
    if num == 0:
        return alphabet[0]
    arr = []
    base = len(alphabet)
    while num:
        rem = num % base
        #print 'num is:', num
        num //= base
        arr.append(alphabet[rem])
    arr.reverse()
    return ''.join(arr)


def decode_base58(string, alphabet=ALPHABET):
    """Decode a Base X encoded string into the number

    Arguments:
    - `string`: The encoded string
    - `alphabet`: The alphabet to use for encoding
    """
    base = len(alphabet)
    str_len = len(string)
    num = 0

    try:
        power = str_len - 1
        for char in string:
            num += alphabet.index(char) * (base ** power)
            power -= 1
    except:
        # character not found (like a space character or a 0)
        return 0
    return num


def encode_varint(integer):
    if integer < 0:
        print('varint cannot be < 0')
        raise SystemExit
    if integer < 253:
        return pack('>B', integer)
    if 253 <= integer < 65536:
        return pack('>B', 253) + pack('>H', integer)
    if 65536 <= integer < 4294967296:
        return pack('>B', 254) + pack('>I', integer)
    if 4294967296 <= integer < 18446744073709551616:
        return pack('>B', 255) + pack('>Q', integer)
    if integer >= 18446744073709551616:
        print('varint cannot be >= 18446744073709551616')
        raise SystemExit


def decode_varint(data):
    if len(data) == 0:
        return 0, 0
    fist_byte, = unpack('>B', data[0:1])
    if fist_byte < 253:
        return fist_byte, 1  # the 1 is the length of the varint
    if fist_byte == 253:
        a, = unpack('>H', data[1:3])
        return a, 3
    if fist_byte == 254:
        a, = unpack('>I', data[1:5])
        return a, 5
    if fist_byte == 255:
        a, = unpack('>Q', data[1:9])
        return a, 9


def calculate_inventory_hash(data):
    sha = hashlib.new('sha512')
    sha2 = hashlib.new('sha512')
    sha.update(data)
    sha2.update(sha.digest())
    return sha2.digest()[0:32]


def encode_address(version, stream, ripe):
    if 2 <= version < 4:
        if len(ripe) != 20:
            raise Exception("Programming error in encodeAddress: The length of a given ripe hash was not 20.")
        if ripe[:2] == '\x00\x00':
            ripe = ripe[2:]
        elif ripe[:1] == '\x00':
            ripe = ripe[1:]
    elif version == 4:
        if len(ripe) != 20:
            raise Exception("Programming error in encodeAddress: The length of a given ripe hash was not 20.")
        ripe = ripe.lstrip('\x00')

    a = encode_varint(version) + encode_varint(stream) + ripe
    sha = hashlib.new('sha512')
    sha.update(a)
    current_hash = sha.digest()
    #print 'sha after first hashing: ', sha.hexdigest()
    sha = hashlib.new('sha512')
    sha.update(current_hash)
    #print 'sha after second hashing: ', sha.hexdigest()

    checksum = sha.digest()[0:4]
    #print 'len(a) = ', len(a)
    #print 'checksum = ', checksum.encode('hex')
    #print 'len(checksum) = ', len(checksum)

    as_int = int(a.encode('hex') + checksum.encode('hex'), 16)
    #as_int = int(checksum.encode('hex') + a.encode('hex'),16)
    # print as_int
    return 'BM-' + encode_base58(as_int)


def decode_address(address):
    # returns (status, address version number, stream number, data (almost certainly a ripe hash))

    address = str(address).strip()

    if address[:3] == 'BM-':
        integer = decode_base58(address[3:])
    else:
        integer = decode_base58(address)
    if integer == 0:
        status = 'invalidcharacters'
        return status, 0, 0, ""
    # after converting to hex, the string will be prepended with a 0x and appended with a L
    hex_data = hex(integer)[2:-1]

    if len(hex_data) % 2 != 0:
        hex_data = '0' + hex_data

    #print 'hex_data', hex_data

    data = hex_data.decode('hex')
    checksum = data[-4:]

    sha = hashlib.new('sha512')
    sha.update(data[:-4])
    current_hash = sha.digest()
    #print 'sha after first hashing: ', sha.hexdigest()
    sha = hashlib.new('sha512')
    sha.update(current_hash)
    #print 'sha after second hashing: ', sha.hexdigest()

    if checksum != sha.digest()[0:4]:
        status = 'checksumfailed'
        return status, 0, 0, ""
    #else:
    #    print 'checksum PASSED'

    address_version_number, bytes_used_by_version_number = decode_varint(data[:9])
    #print 'address_version_number', address_version_number
    #print 'bytes_used_by_version_number', bytes_used_by_version_number

    if address_version_number > 4:
        print('cannot decode address version numbers this high')
        status = 'versiontoohigh'
        return status, 0, 0, ""
    elif address_version_number == 0:
        print('cannot decode address version numbers of zero.')
        status = 'versiontoohigh'
        return status, 0, 0, ""

    stream_number, bytes_used_by_stream_number = decode_varint(data[bytes_used_by_version_number:])
    #print stream_number
    status = 'success'
    bytes_used_by_stream_and_version_numbers = bytes_used_by_stream_number + bytes_used_by_version_number

    if address_version_number == 1:
        return status, address_version_number, stream_number, data[-24:-4]
    elif address_version_number == 2 or address_version_number == 3:
        if len(data[bytes_used_by_stream_and_version_numbers:-4]) == 19:
            return status, address_version_number, \
                stream_number, '\x00' + data[bytes_used_by_stream_and_version_numbers:-4]
        elif len(data[bytes_used_by_stream_and_version_numbers:-4]) == 20:
            return status, address_version_number, stream_number, \
                data[bytes_used_by_stream_and_version_numbers:-4]
        elif len(data[bytes_used_by_stream_and_version_numbers:-4]) == 18:
            return status, address_version_number, \
                stream_number, '\x00\x00' + data[bytes_used_by_stream_and_version_numbers:-4]
        elif len(data[bytes_used_by_stream_and_version_numbers:-4]) < 18:
            return 'ripetooshort', 0, 0, ""
        elif len(data[bytes_used_by_stream_and_version_numbers:-4]) > 20:
            return 'ripetoolong', 0, 0, ""
        else:
            return 'otherproblem', 0, 0, ""
    elif address_version_number == 4:
        if len(data[bytes_used_by_stream_and_version_numbers:-4]) > 20:
            return 'ripetoolong', 0, 0, ""
        elif len(data[bytes_used_by_stream_and_version_numbers:-4]) < 4:
            return 'ripetooshort', 0, 0, ""
        else:
            x00string = '\x00' * (20 - len(data[bytes_used_by_stream_and_version_numbers:-4]))
            return status, address_version_number, stream_number, \
                x00string + data[bytes_used_by_stream_and_version_numbers:-4]


def add_bm_if_not_present(address):
    address = str(address).strip()
    if address[:3] != 'BM-':
        return 'BM-' + address
    else:
        return address

if __name__ == "__main__":
    print('Let us make an address from scratch. Suppose we generate two random 32 byte values and call the first one the signing key and the second one the encryption key:')
    privateSigningKey = '93d0b61371a54b53df143b954035d612f8efa8a3ed1cf842c2186bfd8f876665'
    privateEncryptionKey = '4b0b73a54e19b059dc274ab69df095fe699f43b17397bca26fdf40f4d7400a3a'
    print('privateSigningKey =', privateSigningKey)
    print('privateEncryptionKey =', privateEncryptionKey)
    print('Now let us convert them to public keys by doing an elliptic curve point multiplication.')
    publicSigningKey = arithmetic.privtopub(privateSigningKey)
    publicEncryptionKey = arithmetic.privtopub(privateEncryptionKey)
    print('publicSigningKey =', publicSigningKey)
    print('publicEncryptionKey =', publicEncryptionKey)

    print('Notice that they both begin with the \\x04 which specifies the encoding type. This prefix is not send over the wire. You must strip if off before you send your public key across the wire, and you must add it back when you receive a public key.')

    publicSigningKeyBinary = arithmetic.changebase(publicSigningKey, 16, 256, minlen=64)
    publicEncryptionKeyBinary = arithmetic.changebase(publicEncryptionKey, 16, 256, minlen=64)

    ripe = hashlib.new('ripemd160')
    sha = hashlib.new('sha512')
    sha.update(publicSigningKeyBinary+publicEncryptionKeyBinary)

    ripe.update(sha.digest())
    addressVersionNumber = 2
    streamNumber = 1
    print('Ripe digest that we will encode in the address:', ripe.digest().encode('hex'))
    returnedAddress = encode_address(addressVersionNumber, streamNumber, ripe.digest())
    print('Encoded address:', returnedAddress)
    status, addressVersionNumber, streamNumber, data = decode_address(returnedAddress)
    print('\nAfter decoding address:')
    print('Status:', status)
    print('addressVersionNumber', addressVersionNumber)
    print('streamNumber', streamNumber)
    print('length of data(the ripe hash):', len(data))
    print('ripe data:', data.encode('hex'))

