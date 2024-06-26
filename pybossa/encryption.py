import base64
from hashlib import sha256
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import six


class AESWithGCM(object):

    def __init__(self, key, iv_length=12, tag_length=16):
        """
        Encrypt/Decrypt text using AES256 and GCM. The input to the encrypt
        method and the output of decrypt method are base64 encoded byte
        strings with the following structure:

        - the first byte of the string is the lenght of the IV in bytes
        - the remaining is the concatenation of IV + ciphertext + tag

        @param key: the secret key, unhashed
        @param iv_length: length of the initialization vector. Only needed for
            encryption.
        @param tag_length (bytes): only needed for decryption. Encryption always
            produces 16 bytes tags.
        """
        self.iv_length = iv_length
        self.tag_length = tag_length
        self.key = self._hash_key(key)

    @staticmethod
    def _hash_key(key):
        _hash = sha256()
        # unicode string to bytes
        if type(key) == str:
            key = key.encode()
        _hash.update(key)
        return _hash.digest()

    def get_cipher(self, iv, tag=None):
        backend = default_backend()
        mode = modes.GCM(iv, tag)
        algo = algorithms.AES(self.key)
        return Cipher(algo, mode, backend)

    def encrypt(self, string):
        """
        @param string: a byte string to encrypt
        Returns a unicode string

        Decode as soon as possible thus we don't need to deal with bytes
        in the program. Reference: Unicode sandwich
        in https://nedbatchelder.com/text/unipain.html
        """
        if type(string) == str:
            string = string.encode()
        iv = os.urandom(self.iv_length)
        encryptor = self.get_cipher(iv).encryptor()
        ct = encryptor.update(string) + encryptor.finalize()
        tag = encryptor.tag
        encrypted = six.int2byte(self.iv_length) + iv + ct + tag
        return base64.b64encode(encrypted).decode()

    def _split_ciphertext(self, string):
        """
        @param string: a byte string
        """
        # a bytes string can be indexed and returns a number in Python3
        # a number is not subscriptable, thus six.byte2int is not needed
        iv_length = string[0]
        iv = string[1:iv_length + 1]
        ciphertext = string[iv_length + 1:-self.tag_length]
        tag = string[-self.tag_length:]
        return iv, ciphertext, tag

    def decrypt(self, string):
        '''
        @param string: expected to be base64 encoded.
        Return a unicode string

        The idea to return unicode string is to keep all text in the program as
        Unicode. Reference: https://nedbatchelder.com/text/unipain.html
        '''
        decoded = base64.b64decode(string)
        iv, ciphertext, tag = self._split_ciphertext(decoded)
        decryptor = self.get_cipher(iv, tag).decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        try:
            decrypted = decrypted.decode()
        except (UnicodeDecodeError, AttributeError) as e:
            pass
        return decrypted
